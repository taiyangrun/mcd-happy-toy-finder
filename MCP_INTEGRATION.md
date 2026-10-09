# 麦当劳 MCP 接入说明（MCP Integration Guide）

本说明介绍 `mcd-happy-toy-finder` 如何接入并使用麦当劳中国官方 MCP 服务。

## 1. 申请 MCP Token
1. 打开 https://open.mcd.cn/mcp ，点击右上角【登录】，用手机号验证登录；
2. 登录后点击右上角【控制台】→【激活】申请 MCP Token；
3. 同意《麦当劳 MCP 服务规则》后，一键复制 Token 妥善保管。

## 2. 接入参数
| 项 | 值 |
|----|----|
| 服务器地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（**不支持** WebSocket） |
| 认证方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| 支持 MCP 版本 | `2025-06-18` 及之前 |
| 限流 | 每 Token 每分钟 ≤ 600 次（超限 429） |
| 响应结构 | 优先使用 `structuredContent`（含 `success/code/message/data`），否则解析 `content[].text` 内 JSON |

## 3. 在 WorkBuddy 中配置（推荐，可获参赛专项奖励）
在 WorkBuddy 的「连接器 / MCP」中添加如下配置，替换 `YOUR_MCP_TOKEN` 后启用：
```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```
启用后在对话框直接用自然语言即可触发本 Skill，例如：
> "帮我查上海南京东路那家麦当劳，现在开心乐园餐发什么玩具？"

> 仓库根目录已附带脱敏配置示例 **`mcp-config.example.json`**（仅含 `${MCD_MCP_TOKEN}` 环境变量占位符，不含任何真实 Token），可直接参考或复制到 WorkBuddy / 自建 MCP 客户端中使用。

## 4. 直接运行脚本（命令行）
```bash
# 配置 Token（Linux/macOS）
export MCD_MCP_TOKEN="你的Token"

# Windows PowerShell
$env:MCD_MCP_TOKEN="你的Token"

# 运行查询
python scripts/toy_lookup.py --toy "航海王" --city "上海" --store "南京东路"
```
未配置 Token 时，脚本自动进入**演示模式**（内置样例数据），完整演示查询流程。

## 5. 本作品用到的工具（已在真实环境验证）
| 工具 | 真实必填入参 | 用途 |
|------|------|------|
| `query-nearby-stores` | `beType`(1=到店/5=得来速)、`searchType`(2=按位置)，`searchType=2` 时 `city`/`keyword` 至少其一 | 定位门店，取 `storeCode` |
| `query-meals` | `storeCode`、`orderType`(1=到店/2=外送)、`beType` | 返回 `data.{categories, meals(码→详情), frequent}`，确认开心乐园餐（取 `code`）|
| `query-meal-detail` | `storeCode`、`orderType`、`beType`、`code` | 返回 `data.{code,name,rounds}`，`rounds` 中名称含「玩具」的轮次即当前玩具轮次 |

## 6. 关于「玩具库存」的诚实说明
麦当劳公开 MCP **未提供**「玩具逐件实时库存 / 具体款式」工具，且开心乐园餐玩具为
**随机发放**。本作品通过 `query-meal-detail` 读取套餐「玩具轮次」名称作为代理信号：
- 当轮次为**具体系列名**（如 `海绵宝宝×航海王系列玩具`）时，与本地图鉴做匹配，命中即高置信；
- 当轮次为 `随机玩具1个`（不暴露具体系列）时，回退到图鉴 `status` 状态判断。

结论均明确标注置信度与免责声明。若官方未来上线库存/SKU 类工具，只需在
`scripts/mcp_client.py` 增加对应封装，主流程无需改动。
