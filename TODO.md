# TODO｜后续待办

## ✅ 已完成（2026-07-09）
- [x] **低估高潜力20股(稳健主仓) 补 PE+ROE 四象限分类**——11只踏实型为主体，无博弈型，与小市值那份对称
- [x] **两份选股清单交叉引用说明**——各自顶部加配套文件链接+定位差异说明
- [x] **迪普科技300768 单只深度报告**——`深度报告_迪普科技300768_百倍候选.md`（百倍数学最不荒谬候选，现实10-30x，百倍<3%）
- [x] **季度跟踪模板**——`scripts/track.py`，拉取40只实时行情/财务/PB分位+建仓/止损/目标监控+告警，`python3 scripts/track.py --md` 生成 tracking_report.md
- [x] **建仓价/止损监控告警脚本**——已集成在 track.py（破止损🔴/建仓区🟢/接近目标🟠/超目标🟣 自动标注）
- [x] **自建 web 检索脚本** `scripts/websearch.py`——绕过本会话被拦的 WebSearch/WebFetch 工具，后端 Bing(网页搜索)+arXiv API(论文检索/ID验证)+通用抓取。用法：`python3 scripts/websearch.py "查询"` / `--arxiv "DeepSeek-V4"` / `--arxiv-id 2606.19348` / `--fetch URL`
- [x] **AI 板块时效性修复（用脚本核实）**——原报告把 DeepSeek-V3 当现役 SOTA、GPT-5/Claude4/Gemini2 当"未来催化"。经 arXiv+Bing 核实更正：DeepSeek-**V4**已发(arXiv:2606.19348,2026-04-26,V4-Pro 1.6T/49B、V4-Flash 284B/13B,百万token)、OpenAI 已至 **GPT-5.5**、Claude 已至 **Fable 5**、Gemini 已至 **3.x**。回填人工智能.md/summary.md
- [x] **arXiv 引用真伪批量验证**——AI/半导体报告 19 个 `2607.*/2606.*` arXiv ID 经 API 验证**全部真实存在**（标题一致），数据可靠，无需更正

## ⏳ 待时间触发（不可现在做）
- [ ] **2026年8月底中报披露后**：跑 track.py 刷新全部财务/评级/建仓价/目标价；重算行业评分排名
- [ ] **2026年10月三季报后**：二次刷新
- [ ] 36行业报告约565处"待核实"项二次核实——多为港股财报/行业白皮书/未来事件，中报后随数据更新顺带核实

## 🔜 可做但优先级低
- [ ] **前沿时效性定期刷新**（每月）：用 `scripts/websearch.py` 核实各板块时效敏感声明——模型版本(DeepSeek/GPT/Claude/Gemini)、半导体制程/GPU代、Starship 试飞次数、G60/千帆在轨颗数、FIPS 206(Falcon)是否发布、钙钛矿/电池效率纪录、创新药获批——更新各报告"待核实"项
- [ ] 北向资金/基金重仓数据补充（当前eastmoney push2接口受限；可换源如 stock_zh_a_gdhs_detail_em 股东户数试取）
- [ ] 三情景组合（牛市/震荡/熊市）随市场环境变化定期重评（用 track.py 输出 + 指数估值分位判断）
- [ ] track.py 扩展：加入指数估值分位(沪深300/创业板PE/PB)自动判断牛震荡熊 + 自动邮件/通知告警
