# 麦当劳 MCP 工具参考（本项目用到 / 相关）

> 来源：官方仓库 `M-China/mcd-mcp-server`，接入地址 `https://mcp.mcd.cn`。
> 完整工具列表共 30+ 个，本 Skill 仅使用与「门店 / 开心乐园餐 / 玩具轮次」相关的三个。
> 以下入参/出参为**真实环境 `tools/list` 实测**结果。

## 接入要点
- 协议：Streamable HTTP（**不支持** WebSocket）
- 认证：`Authorization: Bearer <MCP_TOKEN>`，Token 在 https://open.mcd.cn/mcp 申请
- 限流：每 Token 每分钟 ≤ 600 次，超限返回 `429`
- 错误码：`401` Token 无效/过期；`429` 限流
- MCP 版本：仅支持 `2025-06-18` 及之前
- 响应：优先用 `structuredContent`（含 `success/code/message/data`）；否则解析 `content[].text` 内 JSON

## 本 Skill 使用的工具（真实 schema）

### 1. `query-nearby-stores` — 查询门店
- **必填入参**：`beType`(1=到店自提 / 5=得来速)、`searchType`(1=收藏 / 2=按位置)
- **条件必填**：`searchType=2` 时 `city` 或 `keyword` 至少其一非空（实测只传 `city` 会报
  「城市名或者关键词不能为空」，故客户端在仅传城市时自动将其同时作为位置关键词）
- **出参** `data`（列表）：`storeCode`(唯一编号) / `storeName` / `address` / `distance` /
  `reservation` / `reservationTimeOptions`。（`beType=1` 到店自提时门店无 `beCode`）

### 2. `query-meals` — 查询门店在售餐品
- **必填入参**：`storeCode`、`orderType`(1=到店 / 2=外送)、`beType`
- **出参** `data`（字典）：
  - `categories`：分类列表 `[{name, meals:[{code}]}]`
  - `meals`：**以餐品码为键的字典** `{code: {name, currentPrice, originalPrice, canWithOrder, ...}}`
  - `frequent`：`{code, tags}`
- **识别开心乐园餐**：在 `data.meals` 中按 `name` 含「开心乐园」或「玩具」匹配，取其 `code`。

### 3. `query-meal-detail` — 查询套餐详情（含玩具轮次）
- **必填入参**：`storeCode`、`orderType`、`beType`、`code`(餐品码)
- **出参** `data`（字典）：`code` / `name` / `rounds`（选配轮次数组）
- 每个 `round`：`{id, name, quantity, choices:[{code, name, isDefault, diffPrice, ...}]}`
- **识别玩具轮次**：遍历 `rounds`，取 `name` 含「玩具」的轮次的 `choices[].name`。
  - 真实情况 A（具体系列）：`随机玩具1个` 之外的名称，如 `海绵宝宝×航海王系列玩具` → 可与图鉴匹配。
  - 真实情况 B（随机）：`随机玩具1个` → 不暴露具体系列，回退图鉴 `status` 判断。

## ⚠️ 关于「玩具库存」的重要事实
麦当劳官方公开 MCP **没有提供**「某玩具在某门店的逐件实时库存」工具，且玩具为随机发放。
本 Skill 采用**代理判断**方案：

```
门店是否售开心乐园餐  (query-meals)
   + 套餐「玩具轮次」名称 (query-meal-detail)
   ⇒ 具体系列名 → 与本地图鉴匹配（命中=高置信）
   ⇒ 随机玩具1个 → 回退图鉴 status 状态判断
```

并叠加本地图鉴（`assets/toys.json`）里玩具的「在售轮换中 / 往期收藏 / 节日限定」
状态，给出带置信度的结论。最终仍以门店实际发放与麦当劳 App 为准。

> 若未来麦当劳 MCP 上线官方「玩具库存 / 套餐玩具 SKU」工具，只需在
> `scripts/mcp_client.py` 增加对应封装即可无缝接入，Skill 主流程无需改动。
