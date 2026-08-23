# Architecture

## Contents

1. Design goal
2. Six layers
3. Generation flow
4. Learning flow
5. Integration boundary
6. Non-goals

## Design goal

Reduce generic AI writing through two cumulative layers: a complete universal writing baseline and
optional task-aware personalization. The universal layer always applies. The personalized layer
uses confirmed evidence without allowing external prose, model output, or accidental edits to
silently redefine the user's voice.

## Six layers

| Layer | Source of truth | Update rule |
| --- | --- | --- |
| Universal writing layer | `references/universal-writing-rules.md` and `scripts/tone_lint.py` | Change deliberately and validate with the lint self-test |
| Human writing library | Immutable source records and registry metadata | Add with author and provenance |
| Human technique index | Curator-maintained cards linked to human sources | Add only as retrieval cues; never as source facts or universal rules |
| Personal voice memory | User-confirmed final writing and explicit preferences | Add only after confirmation |
| Task retrieval | Reproducible selection from the registry | Rebuild for every task |
| Feedback and evaluation | Append-only edit records and holdout tests | Promote after evidence |

The universal writing layer contains the complete fixed task, fact, narrative, wording, sentence,
structure, heading, formatting, deletion, and anti-AI expression baseline. It applies before and
after optional personalization. The deterministic linter covers known patterns; manual review
applies the full rule set.

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

1. Load the complete universal writing rules.
2. Extract task facts and uncertain claims. If the facts are preserved in the vault, search
   maintained concepts/projects and relevant source records first, then use `prepare` to emit
   a bounded `fact_evidence` section before retrieving style evidence.
3. Classify language, genre, audience, channel, and purpose.
4. Retrieve confirmed personal samples for optional personalization. Keep any returned human
   references in the curator-research channel; they do not shape the task draft.
5. Plan content from task facts.
6. When eligible personal evidence exists, draft with it. Otherwise draft directly with the
   universal layer without adding another style source.
7. When personalization was used, compare the draft with the profile and negative evidence.
8. Apply the complete universal rules again, verify facts, privacy, citations, and user constraints,
   then run the bundled deterministic linter.

Personal style retrieval follows metadata before topic similarity. A technical article about databases
usually benefits more from another confirmed technical explanation than from a social post about
the same database. Rank scope mismatches instead of discarding them: return exact evidence first,
then mark partial or fallback evidence explicitly when the exact corpus is sparse.
Candidate personal material is never a sparse-corpus fallback. Human-reference retrieval remains
available for curator research and compares the declared intended use with each source's structured
`allowed_uses`. Results carry author, license, rights, and usage notes; excluded sources remain
visible only as diagnostic IDs. Third-party excerpts are analysis-only and cannot influence task
drafting or create a third runtime style layer.

Use `audit-corpus` before expanding the library. It reports exact/partial scope coverage, rights
exclusions, missing technique cards, low-confidence confirmed origins, and registered candidates.
It is a gap report, not a promotion command; adding a source still requires provenance and curator
review.

Technique cards are a derived index, not an additional source. Each card points to one confirmed
human reference, states that its labels are curator inference, and can group related chapters with
`collection_id`. The context interface returns the card labels together with the excerpt so the
caller can inspect the evidence. When the first match is exact, fallback sources do not pad the
result; when several candidates are similarly matched, the selector prefers distinct collections
and penalizes near-duplicate technique sets. These results support curator analysis only; the
generation flow does not apply them directly to task output.

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

`Voiceforge` is the external writing seam. It owns both the complete universal writing layer and the
optional personalized layer. `oil-tone` is a legacy compatibility entry and may retain fallback
copies for older callers, but Voiceforge does not depend on that Skill at runtime. The canonical
universal rules and linter for this project live inside Voiceforge.

Integration has two modes:

| Mode | Allowed behavior |
| --- | --- |
| `shadow` | Universal layer active; eligible confirmed personal evidence may be used, but the profile remains provisional |
| `active` | Universal layer active; the personal profile has passed the maturity gates |

`validate` reports the mode. Activation requires all five independent gates: a confirmed
personal profile, a minimally diverse human-reference library, a confirmed holdout, at least one
user-confirmed feedback event, and a user-confirmed passing rollout evaluation. The rollout record
must show zero candidate factual and constraint errors, lower document edit distance, and fewer
substantive edits than the baseline. Missing evidence, changed files, or mismatched metrics keep
the system in shadow mode or make validation fail.

Readiness controls claims about personalization maturity, not Voiceforge routing or availability.
The universal layer runs in both modes. This keeps activation reproducible and prevents an agent
from promoting the personal profile from memory or subjective confidence.

## Non-goals

- Fine-tuning a model or embedding a whole library in the prompt.
- Reproducing a living writer's distinctive expression.
- Treating semantic similarity as proof of stylistic similarity.
- Using style examples as factual sources.
- Claiming a stable personal voice from a few or unverified documents.
