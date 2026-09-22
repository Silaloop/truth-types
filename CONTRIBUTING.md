# Contributing to truth-types

Thanks for looking. This library is small on purpose, and the rules below are what keep it small
enough to trust: everything here is enforceable by a test or by the build, and nothing here is
negotiated case by case.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Two acceptance criteria for any addition

1. **A rule belongs here only if it can be enforced in code.** It must be able to *fail a call*.
   A convention that cannot fail belongs in your pipeline, not in this library.
2. **The compatibility promise is binding.** Exported names and the four truth-type strings are the
   wire format of the JSONL records and audit files — see the compatibility contract in
   [SPEC §7.8](SPEC.md). Additions that widen the public surface start as a **discussion against the
   specification**: [SPEC.md](SPEC.md) is normative and is amended before the code is written.

Corollary, and the most common review comment: **message text is not API.** Branch on the structured
fields (`ok`, `allowed`, `action`, `from_type`, `to_type`), never on the wording of `reason` /
`detail`. Tests assert outcomes and structured fields, not sentences.

## Development setup

Python 3.10+ (the CI matrix runs 3.10 – 3.13). No runtime dependencies, ever — the package is
standard library only.

```bash
git clone https://github.com/Silaloop/truth-types
cd truth-types
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # pytest + pyright + build/twine
```

Running the examples needs no install at all: each script puts the repository root on `sys.path`
itself. Nothing in this project touches the network, in tests or in examples.

## Before you open a pull request

```bash
python -m pytest -q                  # 20 tests today, ~3 s
python examples/01_quickstart.py     # the full lifecycle, printed step by step
python examples/02_blocked_promotions.py
python examples/03_audit_query.py
PYTHONPATH=. python -m pytest -q     # equivalent when you prefer not to install
pyright                              # optional, but the package ships py.typed
```

For a change to a rule, add the test that asserts the *rejection*: the illegal call is refused **and**
the refusal is visible in the audit log. "No exception was raised" is not a test of a rule.

## Repository layout

| Path | What lives there |
|:--|:--|
| `truth_types/core.py` | The lattice, the six rules, `TruthTypeRegistry`, the `MESSAGES` catalogue |
| `truth_types/__init__.py` | The public surface (`__all__`) and `__version__` |
| `tests/test_truth_types.py` | The test suite — offline, no fixtures beyond `tmp_path` |
| `examples/` | Three runnable scripts, standard library only |
| `SPEC.md` | The normative specification: rules, guarantees, compatibility contract, known limitations |
| `CHANGELOG.md` | [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format; add under `## [Unreleased]` |

## Pull requests

- Keep the change single-purpose; a rule change and a refactor are two pull requests.
- Describe the **failure mode** being fixed, not only the diff.
- If a rule or a field changes, `SPEC.md` is updated **in the same pull request** and the change is
  called out explicitly in the description.
- If the compatibility promise in SPEC §7.8 narrows, say so in the description and in
  `CHANGELOG.md`; that is a decision for the maintainer, not a side effect of a patch.
- Commit messages: one line, imperative, under ~72 characters, with a body when the *why* is not
  obvious. Reference issues as `Closes #123`.

## Sign-off (DCO)

Every commit must be signed off — `git commit -s` — which adds:

```text
Signed-off-by: Your Name <you@example.com>
```

That is the [Developer Certificate of Origin 1.1](DCO.md): you certify you have the right to submit
the contribution under Apache-2.0. There is no CLA and no copyright assignment; you keep your
copyright. Contributions that cannot be signed off cannot be merged.

```bash
git commit -s -m "reject opaque parents in add()"
git rebase --signoff main      # retro-fit sign-off onto an existing branch
```

## Reporting bugs and security issues

- Bugs and feature requests: the issue templates in
  [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/) ask for the version, a minimal reproduction
  and the relevant audit lines. A reproduction of five lines beats a description of fifty.
- Security issues (rule bypass, audit forgery, unsafe path handling): **not** in a public issue —
  see [SECURITY.md](SECURITY.md).
- Design questions about a rule or the lattice: open a discussion rather than a pull request.

## Releases (maintainer)

```bash
# 1. bump the version in pyproject.toml AND truth_types/__init__.py (CI asserts they match)
# 2. move the CHANGELOG's Unreleased section into a dated version heading
export VERSION=0.1.0
python -m pytest -q
rm -rf dist build && python -m build          # sdist + wheel
python -m twine check dist/*                  # metadata renders on PyPI
python -m venv /tmp/smoke && /tmp/smoke/bin/pip install dist/*.whl
/tmp/smoke/bin/python -c "import truth_types; print(truth_types.__version__)"
git commit -am "release v$VERSION" && git tag -a "v$VERSION" -m "v$VERSION"
git push origin main --follow-tags            # then: python -m twine upload dist/*
```

Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the major
version is `0`, the **minor** version is the compatibility boundary.
