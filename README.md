<div align="center">

# truth-types

**Epistemic truth types for agent knowledge pipelines.**

Every knowledge object carries a truth type — `derived`, `declared`, `canonical` or `opaque` —
together with machine-enforced promotion rules and an append-only audit log, so that AI-generated
content cannot silently become a trusted conclusion.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)
[![Tests: 20 passing](https://img.shields.io/badge/tests-20%20passing-brightgreen.svg)](tests/test_truth_types.py)

[Specification](SPEC.md) · [Examples](examples/) · [简体中文](README.zh-CN.md)

<!-- CI badge: activate with the public repository (Roadmap → v0.2). Until then the badges above
     are static shields.io badges and the test count is maintained by hand. -->

</div>

## Why this exists

In an agent pipeline there is no type boundary between what a model produced and what a human
confirmed: unreviewed text becomes a trusted fact by copy-and-paste, and afterwards nobody can
answer *who confirmed what, at which level, on what evidence*. This library adds the missing field
— four epistemic classes in a partial order (`derived ⊑ declared ⊑ canonical`, with `opaque`
outside the lattice), where only a human may raise a level, one step at a time, and no record may
outrank its weakest parent. The rules live in code and every attempt — accepted or rejected — is
appended to a JSONL audit log, so “how did this become a conclusion?” is a query rather than an
archaeology project.

What you get:

- **Zero runtime dependencies** — standard library only, no service to run, no schema migration,
  works offline. Drop it in front of an existing pipeline.
- **Fail-closed rules** — an illegal promotion returns a rejection instead of a silently changed
  value.
- **Append-only audit** — one JSONL line per `add()` / `promote()` attempt, readable with `grep`,
  `jq`, pandas or a warehouse loader.
- **Weakest-link inheritance** — a child record can never outrank its weakest parent.
- **≈490 lines of Python** (core module + package init), typed (`py.typed`), Apache-2.0.

## Install

v0 is **not published to PyPI yet** — install it from this checkout:

```bash
cd truth-types
python -m venv .venv && source .venv/bin/activate
pip install -e .                # runtime: no dependencies at all
pip install -e ".[dev]"         # optional: pytest + pyright
```

Running the examples needs no install — each script adds the repository root to `sys.path` itself.
A package-index release and an MCP distribution layer are on the [Roadmap](#roadmap).

## Five-minute quickstart

Copy the block below into `quickstart.py` in the repository root and run it. The comments show what
each call actually returns; the same lifecycle is scripted in
[`examples/01_quickstart.py`](examples/01_quickstart.py).

```python
from truth_types import ActorKind, EpistemicRecord, TruthType, TruthTypeRegistry

# 1. a registry backed by two JSONL files: records + append-only audit
reg = TruthTypeRegistry(log_dir="./audit")        # or omit and use TRUTH_TYPES_AUDIT_PATH

# 2. an AI-generated statement enters the pipeline. A requested "canonical" is coerced —
#    AI output is always `derived`.
reg.add(EpistemicRecord(
    eid="n1",
    truth_type=TruthType.CANONICAL,               # requested
    actor_kind=ActorKind.AI,                      # ... but AI output stays `derived`
    statement="Channel inventory grew 18% quarter-on-quarter",
    source_ref="https://example.com/filing#p42",
))
# -> {"ok": True, "reason": "created"}            the coercion is audited as "ai_coerce"

# 3. a human reviewer confirms it once -> declared
reg.promote("n1", TruthType.DECLARED, ActorKind.HUMAN, note="checked against the filing")
# -> {"ok": True}

# 4. an agent may not promote it — rejected AND audited
reg.promote("n1", TruthType.CANONICAL, ActorKind.AI)
# -> {"ok": False, "reason": "only humans may promote (AI output is always derived)"}

# 5. a second human review raises it to canonical — one step at a time, never two
reg.promote("n1", TruthType.CANONICAL, ActorKind.HUMAN)
# -> {"ok": True}

# 6. every attempt is queryable after the fact
reg.blocked_promotions()                          # -> [ {…, "action": "promote", "ok": False} ]

# 7. citation chain: a child record cannot outrank its weakest parent (weakest-link)
reg.add(EpistemicRecord(eid="s1", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                        statement="FY25 filing p.42"))
reg.add(EpistemicRecord(eid="c1", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                        parents=("s1",), statement="Inventory +18% QoQ"))
# -> both {"ok": True}  (c1 cites s1; declared == min(parents))

reg.add(EpistemicRecord(eid="bad", truth_type=TruthType.CANONICAL, actor_kind=ActorKind.HUMAN,
                        parents=("s1",)))
# -> {"ok": False, "reason": …}  (level-skipping creation: canonical ≠ weakest-link declared)

# 8. publication gate: conclusions need truth_type >= declared AND a non-empty parents list
reg.check_on_screen("c1")    # -> {"ok": True, "reason": "ok"}
reg.check_on_screen("n1")    # -> {"ok": False, "reason": …}   (no parents recorded)
```

Then run it and the test suite — no install, no network:

```bash
python quickstart.py         # the lifecycle above
python -m pytest -q          # 20 passed
```

## Examples

Three runnable scripts under [`examples/`](examples/) — standard library only, no install required.
Each one uses a fresh temporary directory for its log files and prints what it does:

| Script | What it shows |
|:--|:--|
| [`examples/01_quickstart.py`](examples/01_quickstart.py) | The whole lifecycle: AI output coerced to `derived` → human promotion to `declared` → AI promotion rejected → second human promotion to `canonical`, plus the blocked-promotion query |
| [`examples/02_blocked_promotions.py`](examples/02_blocked_promotions.py) | The rejection surface: it provokes all five rejection kinds (AI promotion, level skipping, downgrade, `opaque` transition, unknown `eid`) and prints the blocklist, grouped on structured fields rather than on message text |
| [`examples/03_audit_query.py`](examples/03_audit_query.py) | Audit query: reads the raw `truth_types_audit.jsonl` back with nothing but the standard library, summarises it (by action, by outcome, per-`eid` history), and compares it with `blocked_promotions()` / `audit_entries()` |

```bash
python examples/01_quickstart.py
python examples/02_blocked_promotions.py
python examples/03_audit_query.py
```

## Core concepts

### The four truth types

| Type | Lattice position | Who can produce it | Meaning |
|:--|:--|:--|:--|
| `derived` | bottom | AI or human | Machine-derived; no human confirmation yet |
| `declared` | middle | human promotion (from `derived`) | A human has asserted it on the record |
| `canonical` | top | human promotion (from `declared`) | Human-confirmed and reviewable as a conclusion |
| `opaque` | outside the lattice | — | Isolated: may be neither cited nor promoted |

`opaque` is a storage decision, not a fourth rung: a statement that is deliberately not modelled is
not on the same axis as a statement that is modelled and reviewed to some degree
([SPEC §2.4](SPEC.md)).

### Promotion rules (machine-enforced, fail-closed)

| # | Rule | Enforcement |
|:--|:--|:--|
| 1 | Only humans may promote | `AI` promotions are rejected and audited |
| 2 | No level skipping | only the edges `derived→declared` and `declared→canonical` exist (`PROMOTION_EDGES`) |
| 3 | No downgrading | target must be strictly above current |
| 4 | `opaque` is isolated | never promotable, never a parent |
| 5 | Creation = `min(parents)` (weakest link) | a child cannot outrank its weakest parent |
| 6 | Publication gate | conclusions need `truth_type >= declared` **and** a non-empty `parents` |

Every `add()` / `promote()` attempt — accepted or rejected — appends one line to the audit log,
which is what makes blocked transitions reviewable after the fact.

### Isolation guarantee

**A record produced by an AI actor can reach `canonical` only after at least two promotion acts
attributed to human actors, passing through the observable intermediate state `declared`**
([SPEC §4.1](SPEC.md)) — the edge set is enumerated rather than computed, so the shortcut does not
exist in any code path. The guarantee is conditional on truthful `actor_kind`: the library enforces
the *contract*, not the *identity* ([SPEC §4.2](SPEC.md), [§4.6](SPEC.md)).

## Comparison with adjacent tools

One line each — they answer different questions, and none of them is made redundant by this
library.

| Alternative | What it is for | How truth-types relates |
|:--|:--|:--|
| A `confidence` score (`"confidence": "high"`) | How strongly someone believes a statement | A free-form score has no partial order, no permitted-transition set and no record of who set it; truth-types adds the order, the edge set and an audit line per attempt. A score is about belief, a truth type is about status. |
| JSON Schema / typed models | Validating the *shape* of a record — which keys exist, which values are allowed | A schema can require `truth_type ∈ {derived, declared, canonical, opaque}`; it cannot express who may move a value, that exactly two edges exist, or what happens to a refused attempt. Schemas govern shape, this library governs transitions. |
| Manual review (checklists, "mark uncertain claims") | Directing a person or a model to be careful | An instruction is not a constraint: violations leave no trace and cannot be detected mechanically afterwards. Here every attempt carries the actor and the reason, so a skipped review becomes a query result instead of an argument. |
| Content-safety guardrails, data catalogs | Deciding whether text *may exist*; tracking datasets, tables and jobs | Guardrails are silent on how much a statement is trusted, and catalogs are silent on individual statements. truth-types governs the review status of one statement at a time. |

## What it is not

- **Not a truth oracle.** `canonical` means “confirmed by humans on the record”, not “correct”. The
  library never reads `statement`.
- **Not a content-safety or policy engine.** It does not decide whether a statement may exist; it
  composes with whatever does.
- **Not an access-control system or RBAC layer.** It does not restrict who may read; it restricts
  which type transitions are legal, and records them.
- **Not an audit-log replacement.** It *produces* an append-only audit trail, but the file is
  tamper-evident only insofar as you copy it elsewhere — nothing prevents rewriting it, and there is
  no rotation, compaction or deletion ([SPEC §7.7](SPEC.md), [§9.1](SPEC.md)). Treat it as one
  evidence source among the ones your regime already requires.
- **Not a knowledge base, graph store or review workflow tool.** Records form a citation graph only
  for the weakest-link rule; there is no traversal API, no query language, no assignments, queues or
  notifications.
- **Not a dataset-lineage system or a compliance certification.** Lineage belongs upstream of the
  statements that cite it; whether the evidence produced here satisfies a given regime is a question
  for that regime.
- **Not a replacement for review.** It makes review necessary and visible; it cannot make review
  good.

## Known limitations (v0)

All of these are verified against `0.1.0.dev0` and stated in full in [SPEC §4.6](SPEC.md) and
[§9.1](SPEC.md):

- **Actor identity is a contract, not a control.** `actor_kind` is supplied by the caller and is not
  authenticated. If model-driven code can call `promote(..., ActorKind.HUMAN)`, the isolation
  guarantee is void — the honest path is the easy path, and the dishonest path is visible in the
  log.
- **Human root records may be created at any level**, including `canonical`, with no promotion
  history. The compensating control is rule 6: such a record fails the publication gate until it
  cites parents.
- **No retraction.** Downgrading is forbidden and `opaque` is outside the lattice, so an existing
  record cannot be withdrawn; corrections must be additive and the wrong statement stays visible in
  history.
- **No record modification other than promotion.** `add()` refuses an existing `eid`; there is no
  update or delete — `statement`, `note` and `source_ref` are fixed at creation.
- **`add()` is not uniformly total.** An `opaque` parent raises `ValueError` (boundary B2); every
  other refusal is a decision object (`{"ok": False, "reason": …}`).
- **`verification` and `graduation` are inert** — stored and audited, but consulted by no rule.
- **`source_grade` is specified but not implemented**; `source_ref` carries source identity in v0
  ([SPEC §5.5](SPEC.md)).
- **Timestamps are local, second-resolution, with no timezone offset** — unsuitable for ordering
  across hosts.
- **Files grow without bound and are not coordinated.** No rotation, no compaction, no locking; two
  processes writing the same directory are not serialized. No re-validation on load: a hand-written
  JSONL file can contain states the API would refuse.
- **Single-node local filesystem, one statement at a time.** No remote store, no replication, no way
  to record that a *set* of records was reviewed together.
- **v0 is not on PyPI yet**, and the `truth-types-mcp` server is not part of this tree.

## API overview

| Symbol | Purpose |
|:--|:--|
| `TruthTypeRegistry(log_dir=...)` | Records (`truth_types.jsonl`) + audit log (`truth_types_audit.jsonl`) |
| `registry.add(record)` | Creation rules; returns `{"ok", "reason", "record"?}` |
| `registry.promote(eid, target, actor, note="")` | Promotion rules; returns `{"ok", "reason"}` |
| `registry.check_on_screen(eid)` | Publication gate (rule 6) |
| `registry.get(eid)` | Fetch one record |
| `registry.audit_entries()` | Full audit trail (list of dicts) |
| `registry.blocked_promotions()` | Rejected promotion attempts only |
| `EpistemicRecord` | `eid`, `truth_type`, `verification`, `graduation`, `actor_kind`, `parents`, `source_ref`, `attestation_ref`, `statement`, `note` + `to_dict()` / `from_dict()` |
| `check_promotion(current, target, actor)` | Pure predicate returning `{"allowed", "reason"}` |
| `weakest_link(types)` | `min(parents)` helper (raises on empty / `opaque` parents) |
| `default_log_dir()` | Resolves the log directory from `TRUTH_TYPES_AUDIT_PATH` or the working directory |
| `PROMOTION_EDGES` | The two legal transitions, as a frozen set of pairs |
| `truth_types.core.MESSAGES` | English message catalogue: every human-readable `reason` / `detail` string, as `str.format` templates — presentation only, not part of the contract |

`VerificationStatus`, `GraduationStatus` and `ActorKind` are enums imported from the package root;
the full public surface is listed normatively in [SPEC §7.1](SPEC.md).

## Configuration

| Setting | Default | Notes |
|:--|:--|:--|
| `TruthTypeRegistry(log_dir=…)` | — | Explicit directory; wins over the environment |
| `TRUTH_TYPES_AUDIT_PATH` | unset | A directory, or a `*.jsonl` file whose parent directory is used |
| *default location* | current working directory | the audit log lands at `./truth_types_audit.jsonl` |

```bash
export TRUTH_TYPES_AUDIT_PATH=/var/lib/myapp/truth        # directory
export TRUTH_TYPES_AUDIT_PATH=/var/lib/myapp/truth/audit.jsonl   # file -> parent dir used
```

## Audit log format

One JSON object per line (`ensure_ascii=False`), appended only — a real rejected promotion:

```json
{"ts": "2026-09-22T19:50:17", "action": "promote", "eid": "n1", "ok": false, "detail": "declared→canonical by ai: only humans may promote (AI output is always derived)", "from_type": "declared", "to_type": "canonical"}
```

`action` ∈ `add` | `promote` | `ai_coerce`; structured fields (`action`, `eid`, `ok`, `from_type`,
`to_type`) are language-neutral. Human-readable `reason` / `detail` strings are English and come
from the catalogue `truth_types.core.MESSAGES` — they are presentation, not API surface: branch on
the structured fields, never on message text ([SPEC §7.8](SPEC.md)). An accepted AI creation that
requested a stronger type writes two lines, `ai_coerce` then `add`.

## Roadmap

**v0.1 — this tree.** The library (four types, six rules, append-only audit), the specification
([SPEC.md](SPEC.md), 959 lines), three runnable examples and 20 tests. Standard library only.

**v0.2 — distribution.**

- `truth-types-mcp`: an MCP server wrapper, so an agent can call `add` / `promote` /
  `check_on_screen` as MCP tools instead of embedding the library.
- Package-index release, CI test matrix over the versions declared in `pyproject.toml`, and the
  badges above switching from static to live.
- Issue/PR templates and contribution guide shipping with the public repository.

**v1 — convergence items** (all recorded in [SPEC §9.3](SPEC.md), none of which weakens the six
rules): implement `source_grade` as a top-level field; UTC timestamps with offset and sub-second
resolution; a retraction path that preserves monotonicity; log rotation or compaction; optional
write serialization for multi-process use; uniform decision objects for boundaries B1 and B2.

## Development

```bash
python -m pytest -q                 # 20 tests, ~3 s
PYTHONPATH=. python -m pytest -q    # equivalent without an install
python examples/01_quickstart.py    # runnable examples (see Examples above)
pyright                             # type check (optional)
```

The library is deliberately small: a proposed rule belongs here only if it can be enforced in code
and exercised by a test. The test count in the badge above is static and maintained by hand until
the CI workflow lands (Roadmap → v0.2).

## Contributing

Bug reports and patches are welcome. Two ground rules: a new rule must be machine-checkable and
covered by a test — a convention that cannot fail a call belongs in your pipeline, not in this
library; and the compatibility promise in [SPEC §7.8](SPEC.md) is binding, since the exported names
and the four truth-type strings are the wire format of the records and audit files. Additions that
widen the surface should start as a discussion against the spec.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).

---

**简体中文：** [README.zh-CN.md](README.zh-CN.md) — 同一份文档的简体中文版（结构与用语对齐本页）。
