"""Tests for the truth-types lattice (offline; no network access).

Coverage:
  1. weakest_link: min(parents) / empty parents rejected / opaque parent rejected
  2. check_promotion: legal edges / no level skipping / no downgrade / no-op rejected /
     opaque isolation / humans only
  3. add: creation rules (weakest-link level-skip rejected / broken chain rejected /
     duplicate rejected) + AI output is always derived (forced downgrade + audit trail)
  4. promote: two-step human promotion up to canonical / rejected attempts recorded in
     the audit log
  5. check_on_screen: publication rule 6
  6. persistence: state and audit log survive a reload
  7. isolation scenario: AI output → single-step human promotion to canonical is
     rejected (the ≥2 human promotions guarantee)
  8. read-only promote handles: `allow_promote=False` refuses every promotion
     (arguments irrelevant), audits the refusal, and leaves add/read/screen and
     the serialized record unchanged

Runtime `reason` / `detail` strings are asserted against the English catalogue in
`truth_types.MESSAGES` (message text is not part of the compatibility contract —
structured fields are).
"""
from __future__ import annotations

import pytest

import truth_types as tt


def _reg(tmp_path):
    return tt.TruthTypeRegistry(log_dir=tmp_path / "tt")


def _rec(eid, ttype, actor=tt.ActorKind.HUMAN, parents=(), **kw):
    return tt.EpistemicRecord(eid=eid, truth_type=ttype, actor_kind=actor, parents=tuple(parents), **kw)


def _must(reg, eid):
    rec = reg.get(eid)
    assert rec is not None
    return rec


def _ro_reg(tmp_path, name="tt-readonly"):
    """A read-only promote handle: may add and read, must not promote."""
    return tt.TruthTypeRegistry(log_dir=tmp_path / name, allow_promote=False)


# ---------- 1. weakest_link ----------

def test_weakest_link_basic():
    assert tt.weakest_link([tt.TruthType.DECLARED, tt.TruthType.DERIVED]) == tt.TruthType.DERIVED
    assert tt.weakest_link([tt.TruthType.CANONICAL, tt.TruthType.DECLARED]) == tt.TruthType.DECLARED
    assert tt.weakest_link([tt.TruthType.CANONICAL]) == tt.TruthType.CANONICAL


def test_weakest_link_empty_raises():
    with pytest.raises(ValueError):
        tt.weakest_link([])


def test_weakest_link_opaque_parent_raises():
    with pytest.raises(ValueError):
        tt.weakest_link([tt.TruthType.DECLARED, tt.TruthType.OPAQUE])


# ---------- 2. check_promotion ----------

