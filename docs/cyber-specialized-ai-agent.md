# 安全 / Cyber 特化 AI 与 Agent：现状、机会与切入方式

> 接续 [agent-data-monetization-security-code.md](./agent-data-monetization-security-code.md) 和 [精简版](./agent-data-monetization-summary.md)，把方向收窄到“cyber 特化的 AI / Agent”。
> 资料截至 2026-11-08。市场数字多来自新闻和厂商自述，未独立核实，引用前请看文末来源。

## 0. 结论先行

2026 年，“cyber 特化模型”这一层已经被前沿实验室占住，而且都是**门控访问**。个人或小团队不应该去做“又一个 cyber 大模型”，也不应该正面去做“又一个自动找漏洞的 Agent”。

还有空间的地方是三处：

1. **可验证的 cyber 任务/环境**：训练方正在从“买数据”转向“买环境”，验证器是核心壁垒。
2. **验证与分诊**：漏洞**发现**已经泛滥，**确认**（复现、去重、可利用性、补丁有效性）才是稀缺的。
3. **前沿模型不覆盖的垂直场景**：私有化/离线部署、特定生态（固件、ICS/OT、机器人等）。

所谓“特化”，对个人来说主要体现在 **harness（工具 + 沙箱 + 验证器 + 数据闭环）**，而不是模型权重。

## 1. 2026 年的格局

### 1.1 前沿实验室：cyber 特化模型已成形，但都要审批

| 厂商 | 模型 | 时间 | 访问方式 |
|------|------|------|----------|
| Anthropic | Claude Mythos Preview（Project Glasswing） | 2026-04-07 | 12 家发布伙伴 + 40 多家关键软件维护组织；开源维护者可经 Claude for Open Source 申请；10-06 起 Cyber Verification Program 扩为三档，面向合格的安全从业者 |
| Anthropic | Mythos 5.1（报道） | 2026-09 | 可信访问 |
| OpenAI | GPT-5.4-Cyber | 2026-04-14 | Trusted Access for Cyber 最高档，需人工审批，不在公开 API |
| OpenAI | GPT-6 Astra / GPT-6 Cyber（预览，报道） | 2026-09 | 分阶段、按能力门控 |
| Google | Gemini 3.8 Flash Cyber（名称未确认） | 2026-09 | 仅限防御方 |

参考量级：Anthropic 称 Mythos Preview 在 CyberGym 上得分 83.1%（Opus 4.6 为 66.6%），并在所有主流操作系统和浏览器中发现了数千个高危漏洞。

**含义**：最强的 cyber 能力在实验室手里，且每几个月刷新一次。个人拿到这种能力的现实方式是**申请可信访问计划**，而不是自己训练。

### 1.2 开源权重的安全特化模型

| 模型 | 来源 | 规模/基座 | 许可要点 |
|------|------|-----------|----------|
| Foundation-Sec-8B（Instruct / Reasoning） | Cisco Foundation AI | 8B，Llama-3.1 | 模型卡限制部分用途（如针对特定组织的攻击计划） |
| RedSage | Khalifa University 等 | 8B | 模型、数据、代码公开（ICLR 2026） |
| XekRung | 阿里安全 | Qwen 系 | CC BY-NC-SA 4.0，**不可商用** |

**含义**：8B 级别模型适合本地、离线、低成本的子任务（告警分诊、日志解析、分类），和前沿门控模型不是一个档次。商用前先看许可证。

### 1.3 产品公司

- **XBOW**：自主渗透测试，2025 年登上 HackerOne 美国榜首；2026-03 完成 1.2 亿美元 C 轮，估值超 10 亿美元。
- **AISLE**：据报道发现了 2026 年 1 月 OpenSSL 安全公告中的全部 12 个 0-day。
- **Unit 42 NOVA**（Palo Alto）：自称两个月内在约 4,000 个开源项目中发现 14,000 多个新漏洞（厂商数字）。
- **Hacktron AI**：被归功于 CVE-2026-1731（BeyondTrust PRA 未授权命令注入）。

