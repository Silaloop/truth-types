<!--
Thanks for the pull request. Keep it small and single-purpose where you can.
Delete any checklist line that genuinely does not apply, but say why in the description.
-->

## What this changes

<!-- One or two sentences. If it changes a rule or a field, name it. -->

## Why

<!-- The failure mode this fixes or the capability it adds. Link the issue: "Closes #123". -->

## Type

- [ ] Bug fix (a rule that did not fire, or a state the lattice should not allow)
- [ ] New machine-checkable rule (it fails a call, and a test asserts the rejection)
- [ ] API / field addition (see the compatibility promise below)
- [ ] Documentation or specification only
- [ ] Packaging, CI or tooling only

## Checklist

- [ ] `python -m pytest -q` passes locally (20 tests on `main` today; a new rule comes with its own).
- [ ] `python examples/01_quickstart.py` still runs.
- [ ] **No new runtime dependencies** — the library is standard library only, and stays that way.
- [ ] **If a rule or a field changed, `SPEC.md` was updated first**: the spec is normative, and the
      compatibility promise in SPEC §7.8 (exported names, the four truth-type strings, the structured
      audit fields) is binding. If this pull request narrows that promise, say so explicitly.
- [ ] **Message text was not treated as API**: `reason` / `detail` wording is presentation, and
      anything that branches on it is a bug. Tests assert structured fields, not sentences.
- [ ] A new test asserts the *outcome* of the change — for a rule, that the illegal call is refused
      and recorded, not merely that no exception was raised.
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]` (Added / Changed / Fixed / Removed).
- [ ] Commits are signed off for the DCO: `git commit -s` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Notes for the reviewer

<!-- Anything you are unsure about, alternatives you rejected, or follow-ups you deliberately left out. -->
