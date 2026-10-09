# 🍔 mcd-happy-toy-finder · 麦当劳开心乐园餐玩具猎人

> 2026 麦当劳程序员创意开发大赛 · 参赛作品
> 基于 **麦当劳 MCP（McDonald's Capability Platform）** + **WorkBuddy** 打造的开心乐园餐玩具查询 Skill。

## 一句话介绍
帮家长、孩子和玩具收藏党，**搜集全国各地的麦当劳开心乐园餐（Happy Meal）玩具图鉴**，
并调用**麦当劳官方 MCP** 判断「某款玩具在指定门店当前发不发 / 能不能拿到」，给出带置信度的答案。

## 痛点
- 开心乐园餐玩具经常「今天这个明天那个」，家长想凑齐某 IP 却不知道哪家店现在发；
- 收藏党想追踪全国各地的限定/往期玩具，缺乏一份可检索的图鉴；
- 麦当劳官方没有「玩具逐件实时库存」查询入口，且玩具为随机发放，只能到店碰运气。

## 我们的方案
采用「**本地图鉴 + 官方 MCP 代理查询**」双数据源：

1. **玩具图鉴（assets/toys.json）**：整理型知识库，搜集全国各地开心乐园餐玩具系列
   （奶龙、三丽鸥、线条小狗、小黄人、宝可梦、奥特曼、哆啦A梦、泡泡玛特、海绵宝宝×航海王……），
   覆盖 IP、年代、范围、稀有度、状态等字段，社区可按统一 schema 持续补全。
2. **麦当劳 MCP 代理查询**（已在真实环境端到端验证）：
   - `query-nearby-stores` 定位目标门店（返回 `storeCode` / `storeName` / `address`）；
   - `query-meals` 确认该店开心乐园餐是否在售；
   - `query-meal-detail` 读取套餐「玩具轮次」名称——
     **部分门店会暴露具体系列名**（如 `海绵宝宝×航海王系列玩具`），
     另一些门店显示 `随机玩具1个`；
   - 若轮次为具体系列名，则与图鉴做匹配（命中即高置信）；若为随机玩具，则回退到图鉴 `status` 判断。

> 诚实说明：麦当劳公开 MCP **没有**「玩具实时库存 / 具体款式」工具，且玩具随机发放。
> 本作品以「门店是否售开心乐园餐 + 套餐玩具轮次 + 本地图鉴状态」作为代理信号，
> 并在结果中明确标注置信度与免责声明。若官方后续上线库存接口，仅需扩展
> `scripts/mcp_client.py`，主流程无需改动。

## 真实数据验证（示例）
- 查 `航海王 @ 上海 南京东路` → 该门店当前轮次为「海绵宝宝×航海王系列玩具」，
  **命中图鉴 → 结论「当前轮次命中，可冲 🎉」（高置信）**。
- 查 `奶龙 @ 上海 南京东路` → 当前轮次为航海王系列，**非此款 → 结论「当前轮次非此款」**。
- 查 `奶龙 @ 上海`（随机玩具门店）→ 回退图鉴状态「往期收藏」→ 结论「收藏款」。

## 特性
- 🧸 可扩展的全国玩具图鉴，模糊搜索（中英文/别名）；
- 📍 基于真实 MCP 的门店定位与开心乐园餐在售确认；
- 🎯 识别门店「当前玩具轮次」，能命中具体系列时给出高置信结论；
- 📦 带置信度的库存结论，不夸大、不误导；
- 🤖 原生 WorkBuddy Skill，自然语言即可触发；
- 🧪 内置演示模式，无 Token 也能完整跑通（方便评委体验）。

## 目录结构
```
mcd-happy-toy-finder/
├── SKILL.md              # WorkBuddy Skill 主文档
├── README.md             # 本文件（项目介绍）
├── CONTEST_DECLARATION.md# 参赛声明（官方模板逐字）
├── MCP_INTEGRATION.md    # 麦当劳 MCP 接入说明
├── workbuddy.md          # WorkBuddy 开发上下文（申请专项奖励）
├── scripts/
│   ├── mcp_client.py      # 麦当劳 MCP Streamable HTTP 客户端（含演示模式）
│   └── toy_lookup.py      # 玩具查询主逻辑
├── references/
│   ├── mcd-mcp-tools.md   # 用到的 MCP 工具详解
│   └── toy-catalog.md     # 图鉴格式与维护说明
└── assets/
    └── toys.json          # 全国开心乐园餐玩具图鉴（示例种子数据）
```

## 快速开始
```bash
# 1. 浏览图鉴
python scripts/toy_lookup.py --list

# 2. 演示模式查询（无需 Token）
python scripts/toy_lookup.py --toy "奶龙" --city "上海" --demo

# 3. 真实模式（先配置 Token）
export MCD_MCP_TOKEN="你的麦当劳MCP Token"
python scripts/toy_lookup.py --toy "航海王" --city "上海" --store "南京东路"

# 4. 机器可读输出
python scripts/toy_lookup.py --toy "航海王" --city "上海" --json
```
> 详细 MCP 接入与 Token 申请见 `MCP_INTEGRATION.md`。
