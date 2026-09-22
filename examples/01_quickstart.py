#!/usr/bin/env python3
"""Example 01 — quickstart: the whole lifecycle in one script.

AI output enters the pipeline as ``derived``, a human raises it to ``declared``,
an agent tries to raise it further and is rejected, and a second human review
finally makes it ``canonical``.

Run from the repository root (no install required):

    python examples/01_quickstart.py

Everything is written to a fresh temporary directory, so the example never
touches your working tree; the directory is printed at the end.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run without installing

from truth_types import (  # noqa: E402  (import after the sys.path bootstrap)
    ActorKind,
    EpistemicRecord,
    TruthType,
    TruthTypeRegistry,
)


def stored(reg: TruthTypeRegistry, eid: str) -> EpistemicRecord:
    rec = reg.get(eid)
    assert rec is not None, f"record {eid!r} not found"
    return rec


def main() -> None:
    log_dir = Path(tempfile.mkdtemp(prefix="truth-types-example-01-"))
    reg = TruthTypeRegistry(log_dir=log_dir)
    print(f"registry: {log_dir}")
    print()

    # 1. AI output enters the pipeline. The requested level is ignored: AI output
    #    is always `derived`, and the coercion itself is written to the audit log.
    added = reg.add(
        EpistemicRecord(
            eid="n1",
            truth_type=TruthType.CANONICAL,  # requested ...
            actor_kind=ActorKind.AI,  # ... but AI output stays `derived`
            statement="Channel inventory grew 18% quarter-on-quarter",
            source_ref="https://example.com/filing#p42",
        )
    )
    print(f"1. add  (AI, requested canonical) -> ok={added['ok']}  reason={added['reason']!r}")
    print(f"   stored truth_type = {stored(reg, 'n1').truth_type.value}")

    # 2. A human reviewer confirms it once: derived -> declared.
    first = reg.promote("n1", TruthType.DECLARED, ActorKind.HUMAN, note="checked against the filing")
    print(f"2. promote (human, -> declared)   -> ok={first['ok']}  reason={first['reason']!r}")

    # 3. The agent tries to promote it the rest of the way: rejected *and* audited.
    blocked = reg.promote("n1", TruthType.CANONICAL, ActorKind.AI)
    print(f"3. promote (AI,    -> canonical)  -> ok={blocked['ok']}  reason={blocked['reason']!r}")
    print(f"   stored truth_type = {stored(reg, 'n1').truth_type.value}  (unchanged)")

    # 4. A second human review raises it to canonical — one step at a time, never two.
    second = reg.promote("n1", TruthType.CANONICAL, ActorKind.HUMAN, note="second reviewer signed off")
    print(f"4. promote (human, -> canonical)  -> ok={second['ok']}  reason={second['reason']!r}")
    rec = stored(reg, "n1")
    print(f"   stored truth_type = {rec.truth_type.value}")
    print(f"   attestation_ref   = {rec.attestation_ref}")

    # 5. The rejection from step 3 is queryable after the fact.
    blocked_entries = reg.blocked_promotions()
    print()
    print(f"5. blocked promotions: {len(blocked_entries)}")
    for entry in blocked_entries:
        print(f"   {entry['eid']}: {entry['from_type']}->{entry['to_type']}  {entry['detail']}")

    total = len(reg.audit_entries())
    print()
    print(f"audit trail: {total} entries in {reg.audit_path.name} (accepted and rejected attempts alike)")


if __name__ == "__main__":
    main()
