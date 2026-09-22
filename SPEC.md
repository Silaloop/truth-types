# SPEC — Truth Types: Epistemic Classes for Agent Knowledge Pipelines

| Field | Value |
|:--|:--|
| Document | Specification for the `truth-types` reference implementation |
| Implementation | `truth-types` `0.1.0.dev0` (Python 3.10+, standard library only, Apache-2.0) |
| Status | v0 — specification complete; published as a draft for the first public release |
| Normative core | Sections 2, 3, 4, 5 and 7 specify rules and contracts; Sections 1, 6, 8 and 9 are informative |

**Normative language.** The key words MUST, MUST NOT, REQUIRED, SHALL, SHOULD, SHOULD NOT and MAY
are to be interpreted as described in RFC 2119. Where this document states behaviour of the
reference implementation, that statement is a description of code that exists and is exercised by
the test suite; where it states a rule for implementations, it is normative.

**Scope.** This document specifies a general-purpose mechanism for attaching an epistemic class to
knowledge objects and for machine-checking every attempt to raise that class. It contains
general-purpose concepts only. Material that is specific to one organisation's pipeline, review
process or terminology does not belong in this specification or in this library; it belongs in
downstream documentation that consumes this one.

---

## 1. Problem statement

### 1.1 The missing field

A knowledge object in a modern pipeline arrives from one of several sources: it was produced by a
language model, copied out of a document, restated by a person, or asserted by a person on the
basis of evidence. Once it is inside the pipeline, it is usually just text plus a pointer to where
it came from. What is normally *not* recorded is **how far it has been confirmed, by whom, and on
what basis**.

Pipelines therefore carry two kinds of provenance and only implement one of them:

- *origin* provenance — which URL, file, page or system the text came from (widely implemented);
- *status* provenance — whether a human has confirmed the statement, at which strength, and whether
  any step in the confirmation path was skipped (usually absent).

### 1.2 Failure modes of the missing field

- **F1 — Promotion by copy.** Unreviewed text is pasted into a document that is itself trusted.
  Trust is inherited through citation without any recorded act of review, and the reader cannot
  tell the difference between quoted evidence and generated filler.
- **F2 — No reviewer identity.** Even where review happens, nothing records who confirmed the
  statement, at which level, or against which source. The claim cannot be re-examined later.
- **F3 — Silent level-skipping.** A summariser's summary of a primary document is
  indistinguishable in the data model from the primary document itself. Distance from the original
  evidence is lost.
- **F4 — Diffusion of responsibility.** Every consumer downstream assumes somebody upstream
  confirmed the statement. No consumer can point at the confirmation, because there is none.
- **F5 — Unbounded inheritance.** A conclusion built on an unreviewed parent inherits the parent's
  weakness, but nothing in the data model says so; the weakness is not visible one hop later, let
  alone five hops later.

### 1.3 Why existing tooling does not close the gap

- **Content-safety classifiers** decide whether a statement *may exist* (toxicity, policy,
  PII). They are silent on how much the statement is *trusted*.
- **Ad-hoc status fields** (`"confidence": "high"`, `reviewed: true`) are free text: no order
  between values, no permitted transitions, no record of who set the value, no audit.
- **Data catalogs and lineage systems** track datasets, tables and jobs — the movement of data, not
  the review status of an individual statement.
- **Prompt-level conventions and editorial checklists** ("always mark uncertain claims") are
  instructions to a model or a person. They are not constraints, and violations are not detectable
  mechanically after the fact.

### 1.4 The design response

Attach a **truth type** to every knowledge object; restrict transitions between types to a small,
explicitly enumerated set of human-performed acts; require every object to cite its parents so that
weakness propagates through the graph; and append **every** attempt — accepted or rejected — to an
audit log, so that the history of how a statement acquired its status is queryable. Sections 2 to 7
specify this mechanism; Section 8 describes how to adopt it; Section 9 states what it does not do.

---

## 2. The truth-type lattice

### 2.1 The four values (normative)

| Type | Position | Meaning |
|:--|:--|:--|
| `derived` | bottom of the lattice | Machine-derived content. No human has confirmed it. AI output is always at this level. |
| `declared` | middle | A human has asserted the statement on the record: it is now attributable to a person. |
| `canonical` | top of the lattice | Human-confirmed and eligible to be consumed downstream as a conclusion. |
| `opaque` | outside the lattice | Material the pipeline deliberately does not model. Isolated: it MUST NOT be cited and MUST NOT be promoted. |

An implementation MUST represent these four values with exactly these string forms
(`"derived"`, `"declared"`, `"canonical"`, `"opaque"`), because they are the wire format of the
records and audit files.

### 2.2 The order

```
derived ⊑ declared ⊑ canonical            opaque — outside the lattice
```

The order is total and monotone over the three lattice members: `derived` is below `declared`,
which is below `canonical`. There is no order relation between `opaque` and any other value.

Two properties follow from this and are relied on throughout this specification:

1. **A single order key.** The three lattice values are ordered by a single numeric rank
   (`derived` = 0, `declared` = 1, `canonical` = 2). All comparisons — in the promotion checker, in
   the creation rule and in the publication gate — are performed on that rank, so the ordering
   cannot drift between code paths.
2. **A single edge set.** Only two transitions exist:

```
derived ──▶ declared ──▶ canonical
```

The edge set is enumerated explicitly (`PROMOTION_EDGES`, a frozen set of two pairs) rather than
derived from arithmetic on the ranks. Removing a level-skipping route is therefore a change to a
data structure, not a change to a comparison; there is no code path that can promote
`derived → canonical` directly, even if a caller asks for it.

### 2.3 Why the lattice is monotone

Monotonicity is what makes the type a *trust* level rather than an arbitrary label. If a value could
be raised and then lowered, "current type" would say nothing about the strongest review a statement
has ever received, and a downstream consumer reading `derived` could not distinguish "never
reviewed" from "reviewed and then walked back". Monotonicity also makes the type composable: a
child record can be assigned the weakest of its parents' types (rule 5, Section 3) without any
special cases, because "weakest" is well defined.

### 2.4 `opaque` as isolation, not as a fourth rung

`opaque` is not a level; it is a separate storage decision. It marks material that the pipeline
holds but does not model: raw captures, third-party payloads whose provenance cannot be
established, content whose obligations (licence, consent, attribution) are unmet, or input that has
been quarantined pending a decision.

Rules (normative):

