# Architecture

## Contents

1. Design goal
2. Six layers
3. Generation flow
4. Learning flow
5. Integration boundary
6. Non-goals

## Design goal

Replace a large fixed style rule list with a small invariant policy plus task-aware evidence.
The system should generalize from real examples while preventing external prose, model output,
or accidental edits from silently redefining the user's voice.

## Six layers

| Layer | Source of truth | Update rule |
| --- | --- | --- |
| Invariants | Skill instructions | Change deliberately and infrequently |
| Human writing library | Immutable source records and registry metadata | Add with author and provenance |
| Human technique index | Curator-maintained cards linked to human sources | Add only as retrieval cues; never as source facts or universal rules |
| Personal voice memory | User-confirmed final writing and explicit preferences | Add only after confirmation |
| Task retrieval | Reproducible selection from the registry | Rebuild for every task |
| Feedback and evaluation | Append-only edit records and holdout tests | Promote after evidence |

Invariants cover factual fidelity, privacy, source separation, and preservation of the user's
latest request. They are not an exhaustive catalog of natural language.

The human writing library supplies genre techniques such as how an explanation introduces a
term, moves from mechanism to example, or ends a section. It never supplies personal identity
or task facts. A provenance gate keeps recent, anonymous, weakly attributed, or potentially
machine-generated text out of the confirmed human-reference set until its origin and allowed
use are documented.

Personal memory contains direct statements of preference, confirmed final texts, and confirmed
before/after edits. Quantitative features summarize the corpus, while retrieved excerpts let the
model infer patterns that were never encoded as rules. Store confirmed preferences as structured,
append-only records so they can be retrieved, scoped, superseded, and audited.

## Generation flow

1. Extract task facts and uncertain claims. If the facts are preserved in the vault, search
   maintained concepts/projects and relevant source records first, then use `prepare` to emit
   a bounded `fact_evidence` section before retrieving style evidence.
2. Classify language, genre, audience, channel, and purpose.
3. Retrieve confirmed personal samples and rights-compatible human references into separate sections;
   use the separate human technique index only to rank relevant excerpts and diversify collections.
4. Plan content from task facts.
5. Draft using personal evidence; borrow only general techniques from human references.
6. Compare the draft with the profile and negative evidence.
7. Verify facts, privacy, citations, and user constraints.

Style retrieval follows metadata before topic similarity. A technical article about databases
usually benefits more from another confirmed technical explanation than from a social post about
the same database. Rank scope mismatches instead of discarding them: return exact evidence first,
then mark partial or fallback evidence explicitly when the exact corpus is sparse.
Candidate personal material is never a sparse-corpus fallback. Before scoring human references,
retrieval compares the task's declared intended use with each source's structured `allowed_uses`.
Results carry their author, license, rights, and usage notes; excluded sources remain visible only
as diagnostic IDs and cannot influence drafting. Third-party excerpts pass a retrieval-only hygiene
ranker for accidental promotional, presentation-meta, or chat residue and return any risk flags with
an explicit analysis-only copy policy. This filter does not lint the user's writing or define a new
universal style rule.

Use `audit-corpus` before expanding the library. It reports exact/partial scope coverage, rights
exclusions, missing technique cards, low-confidence confirmed origins, and registered candidates.
It is a gap report, not a promotion command; adding a source still requires provenance and curator
review.

Technique cards are a derived index, not an additional source. Each card points to one confirmed
human reference, states that its labels are curator inference, and can group related chapters with
`collection_id`. The context interface returns the card labels together with the excerpt so the
caller can inspect the evidence. When the first match is exact, fallback sources do not pad the
result; when several candidates are similarly matched, the selector prefers distinct collections
and penalizes near-duplicate technique sets.

## Learning flow

1. Observe an explicit acceptance, rejection, correction, or final version.
2. Preserve the event as an append-only feedback record only after an explicit
   `reviewer_confirmed` signal.
3. Use the event immediately as local task evidence on similar future work.
4. Record both textual edit pairs and quantitative style deltas, then aggregate repeated exact,
   explicit, and directionally consistent signals into candidate preferences.
5. Return evidence paths with each promotion candidate.
6. Require explicit confirmation before appending the preference to the maintained profile.
7. Store explicitly rejected drafts as separate negative evidence when the user wants the pattern
   avoided; negative evidence never enters positive personal statistics.
8. Retrieve that preference or contrastive evidence on the next compatible task and preserve
   superseded records.
9. Run a user-confirmed holdout evaluation before changing the core Skill. Recompute edit ratios
   from the referenced documents and preserve factual, constraint, and substantive-edit counts.

This is controlled adaptation. It avoids a feedback loop in which AI-generated phrases become
training data merely because the user did not edit them.

## Integration boundary

`Voiceforge` is the intended external writing seam. It owns evidence separation, scope-aware
retrieval, controlled memory, and activation readiness. `oil-tone` remains a small compatibility
adapter and deterministic linter; it must not own a second personal-memory model.

Integration has two modes:

| Mode | Allowed behavior |
| --- | --- |
| `shadow` | Explicit `$voiceforge` tests and `$oil-tone` adapter delegation; no global route changes |
| `active` | Eligible to become the default writing entry after a deliberate routing change |

`validate` reports the mode. Activation requires all five independent gates: a confirmed
personal profile, a minimally diverse human-reference library, a confirmed holdout, at least one
user-confirmed feedback event, and a user-confirmed passing rollout evaluation. The rollout record
must show zero candidate factual and constraint errors, lower document edit distance, and fewer
substantive edits than the baseline. Missing evidence, changed files, or mismatched metrics keep
the system in shadow mode or make validation fail.

Readiness authorizes a later integration decision; it does not mutate routing by itself. During
`shadow`, a user who explicitly invokes `$oil-tone` may still receive the delegated `$voiceforge`
path, while unrelated writing requests continue using their existing route.
This keeps activation reproducible and prevents an agent from promoting the system from memory or
subjective confidence.

## Non-goals

- Fine-tuning a model or embedding a whole library in the prompt.
- Reproducing a living writer's distinctive expression.
- Treating semantic similarity as proof of stylistic similarity.
- Using style examples as factual sources.
- Claiming a stable personal voice from a few or unverified documents.
