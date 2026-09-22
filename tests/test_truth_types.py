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