- An `opaque` record MAY be created and stored. It conveys *no* evidentiary status.
- An `opaque` record MUST NOT be cited as a parent by any other record.
- An `opaque` record MUST NOT be promoted to any lattice value, and no lattice record MUST NOT be
  promoted to `opaque`.
- Consequently an `opaque` record can never pass the publication gate (rule 6): it has no lattice
  position, so it can never be at or above `declared`.

Why not a fourth rung:

- If `opaque` sat **above** `canonical`, promotion into it would be a route to high apparent
  authority without review — and statements would be parked there precisely when they are weakest.
- If `opaque` sat **below** `derived`, promotion out of it would launder unmodelled material into
  the lattice, giving an ordinary record a defensible-looking parent.
- Modelling it as isolation removes both routes, because no transition edge touches it in either
  direction. A statement that is not modelled is not on the same axis as a statement that is
  modelled and reviewed to some degree.

### 2.5 Comparison with a four-rung model (informative)

| Design | Consequence |
|:--|:--|
| Four ordered rungs, `opaque` at the bottom | Unmodelled material becomes a legitimate parent; the chain looks continuous but the weakest rung is not evidence at all. |
| Four ordered rungs, `opaque` at the top | Unreviewed material can be parked at the highest apparent authority. |
| Three rungs + isolation (this specification) | Unmodelled material is stored but cannot be referenced or promoted, so it can neither support nor be supported by a lattice record. |

### 2.6 Relationship to human-facing fact/inference tagging (informative)

A fact/inference tag records a *human's judgement* about what a statement is. A truth type records
the *machine-checkable status* of that statement: who promoted it, to what, whether a level was
skipped, and which upstream records it cites. The two layers are complementary and answer different
questions; a pipeline may carry both without either being redundant.

---

## 3. Promotion rules

Six rules are enforced. For each: the rule, the enforcement point in the reference implementation,
the observable effect, and the audit behaviour. All six are machine-checked; none depends on a
caller's discipline.

### 3.1 Rule 1 — only humans may promote

**Rule.** A promotion MUST be performed by an actor of kind `human`. AI output MUST remain
`derived`. Where an AI actor requests a stronger type at creation, the implementation MUST coerce
the record to `derived` rather than reject it, and MUST record the coercion.

- Enforcement: `add()` (coercion at creation), `check_promotion()` (actor check on promotion).
- Observable: `add()` returns `{ok: True, reason: "created", record: {...}}` with
  `record.truth_type == "derived"`; the requested level is not stored anywhere on the record.
- Audit: the coercion appends an `ai_coerce` line; the promotion attempt appends a `promote` line
  with `ok: false` and a reason naming the actor rule.

### 3.2 Rule 2 — no level skipping

**Rule.** The only permitted transitions are `derived → declared` and `declared → canonical`. A
promotion along any other pair of distinct lattice values MUST be rejected, and the creation of a
record whose type exceeds its weakest parent MUST be rejected.

- Enforcement: the enumerated edge set `PROMOTION_EDGES` in `check_promotion()`; the weakest-link
  comparison in `add()`.
- Observable: `promote()` returns `{ok: False, reason: ...}`; `add()` returns
  `{ok: False, reason: ...}` and the record is not stored.
- Audit: both refusals append a line with `ok: false`.

### 3.3 Rule 3 — no downgrading

**Rule.** A promotion MUST move strictly upward. A request whose target is below the record's
current type MUST be rejected. (A request whose target *equals* the current type is also rejected,
as a no-op.)

- Enforcement: the rank comparison in `check_promotion()`.
- Observable: `{ok: False, reason: ...}`; the stored record is unchanged. Implementations of this
  specification that need to withdraw a record MUST NOT use a downgrade; see Section 9.

### 3.4 Rule 4 — `opaque` is isolated

**Rule.** The isolation rules of Section 2.4 MUST hold: `opaque` MUST NOT be a promotion source or
target, and MUST NOT be cited as a parent. Isolation is enforced on both sides of every edge.

- Enforcement: an explicit check in `check_promotion()`; the parent check in `weakest_link()`.
- Observable on promotion: `{ok: False, reason: ...}`.
- Observable on citation: a raised `ValueError` from `add()` — see boundary B2 in Section 3.7.
- Note: an AI actor cannot produce an `opaque` record either, because rule 1 coercion applies to
  every non-`derived` requested type, including `opaque`.

### 3.5 Rule 5 — creation is the weakest link

**Rule.** For a record with a non-empty parent list, the type declared at creation MUST **equal**
the weak set of its parents: `truth_type = min(parents)`. This is an equality, not an upper bound.
A child may neither be created above its weakest parent (rejected as a level-skipping creation) nor
below it (rejected as a downgrade creation). Every cited parent MUST already exist, so the
provenance chain is never broken. A record with an empty parent list is a root record and is not
subject to this rule.

- Enforcement: `weakest_link()` called from `add()`; parents that are not present in the registry
  are rejected before the comparison.
- Observable: `{ok: False, reason: ...}` distinguishing a level-skipping creation from a downgrade
  creation, and a missing-parent rejection when the chain is broken. A root record is accepted.
- Rationale for equality rather than an upper bound: an upper bound would let a caller create a
  child at the weakest parent's level *or below*, which reintroduces downgrade-by-construction;
  equality keeps the invariant "a record's type is exactly the strength its evidence supports" and
  makes every strengthening visible as a promotion act.

### 3.6 Rule 6 — the publication gate

**Rule.** A record MUST NOT be presented downstream as a conclusion unless its type is at or above
`declared` **and** it cites at least one parent. Both conditions are required: a root record at
`canonical` fails the gate for lack of parents, and a `derived` record with parents fails for
insufficient type.

- Enforcement: `check_on_screen()`, a query, not a state change.
- Observable: `{ok: True, reason: "ok"}` or `{ok: False, reason: <all failing conditions>}`. The
  gate reports every failing condition, not only the first.
- Rationale: this is the rule that gives the lattice teeth. Promotion records what is known;
  the gate decides what may be *said*.

### 3.7 Evaluation order, determinism and the two implementation boundaries

**Determinism (normative).** The promotion checker evaluates the conditions of rule 4, then rule 3's
no-op case, then rule 3's downgrade case, then rule 2's edge membership, and finally rule 1's actor
check, returning on the first failure. A given `(current, target, actor)` triple therefore always
produces the same reason, and the reason names one rule, not several. Consumers MUST NOT parse
reasons, but the determinism makes rejection counts stable in a monitoring pipeline.