def test_promotion_legal_edges():
    r = tt.check_promotion(tt.TruthType.DERIVED, tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    assert r["allowed"] is True
    r = tt.check_promotion(tt.TruthType.DECLARED, tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)
    assert r["allowed"] is True


def test_promotion_skip_rejected():
    r = tt.check_promotion(tt.TruthType.DERIVED, tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)
    assert r["allowed"] is False
    assert "level skipping" in r["reason"]


def test_promotion_downgrade_rejected():
    r = tt.check_promotion(tt.TruthType.CANONICAL, tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    assert r["allowed"] is False
    assert "downgrading" in r["reason"]


def test_promotion_same_rejected():
    r = tt.check_promotion(tt.TruthType.DECLARED, tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    assert r["allowed"] is False


def test_promotion_opaque_rejected():
    r = tt.check_promotion(tt.TruthType.OPAQUE, tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    assert r["allowed"] is False
    r = tt.check_promotion(tt.TruthType.DECLARED, tt.TruthType.OPAQUE, tt.ActorKind.HUMAN)
    assert r["allowed"] is False


def test_promotion_ai_rejected():
    r = tt.check_promotion(tt.TruthType.DERIVED, tt.TruthType.DECLARED, tt.ActorKind.AI)
    assert r["allowed"] is False
    assert "only humans" in r["reason"]


# ---------- 3. add ----------

def test_add_root_and_duplicate(tmp_path):
    reg = _reg(tmp_path)
    r = reg.add(_rec("r1", tt.TruthType.DECLARED))
    assert r["ok"] is True
    r2 = reg.add(_rec("r1", tt.TruthType.DERIVED))
    assert r2["ok"] is False
    assert "already exists" in r2["reason"]


def test_add_weakest_link_violation(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("p1", tt.TruthType.DERIVED))
    bad = reg.add(_rec("c1", tt.TruthType.DECLARED, parents=["p1"]))
    assert bad["ok"] is False
    assert "level-skipping creation" in bad["reason"]
    good = reg.add(_rec("c1b", tt.TruthType.DERIVED, parents=["p1"]))
    assert good["ok"] is True


def test_add_break_chain_rejected(tmp_path):
    reg = _reg(tmp_path)
    r = reg.add(_rec("c1", tt.TruthType.DERIVED, parents=["missing"]))
    assert r["ok"] is False
    assert "broken provenance chain" in r["reason"]


def test_ai_forced_derived(tmp_path):
    reg = _reg(tmp_path)
    rec = _rec("ai1", tt.TruthType.DECLARED, actor=tt.ActorKind.AI)
    r = reg.add(rec)
    assert r["ok"] is True
    assert _must(reg, "ai1").truth_type == tt.TruthType.DERIVED
    coerces = [e for e in reg.audit_entries() if e["action"] == "ai_coerce"]
    assert len(coerces) == 1


# ---------- 4. promote ----------

def test_promote_flow_to_canonical(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    assert reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is True
    assert reg.promote("r1", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN, note="second review passed")["ok"] is True
    assert _must(reg, "r1").truth_type == tt.TruthType.CANONICAL


def test_promote_blocked_recorded(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    r = reg.promote("r1", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)
    assert r["ok"] is False
    blocked = reg.blocked_promotions()
    assert len(blocked) == 1
    assert "level skipping" in blocked[0]["detail"]


def test_promote_ai_rejected_and_recorded(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    r = reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.AI)
    assert r["ok"] is False
    assert len(reg.blocked_promotions()) == 1


def test_promote_missing_eid(tmp_path):
    reg = _reg(tmp_path)
    r = reg.promote("nope", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    assert r["ok"] is False


# ---------- 5. check_on_screen ----------

def test_on_screen_rules(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("d1", tt.TruthType.DERIVED))
    assert reg.check_on_screen("d1")["ok"] is False

    reg.add(_rec("p1", tt.TruthType.DECLARED))
    reg.add(_rec("c1", tt.TruthType.DECLARED, parents=["p1"]))
    r = reg.check_on_screen("c1")
    assert r["ok"] is True

    # declared but with empty parents → must not be published as a conclusion
    assert reg.check_on_screen("p1")["ok"] is False

    reg.add(_rec("c2", tt.TruthType.DECLARED, parents=["c1"]))
    assert reg.check_on_screen("c2")["ok"] is True
    assert reg.promote("c2", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)["ok"] is True
    assert reg.check_on_screen("c2")["ok"] is True


# ---------- 6. persistence ----------

def test_persistence_reload(tmp_path):
    reg = _reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)
    reg2 = tt.TruthTypeRegistry(log_dir=tmp_path / "tt")
    assert _must(reg2, "r1").truth_type == tt.TruthType.DECLARED
    assert len(reg2.audit_entries()) >= 2


# ---------- 7. isolation scenario (≥2 human promotions) ----------

def test_isolation_scenario(tmp_path):
    """AI output is always derived; reaching canonical requires ≥2 human promotions."""
    reg = _reg(tmp_path)
    reg.add(_rec("ai_out", tt.TruthType.CANONICAL, actor=tt.ActorKind.AI))  # coerced to derived
    assert _must(reg, "ai_out").truth_type == tt.TruthType.DERIVED

    # single-step jump to canonical is rejected (level skipping)
    assert reg.promote("ai_out", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)["ok"] is False
    # the two-step path is allowed
    assert reg.promote("ai_out", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is True
    assert reg.promote("ai_out", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN)["ok"] is True
    assert _must(reg, "ai_out").truth_type == tt.TruthType.CANONICAL


# ---------- 8. read-only promote handles (allow_promote=False) ----------

def test_readonly_default_true_promotes(tmp_path):
    """The default stays promote-capable: existing callers see no change."""
    reg = tt.TruthTypeRegistry(log_dir=tmp_path / "tt")
    assert reg.allow_promote is True

    explicit = tt.TruthTypeRegistry(log_dir=tmp_path / "tt-explicit", allow_promote=True)
    assert explicit.allow_promote is True
    explicit.add(_rec("r1", tt.TruthType.DERIVED))
    assert explicit.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is True


def test_readonly_handle_refuses_legal_promotion(tmp_path):
    reg = _ro_reg(tmp_path)
    assert reg.allow_promote is False
    reg.add(_rec("r1", tt.TruthType.DERIVED))

    # a promotion that the rules of Section 3 would accept is still refused
    r = reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN, note="agent attempt")
    assert r["ok"] is False
    assert r["reason"] == (
        "promotion is disabled on this registry (read-only promote handle); "
        "construct a promoting registry in the human review surface"
    )
    assert set(r) == {"ok", "reason"}  # same decision-object shape as any refusal

    rec = _must(reg, "r1")
    assert rec.truth_type == tt.TruthType.DERIVED  # nothing was promoted
    assert rec.attestation_ref == ""               # no stamp, no side effect
    assert len(reg.blocked_promotions()) == 1


def test_readonly_handle_attempt_is_audited(tmp_path):
    """Every attempt leaves a trace, on every handle: the refusal is recorded."""
    reg = _ro_reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    before = len(reg.audit_entries())

    reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN, note="agent attempt")

    entries = reg.audit_entries()
    assert len(entries) == before + 1
    last = entries[-1]
    assert (last["action"], last["eid"], last["ok"]) == ("promote", "r1", False)
    # structured fields: the attempted transition and the handle that refused
    assert last["from_type"] == "derived"
    assert last["to_type"] == "declared"
    assert last["handle"] == "read-only"
    assert "promotion is disabled" in last["detail"]

    blocked = reg.blocked_promotions()
    assert len(blocked) == 1
    assert blocked[0]["ok"] is False
    assert "read-only promote handle" in blocked[0]["detail"]


def test_readonly_handle_leaves_add_and_reads_unchanged(tmp_path):
    """Only the promotion capability narrows: creation, retrieval and the screen rule are untouched."""
    reg = _ro_reg(tmp_path)
    assert reg.add(_rec("p1", tt.TruthType.DECLARED))["ok"] is True
    assert reg.add(_rec("c1", tt.TruthType.DECLARED, parents=["p1"]))["ok"] is True
    assert reg.add(_rec("ai1", tt.TruthType.CANONICAL, actor=tt.ActorKind.AI))["ok"] is True
    assert _must(reg, "ai1").truth_type == tt.TruthType.DERIVED  # rule 1 still coerces

    # creation rules still refuse, with the same decision-object reasons
    dup = reg.add(_rec("p1", tt.TruthType.DERIVED))
    assert dup["ok"] is False and "already exists" in dup["reason"]
    skip = reg.add(_rec("c2", tt.TruthType.DECLARED, parents=["ai1"]))
    assert skip["ok"] is False and "weakest-link" in skip["reason"]
    broken = reg.add(_rec("c3", tt.TruthType.DERIVED, parents=["nope"]))
    assert broken["ok"] is False and "broken provenance chain" in broken["reason"]

    assert _must(reg, "p1").eid == "p1"
    assert reg.get("absent") is None
    assert reg.check_on_screen("c1")["ok"] is True
    assert reg.check_on_screen("p1")["ok"] is False  # declared but no parents


def test_readonly_handle_switch_precedes_other_validation(tmp_path):
    """The capability check runs first: the refusal is argument-independent."""
    reg = _ro_reg(tmp_path)
    reg.add(_rec("r1", tt.TruthType.DERIVED))

    attempts = [
        ("missing_eid", tt.TruthType.DECLARED, tt.ActorKind.HUMAN),   # unknown eid
        ("r1", tt.TruthType.CANONICAL, tt.ActorKind.HUMAN),           # level skipping
        ("r1", tt.TruthType.OPAQUE, tt.ActorKind.HUMAN),              # opaque isolation
        ("r1", tt.TruthType.DERIVED, tt.ActorKind.AI),                # AI is never the blocker here
    ]
    for eid, target, actor in attempts:
        r = reg.promote(eid, target, actor)
        assert r["ok"] is False
        assert "promotion is disabled" in r["reason"]

    # every attempt is on the record, including the unknown-eid one
    refused = reg.blocked_promotions()
    assert len(refused) == len(attempts)
    assert [e["eid"] for e in refused] == [a[0] for a in attempts]

    # the unknown eid leaves no `from_type`: a read-only handle is no existence oracle
    unknown = refused[0]
    assert "from_type" not in unknown
    assert unknown["to_type"] == "declared"
    # a known eid does carry the transition it would have attempted
    assert refused[1]["from_type"] == "derived"
    assert refused[1]["to_type"] == "canonical"


def test_readonly_handle_is_not_rearmable(tmp_path):
    reg = _ro_reg(tmp_path)
    with pytest.raises(AttributeError):
        setattr(reg, "allow_promote", True)
    assert reg.allow_promote is False
    reg.add(_rec("r1", tt.TruthType.DERIVED))
    assert reg.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is False


def test_readonly_and_promoting_handles_share_the_log(tmp_path):
    """The deployment form: read-only handle for the agent, promoting handle for the review surface."""
    log_dir = tmp_path / "shared"
    agent = tt.TruthTypeRegistry(log_dir=log_dir, allow_promote=False)
    agent.add(_rec("r1", tt.TruthType.DERIVED))
    assert agent.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is False

    human = tt.TruthTypeRegistry(log_dir=log_dir)  # promoting handle, same directory
    assert human.promote("r1", tt.TruthType.DECLARED, tt.ActorKind.HUMAN)["ok"] is True

    reloaded = tt.TruthTypeRegistry(log_dir=log_dir)
    assert _must(reloaded, "r1").truth_type == tt.TruthType.DECLARED
    assert len(reloaded.audit_entries()) == 3          # add + refused promote + accepted promote
    assert len(reloaded.blocked_promotions()) == 1


def test_readonly_handle_serialization_unaffected(tmp_path):
    """The handle is construction-time only: it never reaches the record or the wire format."""
    ro = _ro_reg(tmp_path, name="ro")
    rw = tt.TruthTypeRegistry(log_dir=tmp_path / "rw")
    for reg in (ro, rw):
        reg.add(_rec("r1", tt.TruthType.DERIVED, statement="identical", parents=()))

    a = _must(ro, "r1").to_dict()
    b = _must(rw, "r1").to_dict()
    assert a == b
    assert "allow_promote" not in a
    assert tt.EpistemicRecord.from_dict(a).to_dict() == a

    # and the two directories hold the same record line, byte for byte
    assert ro.records_path.read_text(encoding="utf-8") == rw.records_path.read_text(encoding="utf-8")