**含义**：“通用自动找漏洞”赛道已有资本密集、领先的玩家。

### 1.4 副作用：报告泛滥，“确认”变成瓶颈

- curl 于 2026 年 1 月底结束漏洞赏金计划。
- HackerOne 的 Internet Bug Bounty 于 2026-03-27 暂停新提交。
- GitHub 对 2026-07-27 起提交的报告改为两档制。
- Wireshark 接受 AI 辅助的报告，但拒绝 Agent 直接提交的报告。
- 一份对 53 个项目政策的统计显示：没有项目完全禁止 AI 辅助报告，但 36 个（67.9%）对此没有任何规定，关键在于“有没有人为这份报告负责”。

**含义**：前一份文档里的“路径 C：增强型 Bug Bounty”难度明显上升。没有人工确认、没有可靠 PoC 的 Agent 报告基本没有价值，还可能损害账号信誉。反过来，**“帮维护者把报告筛干净”本身成了需求**。

### 1.5 训练方在买什么：从“数据”转向“环境”

- RL 环境/任务的公开报价：多数在**每个任务 200–2,000 美元**，极少数复杂任务可到 2 万美元（来自 2025 年底到 2026 年初的访谈和报道，没有官方价目）。
- 买方的核心要求是**验证器不能被钻空子**（“a verifier that can't be gamed is the product”），签约前会测试 reward hacking；比起几个展示用的任务，更看重**数百个定义清晰、互不相同的任务**。
- 已有数据/环境供应商（如 Collinear AI）把 cybersecurity 列为供应方向之一。
- 学术上的参照：**CyberForge**（2026-08）向真实 C/C++ 仓库**注入**漏洞来生成训练实例。验证方式是：注入后项目原有单元测试仍全部通过，生成的 PoV 在注入版本触发、在干净版本不触发。共 1,034 个实例，覆盖 80 个项目、63 类 CWE；用这些实例上采集的 Agent 轨迹做微调，在 SEC-bench 补丁修复上提升 3.3–14.7 分。

**含义**：前两份文档的思路（带验证信号的过程数据）在 cyber 方向的最佳载体，是**带验证器的任务/环境**，轨迹是它的副产品。

## 2. 方向判断

| 方向 | 建议 | 理由 |
|------|------|------|
| 自训 cyber 基座模型 | 不做 | 前沿实验室门控领先、迭代快、资本密集 |
| 微调小模型（8B 级） | 仅限特定场景 | 私有化、离线、成本敏感的子任务；注意基座许可 |
| 通用“自动找漏洞” Agent | 不建议正面竞争 | XBOW、AISLE、前沿实验室已在做；发现本身已泛滥 |
| **可验证的 cyber 任务/环境** | **推荐** | 训练方正在买；验证器是壁垒；与“数据变现”思路一致 |
| **验证与分诊层** | **推荐** | 维护者和赏金平台被报告淹没；同一套验证器可复用 |
| 垂直场景 Agent | 可选 | 选前沿模型覆盖不到的地方：固件/嵌入式、ICS/OT、机器人、内网/离线部署 |

## 3. 一个 cyber 特化 Agent 的结构

特化能力主要来自下面这套 harness，而不是权重：

```
任务（目标仓库/服务 + 目标描述）
   │
   ▼
模型路由
   ├─ 前沿 cyber 模型（经可信访问计划）：推理、利用、修复
   └─ 小模型（如 Foundation-Sec-8B）：本地分诊、分类、日志
   │
   ▼
工具层：代码检索、构建、fuzzer（libFuzzer / AFL++）、
        sanitizer（ASan / UBSan）、调试器（gdb）、静态分析（CodeQL / Semgrep）
   │
   ▼
隔离沙箱：容器、默认断网、可快照回滚
   │
   ▼
验证器（核心）
   ├─ PoC 在漏洞版本触发、在修复版本不触发
   ├─ 打补丁后原有测试全部通过
   └─ Web/服务类：拿到预置的 canary / flag
   │
   ▼
轨迹记录：推理摘要、工具调用、失败与重试、验证结果、人工结论
   │
   ▼
人工审核闸门（任何对外披露或提交前必须经过）
```