**Static vs runtime checkability (informative).**

| Check | Decidable without reading content | Needs runtime input |
|:--|:--|:--|
| Edge membership, rank comparison, no-op | yes — structural | — |
| Weakest-link creation | yes — given the parents' stored types | parent existence |
| Actor restriction | — | `actor_kind`, supplied by the caller |
| Publication gate | — | the stored record's type and parent list |
| `opaque` isolation | yes — structural | — |

**Fail-closed posture (normative).** Every rejected attempt MUST produce a decision object *and* an
audit line. There is no bypass flag, no `force` parameter and no silent acceptance path. A caller
that cannot handle a rejection MUST treat the returned `{ok: False}` / `{allowed: False}` as an
error condition; ignoring it is not a supported use.

Two boundaries of the v0 implementation are recorded here because they are observable and are
candidates for convergence in v1. Both are stated as facts about `0.1.0.dev0`, not as intended
behaviour.

- **B1 — an AI record cannot cite a stronger parent.** Coercion (rule 1) is applied *before* the
  weakest-link comparison (rule 5). An AI request that cites a `declared` parent is first coerced
  to `derived`, and then fails the equality check against the parents' weak set, so the record is
  rejected — whether the AI asked for `declared` or honestly asked for `derived`. Consequence: an
  AI-produced note cannot be attached as a child of a human-declared statement; AI records may only
  cite parents whose weak set is `derived`. Workarounds within v0: have the human create the
  linking record, or store the machine note as a root record with a `source_ref`. Convergence:
  compute the creation type as the weaker of the coerced type and the parents' weak set and store
  that, or keep rejecting and document it as intended. v1 will choose one; v0 rejects.
- **B2 — an `opaque` parent raises instead of returning a decision object.** The isolation check on
  citation (`weakest_link()`) raises `ValueError`, and `add()` does not catch it, so this single
  rejection path is an exception rather than a `{ok: False, reason: ...}` result. Every other
  rejection in the library is a decision object. Consumers MUST therefore wrap `add()` in a
  `try/except ValueError` when an `opaque` parent is possible. Convergence: convert the raise into
  a rejection object so that `add()` is uniformly total. Note that the same helper's empty-parent
  raise is unreachable from `add()` (the check is skipped when the parent list is empty), so a root
  record never raises.

### 3.8 What each rule costs (informative)

| Rule | Cost to the pipeline | What it buys |
|:--|:--|:--|
| 1. Humans only | every promotion needs a human act | AI output can never self-authorise |
| 2. No level skipping | two review steps, not one, for full strength | distance from evidence stays visible |
| 3. No downgrading | mistakes are corrected forward, not erased | the type is monotone, hence readable |
| 4. Isolation | unmodelled material must be handled explicitly | no laundering of unmodelled text |
| 5. Weakest link | every record needs citations | weakness propagates, never hides |
| 6. Publication gate | conclusions need both a type and parents | what is shown has a traceable basis |

---

## 4. Isolation guarantee

### 4.1 Statement

**Guarantee (property of the reference implementation, normative for v0 unless a boundary
condition in 4.6 applies):** a record produced by an AI actor can acquire the type `canonical` only
after **at least two promotion acts attributed to human actors**, passing through the observable
intermediate state `declared`.

This property corresponds to the *Isolation* theorem of TR-E-001 (§6.2), where it is formalized
and machine-checked; here it is realized as API rules rather than proofs, with this realization's
assumptions stated in 4.2.

### 4.2 Assumptions

The guarantee is conditional on all of the following:

1. `actor_kind` on each call is supplied truthfully by the caller. The library does not
   authenticate actors; it enforces the *contract*, not the *identity*.
2. Promotions go through the API. The records and audit files are not edited out of band.
3. Records are not injected by loading a hand-written records file: loading accepts stored state
   without re-validation (Section 7.7).
4. The guarantee counts *acts*, not people. Two promotions performed by the same human satisfy it;
   reviewer independence is out of scope (Section 4.6).

### 4.3 Argument sketch

1. At creation, coercion pins every AI-authored record to `derived` (rule 1). An AI record
   therefore starts at rank 0.
2. The permitted transitions are exactly `derived → declared` and `declared → canonical` (rule 2):
   two edges, no shortcut through a computed comparison.
3. Every permitted transition requires an actor of kind `human` (rule 1).
4. Therefore the minimum path from an AI-authored record to `canonical` is two human acts, and the
   intermediate state between them is `declared`.
5. The intermediate state is observable: each promotion appends an audit line carrying
   `from_type` and `to_type`, and the first human promotion of a record stamps
   `attestation_ref` with `human-promote:<timestamp>` when no attestation is present.

The guarantee is therefore a consequence of the creation rule, the enumerated edge set and the
actor restriction — it does not depend on any separate enforcement mechanism that could be
forgotten in a code path.

### 4.4 Implementation mapping

| Element | Where |
|:--|:--|
| AI output pinned to `derived` | creation-time coercion in `add()` (with an `ai_coerce` audit line) |
| Two and only two transitions | `PROMOTION_EDGES` |
| Human-only transitions | the actor clause of `check_promotion()`, reached last |
| Observable intermediate state | `promote()`'s audit line (`from_type`, `to_type`) and the `attestation_ref` stamp |
| Attempts recorded even when refused | audit append on both outcomes of `promote()` |

### 4.5 Test references

The property is exercised by the test suite in `tests/test_truth_types.py`:

| Test | What it demonstrates |
|:--|:--|
| `test_isolation_scenario` | an AI record requesting `canonical` is stored as `derived`; the single-step jump to `canonical` is refused; the two-step human path succeeds |
| `test_ai_forced_derived` | coercion occurs, and exactly one `ai_coerce` entry is written |
| `test_promotion_legal_edges` | both legal edges are accepted |
| `test_promotion_skip_rejected` / `test_promotion_downgrade_rejected` / `test_promotion_opaque_rejected` / `test_promotion_ai_rejected` | each refusal condition |
| `test_promote_blocked_recorded` / `test_promote_ai_rejected_and_recorded` | a refused promotion is queryable afterwards via `blocked_promotions()` |
| `test_persistence_reload` | types and audit history survive a reload |

### 4.6 Boundary conditions under which the guarantee does not hold

1. **Untrusted actor declarations.** If model-driven code can call `promote(..., ActorKind.HUMAN)`,
   the guarantee is void. The library is a contract layer, not a sandbox: it makes the honest path
   the easy path and the dishonest path visible in the audit log, and nothing more.
