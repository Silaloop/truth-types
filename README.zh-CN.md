<div align="center">

# truth-types

**它管「谁确认的」，不管「对不对」。**

给 AI 产出加一层**证据等级**：AI 写的永远停在最低级 `derived`，只有人能升格、一次一级，
且每一次尝试（包括被拒绝的）都写进**审计留痕** —— 于是「这句话怎么变成结论的」是一条查询，
不是一场考古。

四个状态 —— `derived`、`declared`、`canonical`、`opaque` —— 配人类专属的提升规则、最短板继承，
以及每次尝试一行审计记录（无论接受还是拒绝）。

[![CI](../../actions/workflows/ci.yml/badge.svg?branch=main)](../../actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)
[![Tests: 28 passing](https://img.shields.io/badge/tests-28%20passing-brightgreen.svg)](tests/test_truth_types.py)

[规范 SPEC.md](SPEC.md) · [变更日志 CHANGELOG.md](CHANGELOG.md) · [示例](examples/) · [English](README.md)

*第一个徽章是仓库的 GitHub Actions 工作流徽章：仓库公开、且 CI 在 `main` 上跑过一次之后，
它会自动开始报状态（Python 3.10–3.13 矩阵）。其余数字徽章是 shields.io 静态徽章 ——
v0.1.0 的测试数为 28，由 CI 与 `python -m pytest -q` 双重复核；尚未发布到包索引（见
[安装](#安装)）。*

</div>

## 它防住什么

在一条 Agent 流水线里，模型产出与人已确认的内容之间没有类型边界：**未审文本一次复制粘贴就成了
「事实」**（原文：unreviewed text becomes a trusted fact by copy-and-paste），事后谁也答不出
*谁、在哪一层、基于什么证据确认过*。

本库补上这个缺失字段：每个知识对象携带一个**证据等级**，四个等级构成偏序
（`derived ⊑ declared ⊑ canonical`，`opaque` 在格之外），并且

- **只有人**能提升，且**一次只能升一级**；
- 子记录**不得高于最弱父记录**；
- 每一次尝试 —— 无论接受还是拒绝 —— 都追加一行 **JSONL 审计记录**。

于是「这条怎么成为结论的」是一条查询，而不是一场考古。整个机制四行就能看完：

```python
reg.promote("n1", TruthType.CANONICAL, ActorKind.AI)
# -> {"ok": False, "reason": "only humans may promote (AI output is always derived)"}
```

这次拒绝被**记下来**、而不是被丢掉 —— 被拦的提升是审计流里可查的一行（`blocked_promotions()`）。
「这条到底审没审」于是成了事实，而不是争论。

三个中文团队每天都在发生的场景（本库一视同仁）：

| 场景 | 今天的样子 | 有了证据等级之后 |
|:--|:--|:--|
| 研报 / 咨询报告 | AI 生成的段落被贴进对外交付物，三个月后客户问「这句哪儿来的」，只能翻聊天记录 | 追责变成查询：谁在何时把这条从 `derived` 提到 `declared`，一行看得见 |
| 合同 / 条款抽取 | 模型抽出的条款结论与人工核对过的结论，在系统里长得一模一样 | 类型随陈述走，复制粘贴不会让 `derived` 变成 `canonical` |
| 客服知识库 | 模型总结的答案被当作客户口径直接引用，没人记得谁批过 | 只有人能把它升到可对外的等级，且必须留痕 |

一句话定位，读完这行就可以决定要不要继续看：它**从不读你的 `statement`**（它管评审状态，不管内容
对错）；它**不是**数据质量工具、不是 schema；它也**不做身份认证** —— `actor_kind` 由调用方申报，
所以才有下面两节。

## 30 秒看到效果（不用安装）

示例脚本会自己把仓库根目录加进 `sys.path`，所以**有检出目录就能跑** —— 纯标准库、无需联网、无需起服务：

```bash
python examples/02_blocked_promotions.py
```

它会故意触发全部五类拒绝并打印出来。下面是真实输出（已省略中间的分组明细；脚本第一行会打印它新建的
临时目录，末尾两行是汇总）：

```text
attempted promotions
  REJECTED  ai_note     -> declared  by ai     (AI may never promote)
            reason: only humans may promote (AI output is always derived)
  REJECTED  ai_note     -> canonical by human  (level skipping: derived -> canonical)
            reason: level skipping is forbidden: no direct promotion edge derived→canonical
  REJECTED  human_note  -> declared  by human  (downgrading: canonical -> declared)
            reason: downgrading is forbidden
  REJECTED  raw_dump    -> declared  by human  (opaque is isolated)
            reason: opaque is isolated: no transition into or out of the lattice
  REJECTED  no_such_eid -> declared  by human  (unknown eid)
            reason: eid not found

blocked_promotions(): 5 rejected attempt(s)
audit trail: 10 entries total (every attempt, accepted or rejected)
```

五条被拒、十条审计行、零运行时依赖。被拒记录按**结构化字段**（`from_type` → `to_type`）分组 ——
界面文案（`reason` / `detail`）只是表现层，不属于接口契约。

## 谁手里有 `promote`

隔离保证以 `actor_kind` 如实申报为前提：本库强制的是**契约**，不是**身份**
（[SPEC §4.2](SPEC.md)、[§4.6.1](SPEC.md)）。这件事不该靠承诺解决，而该靠**部署形态**收口：

| 进程 | 允许调用什么 |
|:--|:--|
| 生产侧 / Agent 流水线 | `add()` 与 `check_on_screen()` —— 拿到的只是注册表句柄 |
| 人类审阅面（评审界面、CLI、工单动作） | `promote()` —— 除此之外谁都不给 |

- **代码层（v0.1）**：可以把提升能力物理移除后再交出去 ——
  `TruthTypeRegistry(log_dir=..., allow_promote=False)`（[SPEC §4.7](SPEC.md)）。此时 `promote()`
  对任何参数都返回拒绝决策对象，审计行里带 `handle: "read-only"`，而这次尝试**照样进审计流**：
  拿掉的是能力，不是记录。
- **MCP 层（v0.2）**：`truth-types-mcp` 只向 Agent 暴露 `add` 与 `check_on_screen`；
  **`promote` 刻意不经 MCP 暴露** —— 它属于人类审阅面。集成点是事件流，提升不是 Agent 工具。
- **为什么这样做**：它把「`actor_kind` 由调用方申报」从致命限制变成清晰的架构职责划分，并与
  [SPEC §8.6](SPEC.md) 的反模式清单一致（「在自动化作业里做提升」—— 作业可以**准备**一次提升，
  但不能**执行**它）。
- **它不做什么**：它不验证「这个人是谁」；这个开关是**收窄，不是管控** —— 能构造注册表的人就能构造
  一个可提升的注册表。请把可提升的那个句柄只留在人类审阅面，身份在外层由 SSO / PAM 派生后传进来
  （见下一节）。

## 在受控环境里

写给治理、风控与审计读者的四个问题 —— 每条都讲清 v0.1.0 做了什么、没做什么：

1. **身份。** `actor_kind` 由调用方申报，库内不认证（[SPEC §4.2](SPEC.md)、[§4.6.1](SPEC.md)）。
   受控部署的做法是：在外层包装里把它绑定到你们的 SSO / PAM / 服务账号边界，并让人类审阅面成为
   `promote` 的唯一写入口（见上节）。此时本库记录的是**归于该身份的一次评审动作** —— 提升到了哪一层、
   以及首次人类提升自动盖上的时间戳印记。
2. **证据保全。** 审计 JSONL 只追加，但只有在**被复制到别处**时才是防篡改可见的
   （[SPEC §9.1.16](SPEC.md)）。标准配方：按既有备份节奏把两个 JSONL 文件镜像到一次写入存储
   （S3 Object Lock / WORM 保险库 / 不可变桶）；若需要链条完整，可在复制时给每行加一个 `prev_hash`
   —— 文件本来就是每行一个 JSON 对象，`prev_hash = sha256(上一行)` 两行脚本即可，格式不变。
   留存期按你们所在监管要求执行；本库没有删除路径。
3. **数据卫生。** `statement`、`note`、`detail` 里不要放个人信息与密钥：审计流只追加、无删除
   （[SPEC §8.6](SPEC.md)）。本库从不读 `statement`，敏感正文可以留在你们自己的存储里，只用
   `source_ref` 指过去。
4. **定位。** 本库产出的是**内控级审查证据，不是监管合规认证**（[SPEC §9.2](SPEC.md)）。
   若要写进控制矩阵，可用的措辞是 *composes with* / *is one evidence source for*，
   **不要**写 "satisfies" 或 "compliant with"。站得住的对应关系是：人类专属提升 ↔ 人机权责边界控制
   （AI 不能持有问责权）；每一次尝试（含被拒）都留痕 ↔ 记录保存类要求的**证据来源之一**；
   `check_on_screen()` ↔ 「可对外发布」的条件闸。

## 四行边界（先看这里，再决定怎么用）

| 边界 | 事实 | 你该怎么做 |
|:--|:--|:--|
| **`actor_kind` 不是身份认证** | 由调用方申报，本库不认证（[SPEC §4.2](SPEC.md)、[§4.6.1](SPEC.md)） | `promote` 只留在人类审阅面；用 `allow_promote=False` 把能力从 Agent 进程里移除；身份在外层由 SSO / PAM 派生 |
| **不可撤回** | 禁降级 + `opaque` 在格之外，错误陈述会留在历史里（[SPEC §8.5](SPEC.md)） | 更正用追加：新建一条更正记录，同时引用错的与对的，历史保持完整可读 |
| **单机 JSONL** | 无锁、无轮转、无写协调；时间戳为本地秒级、无时区（[SPEC §9.1](SPEC.md)） | 每个副本各自一个日志目录，读取时合并（追加式文件，合并＝拼接 + 过滤）；要当证据就镜像到 WORM / 对象锁 |
| **B1：AI 记录不能挂到更强的父记录下** | 强制降级先于最短板比较，所以「AI 摘要挂到人工 `declared` 父记录」会被拒 —— 即使 AI 老老实实只请求 `derived`（[SPEC §3.7](SPEC.md)） | 这是 v0 的边界、不是 bug。v0 可行写法：由人建这条链接记录；或把机器笔记存为带 `source_ref` 的**根记录** |

## 安装

v0.1.0 **尚未发布到包索引**。分发物已经 release-ready —— wheel 与 sdist 构建通过、`twine check`
通过（均在 CI 里跑）—— 发布进行中；在发布落地前，从当前检出目录安装：

```bash
cd truth-types
python -m venv .venv && source .venv/bin/activate
pip install -e .                # 运行时：零依赖
pip install -e ".[dev]"         # 可选：pytest + pyright
```

跑示例无需安装 —— 每个脚本自行把仓库根目录加进 `sys.path`。MCP 分发层见
[路线图](#路线图)。

## 五分钟上手

把下面这段存成仓库根目录下的 `quickstart.py` 再运行即可。注释里写的是每次调用的真实返回值；
同一条生命周期也脚本化在 [`examples/01_quickstart.py`](examples/01_quickstart.py) 中。
示例里的中文语句可以直接换成你自己的场景（研报结论 / 合同条款 / 客服答案）—— 本库从不读
`statement`：

```python
from truth_types import ActorKind, EpistemicRecord, TruthType, TruthTypeRegistry

# 1. 注册表由两个 JSONL 文件支撑：记录 + 只增不删的审计流
reg = TruthTypeRegistry(log_dir="./audit")        # 或省略，用 TRUTH_TYPES_AUDIT_PATH

# 2. AI 产出进入流水线；请求 canonical 会被强制降级 —— AI 产出恒为 `derived`
reg.add(EpistemicRecord(
    eid="n1",
    truth_type=TruthType.CANONICAL,               # 请求值
    actor_kind=ActorKind.AI,                      # ……但 AI 产出只能是 `derived`
    statement="研报结论：渠道库存环比增长 18%",       # 中文语句同样可以（本库从不读它）
    source_ref="https://example.com/filing#p42",  # 来源标识：指回你的原文
))
# -> {"ok": True, "reason": "created"}            这次强制降级以 "ai_coerce" 留痕

# 3. 人类评审确认一次 -> declared
reg.promote("n1", TruthType.DECLARED, ActorKind.HUMAN, note="对照年报核对过")
# -> {"ok": True}

# 4. Agent 提升被拒 —— 拒绝本身也留痕
reg.promote("n1", TruthType.CANONICAL, ActorKind.AI)
# -> {"ok": False, "reason": "only humans may promote (AI output is always derived)"}

# 5. 人类二审升到 canonical —— 每次只能升一级，不能跳级
reg.promote("n1", TruthType.CANONICAL, ActorKind.HUMAN)
# -> {"ok": True}

# 6. 事后可查每一次尝试
reg.blocked_promotions()                          # -> [ {…, "action": "promote", "ok": False} ]

# 7. 引用链：子记录不得高于最弱父记录（最短板规则）
reg.add(EpistemicRecord(eid="s1", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                        statement="FY25 年报第 42 页"))
reg.add(EpistemicRecord(eid="c1", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                        parents=("s1",), statement="库存环比 +18%"))
# -> 两条都 {"ok": True}  （c1 引用 s1；declared == min(parents)）

reg.add(EpistemicRecord(eid="bad", truth_type=TruthType.CANONICAL, actor_kind=ActorKind.HUMAN,
                        parents=("s1",)))
# -> {"ok": False, "reason": …}  （创建即跳级：canonical ≠ 最短板 declared）

# 8. 上屏闸门：结论需 truth_type >= declared 且 parents 非空
reg.check_on_screen("c1")    # -> {"ok": True, "reason": "ok"}
reg.check_on_screen("n1")    # -> {"ok": False, "reason": …}   （没有记录父记录）
```

接着运行它和测试套件 —— 无需安装、无需联网：

```bash
python quickstart.py         # 上面的整条生命周期
python -m pytest -q          # 20 passed
```

> **第一次集成就会撞上的边界 B1。** AI 创建的记录**不能引用更强的父记录**：强制降级先于最短板比较，
> 所以把机器笔记挂到人类 `declared` 陈述下面会被拒 —— 即使它老老实实只请求 `derived`
> （[SPEC §3.7](SPEC.md)）。这是 v0 的边界，不是 bug，而这恰好是 RAG 管线最常见的第一个动作。
> v0 的可行写法：**由人**建这条链接记录；或把机器笔记存为带 `source_ref` 的**根记录**。

## 示例

[`examples/`](examples/) 下三个可运行脚本 —— 纯标准库、无需安装。每个都用临时的全新目录存放日志
文件，并把过程打印出来：

| 脚本 | 演示内容 |
|:--|:--|
| [`examples/01_quickstart.py`](examples/01_quickstart.py) | 全生命周期：AI 产出被强制为 `derived` → 人升为 `declared` → AI 提升被拒 → 人二审升为 `canonical`，以及被拦记录查询 |
| [`examples/02_blocked_promotions.py`](examples/02_blocked_promotions.py) | 拒绝面：故意触发全部五类拒绝（AI 提升、跳级、降级、`opaque` 迁移、未知 `eid`）并打印拦截清单，按结构化字段分组而非按消息文本 |
| [`examples/03_audit_query.py`](examples/03_audit_query.py) | 审计查询：只用标准库把原始 `truth_types_audit.jsonl` 读回来，做汇总（按 action、按结果、按 `eid` 的历史），并与 `blocked_promotions()` / `audit_entries()` 对照 |

```bash
python examples/01_quickstart.py
python examples/02_blocked_promotions.py
python examples/03_audit_query.py
```

## 核心概念

### 四个证据等级

| 类型（原词不译） | 格中位置 | 谁能产出 | 中文含义 |
|:--|:--|:--|:--|
| `derived` | 底 | AI 或人 | 机器派生；尚无人确认（AI 产出恒在此级） |
| `declared` | 中 | 人提升（自 `derived`） | 人已在案声明（可理解为「人签过字的草稿级」） |
| `canonical` | 顶 | 人提升（自 `declared`） | 人已确认，可作为结论被消费（「定稿可引用」） |
| `opaque` | 格之外 | —— | 隔离：不得被引用，也不得被提升（「封存不建模」） |

`opaque` 是存放决策，不是第四级台阶：被刻意「不建模」的材料，与「已建模且经过若干评审」的材料
不在同一根轴上（[SPEC §2.4](SPEC.md)）。

### 提升规则（机器强制、失败即拒）

| # | 规则 | 强制方式 |
|:--|:--|:--|
| 1 | 只有人能提升 | `AI` 提升被拒并留痕 |
| 2 | 不得跳级 | 只存在 `derived→declared` 与 `declared→canonical` 两条边（`PROMOTION_EDGES`） |
| 3 | 不得降级 | 目标必须严格高于当前 |
| 4 | `opaque` 隔离 | 永不可提升，永不作为父记录 |
| 5 | 创建即取 `min(parents)`（最短板） | 子记录不得高于最弱父记录 |
| 6 | 上屏闸门 | 结论需 `truth_type >= declared` **且** `parents` 非空 |

每一次 `add()` / `promote()` 尝试 —— 无论接受或拒绝 —— 都追加一行审计记录，这正是被拦迁移事后可
复查的原因。

### 隔离保证

**由 AI 产生的记录，只有在经过至少两次归于人类行为者的提升之后，才可能取得 `canonical`，且必须
经过可观测的中间态 `declared`**（[SPEC §4.1](SPEC.md)）—— 边集是显式枚举而非计算得来，因此任何
代码路径上都不存在那条捷径。该保证以 `actor_kind` 如实申报为前提：本库强制的是**契约**，不是
**身份**（[SPEC §4.2](SPEC.md)、[§4.6](SPEC.md)）。收口这件事是部署问题，做法见
[谁手里有 `promote`](#谁手里有-promote)。

## 与相邻工具的关系

每条一句 —— 它们回答的是不同问题，本库不让其中任何一个变得多余。

| 替代方案 | 它解决什么 | 与 truth-types 的关系 |
|:--|:--|:--|
| 审批流（Airflow 审批节点、MLflow 阶段迁移、分支保护） | 把关一次部署或一次合并 —— 对**系统**的变更 | 本库把关的是一条**陈述**，而且状态随陈述走进每一份下游文档，包括被人手工粘贴进去的那些。那些工具管发布，本库管「这句话能不能说出口」。 |
| 自建的 `reviewed: true` 布尔列（或自家状态枚举） | 标记「看过了」 | 布尔值没有序、没有合法迁移集、也没有「被拒的那次尝试」的记录。在这里，被拒的尝试就是你能查到的那一行；等级不经记录在案的人类动作无法移动。 |
| `confidence` 分数字段（`"confidence": "high"`） | 表达「谁有多相信这条陈述」 | 自由文本分数没有偏序、没有合法迁移集、也没有「谁设的值」的记录；本库补上序、边集与逐次审计行。分数管信念，证据等级管地位。 |
| JSON Schema / 类型化模型 | 校验记录的**形状** —— 有哪些键、允许哪些取值 | Schema 能要求 `truth_type ∈ {derived, declared, canonical, opaque}`；它无法表达「谁能改值」「只存在两条边」「被拒的尝试怎么处理」。Schema 管形状，本库管迁移。 |
| 人工评审（清单、「不确定的要标注」） | 指示人或模型小心行事 | 指示不是约束：违规不留痕，事后无法机械检出。这里每次尝试都带行为者与原因，于是「有没有被跳过评审」是查询结果，而不是争论。 |
| 内容安全护栏、数据目录 | 判断文本**是否可存在**；追踪数据集、表与作业 | 护栏不表达「这条陈述被信任到什么程度」，目录也不表达单条陈述的状态。truth-types 一次只管一条陈述的评审状态。 |

**中文团队常见做法**（下面这些你在内部大概已经有了 —— 本库不是来替代它们的）：

| 你已经在用的 | 它解决什么 | 与 truth-types 的关系 |
|:--|:--|:--|
| LangSmith / Langfuse 的 trace | 每次 run 的链路、耗时与分数 | 它们记录「跑过什么、得分多少」；本库记录「这句话被谁确认到哪一级」。前者是过程记录，后者是状态，状态还能随陈述走进下游文档。 |
| Dify 的人工标注 / 审核节点 | 标注数据集与流程节点 | 标注作用在样本上，标完就停在平台里；本库的状态挂在对象上，被复制粘贴也不会变。 |
| RAG 的 citation 展示 | 答案指向来源 | citation 回答「这句话的出处」，本库回答「这句话被确认到哪一级、谁确认的」。两者可以同时用：出处给你 `source_ref`，等级给你发布闸。 |
| 内部人工审核流（群里确认、OA 审批） | 人确实审了 | 审完的结论和没审的结论在系统里长得一模一样，而且事后查不到。本库把它们区分开并留痕，让「审过了」从口头记忆变成一条查询。 |
| 血缘工具（MLflow tracking、DVC、OpenLineage） | 产物从哪来 | 血缘指向**上游**（输入、运行、版本）；本库管**这条陈述自己的状态** —— 它能变成什么，而不是它从哪来。 |
| 动作闸 / 人工介入点（LangGraph interrupt、Agents SDK 护栏） | 某个**动作**要不要停下来等批准 | 动作闸管「做」，本库管「说」。一个过了动作审核的产出，在有人确认这句话本身之前，仍然是 `derived`。 |
| 策略引擎（OPA、Cedar） | 这个主体有没有权限调这个操作 | 组合关系：策略引擎决定「谁能调 `promote()`」，本库决定「到底存在哪几条合法迁移」—— 且每次尝试（含被拒）都留痕。 |
| 证据充足性检查 / 动作防火墙（claim-guard 类库） | 证据够不够、动作风险大不大 | 充足性与合法性是两道检查：前者审**输入**，本库定**输出的状态**，并把拒绝留在案上。 |

一句话概括这个位置：上面这些**大多是记录**（记录发生了什么），本库是**上锁 + 留痕**（不让状态被
悄悄移动，且每次尝试都留痕）。它们是互补关系，不是替代关系。

另外：本库**不是治理平台、不卖订阅、不替代你已采购的任何平台** —— Apache-2.0 零依赖，无需采购流程即可在现有管道里试用；审计留痕可作为你的评审/备案体系要求的**一类证据来源**，但**不承诺合规、不签认证** —— 是否满足某项要求，由该体系判断。

## 它不是什么

- **不是真值判定器。** `canonical` 的含义是「人在案确认过」，不是「正确」—— 它管「谁确认的」，
  不管「对不对」。本库从不读取 `statement` 的内容。
- **不是内容安全或策略引擎。** 它不判断陈述是否可存在；它与做这件事的组件组合使用。
- **不是权限系统、也不是 RBAC。** 它不限制谁能读；它限制哪些类型迁移合法，并把迁移记录下来。
- **不是日志审计的替代品。** 它**产出**只增不删的审计流，但该文件只有在被你另存他处时才是防篡改
  可见的 —— 没有任何机制阻止重写它，并且没有轮转、压缩或删除（[SPEC §7.7](SPEC.md)、
  [§9.1](SPEC.md)）。请把它当作既有合规体系里的一个证据源（镜像配方见
  [在受控环境里](#在受控环境里)）。
- **不是知识库、图存储或评审工作流工具。** 记录只在最短板规则的意义上构成引用图；没有遍历 API、
  没有查询语言、没有派单、队列或通知。
- **不是数据集血缘系统、也不是合规认证。** 血缘在「引用它的陈述」的上游；这里产出的证据是否满足
  某一监管要求，是那个监管体系的问题。
- **不能替代评审本身。** 它让评审成为必需且可见；它无法让评审变好。

## 已知限制（v0）

**v0 的适用面（部署包络）**：单写者、单机、一个日志目录 —— 放在发布前的批处理步骤或侧车里。
下面这份清单就是该包络的边界，均对 `0.1.0` 实证、完整表述见 [SPEC §4.6](SPEC.md) 与
[§9.1](SPEC.md)；每条先给**可用写法**，再给边界：

- **行为者身份是契约，不是管控** —— 见 [谁手里有 `promote`](#谁手里有-promote)。`actor_kind` 由
  调用方申报，不做认证；若模型驱动的代码能调用 `promote(..., ActorKind.HUMAN)`，隔离保证即失效。
  收口方式：`allow_promote=False` 加上人类专属审阅面 —— 本库让诚实的路径更省事，让不诚实的路径在
  审计流里可见。
- **更正靠追加（没有撤回）。** 写错的处理方式是新建一条更正记录并同时引用错的与对的，历史保持可读
  （[SPEC §8.5](SPEC.md)）。边界：既有记录无法被撤销 —— 禁降级 + `opaque` 在格之外，错误陈述会留在
  历史里。
- **时间戳是本地挂钟、每次尝试一行、秒级。** 这足够给单个日志目录内的事件排序，也足够在该目录内算
  评审时延（[SPEC §8.3](SPEC.md)，“Time to promote”）。边界：无时区偏移、不是跨主机时钟 —— 合并多个
  目录时请按你自己的入库字段排序（v1 会加带偏移的 UTC）。
- **一个目录一个写者。** 文件是追加式 JSONL，所以合并视图＝拼接 + 过滤，永远不用改写；每目录单写者
  时，审计行顺序是有意义的。边界：无锁、无写协调，两个进程写同一目录不会被串行化
  （[SPEC §9.1.11](SPEC.md)）。请给每个副本各自的目录。
- **体积与轮转：** 文件无界增长 —— 没有轮转、没有压缩、没有上限；每次提升会追加整条记录副本。
  请为它留预算（长跑流水线的审计文件就是要送去冷存储的那部分），或等 v1 的轮转。
- **人类可以直接创建任意层级的根记录**，包括 `canonical`，且无提升历史。补偿控制是规则 6：该记录
  在补上父引用之前过不了上屏闸门。
- **除提升外没有记录修改。** `add()` 拒绝已存在的 `eid`；没有 update 也没有 delete ——
  `statement`、`note`、`source_ref` 在创建时即固定。
- **边界 B1：AI 记录不能引用更强的父记录** —— 即上文「五分钟上手」里的首集成陷阱
  （[SPEC §3.7](SPEC.md)）。
- **边界 B2：`add()` 并非处处全函数。** `opaque` 作父记录时抛 `ValueError`；其余拒绝一律是决策
  对象（`{"ok": False, "reason": …}`）。
- **加载时不重校验。** 手写的 JSONL 文件可以包含 API 会拒绝的状态（[SPEC §7.7](SPEC.md)）。
- **`verification` 与 `graduation` 是惰性字段** —— 被存储、被审计，但不被任何规则读取。
- **`source_grade` 只有规范、尚未实现**；v0 用 `source_ref` 承载来源标识（[SPEC §5.5](SPEC.md)）。
- **单机本地文件系统、一次一条陈述。** 没有远端存储、没有复制，也无法表达「一组记录被一起评审
  过」。
- **v0.1.0 尚未发布到包索引**（分发物已构建并在 CI 中检查，发布进行中），`truth-types-mcp`
  服务也不在本仓库内。

## API 一览

| 符号 | 用途 |
|:--|:--|
| `TruthTypeRegistry(log_dir=..., allow_promote=False)` | 记录（`truth_types.jsonl`）+ 审计流（`truth_types_audit.jsonl`）；`allow_promote=False` 交出的注册表 `promote()` 一律拒绝，且照样留痕 |
| `registry.add(record)` | 创建规则；返回 `{"ok", "reason", "record"?}` |
| `registry.promote(eid, target, actor, note="")` | 提升规则；返回 `{"ok", "reason"}` |
| `registry.check_on_screen(eid)` | 上屏闸门（规则 6） |
| `registry.get(eid)` | 取单条记录 |
| `registry.audit_entries()` | 完整审计流（dict 列表） |
| `registry.blocked_promotions()` | 仅被拒的提升尝试 |
| `EpistemicRecord` | `eid`、`truth_type`、`verification`、`graduation`、`actor_kind`、`parents`、`source_ref`、`attestation_ref`、`statement`、`note` + `to_dict()` / `from_dict()` |
| `check_promotion(current, target, actor)` | 纯谓词，返回 `{"allowed", "reason"}` |
| `weakest_link(types)` | `min(parents)` 辅助函数（空输入或 `opaque` 父记录时抛异常） |
| `default_log_dir()` | 由 `TRUTH_TYPES_AUDIT_PATH` 或工作目录解析日志目录 |
| `PROMOTION_EDGES` | 两条合法迁移，冻结的二元组集合 |
| `truth_types.core.MESSAGES` | 英文消息目录：全部面向人的 `reason` / `detail` 字符串，`str.format` 模板 —— 仅表现层，不属于契约 |

`VerificationStatus`、`GraduationStatus`、`ActorKind` 为枚举，从包根导入；完整公共面见
[SPEC §7.1](SPEC.md)。

## 落盘配置

| 设置 | 默认 | 说明 |
|:--|:--|:--|
| `TruthTypeRegistry(log_dir=…)` | —— | 显式目录；优先级高于环境变量 |
| `TRUTH_TYPES_AUDIT_PATH` | 未设 | 目录，或一个 `*.jsonl` 文件（取其父目录） |
| *默认位置* | 当前工作目录 | 审计流落在 `./truth_types_audit.jsonl` |

```bash
export TRUTH_TYPES_AUDIT_PATH=/var/lib/myapp/truth        # 目录
export TRUTH_TYPES_AUDIT_PATH=/var/lib/myapp/truth/audit.jsonl   # 文件 -> 取其父目录
```

## 审计行格式

每行一个 JSON 对象（`ensure_ascii=False`），只追加 —— 下面是一条真实的被拒提升：

```json
{"ts": "2026-09-22T19:50:17", "action": "promote", "eid": "n1", "ok": false, "detail": "declared→canonical by ai: only humans may promote (AI output is always derived)", "from_type": "declared", "to_type": "canonical"}
```

`action` ∈ `add` | `promote` | `ai_coerce`；结构化字段（`action`、`eid`、`ok`、`from_type`、
`to_type`）与语言无关。面向人的 `reason` / `detail` 为英文，集中定义在
`truth_types.core.MESSAGES`（单表、可整体替换，便于 i18n）—— 消息文本不属于兼容契约，消费方请以
结构化字段分支判断，切勿依赖消息文本（[SPEC §7.8](SPEC.md)）。AI 创建时请求了更强类型并被接受
的，会写两行：先 `ai_coerce`，后 `add`。

## 路线图

**v0.1 —— 当前这棵树（v0.1.0）。** 库本体（四类型、六规则、只增不删审计流）、规范
（[SPEC.md](SPEC.md)，1015 行）、三个可运行示例、28 个测试，以及覆盖 Python 3.10–3.13 的 CI 工作流。
纯标准库。分发物已 release-ready —— wheel 与 sdist 构建通过、`twine check` 通过（均在 CI 中）——
包索引发布进行中。

**v0.2 —— 分发。**

- 包索引发布，安装一行收敛为 `pip install truth-types`，上方徽章由静态切为实时。
- `truth-types-mcp`：MCP 服务封装，向 Agent 暴露 `add` 与 `check_on_screen`，让 Agent 通过 MCP
  读写与检查，而不是内嵌本库。**`promote` 刻意不经 MCP 暴露**（见
  [谁手里有 `promote`](#谁手里有-promote)）。
- 公开仓库，连同已经在本树内的 issue / PR 模板与贡献指南。

**v1 —— 收敛项**（均记录在 [SPEC §9.3](SPEC.md)，没有任何一项削弱六条规则）：把 `source_grade`
实现为顶层字段并强制；UTC 时间戳（带偏移、亚秒精度）；保持单调性的撤回路径；日志轮转或压缩；
多进程场景的可选写串行化；边界 B1/B2 统一为决策对象。

## 开发

```bash
python -m pytest -q                 # 28 个测试
PYTHONPATH=. python -m pytest -q    # 未安装时的等价写法
python examples/01_quickstart.py    # 可运行示例（见上文「示例」）
pyright                             # 类型检查（可选）
```

CI 在 Python 3.10–3.13 上跑同一套测试，断言安装后的元数据（零运行时依赖、`__version__` 一致），
并构建 + `twine check` 分发物（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）。

本库刻意保持小：只有当一条规则能在代码里强制、并被测试覆盖时，它才属于这里。徽章里的测试数为
v0.1.0 的 20 —— 仓库公开后，CI 会在每次推送时复核这个数字，工作流徽章也从那时起开始报状态。

## 贡献

欢迎提 issue 与补丁 —— 见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。两条硬规矩：新增规则必须可机器
校验且有测试覆盖 —— 一条「无法让调用失败」的约定属于你的流水线，不属于这个库；
[SPEC §7.8](SPEC.md) 的兼容承诺具约束力，因为导出名与四个真值类型字符串就是记录与审计文件的线上
格式。会扩大公共面的改动，请先对照规范开一个讨论。

## 许可

Apache-2.0 —— 见 [`LICENSE`](LICENSE)。

---

**English:** [README.md](README.md) — this document's English original; structure and wording are
kept in sync.
