#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳开心乐园餐玩具 · 门店库存查询主逻辑

流程：
  1. 在本地图鉴（assets/toys.json）中模糊匹配用户想找的玩具；
  2. 通过麦当劳官方 MCP 定位目标门店（城市/关键字）；
  3. 查询该门店在售餐品，确认「开心乐园餐」是否在售；
  4. 查询开心乐园餐详情，提取套餐内「可选玩具」；
  5. 综合图鉴状态 + 门店套餐选项，给出库存判断与置信度。

注意：麦当劳公开 MCP 没有「玩具逐件实时库存」接口，结论基于
「开心乐园餐在售 + 套餐可选玩具」的代理判断，已在报告中标注。

用法：
  python toy_lookup.py --toy "奶龙" --city "上海"
  python toy_lookup.py --toy "三丽鸥" --city "北京" --store "三里屯"
  python toy_lookup.py --toy-id nailong-2024 --city "上海" --json
  python toy_lookup.py --list            # 列出图鉴全部玩具
  python toy_lookup.py --toy "奶龙" --demo  # 强制演示模式（无需 Token）
"""

import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
TOYS_PATH = os.path.join(SKILL_DIR, "assets", "toys.json")

sys.path.insert(0, HERE)
from mcp_client import McdMcpClient, McdMcpError  # noqa: E402


# ---------------------------------------------------------------------- #
# 图鉴
# ---------------------------------------------------------------------- #
def load_catalog(path: str = TOYS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_toys(catalog: dict, query: str):
    """在图鉴中模糊匹配玩具，返回 (best_match, all_matches)。"""
    q = (query or "").strip().lower()
    matches = []
    for toy in catalog.get("toys", []):
        haystack = " ".join([
            toy.get("name", ""),
            toy.get("ip", ""),
            toy.get("series", ""),
            " ".join(toy.get("keywords", [])),
        ]).lower()
        if q in haystack:
            matches.append(toy)
    # 精确名优先
    matches.sort(key=lambda t: 0 if q == t.get("name", "").lower() else 1)
    return (matches[0] if matches else None, matches)


# ---------------------------------------------------------------------- #
# MCP 解析
# ---------------------------------------------------------------------- #
def _safe_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def resolve_store(client: McdMcpClient, city: str, keyword: str = None) -> dict:
    """定位门店，返回第一个匹配门店的字典。"""
    raw = client.query_nearby_stores(keyword=keyword, city=city)
    data = _safe_json(raw)
    stores = data if isinstance(data, list) else []
    if not stores:
        return None
    if keyword:
        for s in stores:
            if keyword in (s.get("name", "") + s.get("address", "")):
                return s
    return stores[0]


def get_store_toy_options(client: McdMcpClient, store_id: str):
    """返回 (开心乐园餐在售?, 套餐名, 可选玩具列表)。"""
    raw = client.query_meals(store_id)
    meals = _safe_json(raw)
    if not isinstance(meals, list):
        meals = []
    happy = None
    for m in meals:
        name = m.get("name", "")
        if "开心乐园" in name or m.get("category") == "儿童" or "玩具" in name:
            happy = m
            break
    if not happy:
        return (False, None, [])
    detail_raw = client.query_meal_detail(happy.get("mealCode"))
    detail = _safe_json(detail_raw) or {}
    toy_options = []
    for grp in detail.get("options", []):
        if "玩具" in grp.get("group", ""):
            toy_options.extend(grp.get("items", []))
    return (True, happy.get("name"), toy_options)


# ---------------------------------------------------------------------- #
# 库存判断
# ---------------------------------------------------------------------- #
def decide(toy: dict, happy_available: bool, toy_options: list):
    """根据图鉴状态与门店套餐选项，给出判断与置信度。"""
    toy_name = toy.get("name", "")
    status = toy.get("status", "往期收藏")

    if not happy_available:
        return ("unavailable_store",
                "该门店当前未查询到开心乐园餐在售，无法发放玩具",
                "低（门店维度）")
    if toy_name in toy_options:
        return ("available",
                f"✅ 该门店开心乐园餐在售，且套餐可选玩具中包含「{toy_name}」",
                "中高（菜单+套餐选项代理）")
    if status == "在售轮换中":
        return ("likely",
                f"🟡 开心乐园餐在售，但本店当前套餐玩具选项未列出「{toy_name}」，"
                "可能处于轮换间隙或未覆盖该款",
                "中（菜单代理，需到店确认）")
    return ("collector_only",
            f"⚪ 「{toy_name}」为{status}款，当前不在门店轮换发放中，属收藏向",
            "高（图鉴状态）")


VERDICT_TEXT = {
    "available": "有货，可冲 🎉",
    "likely": "可能有，建议到店/App 再确认",
    "collector_only": "当前门店不发放，属收藏款",
    "unavailable_store": "该门店暂未提供开心乐园餐",
}


# ---------------------------------------------------------------------- #
# 报告
# ---------------------------------------------------------------------- #
def build_report(toy, store, happy_available, happy_name, toy_options, decision):
    code, detail, confidence = decision
    lines = []
    lines.append(f"# 🍔 麦当劳玩具猎人 · 库存报告")
    lines.append("")
    lines.append(f"## 🧸 玩具档案（本地图鉴）")
    lines.append(f"- 名称：{toy.get('name')}")
    lines.append(f"- 系列：{toy.get('series')} / IP：{toy.get('ip')}")
    lines.append(f"- 年代：{toy.get('era')} ｜ 范围：{toy.get('region')} ｜ 稀有度：{toy.get('rarity')}")
    lines.append(f"- 状态：{toy.get('status')}")
    lines.append(f"- 简介：{toy.get('description')}")
    lines.append("")
    lines.append(f"## 📍 门店定位（麦当劳 MCP）")
    if store:
        lines.append(f"- 门店：{store.get('name')}")
        lines.append(f"- 地址：{store.get('address')} ｜ 城市：{store.get('city')}")
        lines.append(f"- 门店ID：{store.get('storeId')}")
    else:
        lines.append("- 未定位到门店（请检查城市/关键字，或确认 MCP Token）")
    lines.append("")
    lines.append(f"## 📦 库存判断")
    lines.append(f"- 开心乐园餐在售：{'是' if happy_available else '否'}")
    if happy_name:
        lines.append(f"- 套餐名：{happy_name}")
    if toy_options:
        lines.append(f"- 本店套餐可选玩具：{', '.join(toy_options)}")
    lines.append(f"- **结论：{VERDICT_TEXT.get(code, code)}**")
    lines.append(f"- 说明：{detail}")
    lines.append(f"- 置信度：{confidence}")
    lines.append("")
    lines.append("> ⚠️ 说明：麦当劳公开 MCP 未提供「玩具逐件实时库存」接口，")
    lines.append("> 本结论基于「开心乐园餐在售 + 套餐可选玩具选项」的代理判断。")
    lines.append("> 最终请以门店实际发放 / 麦当劳 App 为准。")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="麦当劳开心乐园餐玩具门店库存查询")
    ap.add_argument("--toy", help="想找的玩具名称 / 关键词")
    ap.add_argument("--toy-id", help="图鉴中的玩具 id")
    ap.add_argument("--city", help="目标城市，如 上海")
    ap.add_argument("--store", help="门店关键字，如 南京东路")
    ap.add_argument("--list", action="store_true", help="列出图鉴全部玩具")
    ap.add_argument("--demo", action="store_true", help="强制演示模式（无需 Token）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    catalog = load_catalog()

    if args.list:
        rows = [{"id": t["id"], "name": t["name"], "series": t["series"], "status": t["status"]}
                for t in catalog.get("toys", [])]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    # 选定玩具
    toy = None
    if args.toy_id:
        toy = next((t for t in catalog.get("toys", []) if t["id"] == args.toy_id), None)
    elif args.toy:
        toy, _ = find_toys(catalog, args.toy)
    if not toy:
        print("❌ 未在图鉴中找到匹配的玩具，试试 --list 查看全部，或用更通用的关键词。")
        sys.exit(1)

    client = McdMcpClient(demo=args.demo)
    try:
        client.initialize()
        store = resolve_store(client, args.city or "上海", args.store)
        if store:
            happy_available, happy_name, toy_options = get_store_toy_options(client, store.get("storeId"))
        else:
            happy_available, happy_name, toy_options = (False, None, [])
    except McdMcpError as e:
        print(f"⚠️ MCP 调用出错：{e}")
        print("（可加 --demo 使用演示数据体验完整流程）")
        sys.exit(1)

    decision = decide(toy, happy_available, toy_options)
    report = build_report(toy, store, happy_available, happy_name, toy_options, decision)

    if args.json:
        out = {
            "toy": toy,
            "store": store,
            "happy_meal_available": happy_available,
            "toy_options": toy_options,
            "verdict_code": decision[0],
            "verdict_text": VERDICT_TEXT.get(decision[0], decision[0]),
            "detail": decision[1],
            "confidence": decision[2],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(report)


if __name__ == "__main__":
    main()