2. **Human-authored root records.** A human actor may create a root record directly at any lattice
   level, including `canonical`, with no promotion history at all. The guarantee constrains *paths*
   from AI output, not authors. The compensating control is rule 6: such a record fails the
   publication gate for lack of parents until it is given citations, and any citation it is given
   must match its weakest parent.
3. **Out-of-band records.** Records injected into the JSONL files by other means are accepted on
   load; the file is storage, not a validator.
4. **Content truth is not certified.** Two human promotions make a statement `canonical`, not true.
   The guarantee is about review provenance.
5. **Reviewer independence.** One human may perform both promotions; the audit shows two acts by
   the same attestation trail but the library does not require two distinct people.
6. **Retraction is not expressible.** Because downgrading is forbidden and `opaque` is outside the
   lattice, v0 has no way to mark an existing lattice record as withdrawn (Section 9.1).

---

## 5. Source grading and disclosure-grade sources

### 5.1 Purpose

Truth types say how far a statement has been *reviewed*. They say nothing about the strength of the
*artefact* the statement rests on. A pipeline that treats a social-media post and a regulator-filed
annual report as equally good evidence will produce canonical records whose evidentiary basis
varies by orders of magnitude. Source grading closes that gap with a second, orthogonal axis.

### 5.2 The disclosure-grade ladder (normative when the field is implemented)

```
disclosure-grade  >  authoritative institution  >  media report  >  self-declared statement
```

| Grade | Definition | Typical artefacts |
|:--|:--|:--|
| **disclosure-grade** | Regulated disclosure produced under an audited process, signed by accountable officers, filed with or published under a regulator's regime; misstatement carries legal consequence | listed-company annual and interim reports, exchange filings, prospectuses, regulatory registrations and statutory accounts |
| **authoritative institution** | Publication by an institution whose process is documented and whose editorial or technical accountability is institutional, but which is not itself audited disclosure | standards bodies, statistical agencies, court records, peer-reviewed literature, material published under a named institutional review process |
| **media report** | Journalism or secondary reporting that follows an editorial process, resting on sources that the reader cannot inspect | news articles, trade press, newsletters with editorial oversight |
| **self-declared statement** | A claim made by an interested party about itself, with no independent process attached | corporate self-description, vendor claims, statements in interview or presentation without underlying artefacts |

**Disclosure-grade is the top rung by construction**, not by preference: it is the only rung at
which the artefact is prepared under an audit regime, attributed to accountable signatories, and
subject to legal consequence if wrong. Calibrating a pipeline's evidence discipline against that
rung — rather than against self-reported claims — makes the ceiling of evidential strength an
auditable artefact instead of an opinion, and gives reviewers a rule they can apply without
judging an author's credibility.

### 5.3 The field

When implemented, an implementation MUST carry the grade as a top-level field on the record:

| Field | Type | Values | Default |
|:--|:--|:--|:--|
| `source_grade` | string | `disclosure`, `authoritative`, `media`, `self_declared` | empty string (unspecified) |

The value names the grade of the artefact identified by `source_ref`. A record MAY leave the grade
unspecified; an unspecified grade MUST be treated as no better than the lowest rung for review
purposes, and MUST NOT be treated as disclosure-grade.

### 5.4 How a grade interacts with the other fields

| Field | Answers the question | Enforced? |
|:--|:--|:--|
| `source_grade` | How accountable is the artefact this rests on? | Rules below, once implemented |
| `truth_type` | Who confirmed it, and at which level? | Yes — rules 1–6 (Section 3) |
| `verification` | What verification outcome was recorded? | No — a fixed value set, stored and audited, semantics defined by the application |
| `graduation` | At which stage of its lifecycle is the claim? | No — a fixed value set, stored and audited, semantics defined by the application |

Rules (normative when implemented):

1. A grade MUST NOT raise a truth type. Only a promotion act (Section 3) changes `truth_type`.
2. The grade SHOULD be recorded at creation and MUST be preserved unchanged across promotion.
3. A promotion to `canonical` for a claim about the world SHOULD rest on at least one artefact of
   grade `disclosure` or `authoritative`. `media` and `self_declared` sources MAY support
   `derived` and `declared` records.
4. When two sources conflict, the higher-grade artefact SHOULD be promoted first; the
   lower-grade item SHOULD NOT be raised past `declared` while the conflict stands.
5. A grade never expires by itself. Staleness is expressed through the `verification` and
   `graduation` fields, whose semantics the application defines.

### 5.5 Implementation status (statement of fact)

`source_grade` is **not implemented** in the reference implementation `0.1.0.dev0`:
`EpistemicRecord` has no such field, and no rule consults a grade. In v0 the carriers of source
identity are `source_ref` (identity of the artefact) and `note` (free text on the record and on a
promotion).

Consequences for implementers:

- An implementation that needs machine-readable grading before v1 MUST carry the field downstream
  of this library (for example, by storing the grade alongside the record in its own store, keyed
  by `eid`).
- An implementation MUST NOT assume the registry will verify, propagate or audit a grade.
- The rules in 5.4 describe the intended behaviour of v1 and are listed here so that downstream
  conventions do not diverge from a future field definition.

### 5.6 Why an explicit top-rung definition matters (informative)

Ladders without a defined top rung degrade into taste: reviewers place anything they consider
"good" at the top, and the top rung then means "I trust this author". Naming the top rung
*disclosure-grade* and tying it to an external regime — regulated, audited, legally consequential —
makes the strongest rung verifiable by a third party and keeps the remaining rungs in their proper
place as fallbacks rather than equivalents.

---

## 6. Related work

### 6.1 Positioning

Several independent lines of work have converged on the same position: that knowledge used by
agents needs an explicit epistemic type, that machine-produced content must be distinguishable from
human-endorsed content, and that the distinction should be enforced mechanically rather than by
convention. This document records the four works that most directly shaped that position, and
states for each what this implementation does and does not cover. **They are related work only —
not dependencies, not endorsements, and not affiliations**: no code or data is copied from
them; quotations are short and attributed, and nothing here should be read as a claim to implement
their complete scope. Where the rules this library enforces correspond directly to a formalized
property — the promotion and isolation fragment of TR-E-001 — that correspondence is stated in its
entry below.

### 6.2 Citations

**OIDA.** Bottino, Ferrero, Dosio, and Beneventano. *Retrieval Is Not Enough: Why Organizational AI
Needs Epistemic Infrastructure.* arXiv:2604.11759v2, 2026-04-13 (v2 2026-05-22).
<https://arxiv.org/abs/2604.11759>

