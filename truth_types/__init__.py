"""truth-types — epistemic truth types for agent knowledge pipelines.

Four truth types (``derived ⊑ declared ⊑ canonical``, plus the isolated
``opaque``) with machine-enforced promotion rules and an append-only audit log,
so that AI-generated content cannot silently become a trusted conclusion.

Quickstart::

    from truth_types import ActorKind, EpistemicRecord, TruthType, TruthTypeRegistry

    reg = TruthTypeRegistry()                      # or TruthTypeRegistry(log_dir=Path("./audit"))
    reg.add(EpistemicRecord(eid="n1", truth_type=TruthType.DERIVED, actor_kind=ActorKind.AI))
    reg.promote("n1", TruthType.DECLARED, ActorKind.HUMAN)      # ok
    reg.promote("n1", TruthType.CANONICAL, ActorKind.HUMAN)     # blocked: level skipping

Public API: :class:`TruthType`, :class:`VerificationStatus`,
:class:`GraduationStatus`, :class:`ActorKind`, :data:`PROMOTION_EDGES`,
:func:`weakest_link`, :func:`check_promotion`, :class:`EpistemicRecord`,
:class:`TruthTypeRegistry`, :func:`default_log_dir`.

The English catalogue of human-readable runtime messages lives in
:data:`truth_types.core.MESSAGES` (presentation only, outside the stable
contract — see SPEC.md §7.8).
"""

from .core import (
    AUDIT_PATH_ENV,
    DEFAULT_AUDIT_FILENAME,
    MODE,
    PROMOTION_EDGES,
    RECORDS_FILENAME,
    ActorKind,
    EpistemicRecord,
    GraduationStatus,
    TruthType,
    TruthTypeRegistry,
    VerificationStatus,
    check_promotion,
    default_log_dir,
    weakest_link,
)

__version__ = "0.1.0"  # keep in sync with pyproject.toml (CI asserts they match)

__all__ = [
    "AUDIT_PATH_ENV",
    "DEFAULT_AUDIT_FILENAME",
    "MODE",
    "PROMOTION_EDGES",
    "RECORDS_FILENAME",
    "ActorKind",
    "EpistemicRecord",
    "GraduationStatus",
    "TruthType",
    "TruthTypeRegistry",
    "VerificationStatus",
    "__version__",
    "check_promotion",
    "default_log_dir",
    "weakest_link",
]