**同一个验证器被用了三次**：让 Agent 的结果可信；让轨迹数据有价值；本身就是 RL 环境这个“产品”的核心。

## 4. 推荐切入路线

### 阶段 1（2–4 周）：做出第一批可验证任务
1. 选 1–2 个**许可宽松**、已接入 OSS-Fuzz 的 C/C++ 项目（自带构建脚本和 fuzz harness，起步成本低）。
2. 生成任务的两种来源：
   - **漏洞注入**（CyberForge 式）：新鲜、未公开，不会和训练数据重叠，适合卖给训练方。
   - **历史 CVE 复现**：适合做评测和练手，但已公开，训练方价值低（数据污染）。
3. 每个任务的交付物：Docker 镜像 + 漏洞版本 + 干净版本 + PoV + 验证脚本 + 元数据（CWE、难度、预期解法）。

### 阶段 2：用 Agent 跑任务，并攻击自己的验证器
1. 用不同模型跑这些任务，记录轨迹和验证结果，统计通过率，剔除过易或无解的任务。
2. 专门测试 reward hacking：Agent 能否通过删测试、硬编码输出、修改验证脚本等方式“通过”。验证器扛不住，任务就卖不出去。

### 阶段 3：选变现方向
- **任务/环境授权**：直接对接实验室，或通过环境/数据供应商。
- **验证与分诊服务**：同一套验证器，为开源维护者或企业复现、去重、确认收到的漏洞报告。
- **申请更强模型的访问**：Anthropic Cyber Verification Program、Claude for Open Source（维护者）、OpenAI Trusted Access for Cyber。

## 5. 这个方向特有的风险

- **授权**：只测试自己有权限的目标。未授权扫描或渗透他人系统在多数司法辖区违法。
- **模型服务条款**：前沿模型的条款通常限制把输出用于训练竞争模型。**用 Claude / GPT 跑出来的轨迹卖给其他 AI 实验室做训练数据，可能违约**，出售前要逐条核对。自己写的环境、注入的漏洞、验证器，权利更清楚。
- **未公开漏洞的流转**：如果在中国境内，《网络产品安全漏洞管理规定》（2021-09-01 施行）第九条限制向产品提供者以外的境外组织或个人提供未公开漏洞信息，第四条禁止非法收集、出售、发布漏洞信息。把真实 0-day 数据卖给境外实验室风险很高。人为注入的漏洞和真实未公开漏洞性质不同，但仍建议咨询律师。其他司法辖区还需留意入侵软件相关的出口管制。
- **负责任披露**：发现真实漏洞先走厂商/维护者渠道，修复后再考虑进入数据集。
- **双重用途**：可用的利用代码和自动化攻击能力不要公开发布。
- **赏金平台规则**：越来越多项目要求人工确认，拒绝 Agent 直接提交。

## 6. 对前两份文档的修正建议

- **路径 A 的“$20,000–$750,000”**：没找到出处。能找到的最接近说法是数据经纪商自述的“一般企业数据授权多在 10 万–200 万美元”，并不针对安全数据。建议删除，或改成注明来源的说法。
- **路径 C（增强型 Bug Bounty）**：难度上调，前提改为“人工确认 + 可复现 PoC”。
- **新增资产类型**：“带验证器的任务/环境”，按任务计价，比静态数据集更贴合 2026 年的买方需求。

## 来源

