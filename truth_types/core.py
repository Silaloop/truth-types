#!/usr/bin/env python3
"""truth_types.core — an epistemic truth-type system for agent knowledge pipelines.

Four truth types form a monotone lattice::

    derived ⊑ declared ⊑ canonical        (opaque sits outside the lattice)

Rules enforced by this module:
  1. Only humans may promote; AI output is always derived.
  2. No level skipping (there is no direct derived → canonical edge).
  3. No downgrading.
  4. opaque is isolated: it may be neither referenced nor promoted.
  5. On creation, truth_type = min(parents) (weakest-link).
  6. Publisability: a statement may be shown as a conclusion only when
     truth_type >= declared and it has at least one parent.

Relationship to human-facing tagging: a fact/inference tag records a human's
judgement about *what* a statement is; this module carries the machine-checkable
provenance of its *status* — who promoted it to what, whether a level was
skipped, and which upstream records it cites. The two layers are complementary.

Purpose: attach truth-type fields to knowledge objects and machine-check every
promotion attempt. Every attempt — accepted or rejected — is appended to an
audit log (JSONL).

Every human-readable ``reason`` / ``detail`` string comes from the single English
message catalogue :data:`MESSAGES` (see its docstring for why message text is not
part of the compatibility contract). See SPEC.md §Related Work for academic
background.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

MODE = "truth_types"

#: Environment variable that overrides the default on-disk location of the
#: records/audit files (a directory, or a ``*.jsonl`` file whose parent is used).
AUDIT_PATH_ENV = "TRUTH_TYPES_AUDIT_PATH"

#: File names written inside the resolved log directory.
RECORDS_FILENAME = "truth_types.jsonl"
DEFAULT_AUDIT_FILENAME = "truth_types_audit.jsonl"

#: English message catalogue — every runtime ``reason`` / ``detail`` string.
#:
#: Entries with placeholders are ``str.format`` templates. The catalogue is a
#: single table so that (a) message text is easy to audit and reword in one
#: place, and (b) a translation layer can replace it wholesale (or patch
#: individual keys) without touching the enforcement code.
#:
#: Message text is deliberately *not* part of the compatibility contract:
#: branch on the structured fields (``ok``, ``allowed``, ``action``,
#: ``from_type``, ``to_type``), never on the wording of ``reason`` / ``detail``.
MESSAGES: dict[str, str] = {
    # --- weakest_link (creation rule 5) ---
    "weakest_link_no_parents": (
        "parents must be non-empty: a record has to cite upstream records (weakest-link rule)"
    ),
    "weakest_link_opaque_parent": (
        "opaque is isolated: it may not be cited as an upstream parent"
    ),
    # --- check_promotion ---
    "promote_opaque": "opaque is isolated: no transition into or out of the lattice",
    "promote_same_type": "target truth type equals the current truth type (no change)",
    "promote_downgrade": "downgrading is forbidden",
    "promote_level_skip": (
        "level skipping is forbidden: no direct promotion edge {current}→{target}"
    ),
    "promote_humans_only": "only humans may promote (AI output is always derived)",
    "promote_ok": "{current}→{target} (human promotion, legal edge)",
    # --- TruthTypeRegistry.add ---
    "add_duplicate_eid": "eid already exists (overwriting is forbidden: the log is append-only)",
    "add_ai_coerce": (
        "AI creation coerced to derived (requested {requested}; AI output is always derived)"
    ),
    "add_broken_chain": "unresolved citation (broken provenance chain): {missing}",
    "add_level_skip_kind": "level-skipping creation",
    "add_downgrade_kind": "downgrade creation",
    "add_parent_mismatch": "{kind}: declared {declared} != weakest-link {computed}",
    "add_ok": "created",
    "add_created": "created {truth_type} (actor={actor})",
    # --- TruthTypeRegistry.promote ---
    # The capability check runs before every other condition (SPEC.md §4.7).
    "promote_disabled": (
        "promotion is disabled on this registry (read-only promote handle); "
        "construct a promoting registry in the human review surface"
    ),
    "promote_missing_eid": "eid not found",
    "promote_audit_detail": "{current}→{target} by {actor}: {reason}",
    "promote_note_separator": " | ",
    # --- TruthTypeRegistry.check_on_screen (rule 6) ---
    "screen_below_declared": (
        "truth_type={truth_type} < declared (not publisable as a conclusion)"
    ),
    "screen_no_parents": "parents is empty (a conclusion must cite upstream records)",
    "screen_problem_separator": "; ",
    "screen_ok": "ok",
}


class TruthType(str, Enum):
    """Four truth types (monotone lattice: derived ⊑ declared ⊑ canonical; opaque sits outside it)."""

    DERIVED = "derived"
    DECLARED = "declared"
    CANONICAL = "canonical"
    OPAQUE = "opaque"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VPENDING = "vpending"
    VERIFIED = "verified"
    VFAILED = "vfailed"
    CANNOT_VERIFY = "cannot_verify"


class GraduationStatus(str, Enum):
    ASSERTED = "asserted"
    INVESTIGATING = "investigating"
    CORROBORATED = "corroborated"
    GVERIFIED = "gverified"
    GRADUATED = "graduated"


class ActorKind(str, Enum):
    HUMAN = "human"
    AI = "ai"


_LATTICE_ORDER: dict[TruthType, int] = {
    TruthType.DERIVED: 0,
    TruthType.DECLARED: 1,
    TruthType.CANONICAL: 2,
}

# The only two promotion edges (structural guarantee against skipping levels, derived→canonical)
PROMOTION_EDGES: frozenset[tuple[TruthType, TruthType]] = frozenset(
    {
        (TruthType.DERIVED, TruthType.DECLARED),
        (TruthType.DECLARED, TruthType.CANONICAL),
    }
)


def _order(tt: TruthType) -> Optional[int]:
    return _LATTICE_ORDER.get(tt)


def weakest_link(types: Iterable[TruthType]) -> TruthType:
    """Creation rule 5: truth_type = min(parents) (weakest-link).

    - Empty parents → ValueError (a statement must cite upstream records).
    - Any opaque parent → ValueError (opaque is isolated).
    """
    vals = list(types)
    if not vals:
        raise ValueError(MESSAGES["weakest_link_no_parents"])
    if TruthType.OPAQUE in vals:
        raise ValueError(MESSAGES["weakest_link_opaque_parent"])
    return min(vals, key=lambda t: _order(t) or 0)


def check_promotion(
    current: TruthType,
    target: TruthType,
    actor: ActorKind,
) -> dict:
    """Validate a promotion attempt (machine-checkable, fail-closed). Returns {allowed, reason}."""
    if current == TruthType.OPAQUE or target == TruthType.OPAQUE:
        return {"allowed": False, "reason": MESSAGES["promote_opaque"]}
    if target == current:
        return {"allowed": False, "reason": MESSAGES["promote_same_type"]}
    if (_order(target) or 0) < (_order(current) or 0):
        return {"allowed": False, "reason": MESSAGES["promote_downgrade"]}
    if (current, target) not in PROMOTION_EDGES:
        return {
            "allowed": False,
            "reason": MESSAGES["promote_level_skip"].format(
                current=current.value, target=target.value
            ),
        }
    if actor != ActorKind.HUMAN:
        return {"allowed": False, "reason": MESSAGES["promote_humans_only"]}
    return {
        "allowed": True,
        "reason": MESSAGES["promote_ok"].format(current=current.value, target=target.value),
    }


@dataclass
class EpistemicRecord:
    """A single governed evidence record."""

    eid: str
    truth_type: TruthType
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    graduation: GraduationStatus = GraduationStatus.ASSERTED
    actor_kind: ActorKind = ActorKind.HUMAN
    parents: tuple[str, ...] = ()
    source_ref: str = ""
    attestation_ref: str = ""
    statement: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["truth_type"] = self.truth_type.value
        d["verification"] = self.verification.value
        d["graduation"] = self.graduation.value
        d["actor_kind"] = self.actor_kind.value
        d["parents"] = list(self.parents)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EpistemicRecord":
        return cls(
            eid=d["eid"],
            truth_type=TruthType(d["truth_type"]),
            verification=VerificationStatus(d.get("verification", "unverified")),
            graduation=GraduationStatus(d.get("graduation", "asserted")),
            actor_kind=ActorKind(d.get("actor_kind", "human")),
            parents=tuple(d.get("parents", [])),
            source_ref=d.get("source_ref", ""),
            attestation_ref=d.get("attestation_ref", ""),
            statement=d.get("statement", ""),
            note=d.get("note", ""),
        )


def default_log_dir() -> Path:
    """Resolve the default directory holding the records/audit JSONL files.

    Resolution order:
      1. ``TRUTH_TYPES_AUDIT_PATH`` environment variable, when set: a ``*.jsonl``
         value is treated as the audit file itself (its parent directory is
         used), any other value is treated as the directory.
      2. Otherwise the current working directory, so the audit log lands at
         ``./truth_types_audit.jsonl``.
    """
    raw = os.environ.get(AUDIT_PATH_ENV, "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        return candidate.parent if candidate.suffix.lower() == ".jsonl" else candidate
    return Path.cwd()


class TruthTypeRegistry:
    """Registry of truth-typed records (records JSONL + append-only audit JSONL).

    - add(): applies the creation rules (weakest-link / AI is always derived /
      a level-skipping declaration is rejected)
    - promote(): applies the promotion rules (humans only / no level skipping /
      no downgrading / opaque is isolated)
      * every attempt — accepted or rejected — is written to the audit log, which
        is what makes blocked promotions reviewable
    - check_on_screen(): publication rule 6

    ``allow_promote`` is a construction-time **capability handle** (SPEC.md §4.7):
    with ``allow_promote=False`` the registry is a *read-only promote handle* —
    every ``promote()`` call is refused (and still audited), while ``add()``,
    ``get()``, ``check_on_screen()`` and the audit queries behave as usual.
    Agent processes SHOULD be handed a read-only handle; a promote-capable
    registry belongs to the human review surface.
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        allow_promote: bool = True,
    ) -> None:
        """Open (or create) the registry's directory and load existing records.

        ``allow_promote`` is set at construction and exposed as a read-only
        property: ``False`` yields a read-only promote handle (SPEC.md §4.7) for
        processes that may add and read records but must not promote. Passing a
        promoting registry to agent code is a deployment choice; passing a
        read-only one makes the safe path the default path.
        """
        self.dir = Path(log_dir) if log_dir is not None else default_log_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.records_path = self.dir / RECORDS_FILENAME
        self.audit_path = self.dir / DEFAULT_AUDIT_FILENAME
        self._allow_promote = bool(allow_promote)
        self._records: dict[str, EpistemicRecord] = {}
        self._load()

    @property
    def allow_promote(self) -> bool:
        """Whether this handle may promote. Read-only: a handle is armed at construction."""
        return self._allow_promote

    # ---------- internal ----------

    def _load(self) -> None:
        if not self.records_path.exists():
            return
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            self._records[d["eid"]] = EpistemicRecord.from_dict(d)

    def _save_record(self, rec: EpistemicRecord) -> None:
        with self.records_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def _audit(self, action: str, eid: str, ok: bool, detail: str, **extra) -> dict:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": action,
            "eid": eid,
            "ok": ok,
            "detail": detail,
            **extra,
        }
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # ---------- public API ----------

    def get(self, eid: str) -> Optional[EpistemicRecord]:
        return self._records.get(eid)

    def add(self, rec: EpistemicRecord) -> dict:
        """Add a record. Returns {ok, reason, record?}. Rejection reasons include: level-skipping creation / downgrade creation / opaque reference."""
        if rec.eid in self._records:
            return self._audit_call("add", rec.eid, False, MESSAGES["add_duplicate_eid"])

        # Rule 1: AI output is always derived (coerce and leave an audit trail,
        # whatever level was requested).
        if rec.actor_kind == ActorKind.AI and rec.truth_type != TruthType.DERIVED:
            self._audit(
                "ai_coerce", rec.eid, True,
                MESSAGES["add_ai_coerce"].format(requested=rec.truth_type.value),
            )
            rec = EpistemicRecord(
                eid=rec.eid,
                truth_type=TruthType.DERIVED,
                verification=rec.verification,
                graduation=rec.graduation,
                actor_kind=rec.actor_kind,
                parents=rec.parents,
                source_ref=rec.source_ref,
                attestation_ref=rec.attestation_ref,
                statement=rec.statement,
                note=rec.note,
            )

        # Rule 5: on creation, truth_type = min(parents) (weakest-link)
        if rec.parents:
            missing = [p for p in rec.parents if p not in self._records]
            if missing:
                return self._audit_call(
                    "add", rec.eid, False,
                    MESSAGES["add_broken_chain"].format(missing=missing),
                )
            computed = weakest_link(self._records[p].truth_type for p in rec.parents)
            if rec.truth_type != computed:
                kind = (
                    MESSAGES["add_level_skip_kind"]
                    if (_order(rec.truth_type) or 0) > (_order(computed) or 0)
                    else MESSAGES["add_downgrade_kind"]
                )
                return self._audit_call(
                    "add", rec.eid, False,
                    MESSAGES["add_parent_mismatch"].format(
                        kind=kind, declared=rec.truth_type.value, computed=computed.value
                    ),
                )
        self._records[rec.eid] = rec
        self._save_record(rec)
        self._audit(
            "add", rec.eid, True,
            MESSAGES["add_created"].format(
                truth_type=rec.truth_type.value, actor=rec.actor_kind.value
            ),
        )
        return {"ok": True, "reason": MESSAGES["add_ok"], "record": rec.to_dict()}

    def _audit_call(self, action: str, eid: str, ok: bool, detail: str, **extra) -> dict:
        self._audit(action, eid, ok, detail, **extra)
        return {"ok": ok, "reason": detail}

    def promote(
        self,
        eid: str,
        target: TruthType,
        actor: ActorKind,
        note: str = "",
    ) -> dict:
        """Promote a record (machine-checked, fully audited). Returns {ok, reason}.

        On a read-only promote handle (``allow_promote=False``, SPEC.md §4.7) this
        is a no-op refusal: nothing is promoted, the returned ``ok`` is ``False``
        for every argument, and the attempt is still appended to the audit log —
        a read-only handle is never invisible in the record of attempts.
        """
        if not self._allow_promote:
            rec = self._records.get(eid)
            extra: dict = {"to_type": target.value, "handle": "read-only"}
            if rec is not None:
                extra["from_type"] = rec.truth_type.value
            return self._audit_call("promote", eid, False, MESSAGES["promote_disabled"], **extra)
        rec = self._records.get(eid)
        if rec is None:
            return self._audit_call("promote", eid, False, MESSAGES["promote_missing_eid"])
        check = check_promotion(rec.truth_type, target, actor)
        ok = bool(check["allowed"])
        self._audit(
            "promote", eid, ok,
            MESSAGES["promote_audit_detail"].format(
                current=rec.truth_type.value,
                target=target.value,
                actor=actor.value,
                reason=check["reason"],
            )
            + (MESSAGES["promote_note_separator"] + note if note else ""),
            from_type=rec.truth_type.value,
            to_type=target.value,
        )
        if not ok:
            return {"ok": False, "reason": check["reason"]}
        rec.truth_type = target
        if actor == ActorKind.HUMAN and rec.attestation_ref == "":
            rec.attestation_ref = f"human-promote:{time.strftime('%Y%m%dT%H%M%S')}"
        self._save_record(rec)
        return {"ok": True, "reason": check["reason"]}

    def check_on_screen(self, eid: str) -> dict:
        """Rule 6: a publisable conclusion requires truth_type >= declared and a non-empty parents list."""
        rec = self._records.get(eid)
        if rec is None:
            return {"ok": False, "reason": MESSAGES["promote_missing_eid"]}
        problems: list[str] = []
        if (_order(rec.truth_type) or -1) < _LATTICE_ORDER[TruthType.DECLARED]:
            problems.append(
                MESSAGES["screen_below_declared"].format(truth_type=rec.truth_type.value)
            )
        if not rec.parents:
            problems.append(MESSAGES["screen_no_parents"])
        return {
            "ok": not problems,
            "reason": MESSAGES["screen_problem_separator"].join(problems)
            or MESSAGES["screen_ok"],
        }

    def audit_entries(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def blocked_promotions(self) -> list[dict]:
        """Promotions that were attempted and rejected."""
        return [e for e in self.audit_entries() if e.get("action") == "promote" and not e.get("ok")]
