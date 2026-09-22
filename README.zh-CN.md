<div align="center">

# truth-types

**面向 Agent 知识流水线的真值类型系统。**

每个知识对象携带一个真值类型 —— `derived`、`declared`、`canonical` 或 `opaque` —— 配机器强制的
提升规则与只增不删的审计流，让 AI 产出无法「悄悄变成结论」。

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)
[![Tests: 20 passing](https://img.shields.io/badge/tests-20%20passing-brightgreen.svg)](tests/test_truth_types.py)

[规范 SPEC.md](SPEC.md) · [示例](examples/) · [English](README.md)

<!-- CI 徽章：随公开仓库一起激活（见「路线图 → v0.2」）。在此之前上方为 shields.io 静态徽章，
     测试数由人工维护。 -->

</div>

## 为什么要它

在一条 Agent 流水线里，模型产出与人已确认的内容之间没有类型边界：未审文本一次复制粘贴就成了
「事实」，事后谁也答不出**谁、在哪一层、基于什么证据确认过**。本库补上这个缺失字段 —— 四类真值
类型构成偏序（`derived ⊑ declared ⊑ canonical`，`opaque` 在格之外），只有人能提升、且每次只能
升一级，子记录不得高于最弱父记录。规则写在代码里，每一次尝试（无论接受还是拒绝）都追加一行
JSONL 审计记录 —— 于是「这条怎么成为结论的」是一条查询，而不是一场考古。

你会得到：

- **零运行时依赖** —— 纯标准库、无需起服务、无需改库表，可离线运行。直接挂在既有流水线前面。
- **失败即拒（fail-closed）** —— 非法提升返回明确拒绝，而不是把值悄悄改掉。
- **只增不删的审计流** —— 每次 `add()` / `promote()` 一行 JSONL，`grep`、`jq`、pandas 或数仓
  装载器都能直接消费。
- **最短板继承** —— 子记录永远不能高于其最弱父记录。
- **约 490 行 Python**（核心模块 + 包初始化），带类型标注（`py.typed`），Apache-2.0。

## 安装

v0 **尚未发布至 PyPI** —— 从当前检出目录安装：

```bash
cd truth-types
python -m venv .venv && source .venv/bin/activate
pip install -e .                # 运行时：零依赖
pip install -e ".[dev]"         # 可选：pytest + pyright
```

跑示例无需安装 —— 每个脚本自行把仓库根目录加进 `sys.path`。包索引发布与 MCP 分发层见
[路线图](#路线图)。

## 五分钟上手

把下面这段存成仓库根目录下的 `quickstart.py` 再运行即可。注释里写的是每次调用的真实返回值；
同一条生命周期也脚本化在 [`examples/01_quickstart.py`](examples/01_quickstart.py) 中。

```python
from truth_types import ActorKind, EpistemicRecord, TruthType, TruthTypeRegistry

# 1. 注册表由两个 JSONL 文件支撑：记录 + 只增不删的审计流
reg = TruthTypeRegistry(log_dir="./audit")        # 或省略，用 TRUTH_TYPES_AUDIT_PATH

# 2. AI 产出进入流水线；请求 canonical 会被强制降级 —— AI 产出恒为 `derived`
reg.add(EpistemicRecord(
    eid="n1",
    truth_type=TruthType.CANONICAL,               # 请求值
    actor_kind=ActorKind.AI,                      # ……但 AI 产出只能是 `derived`
    statement="Channel inventory grew 18% quarter-on-quarter",
    source_ref="https://example.com/filing#p42",
))
# -> {"ok": True, "reason": "created"}            这次强制降级以 "ai_coerce" 留痕

# 3. 人类评审确认一次 -> declared
reg.promote("n1", TruthType.DECLARED, ActorKind.HUMAN, note="checked against the filing")
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
                        statement="FY25 filing p.42"))
reg.add(EpistemicRecord(eid="c1", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                        parents=("s1",), statement="Inventory +18% QoQ"))
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

### 四个真值类型

| 类型 | 格中位置 | 谁能产出 | 含义 |
|:--|:--|:--|:--|
| `derived` | 底 | AI 或人 | 机器派生；尚无人确认 |
| `declared` | 中 | 人提升（自 `derived`） | 人已在案声明 |
| `canonical` | 顶 | 人提升（自 `declared`） | 人已确认，可作为结论被消费 |
| `opaque` | 格之外 | —— | 隔离：不得被引用，也不得被提升 |

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
**身份**（[SPEC §4.2](SPEC.md)、[§4.6](SPEC.md)）。

## 与相邻工具的关系

每条一句 —— 它们回答的是不同问题，本库不让其中任何一个变得多余。

| 替代方案 | 它解决什么 | 与 truth-types 的关系 |
|:--|:--|:--|
| `confidence` 分数字段（`"confidence": "high"`） | 表达「谁有多相信这条陈述」 | 自由文本分数没有偏序、没有合法迁移集、也没有「谁设的值」的记录；本库补上序、边集与逐次审计行。分数管信念，真值类型管地位。 |
| JSON Schema / 类型化模型 | 校验记录的**形状** —— 有哪些键、允许哪些取值 | Schema 能要求 `truth_type ∈ {derived, declared, canonical, opaque}`；它无法表达「谁能改值」「只存在两条边」「被拒的尝试怎么处理」。Schema 管形状，本库管迁移。 |
| 人工评审（清单、「不确定的要标注」） | 指示人或模型小心行事 | 指示不是约束：违规不留痕，事后无法机械检出。这里每次尝试都带行为者与原因，于是「有没有被跳过评审」是查询结果，而不是争论。 |
| 内容安全护栏、数据目录 | 判断文本**是否可存在**；追踪数据集、表与作业 | 护栏不表达「这条陈述被信任到什么程度」，目录也不表达单条陈述的状态。truth-types 一次只管一条陈述的评审状态。 |

## 它不是什么

- **不是真值判定器。** `canonical` 的含义是「人在案确认过」，不是「正确」。本库从不读取
  `statement` 的内容。
- **不是内容安全或策略引擎。** 它不判断陈述是否可存在；它与做这件事的组件组合使用。
- **不是权限系统、也不是 RBAC。** 它不限制谁能读；它限制哪些类型迁移合法，并把迁移记录下来。
- **不是日志审计的替代品。** 它**产出**只增不删的审计流，但该文件只有在被你另存他处时才是防篡改
  可见的 —— 没有任何机制阻止重写它，并且没有轮转、压缩或删除（[SPEC §7.7](SPEC.md)、
  [§9.1](SPEC.md)）。请把它当作既有合规体系里的一个证据源。
- **不是知识库、图存储或评审工作流工具。** 记录只在最短板规则的意义上构成引用图；没有遍历 API、
  没有查询语言、没有派单、队列或通知。
- **不是数据集血缘系统、也不是合规认证。** 血缘在「引用它的陈述」的上游；这里产出的证据是否满足
  某一监管要求，是那个监管体系的问题。
- **不能替代评审本身。** 它让评审成为必需且可见；它无法让评审变好。

## 已知限制（v0）

以下均对 `0.1.0.dev0` 实证，完整表述见 [SPEC §4.6](SPEC.md) 与 [§9.1](SPEC.md)：

- **行为者身份是契约，不是管控。** `actor_kind` 由调用方申报，不做认证。若模型驱动的代码能调用
  `promote(..., ActorKind.HUMAN)`，隔离保证即失效 —— 本库让诚实的路径更省事，让不诚实的路径在
  审计流里可见。
- **人类可以直接创建任意层级的根记录**，包括 `canonical`，且无提升历史。补偿控制是规则 6：该记录
  在补上父引用之前过不了上屏闸门。
- **没有撤回。** 禁降级 + `opaque` 在格之外，使既有记录无法被撤销；更正必须是追加式的，错误陈述
  会留在历史里。
- **除提升外没有记录修改。** `add()` 拒绝已存在的 `eid`；没有 update 也没有 delete ——
  `statement`、`note`、`source_ref` 在创建时即固定。
- **`add()` 并非处处全函数。** `opaque` 作父记录时抛 `ValueError`（边界 B2）；其余拒绝一律是决策
  对象（`{"ok": False, "reason": …}`）。
- **`verification` 与 `graduation` 是惰性字段** —— 被存储、被审计，但不被任何规则读取。
- **`source_grade` 只有规范、尚未实现**；v0 用 `source_ref` 承载来源标识（[SPEC §5.5](SPEC.md)）。
- **时间戳为本地时间、秒级、无时区偏移** —— 不适合跨主机排序。
- **文件无界增长且无写协调。** 没有轮转、压缩或加锁；两个进程写同一目录不会被串行化。加载时不重
  校验：手写的 JSONL 文件可以包含 API 会拒绝的状态。
- **单机本地文件系统、一次一条陈述。** 没有远端存储、没有复制，也无法表达「一组记录被一起评审
  过」。
- **v0 尚未发布到 PyPI**，`truth-types-mcp` 服务也不在本仓库内。

## API 一览

| 符号 | 用途 |
|:--|:--|
| `TruthTypeRegistry(log_dir=...)` | 记录（`truth_types.jsonl`）+ 审计流（`truth_types_audit.jsonl`） |
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

**v0.1 —— 当前这棵树。** 库本体（四类型、六规则、只增不删审计流）、规范
（[SPEC.md](SPEC.md)，959 行）、三个可运行示例、20 个测试。纯标准库。

**v0.2 —— 分发。**

- `truth-types-mcp`：MCP 服务封装，让 Agent 以 MCP 工具直接调用 `add` / `promote` /
  `check_on_screen`，无需内嵌本库。
- 包索引发布、覆盖 `pyproject.toml` 所声明版本的 CI 测试矩阵，上方的徽章由静态切为实时。
- 随公开仓库一起落地 issue/PR 模板与贡献指南。

**v1 —— 收敛项**（均记录在 [SPEC §9.3](SPEC.md)，没有任何一项削弱六条规则）：把 `source_grade`
实现为顶层字段并强制；UTC 时间戳（带偏移、亚秒精度）；保持单调性的撤回路径；日志轮转或压缩；
多进程场景的可选写串行化；边界 B1/B2 统一为决策对象。

## 开发

```bash
python -m pytest -q                 # 20 个测试，约 3 秒
PYTHONPATH=. python -m pytest -q    # 未安装时的等价写法
python examples/01_quickstart.py    # 可运行示例（见上文「示例」）
pyright                             # 类型检查（可选）
```

本库刻意保持小：只有当一条规则能在代码里强制、并被测试覆盖时，它才属于这里。上方徽章中的测试数在
CI 工作流落地前为静态、人工维护（见路线图 v0.2）。

## 贡献

欢迎提 issue 与补丁。两条硬规矩：新增规则必须可机器校验且有测试覆盖 —— 一条「无法让调用失败」的
约定属于你的流水线，不属于这个库；[SPEC §7.8](SPEC.md) 的兼容承诺具约束力，因为导出名与四个真值
类型字符串就是记录与审计文件的线上格式。会扩大公共面的改动，请先对照规范开一个讨论。

## 许可

Apache-2.0 —— 见 [`LICENSE`](LICENSE)。

---

**English:** [README.md](README.md) — this document's English original; structure and wording are
kept in sync.