- Position: the ceiling for organisational AI is not retrieval fidelity but *epistemic* fidelity —
  whether commitment strength, contradiction state and organisational ignorance can be represented
  as computable properties.
- Scope: knowledge objects carrying an epistemic class, class-specific importance decay, signed
  contradiction edges, a deterministic score-maintenance engine with stated convergence
  conditions, and a primitive for modelled ignorance ("what the organisation does not know") whose
  urgency *increases* over time.
- What this implementation takes: the diagnosis that typing knowledge objects is the load-bearing
  step, and the use of a small fixed class set.
- What it does not cover: no importance decay, no contradiction edges, no score maintenance, no
  modelled-ignorance primitive, no graph engine. This library is a single-module enforcement layer
  for the promotion and citation rules alone.

**WMGF.** Smith, C. *World Model Governance Framework (WMGF): Ten Ingredients, Nineteen Structural
Primitives, and the 190 Control Objectives of a Governable World Model.* WMGF-001 v0.5.0, working
draft, GrytLabs Dynamics Inc., 2026-07-06. DOI: 10.5281/zenodo.21220866. CC-BY 4.0.

- Position: governance of a world-model-based system is the practice of making structure visible —
  naming what a system may express, what may verify it, and who is accountable for it.
- Scope: a framework coupling a ten-component model with nineteen structural primitives, yielding
  190 named control objectives; among them an actor-boundary control stating that actor type
  ceilings are enforced and that AI cannot hold accountable authority.
- What this implementation takes: the separation between capability and accountable authority,
  expressed here as the rule that only human actors may promote.
- What it does not cover: no component model, no primitive set, no control-objective matrix, no
  evidence-obligations or authority-mapping machinery. This library implements three rules that a
  framework of that kind would require, and nothing else of it.

**AGL-1.** Sure, R. W. *AGL-1: The Enterprise AI Governance Layer as a Control Plane for Trusted
Enterprise Intelligence.* arXiv:2607.03516, 2026-07-03. <https://arxiv.org/abs/2607.03516>

- Position: the enterprise challenge should be restated as *governed intelligence operations*, and
  addressed by a control plane rather than by per-application policy.
- Scope: a vendor-neutral reference model whose concerns include authorising execution, retaining
  context lineage, governing durable memory, detecting stale or conflicting knowledge, constraining
  agentic execution, and producing audit-ready evidence across distributed AI assets.
- What this implementation takes: the requirement that governance evidence be produced
  continuously rather than assembled retrospectively — here, the append-only audit log.
- What it does not cover: no execution authorisation, no context lineage across systems, no memory
  governance, no staleness or conflict detection, no policy engine, no observability. This library
  governs one field of one record type.

**TR-E-001.** Smith, C. *Compiling Organizational Intelligence: A Formal Mapping Between Governance
Infrastructure and Compiler Theory.* TR-E-001 v1.0, GrytLabs Dynamics Inc., 2026-07-16.
DOI: 10.5281/zenodo.21390128. CC-BY 4.0.

- Position: governance infrastructure for organizational intelligence can be treated as a type
  system over records, and the central correctness question is whether epistemic status is
  preserved across state transitions.
- Scope: a formal calculus (lambda-DLP) whose metatheory is machine-checked in Lean 4 — including
  the headline *Isolation* result: approximate (AI-generated) data cannot reach canonical
  (human-endorsed) status without traversing a human gate, at least two explicit human promotion
  steps through an observable intermediate state — together with a weakest-link creation rule
  ("no record more authoritative than its least authoritative cited input") and a graph-level
  anti-collapse theorem.
- What this implementation takes: the rule structure itself — a small ordered set of truth types,
  a two-edge promotion path restricted to human actors, weakest-link creation, and the resulting
  two-human-step isolation property — re-expressed as dependency-free API rules rather than
  proofs. Section 4 states the guarantee this realization provides; 4.2 states its assumptions.
- What it does not cover: no formal calculus, no machine-checked proofs (this implementation
  carries a twenty-case test suite instead), no co-signature by two *distinct* human identities,
  no authority-chain or constraint machinery, no compilation pipeline. This library enforces the
  promotion fragment only.

### 6.3 What is specific to this work (informative)

The works above are frameworks, formalisms or reference architectures. What this document
adds is deliberately narrow: a *runnable*, dependency-free implementation of the promotion and
isolation rules, where

- the rule set is small enough to be read in full and audited line by line;
- enforcement happens at the API boundary, so violations are refused before they reach storage;
- refusals are first-class data (a decision object plus an audit line) rather than log noise;
- the isolation property follows from the creation and transition rules rather than from a separate
  mechanism.

---

## 7. API overview

### 7.1 Public surface (normative)

The package MUST export exactly these names; they are the stable surface referred to in 7.8:

`TruthType`, `VerificationStatus`, `GraduationStatus`, `ActorKind`, `EpistemicRecord`,
`TruthTypeRegistry`, `weakest_link`, `check_promotion`, `default_log_dir`, `PROMOTION_EDGES`,
`AUDIT_PATH_ENV`, `RECORDS_FILENAME`, `DEFAULT_AUDIT_FILENAME`, `MODE`.

### 7.2 Value types

| Type | Values (string form) |
|:--|:--|
| `TruthType` | `derived`, `declared`, `canonical`, `opaque` |
| `ActorKind` | `human`, `ai` |
| `VerificationStatus` | `unverified`, `vpending`, `verified`, `vfailed`, `cannot_verify` |
| `GraduationStatus` | `asserted`, `investigating`, `corroborated`, `gverified`, `graduated` |

`VerificationStatus` and `GraduationStatus` are stored and audited; no rule in this specification
consults them (Section 5.4).

### 7.3 Callable signatures

Signatures are given as they exist in `0.1.0.dev0`; annotations are part of the documented surface.

