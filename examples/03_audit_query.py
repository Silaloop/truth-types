#!/usr/bin/env python3
"""Example 03 — audit query: read the audit JSONL back and answer questions of it.

The audit log is a plain JSONL file: one self-contained JSON object per line, so
any grep / jq / pandas / warehouse loader can consume it without this library.
This script writes a small trail, then reads the raw file line by line and
summarises it, and finally shows the two convenience queries on the registry.

Run from the repository root (no install required):

    python examples/03_audit_query.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
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


def build_trail(reg: TruthTypeRegistry) -> None:
    """Produce a mixed trail: accepted adds, an AI coercion, promotions, rejections."""
    # a human-declared root (no parents: it is the ground record)
    reg.add(EpistemicRecord(eid="filing", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                            statement="FY25 filing p.42", source_ref="https://example.com/filing#p42"))
    # AI output: the requested level is ignored and coerced to derived
    reg.add(EpistemicRecord(eid="model_note", truth_type=TruthType.CANONICAL, actor_kind=ActorKind.AI,
                            statement="Model summary of the filing"))
    # a child of `filing`: its type must equal the weakest parent (declared), so it passes
    reg.add(EpistemicRecord(eid="quote", truth_type=TruthType.DECLARED, actor_kind=ActorKind.HUMAN,
                            parents=("filing",), statement="Inventory +18% QoQ"))
    reg.promote("quote", TruthType.CANONICAL, ActorKind.AI)                      # blocked: humans only
    reg.promote("quote", TruthType.CANONICAL, ActorKind.HUMAN,
                note="reviewed against the filing")                              # accepted
    reg.promote("quote", TruthType.DECLARED, ActorKind.HUMAN)                    # blocked: downgrading
    reg.promote("model_note", TruthType.CANONICAL, ActorKind.HUMAN)              # blocked: level skipping
    reg.add(EpistemicRecord(eid="orphan", truth_type=TruthType.DERIVED, actor_kind=ActorKind.HUMAN,
                            parents=("missing",), statement="cites a record that does not exist"))  # blocked


def main() -> None:
    log_dir = Path(tempfile.mkdtemp(prefix="truth-types-example-03-"))
    reg = TruthTypeRegistry(log_dir=log_dir)
    build_trail(reg)
    print(f"registry: {log_dir}")
    print()

    # --- 1. the raw file, read with nothing but the standard library ---
    print(f"raw {reg.audit_path.name} (line by line, unmodified):")
    lines = [ln for ln in reg.audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for i, line in enumerate(lines, start=1):
        print(f"  {i:2d}. {line}")

    rows = [json.loads(line) for line in lines]

    # --- 2. summaries over the parsed rows ---
    print()
    print("by action:", dict(sorted(Counter(row["action"] for row in rows).items())))
    print("by outcome:", {"accepted": sum(1 for r in rows if r["ok"]),
                          "rejected": sum(1 for r in rows if not r["ok"])})
    print("eids seen:", sorted({row["eid"] for row in rows}))

    # --- 3. one record's history: who attempted what, and how it ended ---
    print()
    print("history for eid='quote':")
    for row in rows:
        if row["eid"] != "quote":
            continue
        outcome = "ok" if row["ok"] else "blocked"
        print(f"  {row['ts']}  {row['action']:9s} {outcome:7s} {transition(row):24s} {row['detail']}")

    # --- 4. the two convenience queries on the registry ---
    print()
    blocked = reg.blocked_promotions()
    print(f"registry.blocked_promotions() -> {len(blocked)} of {len(rows)} audit entries")
    for entry in blocked:
        print(f"  {entry['eid']:11s} {transition(entry):24s} {entry['detail']}")
    print(f"registry.audit_entries()      -> {len(reg.audit_entries())} entries")

    # --- 5. state vs. trail: the registry is reloadable from the records file alone ---
    reloaded = TruthTypeRegistry(log_dir=log_dir)
    for eid in ("filing", "quote", "model_note"):
        rec = reloaded.get(eid)
        assert rec is not None
        print(f"reloaded {eid:11s} truth_type={rec.truth_type.value}")


if __name__ == "__main__":
    main()
