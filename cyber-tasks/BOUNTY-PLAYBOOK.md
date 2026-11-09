# Bug Bounty 实操清单(单人 / 业余 / 近期现金)

> 配合 [tools/](./tools) 的流水线使用。背景和路径选择见
> [../docs/cyber-specialized-ai-agent.md](../docs/cyber-specialized-ai-agent.md)。
>
> **核心打法**:打**源码可得、能本地复现**的目标,用 fuzzing 找崩溃,用
> `reproduce.py` 自动复现+最小化,交出带可复现 PoC 的报告。2026 年平台最缺的
> 就是这种"已验证"的报告。

---

## 全流程一张图

```
选目标 → 确认授权/scope → 本地 fuzzing → 复现+最小化 → 人工把关 → 写报告 → 提交 → 披露
 Step1      Step0         Step2-3         Step3        Step4     Step5    Step5   Step6
```

---

## Step 0 — 合规与授权(先做,别跳)

**未授权访问他人系统是犯罪**(日本《不正アクセス禁止法》,最高 3 年或 100 万日元)。
所以只碰下面三类目标:

- ✅ 你能合法 clone 的开源代码(在**你自己机器上**跑它自己的代码)
- ✅ 你自己的软件
- ✅ 某个赏金项目 **scope 明确覆盖**的目标(scope = 书面授权)

绝不碰:不在 scope 内的线上系统、别人的生产环境、需要绕过认证才能测的东西。

另外两条自查:
- [ ] 如果是副业:看雇佣合同有没有副業禁止 / 竞业条款。
- [ ] 本流水线(`fuzz.py` / `reproduce.py`)只在本地跑目标自己的代码,**不碰任何线上第三方系统**——风险最低,优先走这条。

---

## Step 1 — 选目标

**最契合你的:带 OSS-Fuzz harness 的开源 C/C++ 库。** 理由:源码可得、自带
fuzz 入口(省去写 harness)、内存安全 bug 多、能本地复现。

优先找这类代码:

- 解析器 / 反序列化:图片、音频、视频、字体、压缩、协议、模型文件(`.safetensors`、
  `.gguf`、`.onnx`、pickle 等)。
- AI/ML 生态的底层 C/C++ 依赖(张量库、预处理、编解码)——`huntr` 这类 AI/ML
  赏金平台正好收这些。

挑目标时的自查清单:

- [ ] 它在某个**付费**赏金项目的 scope 内(不是只给名誉的 VDP)。
- [ ] 源码能拿到,且项目**接了 OSS-Fuzz**(GitHub 里搜 `.clusterfuzzlite` 或
      `fuzz/`、`oss-fuzz` 目录;或查 google/oss-fuzz 仓库里有没有它)。
- [ ] 许可证允许你本地 clone 和测试(开源基本都行)。
- [ ] 避开已经被挖烂的超热门目标(重复率高),也避开 2026 年已关闭的项目
      (如 Google OSS 产品 VRP 已不收产品漏洞)。

> ⚠️ 平台现状会变。动手前上目标所在平台(huntr / HackerOne / Bugcrowd)**官网
> 核实**:它还收不收、赏金多少、对 AI 工具有什么要求。

---

## Step 2 — 本地装 fuzzing 引擎

这台云机器没装 libFuzzer / AFL++ 的运行时,所以**深度 fuzzing 在你本地做**。

- **macOS**:`brew install llvm afl++`(llvm 带 clang + libFuzzer 运行时)
- **Ubuntu/Debian**:`sudo apt install clang llvm afl++`,或装
  `libclang-rt-dev` 以补齐 `-fsanitize=fuzzer,address` 的运行时库。

验证 libFuzzer 能用(应能编译并跑起来):

```bash
cat > t.c <<'EOF'
#include <stdint.h>
#include <stddef.h>
int LLVMFuzzerTestOneInput(const uint8_t*d,size_t s){if(s>2&&d[0]=='F'&&d[1]=='U'&&d[2]=='Z')__builtin_trap();return 0;}
EOF
clang -fsanitize=fuzzer,address -O1 t.c -o t && ./t -max_total_time=5
```

---

## Step 3 — 跑流水线

### 3a. 用目标自带的 OSS-Fuzz harness(推荐)

多数接了 OSS-Fuzz 的项目有一个 `LLVMFuzzerTestOneInput` 入口。直接 libFuzzer:

```bash
clang -fsanitize=fuzzer,address,undefined -O1 -g \
    -I<目标include> <目标源文件...> <目标的fuzz_harness.c> -o fuzz_target
./fuzz_target -max_total_time=600 -artifact_prefix=crashes/
```

