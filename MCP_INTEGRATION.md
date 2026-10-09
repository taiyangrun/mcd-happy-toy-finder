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
> "帮我查上海南京东路那家麦当劳，现在开心乐园餐有没有三丽鸥玩具？"

## 4. 直接运行脚本（命令行）
```bash
# 配置 Token（Linux/macOS）
export MCD_MCP_TOKEN="你的Token"

# Windows PowerShell
$env:MCD_MCP_TOKEN="你的Token"

# 运行查询
python scripts/toy_lookup.py --toy "三丽鸥" --city "上海" --store "南京东路"
```
未配置 Token 时，脚本自动进入**演示模式**（内置样例数据），完整演示查询流程。

## 5. 本作品用到的工具
| 工具 | 用途 |
|------|------|
| `query-nearby-stores` | 按城市/关键字定位门店（取 storeId） |
| `query-meals` | 查询门店在售餐品，确认开心乐园餐 |
| `query-meal-detail` | 提取开心乐园餐内「可选玩具」选项 |

> 详见 `references/mcd-mcp-tools.md`。

## 6. 关于「玩具库存」的诚实说明
麦当劳公开 MCP **未提供**「玩具逐件实时库存」工具。本作品以「开心乐园餐在售 +
套餐可选玩具」作为库存的**代理信号**，并结合本地图鉴状态给出带置信度的结论，
结果中明确标注免责声明。若官方未来上线库存/SKU 类工具，只需在 `scripts/mcp_client.py`
增加对应封装，主流程无需改动。