| Callable | Signature | Contract |
|:--|:--|:--|
| `weakest_link` | `weakest_link(types: Iterable[TruthType]) -> TruthType` | Pure. Returns the lowest-ranked lattice type in `types`. Raises `ValueError` on an empty input or when any input is `opaque`. |
| `check_promotion` | `check_promotion(current: TruthType, target: TruthType, actor: ActorKind) -> dict` | Pure predicate, fail-closed. Returns `{allowed, reason}`; never raises, never mutates. |
| `default_log_dir` | `default_log_dir() -> Path` | Resolves the default directory (7.6). Pure w.r.t. the filesystem apart from reading the environment. |
| `TruthTypeRegistry` | `TruthTypeRegistry(log_dir: Optional[Path] = None)` | Creates the directory if needed and loads existing records. |
| `add` | `add(rec: EpistemicRecord) -> dict` | Applies the creation rules. Returns `{ok: True, reason: "created", record: <dict>}` or `{ok: False, reason: <str>}` with no `record` key. Raises `ValueError` in the `opaque`-parent case (B2). |
| `promote` | `promote(eid: str, target: TruthType, actor: ActorKind, note: str = "") -> dict` | Applies the promotion rules. Returns `{ok, reason}` in every case, including an unknown `eid`. |
| `check_on_screen` | `check_on_screen(eid: str) -> dict` | Publication gate (rule 6). Returns `{ok, reason}`; does not mutate. |
| `get` | `get(eid: str) -> Optional[EpistemicRecord]` | The stored record, or `None`. |
| `audit_entries` | `audit_entries() -> list[dict]` | Every audit line, in file order. |
| `blocked_promotions` | `blocked_promotions() -> list[dict]` | The audit lines with `action == "promote"` and `ok == False`. |
| `EpistemicRecord.to_dict` | `to_dict() -> dict` | JSON-ready dict; enum values become strings, `parents` becomes a list. |
| `EpistemicRecord.from_dict` | `from_dict(d: dict) -> EpistemicRecord` | Inverse of `to_dict`; missing optional keys fall back to their defaults. |

### 7.4 Record schema

| Key | Type | Default | Meaning |
|:--|:--|:--|:--|
| `eid` | string | required | Stable identifier of the record; unique within a registry. |
| `truth_type` | string | required | One of the four truth types. |
| `verification` | string | `"unverified"` | Recorded verification outcome. |
| `graduation` | string | `"asserted"` | Recorded lifecycle stage. |
| `actor_kind` | string | `"human"` | Who created the record. |
| `parents` | list of strings | `[]` | `eid`s of the records this one cites. |
| `source_ref` | string | `""` | Identity of the source artefact (URL, filing, page). |
| `attestation_ref` | string | `""` | Attestation stamp; set to `human-promote:<timestamp>` by the first human promotion when empty. |
| `statement` | string | `""` | The statement itself. |
| `note` | string | `""` | Free text. |

An implementation MUST NOT require any key beyond `eid` and `truth_type` (plus `actor_kind` where
rule 1 must be applied), and MUST tolerate additional keys when reading (Section 7.8).

### 7.5 Audit-line schema

Every `add()` and every `promote()` call appends to the log, one JSON object per line. An
accepted creation by an AI actor that requested a stronger type appends two lines — `ai_coerce`
followed by `add` — so the log records both the request and the stored outcome:

| Key | Type | Present | Meaning |
|:--|:--|:--|:--|
| `ts` | string | always | Local timestamp, `YYYY-MM-DDTHH:MM:SS`, second resolution, no timezone offset (Section 9.1). |
| `action` | string | always | `add`, `promote` or `ai_coerce`. |
| `eid` | string | always | The record the attempt concerned. |
| `ok` | boolean | always | Whether the attempt was accepted. |
| `detail` | string | always | Human-readable explanation. |
| `from_type` / `to_type` | string | `promote` only | The transition that was attempted. |

`action`, `eid`, `ok`, `from_type` and `to_type` are language-neutral and stable. `detail` is
human-readable and is not part of the stable contract (Section 7.8).

### 7.6 Log directory resolution

1. The `log_dir` argument of `TruthTypeRegistry`, when given.
2. Otherwise the `TRUTH_TYPES_AUDIT_PATH` environment variable: a value ending in `.jsonl` is
   treated as the audit file itself and its parent directory is used; any other value is treated as
   the directory.
3. Otherwise the current working directory, so the audit log lands at
   `./truth_types_audit.jsonl`.

Two files are created inside the resolved directory: records in `truth_types.jsonl`, audit lines in
`truth_types_audit.jsonl`. Both are UTF-8, one JSON object per line, with non-ASCII characters
written literally (`ensure_ascii=false`).

### 7.7 On-disk semantics

- **Append-only.** Records are never rewritten in place. A promotion appends a new record line; a
  reload takes the most recent line for each `eid` (last-write-wins), so the file is the full
  history of every state a record has held.
- **No overwrite, no deletion.** Adding a second record with an existing `eid` is refused; there is
  no delete operation and no compaction.
- **No re-validation on load.** Records read from the file are accepted as stored; the rules of
  Section 3 are not re-applied (Section 4.6.3).
- **Unbounded growth.** Neither file is rotated or truncated (Section 9.1).

### 7.8 Compatibility promise (normative)

After the first public release:

- The exported names in 7.1 MUST NOT be removed or renamed.
- The four truth-type string values, the `ActorKind` string values and the audit keys `action`,
  `eid`, `ok`, `from_type`, `to_type` MUST NOT be renamed; they are the wire format.
- New optional fields MAY be added to records and audit lines. Consumers MUST ignore unknown keys,
  and MUST NOT interpret a missing optional key as an error.
- The rule semantics of Section 3 MUST NOT be weakened. Rules MAY be added, and a rule MAY be
  tightened only in a release that documents the change as breaking.
- Human-readable `reason` and `detail` strings are **not** part of the contract: in v0 they come
  from a single English message catalogue (`truth_types.core.MESSAGES`, presentation only), which
  MAY be reworded or re-translated in any release without notice.
  Consumers MUST branch on structured fields (`ok`, `allowed`, `action`, `from_type`, `to_type`),
  never on message text.

---

## 8. Adoption guide

### 8.1 The integration pattern

```
knowledge object enters the pipeline
        │
        ├─ produced by a model ──────────────▶ add(derived)         [coercion guarantees this]
        └─ asserted by a person ─────────────▶ add(declared | canonical as appropriate)
                                                     │
                                                human review
                                                     │
                              promote(declared) ─────┴────▶ promote(canonical)
                                                     │
                                          check_on_screen() gate
                                                     │
                                        conclusion leaves the pipeline
```

The registry sits at the point where knowledge objects are created, and at the point where a human
is asked to sign off on them. Nothing else in the pipeline needs to change: consumers keep reading
the same objects, and gain one extra field (`truth_type`) plus a queryable history.

### 8.2 A minimal worked example

