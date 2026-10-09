#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳 MCP 客户端封装（Streamable HTTP）

这是 mcd-happy-toy-finder Skill 的核心连接器，负责与麦当劳中国官方 MCP
服务（https://mcp.mcd.cn）通信，调用与「门店 / 开心乐园餐 / 套餐玩具选项」
相关的工具，为「某玩具在某门店是否有货」提供数据支撑。

关键事实（来自官方仓库 M-China/mcd-mcp-server）：
- 接入地址： https://mcp.mcd.cn
- 协议：     Streamable HTTP（非 WebSocket）
- 认证：     Authorization: Bearer <MCP_TOKEN>
- Token：    在 https://open.mcd.cn/mcp 登录后控制台申请
- 限流：     每 Token 每分钟最多 600 次，超限返回 429
- 重要：     官方 MCP **没有**「玩具逐件实时库存」工具。本 Skill 用
            query-nearby-stores（门店定位）+ query-meals（开心乐园餐在售）
            + query-meal-detail（套餐内可选玩具选项）作为库存的代理判断。

本模块不依赖任何第三方库，仅使用 Python 标准库。

两种运行模式：
1) 真实模式：设置环境变量 MCD_MCP_TOKEN 后自动启用，直连官方 MCP。
2) 演示模式（默认，无 Token 时）：返回内置样例数据，便于离线演示与评委测试。
"""

import os
import sys
import json
import urllib.request
import urllib.error

MCP_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class McdMcpError(RuntimeError):
    """麦当劳 MCP 调用相关的错误。"""


class McdMcpClient:
    """极简麦当劳 MCP Streamable HTTP 客户端。"""

    def __init__(self, token: str = None, demo: bool = False):
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        # 没有 Token 时强制走演示模式，保证可离线运行。
        self.demo = demo or not self.token
        self.session_id = None
        self._id = 0

    # ------------------------------------------------------------------ #
    # 底层传输
    # ------------------------------------------------------------------ #
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    @staticmethod
    def _parse_body(body: str):
        """兼容 JSON 与 SSE（text/event-stream）两种响应。"""
        body = (body or "").strip()
        if not body:
            return None
        if body.startswith("{"):
            return json.loads(body)
        # SSE: 多行 "event: x" / "data: {...}"
        last = None
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    try:
                        last = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
        return last

    def _post(self, payload: dict):
        if self.demo:
            return self._mock(payload)

        data = json.dumps(payload).encode("utf-8")
        headers = dict(DEFAULT_HEADERS)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(MCP_URL, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise McdMcpError("MCP Token 无效 / 已过期 / 未提供（HTTP 401）。请在 https://open.mcd.cn/mcp 重新申请。")
            if e.code == 429:
                raise McdMcpError("触发限流（HTTP 429），每分钟最多 600 次请求。请降低调用频率。")
            raise McdMcpError(f"MCP 请求失败：HTTP {e.code}")
        except urllib.error.URLError as e:
            raise McdMcpError(f"无法连接麦当劳 MCP 服务：{e.reason}")

        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        return self._parse_body(resp.read().decode("utf-8", errors="replace"))

    # ------------------------------------------------------------------ #
    # MCP 握手
    # ------------------------------------------------------------------ #
    def initialize(self):
        """执行 initialize 握手并发送 initialized 通知。"""
        if self.demo:
            return {"result": {"serverInfo": {"name": "mcd-mcp (demo)"}}}
        self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-happy-toy-finder", "version": "1.0.0"},
            },
        })
        # 通知类请求（无需返回）
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 工具调用
    # ------------------------------------------------------------------ #
    def call_tool(self, name: str, arguments: dict = None) -> dict:
        """调用任意 MCP 工具，返回解析后的 result 内容。"""
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        if not resp:
            raise McdMcpError(f"工具 {name} 无响应")
        if "error" in resp:
            raise McdMcpError(f"工具 {name} 返回错误：{resp['error']}")
        return resp.get("result", resp)

    @staticmethod
    def _extract_text(result: dict) -> str:
        """把 MCP content 数组里的文本拼起来（MCP 标准返回结构）。"""
        parts = []
        for item in (result or {}).get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # 业务封装
    # ------------------------------------------------------------------ #
    def query_nearby_stores(self, keyword: str = None, city: str = None,
                            latitude: float = None, longitude: float = None) -> str:
        """查询附近/指定城市的麦当劳门店。"""
        args = {}
        if keyword:
            args["keyword"] = keyword
        if city:
            args["city"] = city
        if latitude is not None:
            args["latitude"] = latitude
        if longitude is not None:
            args["longitude"] = longitude
        return self._extract_text(self.call_tool("query-nearby-stores", args))

    def query_meals(self, store_id: str) -> str:
        """查询指定门店当前在售餐品（含开心乐园餐）。"""
        return self._extract_text(self.call_tool("query-meals", {"storeId": store_id}))

    def query_meal_detail(self, meal_code: str) -> str:
        """查询套餐详情，提取套餐内可选玩具选项。"""
        return self._extract_text(self.call_tool("query-meal-detail", {"mealCode": meal_code}))

    # ------------------------------------------------------------------ #
    # 演示模式数据
    # ------------------------------------------------------------------ #
    def _mock(self, payload: dict):
        method = payload.get("method")
        params = payload.get("params", {})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "query-nearby-stores":
                return {"result": {"content": [{"type": "text", "text": json.dumps([
                    {"storeId": "SH001", "name": "麦当劳上海南京东路餐厅", "address": "上海市黄浦区南京东路100号", "city": "上海"},
                    {"storeId": "SH002", "name": "麦当劳上海徐家汇餐厅", "address": "上海市徐汇区肇嘉浜路1000号", "city": "上海"},
                    {"storeId": "BJ001", "name": "麦当劳北京三里屯餐厅", "address": "北京市朝阳区三里屯路19号", "city": "北京"},
                ], ensure_ascii=False)}]}}
            if name == "query-meals":
                return {"result": {"content": [{"type": "text", "text": json.dumps([
                    {"mealCode": "HM001", "name": "开心乐园餐（玩具随机）", "category": "儿童", "price": 29.0, "available": True},
                    {"mealCode": "C001", "name": "巨无霸套餐", "category": "汉堡", "price": 33.0, "available": True},
                ], ensure_ascii=False)}]}}
            if name == "query-meal-detail":
                return {"result": {"content": [{"type": "text", "text": json.dumps({
                    "mealCode": "HM001",
                    "name": "开心乐园餐（玩具随机）",
                    "options": [
                        {"group": "玩具", "items": ["麦麦哒哒", "线条小狗", "三丽鸥家族"]},
                        {"group": "饮料", "items": ["可乐", "橙汁", "牛奶"]},
                    ],
                }, ensure_ascii=False)}]}}
        # initialize / 其它
        return {"result": {"serverInfo": {"name": "mcd-mcp (demo)"}}}


if __name__ == "__main__":
    client = McdMcpClient()
    client.initialize()
    print("=== 演示：附近门店 ===")
    print(client.query_nearby_stores(city="上海"))
    print("=== 演示：门店在售餐品 ===")
    print(client.query_meals("SH001"))
    print("=== 演示：开心乐园餐详情（含玩具选项）===")
    print(client.query_meal_detail("HM001"))