崩溃会落在 `crashes/`。然后把每个崩溃喂给复现器:

```bash
python3 cyber-tasks/tools/reproduce.py \
    --target <目标源文件.c> \
    --driver <能读文件并调用入口的driver.c> \
    --include <目标include> \
    --input crashes/crash-xxxx --out reports/xxxx --minimize
```

### 3b. 或用本仓库的 `fuzz.py` 串起来

```bash
cd cyber-tasks/tools
# 运行时齐全时用 libfuzzer 引擎:
python3 fuzz.py --engine libfuzzer \
    --target <目标.c> --fuzz-harness <harness.c> --include <inc> \
    --seconds 600
# 只想冒烟 / 没运行时时用内置引擎(coverage-blind,只抓浅层 bug):
python3 fuzz.py --target <目标.c> --driver <driver.c> --include <inc> \
    --seconds 60 --reproduce
```

产物:`findings/crashes/`(每个唯一签名一个输入)、
`findings/reports/<sig>/`(`report.md` + `poc.bin` + `trajectory.jsonl`)。

> 深度靠 libFuzzer/AFL++ 的覆盖率引导。内置引擎没有覆盖率反馈,只适合浅层 bug
> 和冒烟测试。

---

## Step 4 — 人工把关(最关键,工具替不了)

报告草稿顶部那句 banner 不是摆设。提交前你**必须**逐条确认:

- [ ] **可达性**:这个崩溃能不能被**真实的、攻击者可控的输入**触发?(不只是你的
      driver 喂进去。确认漏洞函数在产品里真的处理外部数据。)
- [ ] **去重**:项目的 issue / 已知 CVE / 赏金历史里是不是已经报过了?
- [ ] **严重性**:是单纯崩溃(DoS),还是可控的越界写(可能更严重)?老实评估,
      别夸大。
- [ ] **稳定复现**:`poc.bin` 在**干净 clone + 文档里的 build 命令**下能稳定重现。
- [ ] **去敏**:PoC 和日志里没有你本地的密钥、路径、无关信息。

过不了这几条的,别交——交了只会掉信誉分。

---

## Step 5 — 写报告 & 提交

`reproduce.py` 生成的 `report.md` 已经有:崩溃类型、疑似 CWE、sanitizer 片段、
复现步骤、最小化 PoC。你补上:

- [ ] 真实影响分析(Step 4 想清楚的那些)。
- [ ] 一个候选补丁(有的话)——带修复建议的报告赏金更高。
- [ ] 删掉 banner,按目标项目的格式整理。

**提交前查该项目的 AI 工具规则**(2026 年平台都在收紧):

- Bugcrowd:对"AI 生成但未充分验证"的提交会**封号 30 天**;托管项目要实名。
- HackerOne:你要**对 AI 辅助的发现负责**,禁止大批量未验证提交;部分项目要求
      披露用了 AI 工具。
- 有的项目(如 Wireshark)**禁止 Agent 直接提交**,但接受"有人验证过"的 AI 辅助报告。

原则一句话:**可以用 AI 辅助,但必须你亲自验证、你为报告负责、该披露就披露。**

---

## Step 6 — 披露礼仪

- [ ] 先走项目/平台的**私密**渠道报告,给维护者修复时间(常见 90 天禁言期)。
- [ ] 修复发布前**不要**公开漏洞细节或可用的利用代码。
- [ ] 可以申请 CVE(huntr 等会帮你走)。
- [ ] 维护者沟通保持礼貌、配合——赏金圈子小,信誉是长期资产。

---

## 现实预期

- 业余投入,**第一笔有效赏金大概率要几周到几个月**。会遇到重复、无效、石沉大海。
- **第一个里程碑不是赚多少,是跑通一次完整闭环**:
  选 in-scope 目标 → fuzz 出候选 → 复现+最小化 → 交报告 → 拿到平台裁定
  (valid / duplicate / N/A 都算数据,都能让你校准)。
- 每次挖洞 `trajectory.jsonl` 都会留档。中标的那些 = 你的作品集和信誉,也是
  将来"卖验证数据"那条路的原料——近期现金和中期资产不冲突。

## 常见坑

- ❌ 去挤黑盒 Web 大项目:人多、slop 泛滥,你的工程优势用不上。
- ❌ 交没复现的"疑似漏洞":2026 年这是掉信誉甚至封号的主因。
- ❌ 夸大严重性:三查(triage)一眼看穿,降低你后续报告的可信度。
- ❌ 碰 scope 外的目标:法律风险,一票否决。
- ❌ 只靠内置 fuzzer 找深度 bug:它 coverage-blind,深洞得靠 libFuzzer/AFL++。
