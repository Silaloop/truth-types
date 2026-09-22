#!/usr/bin/env python3
"""Example 02 — the rejection surface: collect and print blocked promotions.

Every illegal promotion is refused *and* recorded. This script provokes each
rejection kind on purpose, then reads the blocklist back and branches on the
structured audit fields (`action`, `ok`, `from_type`, `to_type`) — never on the
wording of `detail`, which is presentation only.

Run from the repository root (no install required):

    python examples/02_blocked_promotions.py
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


def transition(entry: dict) -> str:
    """Render the structured transition fields; not every audit line has them."""
    if "from_type" in entry and "to_type" in entry:
        return f"{entry['from_type']}->{entry['to_type']}"
    return "(no transition)"


def main() -> None:
    log_dir = Path(tempfile.mkdtemp(prefix="truth-types-example-02-"))
    reg = TruthTypeRegistry(log_dir=log_dir)
    print(f"registry: {log_dir}")
    print()

    # --- setup: one AI record, one record promoted all the way to canonical,
    #     and one isolated `opaque` record.
    reg.add(EpistemicRecord(eid="ai_note", truth_type=TruthType.DERIVED, actor_kind=ActorKind.AI,
                            statement="Model summary of the FY25 filing"))
    reg.add(EpistemicRecord(eid="human_note", truth_type=TruthType.DERIVED, actor_kind=ActorKind.HUMAN,
                            statement="Analyst note on channel inventory"))
    reg.promote("human_note", TruthType.DECLARED, ActorKind.HUMAN)
    reg.promote("human_note", TruthType.CANONICAL, ActorKind.HUMAN)
    reg.add(EpistemicRecord(eid="raw_dump", truth_type=TruthType.OPAQUE, actor_kind=ActorKind.HUMAN,
                            statement="Unverified dump, deliberately isolated"))

    # --- provoke five rejection kinds ---
    attempts = [
        ("ai_note", TruthType.DECLARED, ActorKind.AI, "AI may never promote"),
        ("ai_note", TruthType.CANONICAL, ActorKind.HUMAN, "level skipping: derived -> canonical"),
        ("human_note", TruthType.DECLARED, ActorKind.HUMAN, "downgrading: canonical -> declared"),
        ("raw_dump", TruthType.DECLARED, ActorKind.HUMAN, "opaque is isolated"),
        ("no_such_eid", TruthType.DECLARED, ActorKind.HUMAN, "unknown eid"),
    ]

    print("attempted promotions")
    for eid, target, actor, why in attempts:
        result = reg.promote(eid, target, actor)
        verdict = "ACCEPTED" if result["ok"] else "REJECTED"
        print(f"  {verdict}  {eid:11s} -> {target.value:9s} by {actor.value:5s}  ({why})")
        print(f"            reason: {result['reason']}")

    # --- read the blocklist back ---
    blocked = reg.blocked_promotions()
    print()
    print(f"blocked_promotions(): {len(blocked)} rejected attempt(s)")
    for i, entry in enumerate(blocked, start=1):
        print(f"  {i}. ts={entry['ts']}  eid={entry['eid']:11s}  ok={entry['ok']}  "
              f"{transition(entry)}")

    # Message text is not part of the contract: classify on structured fields.
    print()
    print("grouped by transition (structured fields only, message text ignored)")
    counts: dict[str, int] = {}
    for entry in blocked:
        key = transition(entry)
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items()):
        print(f"  {key:22s} {count}")

    print()
    print(f"audit trail: {len(reg.audit_entries())} entries total "
          f"(every attempt, accepted or rejected)")


if __name__ == "__main__":
    main()
