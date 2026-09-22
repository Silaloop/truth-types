# Security Policy

## Supported versions

| Version | Supported |
|:--|:--|
| `0.1.x` | ✅ current release candidate |
| `< 0.1` | ❌ pre-release snapshots |

Only the latest `0.x` release receives fixes. While the project is at `0.x`, security fixes are made
on `main` and released as a new `0.x` version; there are no back-ports to earlier minors.

## Reporting a vulnerability

**Please do not open a public issue.** Use GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab → **Report a vulnerability**
   (<https://github.com/Jackxuzhenjie/truth-types/security/advisories/new>), or
2. If that form is unavailable to you, open a minimal public issue that says only *"I would like to
   report a security issue privately"* — with no details — and a maintainer will open a private
   channel for the report.

Please include: the version, the Python version, a minimal reproduction, and the impact you believe
it has. If you have a fix in mind, say so; you will be credited in the advisory unless you ask not to.

## What is in scope

The library is a small, offline, single-process component. Issues that matter here:

- **Rule bypass** — a code path that lets a promotion happen which the six rules forbid, or lets a
  record reach a state the lattice does not allow.
- **Audit-log forgery through the public API** — an accepted or rejected `add()` / `promote()`
  attempt that leaves no audit line, or a line whose structured fields (`action`, `eid`, `ok`,
  `from_type`, `to_type`) misrepresent what happened.
- **CI / supply-chain issues in this repository** — workflow injection, a build step that can be
  made to execute untrusted input, or metadata that misrepresents the published artifact.
- **Path handling** — a value passed to `TruthTypeRegistry(log_dir=…)` or `TRUTH_TYPES_AUDIT_PATH`
  causing writes outside the intended directory.
- **Crash or data loss on load** — a hand-written or partially written JSONL file that makes the
  registry drop records silently, or overwrite them.

## What is *not* a vulnerability (documented limitations of v0)

These are known, stated in the [SPEC](SPEC.md) and in the README's *Known limitations*, and are not
accepted as security reports unless you can show they are worse than documented:

- **`actor_kind` is an unauthenticated claim.** The library enforces the *contract*, not the
  *identity*: if your own code lets a model call `promote(..., ActorKind.HUMAN)`, the isolation
  guarantee is void. That is the caller's trust boundary (SPEC §4.2, §4.6), not a library defect.
- **The audit log is append-only by convention, not tamper-evident.** Nothing prevents rewriting
  the file; there is no rotation, compaction or locking (SPEC §7.7, §9.1).
- **No retraction and no modification** — corrections are additive by design (README, *Known
  limitations*).
- **Local, second-resolution, timezone-less timestamps** — unsuitable for ordering across hosts.

Reports that amount to "the library does not authenticate humans" will be closed with a pointer to
those sections.

## Disclosure process

Best effort, no SLA. The maintainer aims to acknowledge a report within **7 days**, to keep you
informed while a fix and a release are prepared, and to publish a GitHub Security Advisory that
credits the reporter once a fixed version is available. If a report is declined, you get the reason
and the relevant spec section.