```python
from truth_types import ActorKind, EpistemicRecord, TruthType, TruthTypeRegistry

reg = TruthTypeRegistry(log_dir="./tt-audit")          # or omit: TRUTH_TYPES_AUDIT_PATH, else cwd

# 1. Model output enters. A requested "canonical" is coerced: AI output is always derived.
reg.add(EpistemicRecord(
    eid="n:inv-18pct",
    truth_type=TruthType.CANONICAL,                    # requested by the producer
    actor_kind=ActorKind.AI,                           # ... but stored as derived
    statement="Channel inventory grew 18% quarter-on-quarter",
    source_ref="https://example.com/filing#p42",
))
# -> {"ok": True, "reason": "created", "record": {... "truth_type": "derived" ...}}
#    and one "ai_coerce" line in the audit log

# 2. A human confirms it once: derived -> declared, one step, audited.
reg.promote("n:inv-18pct", TruthType.DECLARED, ActorKind.HUMAN, note="checked against filing")
# -> {"ok": True, "reason": ...}; the record now carries an attestation stamp

# 3. An agent tries to raise it further: refused and recorded, not silent.
reg.promote("n:inv-18pct", TruthType.CANONICAL, ActorKind.AI)
# -> {"ok": False, "reason": ...}

# 4. A second human review raises it to canonical.
reg.promote("n:inv-18pct", TruthType.CANONICAL, ActorKind.HUMAN)
# -> {"ok": True, "reason": ...}

# 5. Later, after the fact: what was refused, and why.
blocked = reg.blocked_promotions()                     # [{"action": "promote", "ok": False, ...}]
```

Citation chains work the same way, and the weakest link is enforced at creation:

```python
# a source record, created by a human
reg.add(EpistemicRecord(eid="s:fy25-p42", truth_type=TruthType.DECLARED,
                        actor_kind=ActorKind.HUMAN, statement="FY25 filing p.42"))

# a child at exactly the weakest parent's level: accepted
reg.add(EpistemicRecord(eid="c:inv", truth_type=TruthType.DECLARED,
                        actor_kind=ActorKind.HUMAN, parents=("s:fy25-p42",),
                        statement="Inventory +18% QoQ"))

# a child above its weakest parent: refused (level-skipping creation)
reg.add(EpistemicRecord(eid="c:bad", truth_type=TruthType.CANONICAL,
                        actor_kind=ActorKind.HUMAN, parents=("s:fy25-p42",)))
# -> {"ok": False, "reason": ...}

# publication gate: a conclusion needs type >= declared AND at least one parent
reg.check_on_screen("c:inv")            # -> {"ok": True,  "reason": "ok"}
reg.check_on_screen("s:fy25-p42")       # -> {"ok": False, "reason": ...}  (declared, but no parents)
```

### 8.3 What changes for you

**Who should use this.**

- Teams building RAG or agent pipelines where model output and human-reviewed content flow through
  the same channels and end up in the same documents.
- Analysts and researchers whose output mixes quoted evidence with generated synthesis, and who
  need to answer "where did this sentence come from?" months later.
- Anyone who must show an auditor, a client or a regulator *how* a statement was confirmed — not
  only what it says.
- Library authors and platform teams looking for a small, dependency-free primitive rather than a
  service.

**The pain you have now → what changes.**

| Today | With a truth type on every object |
|:--|:--|
| Unreviewed text becomes "fact" by being copied into a trusted document. | Copying changes nothing: the type travels with the statement and only a human promotion changes it. |
| "Who confirmed this, and when?" is answered by memory or by archaeology in chat history. | Answered by a query over the audit log, including refusals. |
| A summary of a summary looks like a summary of the primary source. | Distance from evidence is visible: the lattice records each review step, one at a time. |
| A claim built on weak evidence looks exactly as strong as its parent's text. | The weakest link is enforced at creation: a child cannot outrank its weakest parent. |
| Guardrail tools tell you a text is *allowed*, not how far it is *trusted*. | The type is orthogonal to content policy and composes with it. |
| "Reviewed" is a boolean, or a free-text `confidence` string. | The type has an order, an enumerated transition set and an audit trail. |

**Comparison with nearby options.**

| Mechanism | What it decides | Why it is not this |
|:--|:--|:--|
| Content-safety / moderation filters | whether a statement may exist | says nothing about how far it is trusted |
| Free-text status fields (`confidence: high`) | nothing mechanically | no order, no permitted transitions, no audit |
| Data-catalog lineage | how datasets and jobs relate | dataset-level, not per-statement review status |
| Editorial checklists and prompt conventions | what a person or model *should* do | violations are not detectable after the fact |
| This library | whether a promotion or citation is legal, and records every attempt | requires each statement to carry a type and cite its parents |

**What is measurable.**

- **Refusals intercepted** — the size of `blocked_promotions()`, and the breakdown by attempted
  transition (`from_type` → `to_type`), both available from structured audit fields. A number
  that rises without incidents usually means the pipeline is testing its own boundaries; one that is zero over a long period deserves a
  check that promotions are actually being attempted through the API.
- **Audit coverage** — every `add()` and `promote()` call produces at least one audit line, and a
  coerced creation produces two (`ai_coerce`, then `add`); the expected line count for a workload is
  therefore computable, and any shortfall means a writer is bypassing the API.
- **Time to promote** — the interval between a record's `add` line and its first successful
  `promote` line, computed from the audit timestamps; a proxy for review latency per record class.
- **Integration size** — under 20 lines for a first integration: construct a registry, add records
  where objects are created, promote where reviews happen.
- **Time to answer "why is this a conclusion?"** — one query filtered by `eid` over
  `audit_entries()`, instead of searching documents and conversations.

### 8.4 Auditing and querying

- Query by record: filter `audit_entries()` by `eid` to reconstruct the full history of a statement
  — creation, each promotion attempt, each refusal.
- Monitor refusals: `blocked_promotions()` is the review queue for governance: every entry is an
  attempt that a rule stopped.
- Distinguish refusals using structured fields only: a refused entry whose `from_type` → `to_type`
  is a legal edge (for example `derived` → `declared`) was stopped by the actor rule, which usually
  means an automated job is trying to promote and should be changed; a refused step to a type that
  is not a legal edge, or a refused creation, usually means a producer is declaring a strength the
  evidence does not support. Do not branch on `detail` text (7.8).
- Keep the files: both JSONL files are the evidence. Copy them into long-term storage on the same
  schedule as the rest of the pipeline's data.

### 8.5 Failure handling

