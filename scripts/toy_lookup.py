#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳开心乐园餐玩具 · 门店库存查询主逻辑

流程：
  1. 在本地图鉴（assets/toys.json）中模糊匹配用户想找的玩具，给出其
     系列 / 年代 / 投放范围 / 稀有度 / 是否在当前轮换等科普信息；
  2. 通过麦当劳官方 MCP 定位目标门店（城市/关键字）；
  3. 查询该门店在售餐品，确认「开心乐园餐」是否在售；
  4. 查询开心乐园餐详情，确认玩具轮次（官方为「随机玩具1个」，随机发放）；
  5. 综合图鉴状态 + 门店是否在售开心乐园餐，给出判断与置信度。

注意：麦当劳公开 MCP 不提供「玩具逐件实时库存 / 具体款式」接口，玩具
为随机发放。结论基于「门店是否在售开心乐园餐 + 本地图鉴状态」的代理判断，
已在报告中诚实标注。

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
def resolve_store(client: McdMcpClient, city: str, keyword: str = None) -> dict:
    """定位门店，返回第一个匹配门店的字典（含 storeCode/storeName/address）。"""
    stores = client.query_nearby_stores(city=city, keyword=keyword)
    if not stores:
        return None
    if keyword:
        for s in stores:
            if keyword in (s.get("storeName", "") + s.get("address", "")):
                return s
    return stores[0]


def get_store_happy_meal(client: McdMcpClient, store_code: str):
    """返回 (开心乐园餐在售?, 餐品code, 餐品名)。

    在 query-meals 的 meals 字典（键为餐品码）中按名称匹配开心乐园餐。
    """
    meals = client.query_meals(store_code)
    meal_map = meals.get("meals", {}) if isinstance(meals, dict) else {}
    for code, m in meal_map.items():
        nm = m.get("name", "")
        if "开心乐园" in nm or "玩具" in nm:
            return (True, code, m.get("name"))
    return (False, None, None)


def get_toy_round_names(detail: dict) -> list:
    """从套餐详情的 rounds 中提取玩具轮次的选项名称。

    真实接口玩具轮次通常为「随机玩具1个」，即随机发放、不暴露具体款式。
    """
    if not isinstance(detail, dict):
        return []
    names = []
    for r in detail.get("rounds", []):
        if "玩具" in r.get("name", ""):
            for ch in r.get("choices", []):
                names.append(ch.get("name", ""))
    return names


# ---------------------------------------------------------------------- #
# 库存判断
# ---------------------------------------------------------------------- #
def decide(toy: dict, happy_available: bool, toy_round_names: list):
    """根据图鉴状态与门店当前玩具轮次，给出判断与置信度。

    真实接口在部分门店会于套餐详情的玩具轮次暴露「当前在发系列名」
    （如「海绵宝宝×航海王系列玩具」），另一些门店则显示「随机玩具1个」。
    本函数据此升级判断：能命中当前系列则给高置信，否则回退到图鉴状态判断。
    """
    toy_name = toy.get("name", "")
    status = toy.get("status", "往期收藏")
    joined = " ".join(toy_round_names)
    # 取出「具体系列名」：排除泛化的「随机玩具」
    specific = [n for n in toy_round_names if n and "随机" not in n]

    if not happy_available:
        return ("unavailable_store",
                "该门店当前未查询到开心乐园餐在售，无法领取玩具",
                "低（门店维度）")

    if specific:
        # 门店当前发放的是具体系列，尝试与图鉴玩具匹配
        keys = [toy_name, toy.get("series", "")] + toy.get("keywords", [])
        matched = any(k and (k.lower() in joined.lower() or
                             any(k.lower() in n.lower() for n in toy_round_names))
                      for k in keys)
        if matched:
            return ("available",
                    f"✅ 该门店当前正发放「{joined}」，命中你找的「{toy_name}」",
                    "高（门店当前玩具系列 = 图鉴玩具）")
        return ("series_mismatch",
                f"🟡 该门店当前发放「{joined}」，但非你找的「{toy_name}」系列",
                "中（门店当前轮次不含此款）")

    # 门店为「随机玩具1个」：不暴露具体系列，回退图鉴状态判断
    if status == "在售轮换中":
        return ("likely",
                f"🟡 该门店在售开心乐园餐（随机玩具）。「{toy_name}」属当前轮换系列，"
                "到店有较大概率领到，但官方 MCP 不保证具体款式，需到店或看 App 确认",
                "中（门店在售 + 图鉴状态，款式需到店确认）")
    return ("collector_only",
            f"⚪ 「{toy_name}」为{status}款，当前不在门店轮换发放中，属收藏向"
            "（门店仅发放随机玩具）",
            "高（图鉴状态）")


VERDICT_TEXT = {
    "available": "当前轮次命中，可冲 🎉",
    "series_mismatch": "当前轮次非此款，建议换店/等轮换",
    "likely": "可能有，建议到店/App 再确认",
    "collector_only": "当前门店不发放，属收藏款",
    "unavailable_store": "该门店暂未提供开心乐园餐",
}


# ---------------------------------------------------------------------- #
# 报告
# ---------------------------------------------------------------------- #
def build_report(toy, store, happy_available, happy_name, toy_round_names, decision):
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
        lines.append(f"- 门店：{store.get('storeName')}")
        lines.append(f"- 地址：{store.get('address')}")
        lines.append(f"- 门店编号：{store.get('storeCode')}")
        if store.get('distance') is not None:
            lines.append(f"- 距离：{store.get('distance')} 米")
    else:
        lines.append("- 未定位到门店（请检查城市/关键字，或确认 MCP Token）")
    lines.append("")
    lines.append(f"## 📦 开心乐园餐与玩具")
    lines.append(f"- 开心乐园餐在售：{'是' if happy_available else '否'}")
    if happy_name:
        lines.append(f"- 套餐名：{happy_name}")
    if toy_round_names:
        lines.append(f"- 本店套餐玩具轮次：{', '.join(toy_round_names)}")
    lines.append(f"- **结论：{VERDICT_TEXT.get(code, code)}**")
    lines.append(f"- 说明：{detail}")
    lines.append(f"- 置信度：{confidence}")
    lines.append("")
    lines.append("> ⚠️ 说明：麦当劳公开 MCP 未提供「玩具逐件实时库存 / 具体款式」接口，")
    lines.append("> 玩具为随机发放。本结论基于「门店是否在售开心乐园餐 + 本地图鉴状态」的代理判断。")
    lines.append("> 具体款式请以门店实际发放 / 麦当劳 App 为准。")
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
        happy_available, happy_code, happy_name = (False, None, None)
        detail = {}
        if store:
            happy_available, happy_code, happy_name = get_store_happy_meal(client, store.get("storeCode"))
            if happy_available and happy_code:
                detail = client.query_meal_detail(store.get("storeCode"), happy_code)
        toy_round_names = get_toy_round_names(detail)
    except McdMcpError as e:
        print(f"⚠️ MCP 调用出错：{e}")
        print("（可加 --demo 使用演示数据体验完整流程）")
        sys.exit(1)

    decision = decide(toy, happy_available, toy_round_names)
    report = build_report(toy, store, happy_available, happy_name, toy_round_names, decision)

    if args.json:
        out = {
            "toy": toy,
            "store": store,
            "happy_meal_available": happy_available,
            "toy_round_names": toy_round_names,
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
