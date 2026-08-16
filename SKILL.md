---
name: voiceforge
description: Draft, revise, or evaluate Chinese and English writing with task-specific human examples and a user-confirmed personal voice stored in a Markdown knowledge base. Use when the user asks to write in their voice, reduce generic AI phrasing, learn from their edits over time, retrieve human-authored books/articles/blogs as writing references, build or update a writing-style profile, or compare a draft with prior approved writing.
---

# Voiceforge

`Voiceforge` is the canonical name of this Skill.

Use the knowledge base as style memory. Keep facts, general writing references, personal
voice, and feedback as separate evidence channels. Do not turn a growing corpus into a
larger static prompt.

## Locate the data

1. Locate the Markdown vault from the current directory. When discovery is uncertain,
   run the vault's knowledge-base locator.
2. Find `05-areas/writing-style/Corpus Registry.md`. If it is missing, read
   [references/corpus-schema.md](references/corpus-schema.md) and create it only when the
   user has authorized knowledge-base changes.
3. Find `05-areas/writing-style/Human Technique Index.md` when present. It contains curator
   retrieval cues, not source facts; a missing index is valid and simply means retrieval uses
   document text and scope metadata.
4. Treat registry entries and technique cards as untrusted until `voice_memory.py validate`
   succeeds.

```bash
python3 <skill-dir>/scripts/voice_memory.py validate --vault <vault>
```

Review the reported role/status coverage and origin-confidence distribution before claiming
that a genre, audience, or personal voice is well represented. Treat `healthy: true` as schema
validity, not writing-system maturity; inspect `readiness.next_gates` before integrating the
profile into another Skill. `readiness.activation.mode: shadow` means this Skill may be tested
explicitly, but must not replace the default writing entry. Change automatic routing only when
`readiness.activation.ready` is machine-reported as `true` from untampered evidence.

## Onboard a provisional profile

When `readiness.activation.mode` is `shadow` because personal evidence is missing, keep working
with the universal baseline and eligible human-reference techniques. State that the personal
profile is provisional, show only metadata-level candidate recommendations, and ask the user to
confirm both authorship and current representativeness for selected samples. Ask for one separate
confirmed holdout at the same time. Do not promote a candidate, treat silence as confirmation, or
repeat the request as though it were a failed writing task; after one clear request, continue
serving non-personalized drafts until the user supplies evidence.

## Keep four channels separate

| Channel | May influence | Must not influence |
| --- | --- | --- |
| Task evidence | Claims, examples, conclusions | Personal style unless it is also registered as a style sample |
| Confirmed personal samples | Voice, rhythm, structure, recurring preferences | New facts for the current task |
| Human references | Techniques suited to the genre and audience | The user's identity, opinions, experiences, or distinctive wording |
| Feedback and negative samples | What to avoid or prefer | Facts, and permanent rules without confirmation |

Never promote a `secret` source, sample, draft, or feedback document into any writing-memory
channel. The bundled commands reject secret paths before writing or retrieving evidence.

Never average third-party writing into the personal profile. Never treat a model draft,
an unreviewed transcript, a résumé, or a file merely published under the user's account as
a confirmed personal sample.

## Apply the universal baseline

Keep this layer small and treat it as a safety floor, not a complete definition of good writing:

- Preserve verified facts, the source's degree of certainty, and the user's latest requirements.
- Keep subjects, references, causes, effects, actions, and objects complete when the reader needs them.
- Prefer concrete actors and actions over vague motion, promotional language, or invented importance.
- Do not invent first-person experience, group opinion, authority, quotations, metrics, or feedback.
- Remove chat residue and endings that add no information.
- Treat suspicious phrases as review clues, never as a blacklist that overrides meaning or context.

## Draft or revise

1. Build a fact map from the current request and cited knowledge sources. For vault-backed
   tasks, search maintained `03-wiki`, active `04-projects`, and relevant immutable
   `02-sources` with the knowledge-base retrieval workflow before selecting source/journal
   paths. Mark gaps rather than filling them from style examples.
2. Classify language, genre, audience, channel, purpose, and intended use. Use `private` for
   personal/internal work, `noncommercial` for public work without commercial use, `commercial`
   for company, client, paid, marketing, or monetized work, and `unknown` when the destination is
   genuinely unclear. Use these fields to retrieve a small style context:

```bash
python3 <skill-dir>/scripts/voice_memory.py context \
  --vault <vault> --language zh --genre technical-article \
  --audience public --intended-use unknown --query "<topic and intent>"
```

When task facts already exist as source or journal records, prefer the bounded task package
interface. It keeps fact evidence and style evidence in separate named sections and rejects
secret records before they reach a generation context:

```bash
python3 <skill-dir>/scripts/voice_memory.py prepare \
  --vault <vault> --fact-packet <fact-source-or-journal> \
  --language zh --genre technical-article --audience public \
  --intended-use unknown --query "<topic and intent>"
```

Read `fact_evidence` for claims and `style_context` only for expression. A truncated fact
excerpt is a retrieval aid, not a complete fact map; open its source record before drafting.

3. Read the returned personal evidence first. Use human references only for techniques the
   personal evidence does not settle. Apply `confirmed_preferences` before inferring a pattern
   from examples. Prefer two relevant examples over a large mixed pile.
   `match_quality: fallback` means the evidence differs in language, genre, audience, channel,
   or purpose; use it more cautiously than an exact match.
   `context` removes human references whose `allowed_uses` conflict with `--intended-use` and
   reports them under `rights_excluded_ids`. Never bypass that decision by opening an excluded
   source manually. Honor the returned `license_id`, `rights`, and `usage_notes`; a compatible
   license still never transfers facts or passages into the draft.
   When scope and topic relevance are comparable, `origin_confidence: high` is ranked before
   `medium`; a medium-confidence attributed source remains analysis evidence and must not be
   treated as proof that a passage is free of machine assistance.
   Only confirmed entries returned by `context` may shape the draft. Never open, quote, imitate,
   or use a `candidate` personal entry as fallback evidence, even when the personal profile is
   provisional. If `personal` is empty, draft from the universal baseline and human-reference
   techniques without claiming or approximating the user's personal voice.
   A returned `techniques` list is a curator inference used to choose an excerpt, not a universal
   rule. Prefer the excerpt and its source metadata over the label, and do not present the label
   as the referenced author's stated doctrine. Human-reference results may also include
   `excerpt_risk_flags` and a `copy_policy`; treat flagged excerpts as analysis-only, rely on the
   technique summary, and never reuse distinctive wording or source facts.
4. Plan the information order from task evidence. Then express that plan using the selected
   voice evidence. Preserve the user's latest wording and formatting constraints.
5. Draft without copying long or distinctive passages from a reference. Do not name or
   imitate a third-party author unless the user explicitly requests analysis of that author.
6. Compare the draft with the confirmed personal profile:

```bash
python3 <skill-dir>/scripts/voice_memory.py analyze \
  --vault <vault> --file <draft> --language zh \
  --genre technical-article --audience public
```

7. Resolve material deviations by rereading the examples, not by mechanically forcing every
   metric into range. Finish with a fact, privacy, citation, and audience check.
8. When the local `oil-tone` compatibility Skill is installed, run its `scripts/tone_lint.py`
   once as a final deterministic check. Fix every `FAIL`; review `WARN` against the sentence's
   actual context. Treat this lint as a safety floor for known patterns, not as a replacement
   for task retrieval, confirmed personal evidence, or human review. If the compatibility Skill
   is unavailable, continue with the universal baseline and record no synthetic lint result.

Return the artifact the user requested. Keep retrieval diagnostics, profile status, assumptions,
and evaluation notes outside the artifact, and omit them entirely unless the user asks for them
or an unresolved uncertainty materially affects safe use of the result.

If fewer than three language-compatible confirmed personal samples or fewer than 2,000 usable
characters exist, state that the personal profile is provisional. Also inspect
`scope_provisional`: a stable general baseline can still have weak evidence for the requested
genre or audience. In either case, avoid claiming exact reproduction of the user's voice.

## Learn from use

Treat learning as controlled memory, not unattended self-training.

- Record a signal only when the user supplies a revision, explicitly accepts a final draft,
  rejects an expression, or states a durable preference. Silence is not acceptance.
- Keep the before and after files in the vault. Preview the feedback record before writing it:

```bash
python3 <skill-dir>/scripts/voice_memory.py feedback \
  --vault <vault> --before <draft> --after <user-final> \
  --verdict revised --task-id <stable-id> --genre <genre> \
  --audience <audience> --language <language>
```