- **`{ok: False}` from `add()`** — the record was not stored. Surface the reason to the producer;
  the fix is on the producing side (missing parents, wrong type, duplicate `eid`), not in the
  registry.
- **`{ok: False}` from `promote()`** — the state is unchanged. Route the attempt to the review
  queue; do not retry in a loop, and never retry with an AI actor.
- **A raised `ValueError`** — in v0 this is the `opaque`-parent path (B2). Treat it as a
  programming error: an `opaque` record was used as evidence. Wrap `add()` where that is possible.
- **A record that cannot be published** — `check_on_screen()` reports every failing condition.
  Add citations, or run the record through promotion, rather than editing its type.
- **A statement that turns out to be wrong** — v0 has no retraction: create a correcting record,
  cite both, and leave the history intact (Section 9.1).

### 8.6 Anti-patterns

- **Promoting inside an automated job.** Even if every check passes, a promotion performed by a job
  on behalf of a human erodes the meaning of the type. Promotion is a human act; the job may only
  prepare it.
- **Treating `canonical` as "correct".** It means "a human confirmed it, twice, on the record". It
  does not mean true, and it does not survive new evidence on its own.
- **Using `opaque` as a bin.** `opaque` is a decision to hold material unmodelled, and it is
  terminal: nothing can cite it and it cannot be promoted. Content that is merely uncertain belongs
  in the lattice at `derived`, not in `opaque`.
- **Storing secrets or personal data in records.** The audit log is append-only and there is no
  deletion (Section 9.1). Keep sensitive payloads out of `statement` and `detail`.
- **Editing the JSONL files by hand.** It works, and it silently voids every guarantee in
  Section 4, including the audit trail.
- **One registry per request or per process.** State lives on disk; competing writers to the same
  directory are not coordinated. Use one writer, or serialize access.
- **Reading `reason` strings in code.** They are human-readable, come from a single English
  catalogue, and are not part of the contract. Branch on `ok` / `allowed` and on audit fields.

---

## 9. Boundary conditions and non-goals

### 9.1 Boundary conditions of v0 (all verified against `0.1.0.dev0`)

1. **Actor identity is a contract, not a control.** `actor_kind` is supplied by the caller and is
   not authenticated. The isolation property of Section 4 is void if a caller lies. See 4.6.1.
2. **Human root records may be created at any level.** Rule 5 applies only to records with parents;
   a human may create a `canonical` root record. It fails the publication gate until citations are
   added (rule 6). See 4.6.2.
3. **Boundary B1 — an AI record cannot cite a stronger parent.** Coercion precedes the weakest-link
   check, so such a record is refused rather than stored at the weaker level. See 3.7.
4. **Boundary B2 — the `opaque`-parent path raises `ValueError`.** `add()` is therefore not
   uniformly total; every other refusal is a decision object. See 3.7.
5. **`source_grade` is not implemented.** The ladder in Section 5 is specified but not enforced;
   `source_ref` carries source identity in v0. See 5.5.
6. **No retraction.** Downgrading is forbidden and `opaque` is outside the lattice, so an existing
   lattice record cannot be withdrawn or marked as quarantined. Corrections must be additive; the
   wrong statement stays visible in history.
7. **No record modification other than promotion.** `add()` refuses an existing `eid`; there is no
   update or delete. `statement`, `note` and `source_ref` are fixed at creation.
8. **`verification` and `graduation` are inert.** They have fixed value sets, are stored and
   audited, and are consulted by no rule. Their semantics are the application's business.
9. **Timestamps are local, second-resolution, without a timezone offset.** They are not suitable
   for ordering across hosts or for intervals below one second.
10. **Files grow without bound.** No rotation, no compaction, no size cap; each promotion appends a
    full copy of the record.
11. **No write coordination.** No locking. Two processes writing the same directory are not
    serialized; append semantics protect line integrity in practice, not ordering or exclusivity.
12. **No re-validation on load.** Records read from the file are trusted as stored; a hand-written
    file can contain states the API would refuse.
13. **No identifier validation.** Any string is accepted as `eid` as long as it is unique in the
    registry; there is no format check and no cross-registry identity.
14. **No content inspection.** The library never reads `statement`. It governs provenance, never
    meaning.
15. **Single-node, local filesystem.** Directory paths are resolved on the local machine; there is
    no remote store, no replication and no transport.
16. **Not a distributed ledger.** The audit log is tamper-*evident* only insofar as it is copied and
    kept elsewhere; nothing prevents rewriting the file.
17. **Single-record granularity.** There is no way to express that a *set* of records was reviewed
    together, nor to attach a review act to a document.

### 9.2 Non-goals

- **Not a truth oracle.** `canonical` means "confirmed by humans on the record", not "correct". The
  library never inspects what a statement says.
- **Not a content-safety or policy engine.** It does not decide whether a statement may exist. It
  composes with whatever does.
- **Not an access-control system.** It does not restrict who may read; it restricts which
  transitions are legal and records them.
- **Not a knowledge base or graph store.** Records form a citation graph only for the purpose of
  the weakest-link rule; there is no traversal API, no query language and no index.
- **Not a review workflow tool.** No assignments, no queues, no notifications, no deadlines.
- **Not a dataset lineage system.** Lineage belongs upstream of the statements that cite it.
- **Not a compliance certification.** It produces evidence about review acts; whether that evidence
  satisfies a given regime is a question for that regime.
- **Not a replacement for review.** It makes review necessary and visible; it cannot make review
  good.

### 9.3 Convergence items for v1

The following are explicitly deferred, and are recorded so that downstream implementers know what
may change. None of them weakens the six rules of Section 3.

1. Boundary B1 — accept or refuse, consistently and by decision rather than by accident (3.7).
2. Boundary B2 — convert the `opaque`-parent raise into a decision object, making `add()` uniformly
   total (3.7).
3. Implement `source_grade` as a top-level field, propagate it onto audit lines, and enforce the
   rules of 5.4.
4. UTC timestamps with a timezone offset, and sub-second resolution (9.1.9).
5. A retraction path that preserves monotonicity — for example, a separate withdrawn marker
   orthogonal to `truth_type` (9.1.6).
6. Log rotation or compaction (9.1.10).
7. Optional write serialization for multi-process use (9.1.11).

---

*Specification status: v0 — content complete; the sibling implementation is an extraction-stage
release, not yet published to a package index. Rules stated as normative are enforced in code and
exercised by the test suite; items in Section 9.3 are not.*
