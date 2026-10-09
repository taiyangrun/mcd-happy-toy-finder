# 麦当劳 MCP 工具参考（本项目用到 / 相关）

> 来源：官方仓库 `M-China/mcd-mcp-server`（README），接入地址 `https://mcp.mcd.cn`。
> 完整工具列表共 30+ 个，本 Skill 仅使用与「门店 / 开心乐园餐 / 套餐玩具」相关的几个。

## 接入要点
- 协议：Streamable HTTP（**不支持** WebSocket）
- 认证：`Authorization: Bearer <MCP_TOKEN>`，Token 在 https://open.mcd.cn/mcp 申请
- 限流：每 Token 每分钟 ≤ 600 次，超限返回 `429`
- 错误码：`401` Token 无效/过期；`429` 限流
- MCP 版本：仅支持 `2025-06-18` 及之前

## 本 Skill 使用的工具

### 1. `query-nearby-stores` — 查询附近/指定城市门店
- 用途：把用户的「城市 / 关键字」解析成具体门店（含 `storeId`）。
- 常用入参（以运行时 `tools/list` 为准）：
  - `city`：城市名，如 "上海"
  - `keyword`：门店/地址关键字，如 "南京东路"
  - `latitude` / `longitude`：经纬度（可选，精准定位）
- 出参：门店列表，含 `storeId`、`name`、`address`、`city` 等。

### 2. `query-meals` — 查询门店在售餐品
- 用途：确认目标门店当前是否提供「开心乐园餐」（携带玩具的套餐）。
- 常用入参：`storeId`
- 出参：餐品列表，含 `mealCode`、`name`、`category`、`price`、`available`。
- 识别逻辑：名称含「开心乐园」或 `category == "儿童"` 或名称含「玩具」者，视为开心乐园餐。

### 3. `query-meal-detail` — 查询套餐详情
- 用途：提取开心乐园餐内「可选玩具」选项（库存代理判断的核心）。
- 常用入参：`mealCode`
- 出参：套餐组成，`options` 数组中 `group == "玩具"` 的 `items` 即为当前可选玩具。

## ⚠️ 关于「玩具库存」的重要事实
麦当劳官方公开 MCP **没有提供**「某玩具在某门店的逐件实时库存」工具。
本 Skill 采用**代理判断**方案：

```
开心乐园餐是否在该门店在售  (query-meals)
        + 该套餐当前可选玩具列表 (query-meal-detail)
        ⇒ 作为「该玩具是否可在此店拿到」的代理信号
```

并叠加本地图鉴（`assets/toys.json`）里玩具的「在售轮换中 / 往期收藏 / 节日限定」
状态，给出带置信度的结论。最终仍以门店实际发放与麦当劳 App 为准。

> 若未来麦当劳 MCP 上线官方「玩具库存 / 套餐玩具 SKU」工具，只需在
> `scripts/mcp_client.py` 增加对应封装即可无缝接入，Skill 主流程无需改动。