**前沿 cyber 模型**
- [Anthropic：Project Glasswing](https://www.anthropic.com/glasswing)
- [Simon Willison：OpenAI Trusted Access / GPT-5.4-Cyber](https://simonwillison.net/2026/apr/14/trusted-access-openai)
- [Hackread：OpenAI Launches GPT-5.4-Cyber](https://hackread.com/openai-gpt-5-4-cyber-boost-defensive-cybersecurity/)
- [Semafor：OpenAI begins phased rollout of GPT-6 Astra](https://semafor.com/article/09/03/2026/openai-begins-phased-rollout-of-gpt-6-astra-model)
- [KSL / Reuters：OpenAI to preview GPT-6 Cyber](https://www.ksl.com/article/51628388/openai-to-preview-gpt-6-cyber-within-days-fortune-reports)
- [The Neuron：2026-09-01 AI 动态汇总](https://theneuron.ai/digest/everything-that-happened-in-ai-today-tuesday-september-1-2026/)（Mythos 5.1，二手汇总）
- [2026 年 9 月模型更新汇总](https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html)（Gemini Cyber 变体，二手汇总，名称不一致）

**开源安全模型**
- [Hugging Face：foundation-sec-8b-instruct](https://huggingface.co/fdtn-ai/foundation-sec-8b-instruct)
- [Converge Digest：Cisco security-tuned reasoning LLM](https://convergedigest.com/cisco-unveils-security-tuned-reasoning-llm-for-cyber-defense/?amp=1)
- [RedSage 发布报道](https://menastartupdigest.com/?p=28571)
- [XekRung 技术报告（arXiv 2605.00072）](https://arxiv.org/html/2605.00072v1)

**产品与 AI 漏洞发现规模**
- [XBOW：C 轮融资](https://xbow.com/news/xbow-raises-120m-to-scale)
- [XBOW：HackerOne 榜首与 B 轮](https://xbow.com/blog/series-b)
- [CSA：自主漏洞猎人时代的协调披露改革](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-vulnerability-disclosure-policy-reform/)
- [IBM X-Force：AI vulnerability discovery](https://www.ibm.com/think/x-force/ai-vulnerability-discovery)
- [Google Cloud：AI 时代的漏洞发现与利用趋势](https://cloud.google.com/blog/topics/threat-intelligence/vulnerability-discovery-and-exploitation-trends-in-the-ai-era)

**漏洞赏金与 AI 报告**
- [TechRadar：curl 结束赏金计划](https://www.techradar.com/pro/security/curl-will-stop-bug-bounties-program-due-to-avalanche-of-ai-slop)
- [TechRadar：GitHub 调整赏金计划](https://techradar.com/pro/security/github-restructures-bug-bounty-program-following-flood-of-ai-generated-reports)
- [Computing：赏金平台应对 AI 垃圾报告](https://www.computing.co.uk/news/2026/security/bug-bounty-platforms-battle-ai-slop)
- [Help Net Security：维护者被 AI 垃圾报告淹没](https://www.helpnetsecurity.com/2026/05/18/problems-with-ai-assisted-vulnerability-research/)
- [Stingrai：AI 生成漏洞报告政策统计](https://www.stingrai.io/blog/ai-generated-vulnerability-report-policies-census)
- [Decryption Digest：HackerOne 与 Bugcrowd 的调整](https://www.decryptiondigest.com/blog/bug-bounty-programs-ai-era-hackerone-bugcrowd-2026)

**训练数据与 RL 环境市场**
- [Troveo：How to Sell RL Environments to AI Labs](https://www.troveo.ai/resources/sell-rl-environments)
- [CleverX：Companies Building RL Environments in 2026](https://cleverx.com/blog/companies-building-rl-environments-2026/)
- [SemiAnalysis：RL Environments and RL for Science](https://newsletter.semianalysis.com/p/rl-environments-and-rl-for-science)
- [DataMining Insights：Silicon Valley Stops Buying Data, Starts Buying Worlds](https://www.datamining.cloud/en/insights/2026-10-24-rl-environments.html)
- [CyberForge（arXiv 2608.06471）](https://arxiv.org/abs/2608.06471)
- [CyberFactory（arXiv 2608.23181）](https://arxiv.org/pdf/2608.23181)
- [AI Training Data Broker](https://aitrainingdatabroker.com/)（经纪商自述价格）

**法规**
- [网信办：网络产品安全漏洞管理规定](https://www.cac.gov.cn/2021-07/13/c_1627761607640342.htm)
