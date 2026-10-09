# WorkBuddy 开发上下文（workbuddy.md）

> 本文件用于核验本项目是否使用 WorkBuddy 开发，以符合「麦当劳 × WorkBuddy」联动活动的专项奖励条件。
> 根据活动规则，参加 WorkBuddy 专项奖励（排行榜前 100 名提交本文件即可获得 3,000 积分）时必须提交本文件。

## 开发工具
- **WorkBuddy（腾讯）**：作为 AI 开发助手，完成本 Skill 的需求分析、方案设计、编码实现与本地自测。
- **skill-creator**：用于按 WorkBuddy 规范初始化并校验 Skill 结构（已通过 `package_skill.py` 校验）。
- 开发日期：2026-10-09
- 开发方式：在 WorkBuddy 对话框中以自然语言提出需求，由 WorkBuddy 执行调研、搭建骨架、编写代码与数据、完成自测。

## 关键对话上下文摘要
1. **需求提出**：搜集全国各地麦当劳开心乐园餐（Happy Meal）玩具，并调用麦当劳 MCP 确认某款玩具在指定门店是否还有/能否拿到。
2. **官方调研**：WorkBuddy 检索并解析官方仓库 `M-China/mcd-mcp-server` 与大赛仓库 `M-China/mcd-developer-innovation-challenge`，确认 MCP 接入地址（`https://mcp.mcd.cn`）、Token 申请方式、参赛文件规范与 Issue 报名格式。
3. **方案设计**：调研发现官方公开 MCP **没有**「玩具逐件实时库存」接口。据此确定「本地玩具图鉴 + 门店定位（query-nearby-stores）+ 开心乐园餐在售确认（query-meals）+ 套餐可选玩具提取（query-meal-detail）」的**代理判断**方案，并明确标注置信度与免责声明，避免误导。
4. **编码实现**：编写 `scripts/mcp_client.py`（麦当劳 MCP Streamable HTTP 客户端，含演示模式与真实模式）、`scripts/toy_lookup.py`（图鉴模糊匹配 + 库存代理判断 + 结构化报告）、`assets/toys.json`（全国开心乐园餐玩具图鉴种子数据，13 条，可按 schema 社区补全）、`SKILL.md` 及 `references/` 文档。
5. **自测与打包**：在演示模式（无需 Token）下验证完整查询流程；使用 skill-creator 的 `package_skill.py` 校验并通过，打包为 `mcd-happy-toy-finder.zip`。

## 自测结果（演示模式）
- 查询「奶龙 @ 上海」→ 图鉴状态为往期收藏，套餐可选玩具未含该款 ⇒ 收藏款，当前门店不发放。
- 查询「三丽鸥 @ 北京三里屯」→ 套餐可选玩具命中 ⇒ ✅ 有货，可冲。

## 使用的麦当劳 MCP 工具
`query-nearby-stores`、`query-meals`、`query-meal-detail`（详见 `MCP_INTEGRATION.md`）。

---
*本文件由开发者依据 WorkBuddy 实际开发过程自行导出整理，用于奖励资格核验。*
