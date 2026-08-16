# Evaluation

## Contents

1. Gates
2. Test set
3. Measures
4. Record a rollout evaluation
5. Promotion decision

## Gates

A writing-system change passes only when it preserves task facts and user constraints, does not
increase privacy or attribution risk, and reduces the user's expected editing work. Style scores
cannot compensate for a factual failure.

Treat rights compatibility as part of attribution risk. A test fails if an incompatible human
reference reaches drafting, or if a restricted source reaches a task whose intended use is
unknown, even when the resulting prose does not contain a long quotation.

Use `voice_memory.py validate` to distinguish registry health from operational readiness. Do not
claim the system is ready merely because the schema is healthy. Automatic integration requires
all of these independent gates:

| Gate | Minimum evidence |
| --- | --- |
| Personal profile | At least 3 confirmed personal documents and 2,000 usable characters |
| Human library | At least 6 confirmed human references across 3 genres |
| Holdout | At least 1 confirmed personal holdout excluded from retrieval |
| Feedback | At least 1 explicitly user-confirmed before/after event |
| Rollout | At least 1 user-confirmed passing holdout evaluation |

Until every gate passes, `readiness.activation.mode` must remain `shadow`. A healthy registry or
a passing synthetic test does not authorize a global routing change.

## Test set

Maintain four groups:

1. Confirmed personal samples used for retrieval and profile statistics.
2. Personal holdout samples excluded from retrieval.
3. Human reference samples covering the main genres and audiences.
4. Negative samples containing rejected AI patterns and prior failure cases.

For each writing task, keep the same fact packet and compare the current Skill with the proposed
change. Do not expose the expected final answer to the generating run.

## Measures

| Measure | Evidence |
| --- | --- |
| Factual fidelity | Unsupported, altered, or omitted claims against the fact packet |
| Constraint fidelity | Language, audience, length, format, privacy, and citation requirements |
| Personal similarity | Preference judgment plus distance from holdout style features |
| Generic-AI rate | Contextual review of unsupported framing, vague attribution, and empty endings |
| Editing burden | User edit distance, number of substantive corrections, and rejection rate |
| Generalization | Results across genres not used to create the proposed rule |
| Scope calibration | Exact, partial, and fallback evidence are labeled and weighted appropriately |
| Learning integrity | Only explicitly confirmed preferences become durable and superseded records stop applying |
| Corpus integrity | Candidate personal samples remain unreachable; incompatible licenses are filtered before ranking; rights accompany every returned excerpt |
| Retrieval quality | Returned excerpts contain a relevant substantive paragraph and a nearby supporting paragraph rather than disconnected keyword matches; technique cues improve method recall without letting fallback or same-collection duplicates fill the context; third-party excerpt risk flags are surfaced and do not become draft rules |

Quantitative style features are diagnostics, not a target function. A model can match sentence
length and punctuation while missing the writer's reasoning habits.

## Record a rollout evaluation

Generate the baseline and candidate from the same fact packet without exposing the holdout final
answer. After the user reviews the three documents, count substantive edits, factual errors, and
constraint errors for both outputs. Preserve the review itself in a source or journal record.

Preview first:

```bash
python3 <skill-dir>/scripts/voice_memory.py evaluate-rollout \
  --vault <vault> --baseline <baseline> --candidate <candidate> --final <holdout> \
  --fact-packet <source-or-journal> --review-evidence <source-or-journal> \
  --task-id <stable-id> --language <language> --genre <genre> --audience <audience> \
  --baseline-substantive-edits <n> --candidate-substantive-edits <n> \
  --baseline-factual-errors <n> --candidate-factual-errors <n> \
  --baseline-constraint-errors <n> --candidate-constraint-errors <n> \
  --reviewer user
```

Use `--reviewer curator` for diagnostic review that must never activate the system. Add
`--reviewer-confirmed --write` only after the named reviewer checks the evidence. Failed
evaluations may be written and retained; negative results are part of the audit trail.

The candidate passes only when it has zero factual errors, zero constraint errors, a lower edit
ratio against the holdout final, and fewer substantive edits than the baseline. It qualifies for
activation only when the confirmed reviewer is the user. The journal stores hashes for all five
referenced documents and derived edit metrics. `validate` recomputes those values and rejects
tampered metrics, changed documents, a final file that is not a confirmed holdout, or a scope that
does not match the holdout.

## Promotion decision

- Apply an explicit user preference immediately to the current task.
- Add it to durable personal memory after explicit confirmation.
- Promote an inferred preference only after at least three independent confirmed events and a
  review of counterexamples.
- Verify that a promoted preference appears in the next compatible `context` result and does not
  appear as an exact match in incompatible scopes.
- Change the universal Skill only when the behavior helps multiple genres or users and passes
  regression tests. Keep personal preferences in the profile instead.
- Roll back a change that reduces factual fidelity or increases editing burden, even if surface
  style similarity improves.
- Keep the default writing route unchanged while activation is `shadow`. When the machine gate
  becomes `active`, review the evidence once more before deliberately routing external writing
  requests through `Voiceforge`; retain `oil-tone` as a compatibility linter.
