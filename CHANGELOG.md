# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the major version is
`0`, the **minor** version is the compatibility boundary: a `0.x` release may change an exported
name or a record field, and will say so here.

## [Unreleased]

### Planned
- `truth-types-mcp` — an MCP server exposing `add` / `promote` / `check_on_screen` as tools, so an
  agent can call the rules instead of embedding the library.
- `source_grade` as a top-level record field; UTC timestamps with an offset and sub-second
  resolution; a retraction path that preserves monotonicity.
- Log rotation or compaction, and optional write serialization for multi-process use.
- Uniform decision objects for boundaries B1/B2 (`add()` with an `opaque` parent currently raises
  `ValueError` while every other refusal is a decision object).
- Live CI badge in the README, replacing the static shields.io badges.

## [0.1.0] - 2026-09-22

First public release candidate. Python 3.10+. **Zero runtime dependencies** — standard library
only, offline, no service to run.

### Added
- **Four truth types** in a partial order — `derived ⊑ declared ⊑ canonical`, with `opaque` outside
  the lattice — as the `TruthType` string enum.
- **Six machine-enforced, fail-closed rules**:
  1. only humans may promote (AI output is always `derived`);
  2. no level skipping (`PROMOTION_EDGES` enumerates the only two legal transitions);
  3. no downgrading;
  4. `opaque` is isolated — never promoted, never a parent;
  5. creation is weakest-link: `truth_type = min(parents)`;
  6. publication gate: a conclusion needs `truth_type >= declared` **and** a non-empty `parents`.
- `TruthTypeRegistry` — `add()`, `promote()`, `check_on_screen()`, `get()`, `audit_entries()`,
  `blocked_promotions()`, backed by two JSONL files (`truth_types.jsonl`,
  `truth_types_audit.jsonl`).
- **Append-only audit log** — one line per `add()` / `promote()` attempt, accepted or rejected, with
  language-neutral structured fields (`action`, `eid`, `ok`, `from_type`, `to_type`); an AI creation
  that requested a stronger type records `ai_coerce` and then `add`.
- `EpistemicRecord` — `eid`, `truth_type`, `verification`, `graduation`, `actor_kind`, `parents`,
  `source_ref`, `attestation_ref`, `statement`, `note`, with `to_dict()` / `from_dict()`.
- Helpers and constants: `check_promotion()`, `weakest_link()`, `default_log_dir()`,
  `PROMOTION_EDGES`, `RECORDS_FILENAME`, `DEFAULT_AUDIT_FILENAME`, `AUDIT_PATH_ENV`, `MODE`, and the
  enums `VerificationStatus`, `GraduationStatus`, `ActorKind`.
- **`allow_promote` — read-only promote handles.** `TruthTypeRegistry(log_dir=…, allow_promote=False)`
  yields a handle that may `add()` and read but never promote: every `promote()` call returns
  `{ok: False, reason: …}` whatever the arguments, and is still written to the audit log
  (`handle="read-only"`) so no attempt goes unseen. Rationale: `actor_kind` is a self-declared claim,
  so the smallest real narrowing is to take the *ability* to promote away from the handle the agent
  process holds, leaving a promoting registry to the human review surface (SPEC.md §4.7). It
  defaults to `True`, so existing callers are unchanged.
- **`TRUTH_TYPES_AUDIT_PATH`** — environment override for the log directory (a directory, or a
  `*.jsonl` file whose parent directory is used).
- **`truth_types.core.MESSAGES`** — the single English catalogue every `reason` / `detail` string
  comes from; message text is presentation, not part of the compatibility contract.
- **Typed package** — `py.typed` ships in the wheel; the public surface is declared in `__all__`.
- **Specification** — [SPEC.md](SPEC.md), 959 lines: the six rules, the isolation guarantee, the
  compatibility contract (§7.8), boundary behaviour (§4.6) and the convergence list (§9.3).
- **Examples** — three runnable, dependency-free scripts: the full lifecycle, the rejection surface,
  and reading the audit log back with nothing but the standard library.
- **Tests** — 28 offline tests covering the lattice, all six rules, the audit trail, the read-only
  promote handle (`allow_promote=False`), persistence across a reload, and the isolation scenario (AI
  output reaching `canonical` requires two human promotions through the observable intermediate
  state).
- **Packaging** — PEP 517/518 build from `pyproject.toml` alone; `sdist` + `wheel`; Apache-2.0;
  `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `SECURITY.md`, DCO sign-off, issue and pull-request templates, and a GitHub Actions CI matrix over
  Python 3.10 – 3.13.

### Security
- **Isolation guarantee** — a record created by an AI actor can reach `canonical` only after at least
  two promotion acts attributed to human actors, passing through the observable `declared` state. The
  edge set is enumerated rather than computed, so the shortcut exists in no code path.
- Refused transitions are **recorded**, not silently dropped: `blocked_promotions()` is a query over
  the audit log rather than an argument about what happened.
- The guarantee is conditional on truthful `actor_kind` (the library enforces the contract, not the
  identity) and is scoped accordingly in [SECURITY.md](SECURITY.md).

### Known limitations
- `actor_kind` is an unauthenticated claim supplied by the caller; a read-only promote handle
  (`allow_promote=False`) removes the promotion path from one handle but is not a sandbox (§9.1.18);
  the audit log is append-only by convention, not tamper-evident; there is no retraction; `add()` is
  not uniformly total (an `opaque` parent raises `ValueError`); `verification` / `graduation` are
  stored but inert; `source_grade` is specified but not implemented; timestamps are local with second
  resolution; files grow without bound. The full list is in the README and in SPEC §4.6, §4.7 and
  §9.1.

[Unreleased]: https://github.com/Silaloop/truth-types/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Silaloop/truth-types/releases/tag/v0.1.0
