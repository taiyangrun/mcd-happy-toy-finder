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
    def call_tool_structured(self, name: str, arguments: dict = None) -> dict:
        """调用工具并返回结构化结果。

        优先使用 MCP 响应的 structuredContent（官方服务返回的干净 JSON，
        含 success/code/message/data）；若服务端未提供 structuredContent，
        则回退解析 content[].text 里的 JSON 字符串。失败时抛出 McdMcpError。
        """
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
        result = resp.get("result", resp)
        sc = result.get("structuredContent")
        if isinstance(sc, dict):
            return sc
        text = self._extract_text(result)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"_text": text}

    # ------------------------------------------------------------------ #
    # 业务封装（返回值均为已解析的结构化数据，便于上层直接消费）
    # ------------------------------------------------------------------ #
    def query_nearby_stores(self, city: str = None, keyword: str = None,
                            beType: int = 1, searchType: int = 2) -> list:
        """查询门店，返回门店字典列表。

        真实接口必填 beType(1=到店自提/5=得来速) 与 searchType(2=按位置)；
        searchType=2 时 city/keyword 至少其一非空（实测仅传 city 会报
        「城市名或者关键词不能为空」，故仅传城市时把城市作为位置关键词一并带入）。
        返回 data 为列表，字段：storeCode(唯一编号) / storeName / address /
        distance / reservation。（beType=1 到店自提时门店无 beCode）
        """
        args = {"beType": beType, "searchType": searchType}
        if city:
            args["city"] = city
        if keyword:
            args["keyword"] = keyword
        elif city and searchType == 2:
            args["keyword"] = city
        data = self.call_tool_structured("query-nearby-stores", args).get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []

    def query_meals(self, store_code: str, orderType: int = 1, beType: int = 1) -> dict:
        """查询指定门店当前在售餐品，返回 data 字典。

        真实接口必填 storeCode + orderType(1=到店/2=外送) + beType。
        data 结构：{ categories:[{name,meals:[{code}]}],
                     meals:{code:{name,currentPrice,...}},
                     frequent:{code,tags} }
        """
        args = {"storeCode": store_code, "orderType": orderType, "beType": beType}
        return self.call_tool_structured("query-meals", args).get("data") or {}

    def query_meal_detail(self, store_code: str, meal_code: str,
                          orderType: int = 1, beType: int = 1) -> dict:
        """查询套餐详情，返回 data 字典。

        真实接口必填 storeCode + orderType + beType + code(餐品唯一编码)。
        data 结构：{ code, name, rounds:[{id,name,choices:[{code,name,isDefault}]}] }。
        开心乐园餐的玩具轮次 name 通常为「随机玩具1个」（官方随机发放，
        不暴露具体玩具型号，故无法据此确认某特定玩具是否有货）。
        """
        args = {"storeCode": store_code, "orderType": orderType,
                "beType": beType, "code": meal_code}
        return self.call_tool_structured("query-meal-detail", args).get("data") or {}

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
                DATA = [
                    {"storeCode": "SH001", "storeName": "麦当劳上海南京东路餐厅",
                     "address": "上海市黄浦区南京东路100号", "distance": 120, "reservation": True},
                    {"storeCode": "SH002", "storeName": "麦当劳上海徐家汇餐厅",
                     "address": "上海市徐汇区肇嘉浜路1000号", "distance": 800, "reservation": False},
                    {"storeCode": "BJ001", "storeName": "麦当劳北京三里屯餐厅",
                     "address": "北京市朝阳区三里屯路19号", "distance": 300, "reservation": True},
                ]
                wrap = {"success": True, "code": 200, "message": "请求成功", "data": DATA}
                return {"result": {"content": [{"type": "text", "text": json.dumps(wrap, ensure_ascii=False)}]}}
            if name == "query-meals":
                DATA = {
                    "categories": [{"name": "儿童", "meals": [{"code": "HM001"}]}],
                    "meals": {
                        "HM001": {"name": "鱼排堡开心乐园餐", "currentPrice": "24",
                                  "originalPrice": "24", "canWithOrder": False},
                        "C001": {"name": "巨无霸套餐", "currentPrice": "33",
                                 "originalPrice": "33", "canWithOrder": True},
                    },
                    "frequent": {"code": "C001", "tags": ["我的常点"]},
                }
                wrap = {"success": True, "code": 200, "message": "请求成功", "data": DATA}
                return {"result": {"content": [{"type": "text", "text": json.dumps(wrap, ensure_ascii=False)}]}}
            if name == "query-meal-detail":
                code = args.get("code", "HM001")
                # 真实接口中玩具轮次为「随机玩具1个」，不暴露具体款式
                DATA = {
                    "code": code,
                    "name": "鱼排堡开心乐园餐",
                    "rounds": [
                        {"id": 1, "name": "鱼排堡", "choices": [{"code": "504642", "name": "鱼排堡", "isDefault": 1}]},
                        {"id": 2, "name": "迷你薯条", "choices": [{"code": "504643", "name": "迷你薯条", "isDefault": 1}]},
                        {"id": 5, "name": "随机玩具1个", "choices": [{"code": "7001", "name": "随机玩具1个", "isDefault": 1}]},
                    ],
                }
                wrap = {"success": True, "code": 200, "message": "请求成功", "data": DATA}
                return {"result": {"content": [{"type": "text", "text": json.dumps(wrap, ensure_ascii=False)}]}}
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