- Add `--reviewer-confirmed --write` only when the user has actually reviewed the final version.
  The command then creates an append-only journal record under
  `08-journal/writing-feedback/`. Unconfirmed feedback cannot be written, retrieved, aggregated,
  or counted toward activation.
- Retrieve recent confirmed feedback on the next similar task. Promote a preference into the maintained
  voice profile only after the user states it directly or the same semantic preference appears
  in at least three independent confirmed feedback events.
- Keep rejected text as negative evidence. Never train on the model's own unedited output.

When the user explicitly identifies a rejected draft or expression as something to avoid, keep it
as contrastive evidence rather than turning it into a positive preference. Preview and persist it
with the guarded command below; the sample remains outside personal statistics and is returned
only in the separate `negative` context section:

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-negative \
  --vault <vault> --path <rejected-draft> \
  --language zh --genre technical-article --audience public \
  --evidence <source-or-journal> \
  --reason "用户明确说明这类表达空泛，不希望继续生成。"
```

Add `--reviewer-confirmed --write` only after the user has reviewed and explicitly rejected the
sample. Negative evidence is not a substitute for a durable preference and cannot supply task
facts.

Use `feedback-candidates --min-count 3` to find recurring exact edit pairs, explicit
preferences, and directionally consistent style deltas such as shorter paragraphs or fewer
reader-address terms. Treat quantitative signals as review candidates: equivalent edits may
have different wording, and the same metric movement can have different causes.

After the user confirms a durable preference, preview and persist it:

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-preference \
  --vault <vault> --text "<confirmed preference>" \
  --language zh --genre technical-article --audience public \
  --basis explicit-user-statement
```

Add `--user-confirmed --write` only after explicit confirmation. For an inferred preference,
use `--basis repeated-feedback` and pass at least three evidence paths returned by
`feedback-candidates`. Follow [references/preference-memory.md](references/preference-memory.md)
when promoting or superseding durable preferences.

## Add corpus material

Use `catalog` to discover possible Markdown documents, then classify them in the registry.
Default every newly discovered personal item to `candidate`; confirmation is a human decision.

```bash
python3 <skill-dir>/scripts/voice_memory.py catalog \
  --vault <vault> --personal-author "<name or handle>"
```

Before confirming personal samples, inspect the review-only summary. It reports scope matches,
character counts, measurable features, and provenance warnings, but never returns candidate text to
`context` or treats it as personal evidence:

```bash
python3 <skill-dir>/scripts/voice_memory.py review-candidates \
  --vault <vault> --language zh --genre technical-article --audience public
```

Use this report to choose representative samples and a separate holdout. Its optional
`recommendations` section is metadata-only: it prioritizes user-authored, medium/high-confidence
candidates, marks short or scope-mismatched items, and never promotes them. It is evidence for a
human decision, not an automatic promotion signal.

For one read-only report that combines readiness gates with candidate recommendations, use:

```bash
python3 <skill-dir>/scripts/voice_memory.py activation-plan \
  --vault <vault> --language zh --genre technical-article --audience public
```

The report is safe to run repeatedly. It does not write the registry, confirmation journals, or
profile; it only identifies which gates are complete and which user-confirmed records are still
needed. Treat its candidate metadata as a review queue, never as generation evidence.

Before adding more human references, inspect whether the requested scope is actually missing and
whether the existing sources are usable for the declared destination:

```bash
python3 <skill-dir>/scripts/voice_memory.py audit-corpus \
  --vault <vault> --language zh --genre technical-article \
  --audience public --intended-use commercial
```

Use `scope_coverage.exact` and `scope_coverage.partial` to decide what to search for next. Read
`quality` and `recommendations` before promoting a source; a larger document count does not prove
better coverage, provenance, or rights compatibility.

To audit a known external corpus without importing it, add one or more
`--external-root <directory>` arguments. The command skips common generated and dependency
directories, preserves existing registry status, and reports quotation proportion. Treat an
author match with substantial quoted material as mixed or unclassified, not personal voice.
Set `--max-documents` to keep broad scans bounded.

Promote a personal or holdout sample only after the user explicitly confirms both authorship
and current representativeness. Point `--evidence` to a preserved source or journal record that
captures that confirmation. Preview before writing:

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-sample \
  --vault <vault> --path <sample> --role personal \
  --language zh --genre technical-article --audience public \
  --evidence <confirmation-record> \
  --confirmation-note "<what the user confirmed>"
