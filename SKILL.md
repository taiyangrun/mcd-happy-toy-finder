---
name: mcd-happy-toy-finder
description: 麦当劳开心乐园餐玩具猎人。当用户想「找麦当劳儿童乐园餐/开心乐园餐的玩具」「查某款玩具（奶龙、三丽鸥、线条小狗等）在某某城市/门店还有没有/是否有货」「搜集或浏览全国各地麦当劳 Happy Meal 玩具图鉴」「用麦当劳 MCP 查门店在售套餐与可选玩具」时使用。该 Skill 结合本地玩具图鉴与麦当劳官方 MCP（门店定位 + 开心乐园餐在售 + 套餐可选玩具），给出带置信度的库存判断。
agent_created: true
---

# 麦当劳开心乐园餐玩具猎人（mcd-happy-toy-finder）

## Overview

帮助家长、孩子与玩具收藏爱好者**搜集并查询全国各地的麦当劳开心乐园餐（Happy Meal）
玩具**：一方面维护一份可扩展的本地「玩具图鉴」，另一方面调用**麦当劳官方 MCP**
定位门店、确认开心乐园餐在售情况并提取套餐内可选玩具，从而判断「某玩具在指定门店
是否还有/能否拿到」。

**关键事实（务必知悉）**：麦当劳公开 MCP **没有**「玩具逐件实时库存」接口。本 Skill
采用**代理判断**：用 `query-nearby-stores`（门店定位）+ `query-meals`（开心乐园餐在售）
+ `query-meal-detail`（套餐可选玩具）作为库存信号，叠加本地图鉴的状态字段，给出带
置信度的结论。最终以门店实际发放 / 麦当劳 App 为准。

## When to use

- 用户想找某款麦当劳玩具（如"奶龙还有吗""哪里能拿到三丽鸥玩具"）。
- 用户想知道某城市/某门店当前开心乐园餐发什么玩具。
- 用户想浏览/搜集全国各地麦当劳开心乐园餐玩具图鉴。
- 用户要求"用麦当劳 MCP 查门店套餐和玩具"。

## Workflow

### 1. 准备
- 确认是否已配置麦当劳 MCP Token：环境变量 `MCD_MCP_TOKEN`。
  - 未配置时，脚本自动进入**演示模式**（内置样例数据），仍可完整演示流程。
  - 配置方式见 `MCP接入说明.md`（在 https://open.mcd.cn/mcp 申请，填入 WorkBuddy 的
    麦当劳 MCP 连接器，或在运行脚本前 `export MCD_MCP_TOKEN=xxx`）。

### 2. 匹配玩具（本地图鉴）
- 读取 `assets/toys.json`（图鉴格式见 `references/toy-catalog.md`）。
- 用名称 / IP / 系列 / `keywords` 做模糊匹配；命中多条时优先精确名。
- 若未命中，提示用户用更通用的关键词，或先 `--list` 浏览全部。

### 3. 定位门店（麦当劳 MCP）
- 调用 `query-nearby-stores`，入参 `city` + 可选 `keyword`（门店/地址关键字）。
- 取首个匹配门店，记录 `storeId` / `name` / `address`。

### 4. 判断库存（代理逻辑）
- 调用 `query-meals(storeId)`：找开心乐园餐（`mealCode`）。
  - 找不到 → 该门店暂未提供开心乐园餐。
- 调用 `query-meal-detail(mealCode)`：提取 `options` 中 `group=="玩具"` 的 `items`。
- 结合图鉴 `status` 给出结论（详见 `references/mcd-mcp-tools.md`）：
  - 玩具命中套餐可选列表 → ✅ 有货，可冲。
  - 开心乐园餐在售但选项未含该玩具（且在售轮换中）→ 🟡 可能有，需到店确认。
  - 图鉴状态为往期收藏/节日限定 → ⚪ 收藏款，当前门店不发放。
- **始终在输出中标注**：结论基于"在售菜单+套餐玩具选项"代理判断，非逐件实时库存。

### 5. 输出
- 优先用 `scripts/toy_lookup.py` 生成结构化 Markdown 报告（含玩具档案、门店定位、
  库存判断、置信度、免责说明）。
- 需要机器可读结果时加 `--json`。
- 使用示例：
  ```bash
  python scripts/toy_lookup.py --toy "奶龙" --city "上海"
  python scripts/toy_lookup.py --toy "三丽鸥" --city "北京" --store "三里屯" --json
  python scripts/toy_lookup.py --list
  python scripts/toy_lookup.py --toy "奶龙" --demo   # 无 Token 演示
  ```

## Resources

### scripts/
- `mcp_client.py`：麦当劳 MCP Streamable HTTP 客户端封装（含演示模式与真实模式）。
- `toy_lookup.py`：玩具查询主逻辑（图鉴匹配 + 门店定位 + 库存代理判断 + 报告）。

### references/
- `mcd-mcp-tools.md`：用到的 MCP 工具详解与"玩具库存"代理方案说明。
- `toy-catalog.md`：图鉴 JSON 格式与扩充维护指南。

### assets/
- `toys.json`：全国开心乐园餐玩具图鉴（示例种子数据，可社区持续补全）。

## Notes
- 脚本仅依赖 Python 标准库，无需安装第三方包。
- 真实模式受 MCP 限流（600 次/分钟）约束，请勿高频轮询。
- 如未来麦当劳 MCP 上线官方"玩具库存/SKU"工具，在 `mcp_client.py` 增加封装即可，
  主流程无需改动。
