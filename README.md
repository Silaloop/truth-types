<div align="center">

# truth-types

**Unreviewed text becomes a trusted fact by copy-and-paste. This library puts a review status on
every statement, so that it cannot happen silently.**

Four states — `derived`, `declared`, `canonical`, `opaque` — with human-only promotion, one step at a
time, weakest-link inheritance, and one audit line per attempt, accepted or rejected.

[![CI](../../actions/workflows/ci.yml/badge.svg?branch=main)](../../actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Runtime dependencies: 0](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)
[![Tests: 28 passing](https://img.shields.io/badge/tests-28%20passing-brightgreen.svg)](tests/test_truth_types.py)

[Specification](SPEC.md) · [Changelog](CHANGELOG.md) · [Examples](examples/) · [简体中文](README.zh-CN.md)

*The first badge is the repository's GitHub Actions workflow badge: it starts reporting as soon as
this repository is public and the CI workflow has run on `main` (Python 3.10–3.13). The numeric
badges are shields.io statics — the test count is 28 at v0.1.0 and is re-checked by CI and by
`python -m pytest -q`; there is no package-index release yet (see [Install](#install)).*

</div>

## The failure it prevents

In an agent pipeline there is no type boundary between what a model produced and what a human
confirmed: **unreviewed text becomes a trusted fact by copy-and-paste**, and afterwards nobody can
answer *who confirmed what, at which level, on what evidence*.

This library adds the missing field. Every knowledge object carries a truth type — four classes in a
partial order (`derived ⊑ declared ⊑ canonical`, with `opaque` outside the lattice) — where

- only a **human** may raise a level, **one step at a time**;
- no record may **outrank its weakest parent**;
- every attempt — accepted or rejected — is appended to a **JSONL audit log**.

So “how did this become a conclusion?” is a query rather than an archaeology project. The whole
mechanism shows up in four lines:

```python
reg.promote("n1", TruthType.CANONICAL, ActorKind.AI)
# -> {"ok": False, "reason": "only humans may promote (AI output is always derived)"}
```

That refusal is recorded, not discarded — a blocked promotion is a row you can query afterwards
(`blocked_promotions()`), which is what turns “was this reviewed?” into a fact instead of an argument.

Scope, one line each, so you can stop reading now if this is the wrong shape: it **never reads your
`statement`** (it governs review status, never meaning); it is **not** a data-quality tool and not a
schema; and it does **not** authenticate actors — `actor_kind` is supplied by the caller, which is why
the two sections below exist.

## See it in 30 seconds (no install)

The examples add the repository root to `sys.path` themselves, so a checkout is enough — standard
library only, no network, no service:

```bash
python examples/02_blocked_promotions.py
```

It provokes all five rejection kinds and prints them. Real output, trimmed to the parts that matter —
the script first prints the fresh temporary directory it uses, then the per-attempt detail, then these
summary lines:

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

Five refusals, ten audit lines, zero runtime dependencies. The refusals are grouped on structured
fields (`from_type` → `to_type`), never on message text — message strings are presentation, not API.

## Who holds `promote`

The isolation guarantee is conditional on truthful `actor_kind`: the library enforces the *contract*,
not the *identity* ([SPEC §4.2](SPEC.md), [§4.6.1](SPEC.md)). That is not something to promise away —
it is a boundary you close by deployment shape:

| Process | What it may call |
|:--|:--|
| Producer / agent pipeline | `add()` and `check_on_screen()` — a handle onto the registry |
| Human review surface (review UI, CLI, ticket action) | `promote()` — and nothing else gets it |

- **In code (v0.1):** a registry can be handed out with promotion physically unavailable —
  `TruthTypeRegistry(log_dir=..., allow_promote=False)` ([SPEC §4.7](SPEC.md)). `promote()` then
  returns a refusal decision object for any argument, the audit line carries `handle: "read-only"`,
  and the attempt is still appended to the log: removing the capability does not remove the record.
- **Over MCP (v0.2):** `truth-types-mcp` exposes `add` and `check_on_screen` to agents. **`promote`
  is deliberately not exposed over MCP** — it belongs to the human review surface. The event stream
  is the integration point; promotion is not an agent tool.
- **Why:** it turns “`actor_kind` is caller-supplied” from a fatal limit into a division of
  responsibilities, and it matches the anti-pattern list in [SPEC §8.6](SPEC.md) (“promoting inside
  an automated job” — a job may prepare a promotion, never perform it).
- **What it does not do:** it does not verify who the human is, and the flag is a *narrowing, not a
  control* — whoever can construct a registry can construct a promoting one. Keep the promoting handle
  in the human review surface, and derive identity in your wrapper from SSO / PAM (next section).

## In a control environment

For governance, risk and audit readers, four questions answered with what v0.1.0 does and does not
provide:

1. **Identity.** `actor_kind` is supplied by the caller and is not authenticated
   ([SPEC §4.2](SPEC.md), [§4.6.1](SPEC.md)). In a controlled deployment, bind it in the outer wrapper
   to your SSO / PAM / service-account boundary and make the human review surface the only writer of
   `promote` (see above). What the library then records is a *review act attributed to that identity*,
   with the level it moved and the attestation stamp of the first human promotion.
2. **Evidence preservation.** The audit JSONL is append-only, but tamper-*evident* only insofar as it
   is copied elsewhere ([SPEC §9.1.16](SPEC.md)). Standard recipe: mirror both JSONL files to
   write-once storage (S3 Object Lock / WORM vault / immutable bucket) on your normal backup schedule,
   and if you need chain-of-custody, add one `prev_hash` per line as you copy them out — the lines are
   already one JSON object per line, so `prev_hash = sha256(previous line)` is a two-line script and
   nothing in the format changes. Keep them as long as your regime requires; there is no deletion path.
3. **Data hygiene.** Keep personal data and secrets out of `statement`, `note` and `detail`: the log is
   append-only with no deletion ([SPEC §8.6](SPEC.md)). The library never reads `statement`, so
   sensitive payloads can stay in your own store, referenced by `source_ref`.
4. **Positioning.** What this produces is **internal-control review evidence — not a regulatory
   compliance certification** ([SPEC §9.2](SPEC.md)). If you write a control-matrix row, the defensible
   wording is *composes with* / *is one evidence source for* — never “satisfies” or “compliant with”.
   The correspondences that hold up: human-only promotion ↔ an actor-boundary control (AI cannot hold
   accountable authority); append-only audit of every attempt, refusals included ↔ a
   record-keeping requirement's evidence source; `check_on_screen()` ↔ a gate condition on what may be
   published.

## Install

v0.1.0 is **not on a package index yet**. The distribution is release-ready — wheel and sdist build and
pass `twine check` in CI — and the package-index release is in progress; until it lands, install it
from this checkout:

```bash
cd truth-types
python -m venv .venv && source .venv/bin/activate
pip install -e .                # runtime: no dependencies at all
pip install -e ".[dev]"         # optional: pytest + pyright
```

Running the examples needs no install — each script adds the repository root to `sys.path` itself.
An MCP distribution layer is on the [Roadmap](#roadmap).

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

> **First-integration trap — boundary B1.** An AI-created record cannot cite a *stronger* parent:
> coercion to `derived` runs before the weakest-link comparison, so attaching a machine note under a
> human-`declared` statement is refused — even when the AI honestly asks for `derived`
> ([SPEC §3.7](SPEC.md)). This is a v0 boundary, not a bug, and it is the first thing a RAG pipeline
> usually tries. Workarounds within v0: have the human create the linking record, or store the machine
> note as a **root** record that carries a `source_ref`.

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
the *contract*, not the *identity* ([SPEC §4.2](SPEC.md), [§4.6](SPEC.md)). Closing that gap is a
deployment question, and it is answered in [Who holds `promote`](#who-holds-promote).

## Comparison with adjacent tools

One line each — they answer different questions, and none of them is made redundant by this
library.

| Alternative | What it is for | How truth-types relates |
|:--|:--|:--|
| An approval workflow (Airflow approval node, MLflow stage transition, branch protection) | Gating a deployment or a merge — a change to a system | This gates a *statement*, and the status travels with the statement into every document it is copied into, including the ones a human pastes it into by hand. Those systems gate the release; this gates what may be said. |
| A `reviewed: true` boolean column (or a home-grown status enum) | Marking that something was looked at | A boolean has no order, no legal transition set and no record of the attempt that was refused. Here the refused attempt is the row you query, and the level cannot move without a recorded human act. |
| A `confidence` score (`"confidence": "high"`) | How strongly someone believes a statement | A free-form score has no partial order, no permitted-transition set and no record of who set it; truth-types adds the order, the edge set and an audit line per attempt. A score is about belief, a truth type is about status. |
| JSON Schema / typed models | Validating the *shape* of a record — which keys exist, which values are allowed | A schema can require `truth_type ∈ {derived, declared, canonical, opaque}`; it cannot express who may move a value, that exactly two edges exist, or what happens to a refused attempt. Schemas govern shape, this library governs transitions. |
| Manual review (checklists, “mark uncertain claims”) | Directing a person or a model to be careful | An instruction is not a constraint: violations leave no trace and cannot be detected mechanically afterwards. Here every attempt carries the actor and the reason, so a skipped review becomes a query result instead of an argument. |
| Content-safety guardrails, data catalogs | Deciding whether text *may exist*; tracking datasets, tables and jobs | Guardrails are silent on how much a statement is trusted, and catalogs are silent on individual statements. truth-types governs the review status of one statement at a time. |
| An evaluation or observability stack (Langfuse, promptfoo, Opik, Phoenix) | How a run went — traces, scores, prompt versions | A trace shows the run; it does not carry a trusted-review state on the output. The confirmed level and the refused attempts are the queryable part here. |
| A lineage tool (MLflow tracking, DVC, OpenLineage) | Where an artifact came from | Lineage points upstream — inputs, runs, versions. truth-types governs the claim's own status: what it may become, not where it came from. |
| An action gate or human-in-the-loop interrupt (LangGraph interrupt, Agents SDK guardrails) | Whether an *action* should pause for approval | An action pause is about doing; a truth type is about saying. Output that passed an action review is still `derived` until a human confirms the statement itself. |
| A policy engine (OPA, Cedar) | Whether this actor may call this operation | They compose: the policy decides who may call `promote()`; the library decides which transitions exist at all — and every attempt, refused included, is recorded. |
| An evidence-sufficiency check or an action firewall (claim-guarding and action-firewall libraries) | Whether there is enough evidence — or whether an action is too risky | Sufficiency and legality are different checks: evidence gates judge the input; truth-types fixes the output's status and keeps the refusals on the record. |

And the honest inverse, so you can self-select out: if your real problem is dataset-level (ownership,
lineage, freshness, asset certification), this library sits **below** your problem — it never looks at
your data.

For governance and procurement readers: this is not a governance platform and not a subscription. It is a zero-dependency Apache-2.0 library that can go into an existing pipeline without a procurement cycle, and its audit log can be collected as one evidence source among the ones your regime already requires. It certifies nothing — whether your requirements are met is for your regime to judge.

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
  evidence source among the ones your regime already requires (see
  [In a control environment](#in-a-control-environment) for the mirroring recipe).
- **Not a knowledge base, graph store or review workflow tool.** Records form a citation graph only
  for the weakest-link rule; there is no traversal API, no query language, no assignments, queues or
  notifications.
- **Not a dataset-lineage system or a compliance certification.** Lineage belongs upstream of the
  statements that cite it; whether the evidence produced here satisfies a given regime is a question
  for that regime.
- **Not a replacement for review.** It makes review necessary and visible; it cannot make review
  good.

## Known limitations (v0)

**Intended v0 deployment envelope:** one writer, one host, one log directory — a batch step or a
sidecar in front of publication. The list below is the boundary of that envelope, verified against
`0.1.0` and stated in full in [SPEC §4.6](SPEC.md) and [§9.1](SPEC.md); each item gives the working
pattern first and the boundary second:

- **Actor identity is a contract, not a control** — see [Who holds `promote`](#who-holds-promote).
  `actor_kind` is supplied by the caller and is not authenticated; if model-driven code can call
  `promote(..., ActorKind.HUMAN)`, the isolation guarantee is void. Close it with
  `allow_promote=False` plus a human-only review surface: the honest path becomes the easy path, and
  the dishonest path is visible in the log.
- **Corrections are additive (no retraction).** A wrong statement is handled by adding a correcting
  record that cites both, leaving the history readable ([SPEC §8.5](SPEC.md)). Boundary: nothing can
  be withdrawn — downgrading is forbidden and `opaque` is outside the lattice, so the wrong statement
  stays visible in the history.
- **Timestamps: one local wall-clock line per attempt**, second resolution. That is enough to order
  the events of a single log directory and to compute review latency inside it
  ([SPEC §8.3](SPEC.md), “Time to promote”). Boundary: they carry no timezone offset and are not a
  cross-host clock — when you merge directories, sort on your own ingest field (v1 adds UTC with an
  offset).
- **One writer per directory.** The files are append-only JSONL, so a merged view is a concatenation
  plus a filter — never a rewrite — and with one writer per directory the audit line order stays
  meaningful. Boundary: no locking and no coordination, so two processes writing the same directory
  are not serialized ([SPEC §9.1.11](SPEC.md)). Give each replica its own directory.
- **Size and rotation:** files grow without bound — no rotation, no compaction, no cap; each promotion
  appends a full copy of the record. Budget for it (a long-running pipeline's audit file is the part
  you ship to cold storage), or wait for v1's rotation.
- **Human root records may be created at any level**, including `canonical`, with no promotion
  history. The compensating control is rule 6: such a record fails the publication gate until it
  cites parents.
- **No record modification other than promotion.** `add()` refuses an existing `eid`; there is no
  update or delete — `statement`, `note` and `source_ref` are fixed at creation.
- **Boundary B1: an AI record cannot cite a stronger parent** — the first-integration trap described
  in the quickstart ([SPEC §3.7](SPEC.md)).
- **Boundary B2: `add()` is not uniformly total.** An `opaque` parent raises `ValueError`; every other
  refusal is a decision object (`{"ok": False, "reason": …}`).
- **No re-validation on load.** A hand-written JSONL file can contain states the API would refuse
  ([SPEC §7.7](SPEC.md)).
- **`verification` and `graduation` are inert** — stored and audited, but consulted by no rule.
- **`source_grade` is specified but not implemented**; `source_ref` carries source identity in v0
  ([SPEC §5.5](SPEC.md)).
- **Single-node local filesystem, one statement at a time.** No remote store, no replication, no way
  to record that a *set* of records was reviewed together.
- **v0.1.0 is not on a package index yet** (the distribution is built and checked in CI; publication
  is in progress), and the `truth-types-mcp` server is not part of this tree.

## API overview

| Symbol | Purpose |
|:--|:--|
| `TruthTypeRegistry(log_dir=..., allow_promote=False)` | Records (`truth_types.jsonl`) + audit log (`truth_types_audit.jsonl`); `allow_promote=False` hands out a registry whose `promote()` refuses and is still audited |
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

**v0.1 — this tree (v0.1.0).** The library (four types, six rules, append-only audit), the
specification ([SPEC.md](SPEC.md), 1015 lines), three runnable examples, 28 tests, and a CI workflow
over Python 3.10–3.13. Standard library only. The distribution is release-ready — wheel and sdist
build and pass `twine check` in CI — and the package-index release is in progress.

**v0.2 — distribution.**

- Package-index release, so the install collapses to `pip install truth-types` and the badges switch
  from static to live.
- `truth-types-mcp`: an MCP server wrapper exposing `add` and `check_on_screen` as MCP tools, so an
  agent reads and checks through MCP instead of embedding the library. **`promote` is deliberately not
  exposed over MCP** (see [Who holds `promote`](#who-holds-promote)).
- The public repository, with the issue/PR templates and contribution guide that already ship in this
  tree.

**v1 — convergence items** (all recorded in [SPEC §9.3](SPEC.md), none of which weakens the six
rules): implement `source_grade` as a top-level field; UTC timestamps with offset and sub-second
resolution; a retraction path that preserves monotonicity; log rotation or compaction; optional
write serialization for multi-process use; uniform decision objects for boundaries B1 and B2.

## Development

```bash
python -m pytest -q                 # 28 tests
PYTHONPATH=. python -m pytest -q    # equivalent without an install
python examples/01_quickstart.py    # runnable examples (see Examples above)
pyright                             # type check (optional)
```

CI runs the same suite on Python 3.10–3.13, asserts the installed metadata (zero runtime
dependencies, `__version__` in sync) and builds plus `twine check`s the distribution
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

The library is deliberately small: a proposed rule belongs here only if it can be enforced in code
and exercised by a test. The test count in the badge is 20 at v0.1.0 — a number CI re-checks on every
push once the repository is public, which is also when the workflow badge starts reporting.

## Contributing

Bug reports and patches are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). Two ground rules: a
new rule must be machine-checkable and covered by a test — a convention that cannot fail a call
belongs in your pipeline, not in this library; and the compatibility promise in
[SPEC §7.8](SPEC.md) is binding, since the exported names and the four truth-type strings are the
wire format of the records and audit files. Additions that widen the surface should start as a
discussion against the spec.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).

---

**简体中文：** [README.zh-CN.md](README.zh-CN.md) — 同一份文档的简体中文版（结构与用语对齐本页）。