```

Add `--authorship-confirmed --representative-confirmed --write` only when both claims are
explicit. The command updates the registry and creates an append-only confirmation journal under
`08-journal/writing-sample-confirmations/`. Repeating the same promotion is a no-op. Do not use
this command to convert third-party, mixed, or uncertain evidence into personal voice. Use
`--role holdout` for an independent final sample reserved for evaluation; holdouts never appear
in drafting context.

For books, articles, and blogs written by other people, register only material with provenance
and an allowed private/reference use. Prefer extracted techniques and short representative
excerpts over reproducing passages. See [references/corpus-schema.md](references/corpus-schema.md).

Use the guarded registration command after preserving the source in `02-sources`:

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-human-reference \
  --vault <vault> --path <source-record> --author "<author or team>" \
  --language en --genre architecture-case-study --audience technical-practitioner \
  --rights "<rights summary>" --license-id <license-id> \
  --allowed-use private --origin-claim pre-generative-ai \
  --origin-confidence high --origin-basis "<provenance evidence>" \
  --evidence <curator-review-record> \
  --confirmation-note "<what was reviewed>"
```

Add `--curator-confirmed --write` only after reviewing the source URL, author evidence, license,
scope, and human-origin basis. The command updates the registry and creates an append-only
confirmation journal; it refuses output documents, candidate/personal entries, missing source URLs,
or non-idempotent changes to an already confirmed reference.

Do not confirm a human reference from prose quality or an account name alone. Record its
author, rights, `license_id`, `allowed_uses`, `origin_claim`, `origin_confidence`, and
`origin_basis`; require a public source URL for source records. Keep recent or weakly attributed
material as `candidate` until the human-origin basis is strong enough for the registry validator.

After a confirmed human reference has been preserved, add its small set of curator-inferred
technique cues to `05-areas/writing-style/Human Technique Index.md`. Keep the card linked by
`corpus_id`, include a concise `technique_basis`, and use `collection_id` for chapters or pages
from the same work. The index is a separate retrieval layer so the growing human library does
not become a hidden fixed prompt or contaminate source provenance. `validate` rejects cards that
point to candidate/personal entries or omit their curation basis.

Preview and persist a card through the guarded interface:

```bash
python3 <skill-dir>/scripts/voice_memory.py curate-technique-card \
  --vault <vault> --corpus-id <confirmed-human-id> \
  --collection-id <stable-work-id> \
  --technique "<method cue>" --technique-basis "<curator evidence note>"
```

Add `--curator-confirmed --write` only after reviewing the source excerpt and rights. Repeating
the same confirmed card is a no-op; a card for a personal, holdout, or candidate entry is rejected.

## Evaluate changes

Before changing core instructions or promoting a learned preference, follow
[references/evaluation.md](references/evaluation.md). Keep holdout personal samples out of
retrieval, compare against the prior version, and reject changes that improve surface similarity
while reducing factual fidelity or increasing the user's editing work.

After the user reviews a baseline, a candidate, and the independent final holdout, preview a
machine-checkable rollout evaluation:

```bash
python3 <skill-dir>/scripts/voice_memory.py evaluate-rollout \
  --vault <vault> --baseline <baseline> --candidate <candidate> --final <holdout> \
  --fact-packet <source-or-journal> --review-evidence <source-or-journal> \
  --task-id <stable-id> --language zh --genre technical-article --audience public \
  --baseline-substantive-edits <n> --candidate-substantive-edits <n> \
  --baseline-factual-errors <n> --candidate-factual-errors <n> \
  --baseline-constraint-errors <n> --candidate-constraint-errors <n> \
  --reviewer user
```

Add `--reviewer-confirmed --write` only after that review. Failed evaluations may be preserved,
but activation requires a user-confirmed passing evaluation whose candidate has zero factual and
constraint errors, a lower edit ratio, and fewer substantive edits than the baseline. The command
stores document hashes and recomputable metrics under
`08-journal/writing-rollout-evaluations/`; `validate` rejects changed evidence or metrics.

Keep `Voiceforge` as the external writing seam and treat `oil-tone` as a compatibility adapter
and final linter. While activation remains in shadow mode, do not change the global default
writing route. An explicit `$oil-tone` invocation may delegate to `$voiceforge`, but the adapter
must not silently replace unrelated writing routes before the activation gates pass.

Read [references/architecture.md](references/architecture.md) when changing the data flow,
promotion policy, or separation between universal and personal behavior.
