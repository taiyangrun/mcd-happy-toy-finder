---
name: mcd-happy-toy-finder
description: 麦当劳开心乐园餐玩具猎人。当用户想「找麦当劳儿童乐园餐/开心乐园餐的玩具」「查某款玩具（奶龙、三丽鸥、线条小狗、航海王等）在某某城市/门店现在发不发/能不能拿到」「搜集或浏览全国各地麦当劳 Happy Meal 玩具图鉴」「用麦当劳 MCP 查门店在售套餐与当前玩具轮次」时使用。该 Skill 结合本地玩具图鉴与麦当劳官方 MCP（门店定位 + 开心乐园餐在售确认 + 套餐玩具轮次识别），给出带置信度的判断。
agent_created: true
---

# 麦当劳开心乐园餐玩具猎人（mcd-happy-toy-finder）

## Overview

帮助家长、孩子与玩具收藏爱好者**搜集并查询全国各地的麦当劳开心乐园餐（Happy Meal）
玩具**：一方面维护一份可扩展的本地「玩具图鉴」，另一方面调用**麦当劳官方 MCP**
定位门店、确认开心乐园餐在售情况，并识别该门店当前开心乐园餐的**玩具轮次**（部分门店
会暴露具体系列名，如「海绵宝宝×航海王系列玩具」；另一些门店显示「随机玩具1个」），
从而判断「某玩具在指定门店当前能否拿到」。

**关键事实（务必知悉）**：麦当劳公开 MCP **没有**「玩具逐件实时库存 / 具体款式」接口，
且开心乐园餐玩具为**随机发放**。本 Skill 采用**代理判断**：
- `query-nearby-stores` 定位门店 → `query-meals` 确认开心乐园餐在售 →
  `query-meal-detail` 读取套餐「玩具轮次」名称；
- 若轮次为**具体系列名**，则与本地图鉴做匹配（命中即高置信）；
- 若轮次为「随机玩具1个」（不暴露具体系列），则回退到图鉴的 `status` 状态判断。
最终以门店实际发放 / 麦当劳 App 为准，结论中始终标注置信度与免责声明。

## When to use

- 用户想找某款麦当劳玩具（如"奶龙还有吗""哪里能拿到航海王玩具"）。
- 用户想知道某城市/某门店当前开心乐园餐发什么玩具系列。
- 用户想浏览/搜集全国各地麦当劳开心乐园餐玩具图鉴。
- 用户要求"用麦当劳 MCP 查门店套餐和玩具"。

## Workflow

### 1. 准备
- 确认是否已配置麦当劳 MCP Token：环境变量 `MCD_MCP_TOKEN`。
  - 未配置时，脚本自动进入**演示模式**（内置样例数据），仍可完整演示流程。
  - 配置方式见 `MCP_INTEGRATION.md`（在 https://open.mcd.cn/mcp 申请，填入 WorkBuddy 的
    麦当劳 MCP 连接器，或在运行脚本前 `export MCD_MCP_TOKEN=xxx`）。

### 2. 匹配玩具（本地图鉴）
- 读取 `assets/toys.json`（图鉴格式见 `references/toy-catalog.md`）。
- 用名称 / IP / 系列 / `keywords` 做模糊匹配；命中多条时优先精确名。
- 若未命中，提示用户用更通用的关键词，或先 `--list` 浏览全部。

### 3. 定位门店（麦当劳 MCP）
- 调用 `query-nearby-stores`，必填入参 `beType`(1=到店自提/5=得来速) 与
  `searchType`(2=按位置)；`searchType=2` 时 `city`/`keyword` 至少其一非空
  （实测只传 city 会报"城市名或者关键词不能为空"，客户端已自动把城市同时作为位置关键词）。
- 取首个匹配门店，记录 `storeCode` / `storeName` / `address` / `distance`。

### 4. 判断库存（代理逻辑，已在真实 MCP 验证）
- 调用 `query-meals(storeCode)`：在返回的 `meals` 字典（键为餐品码）中按名称匹配
  「开心乐园餐」（`code` + `name`）。找不到 → 该门店暂未提供开心乐园餐。
- 调用 `query-meal-detail(storeCode, 开心乐园餐code)`：读取 `rounds` 里名称含「玩具」
  的轮次，取其 `choices` 名称作为「当前玩具轮次名」。
- 结合图鉴给出结论（详见 `references/mcd-mcp-tools.md`）：
  - 轮次为**具体系列名**且命中图鉴玩具 → ✅ `available`（高置信，"当前轮次命中"）。
  - 轮次为**具体系列名**但不命中 → 🟡 `series_mismatch`（"当前轮次非此款"）。
  - 轮次为「随机玩具1个」且图鉴 `status==在售轮换中` → 🟡 `likely`（到店大概率可领，款式需确认）。
  - 轮次为「随机玩具1个」且图鉴 `status==往期收藏/节日限定` → ⚪ `collector_only`（收藏款）。
  - 门店未售开心乐园餐 → `unavailable_store`。
- **始终在输出中标注**：结论基于"门店是否售开心乐园餐 + 套餐玩具轮次 + 本地图鉴状态"
  的代理判断，非逐件实时库存。

### 5. 输出
- 优先用 `scripts/toy_lookup.py` 生成结构化 Markdown 报告（含玩具档案、门店定位、
  库存判断、置信度、免责说明）。
- 需要机器可读结果时加 `--json`。
- 使用示例：
  ```bash
  python scripts/toy_lookup.py --toy "奶龙" --city "上海"
  python scripts/toy_lookup.py --toy "航海王" --city "上海" --store "南京东路"
  python scripts/toy_lookup.py --list
  python scripts/toy_lookup.py --toy "奶龙" --demo   # 无 Token 演示
  ```

## Resources

### scripts/
- `mcp_client.py`：麦当劳 MCP Streamable HTTP 客户端封装（真实模式读取 `MCD_MCP_TOKEN`；
  演示模式内置样例；优先解析 `structuredContent`，回退解析文本 JSON）。
- `toy_lookup.py`：玩具查询主逻辑（图鉴匹配 + 门店定位 + 玩具轮次识别 + 报告）。

### references/
- `mcd-mcp-tools.md`：用到的 MCP 工具真实入参/出参与"玩具库存"代理方案说明。
- `toy-catalog.md`：图鉴 JSON 格式与扩充维护指南。

### assets/
- `toys.json`：全国开心乐园餐玩具图鉴（示例种子数据，可社区持续补全）。

## Notes
- 脚本仅依赖 Python 标准库，无需安装第三方包。
- 真实模式受 MCP 限流（600 次/分钟）约束，请勿高频轮询。
- 如未来麦当劳 MCP 上线官方"玩具库存/SKU"工具，在 `mcp_client.py` 增加封装即可，
  主流程无需改动。
