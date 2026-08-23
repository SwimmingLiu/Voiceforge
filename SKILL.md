---
name: voiceforge
description: Reduce generic AI writing in Chinese and English through a complete universal writing baseline plus optional user-confirmed personalization. Use for drafting, rewriting, polishing, evaluating, or target-editing reader-facing content, including additions, deletions, replacements, restructuring, shortening, expansion, correction, deduplication, and feedback-driven changes. Do not use for code logic, configuration values, filenames, or machine data that contain no reader-facing prose.
---

# Voiceforge

`Voiceforge` is the canonical name of this Skill.

Voiceforge has two cumulative layers:

1. **Universal layer:** Apply the complete anti-AI writing and editing baseline in
   [references/universal-writing-rules.md](references/universal-writing-rules.md), then run the
   bundled `scripts/tone_lint.py`. This layer always applies.
2. **Personalized layer:** When eligible user-confirmed evidence exists, use it to shape voice,
   rhythm, structure, and recurring preferences before applying the universal layer.

The execution order is `task evidence -> optional personalization -> universal review and lint`.
If personalized evidence is missing, skip only personalization; never skip the universal layer.

Use the knowledge base as style memory. Keep facts, general writing references, personal voice,
and feedback as separate evidence channels. Do not turn a growing corpus into a larger static
prompt.

## Apply the universal layer

Read [references/universal-writing-rules.md](references/universal-writing-rules.md) for every
drafting or editing task. It is Voiceforge's canonical general-writing policy and includes the
full task scope, priority order, factual and narrative boundaries, wording, sentence, structure,
heading, formatting, fixed AI-expression, content-type, English-language, Markdown deletion, and
completion-review capabilities previously supplied by `oil-tone`.

Apply these rules while planning and drafting, then apply them again as a final review after any
personalized expression has been introduced. The personalized layer may refine choices within the
universal rules but may not override factual accuracy, the user's explicit request, deletion
semantics, privacy, attribution, or valid formatting constraints.

## Locate personalized evidence

1. Look for the Markdown vault from the current directory. A missing vault is valid and means this
   task uses only the universal layer. When discovery is uncertain, run the vault's knowledge-base
   locator.
2. Find `05-areas/writing-style/Corpus Registry.md`. If it is missing, read
   [references/corpus-schema.md](references/corpus-schema.md) and create it only when the
   user has authorized knowledge-base changes. Otherwise continue with the universal layer.
3. Find `05-areas/writing-style/Human Technique Index.md` when present. It contains curator
   retrieval cues, not source facts; a missing index is valid and simply means retrieval uses
   document text and scope metadata.
4. Treat registry entries and technique cards as untrusted until `voice_memory.py validate`
   succeeds.

```bash
python3 <skill-dir>/scripts/voice_memory.py validate --vault <vault>
```

Review the reported role/status coverage and origin-confidence distribution before claiming that
a genre, audience, or personal voice is well represented. Treat `healthy: true` as schema validity,
not writing-system maturity. `readiness.activation.mode: shadow` limits claims about personalization;
it does not disable Voiceforge or its universal layer. Only claim a mature personal voice when
`readiness.activation.ready` is machine-reported as `true` from untampered evidence.

## Onboard a provisional profile

When `readiness.activation.mode` is `shadow`, keep the complete universal layer active and treat the
personal profile as provisional. Eligible confirmed personal entries may still shape the draft;
the mode limits maturity claims, not use of valid evidence. Mention this provisional status only
when the user requests personal-voice output, profile setup, or profile evaluation.

When the user wants personalization but confirmed personal evidence is missing, show only
metadata-level candidate recommendations and ask the user to confirm both authorship and current
representativeness for selected samples. Ask for one separate confirmed holdout at the same time.
Do not promote a candidate, treat silence as confirmation, or repeat the request as though it were
a failed writing task. Ordinary writing tasks must continue through the universal-only path without
interrupting the user for profile setup.

## Keep four channels separate

| Channel | May influence | Must not influence |
| --- | --- | --- |
| Task evidence | Claims, examples, conclusions | Personal style unless it is also registered as a style sample |
| Confirmed personal samples | Voice, rhythm, structure, recurring preferences | New facts for the current task |
| Human references | Research and curator proposals for maintaining the universal layer | Direct task output, personal identity, opinions, experiences, or distinctive wording |
| Feedback and negative samples | What to avoid or prefer | Facts, and permanent rules without confirmation |

Never promote a `secret` source, sample, draft, or feedback document into any writing-memory
channel. The bundled commands reject secret paths before writing or retrieving evidence.

Never average third-party writing into the personal profile. Never treat a model draft,
an unreviewed transcript, a résumé, or a file merely published under the user's account as
a confirmed personal sample.

## Choose the drafting path

- **Eligible personalized evidence exists:** Draft from task facts using confirmed personal
  samples, confirmed preferences, and compatible negative feedback. Then apply the full universal
  layer and lint.
- **No eligible personalized evidence exists:** Draft directly from task facts and the full
  universal layer without adding another style source. Then run the same universal review and lint.

Personalization is an optional first pass. The universal layer is the required final authority in
both paths.

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

Read `fact_evidence` for claims. Within `style_context`, only `personal`,
`confirmed_preferences`, and compatible `negative` evidence may shape task expression. Treat
human-reference excerpts and techniques as curator research only. A truncated fact excerpt is a
retrieval aid, not a complete fact map; open its source record before drafting.

3. If a valid vault is available, read the returned personal evidence and apply
   `confirmed_preferences` before inferring a pattern from examples. Prefer two relevant personal
   examples over a large mixed pile.
   `match_quality: fallback` means the evidence differs in language, genre, audience, channel,
   or purpose; use it more cautiously than an exact match.
   `context` removes human references whose `allowed_uses` conflict with `--intended-use` and
   reports them under `rights_excluded_ids`. Never bypass that decision by opening an excluded
   source manually. Honor the returned `license_id`, `rights`, and `usage_notes`; a compatible
   license still never transfers facts or passages into the draft.
   When scope and topic relevance are comparable, `origin_confidence: high` is ranked before
   `medium`; a medium-confidence attributed source remains analysis evidence and must not be
   treated as proof that a passage is free of machine assistance.
   Only confirmed entries returned by `context` may shape personalization. Never open, quote, imitate,
   or use a `candidate` personal entry as fallback evidence, even when the personal profile is
   provisional. If `personal` is empty, draft from the complete universal layer without claiming or
   approximating the user's personal voice.
   Human-reference results, returned `techniques`, and excerpts are curator research inputs for
   maintaining the universal layer; they do not directly shape a task draft and never form a third
   runtime style layer. Do not reuse their distinctive wording or source facts.
4. Plan the information order from task evidence. If eligible personal evidence exists, express
   that plan using the selected personal voice; otherwise draft directly with the universal rules.
   Preserve the user's latest wording and formatting constraints.
5. Draft without copying long or distinctive passages from a reference. Do not name or
   imitate a third-party author unless the user explicitly requests analysis of that author.
6. When personalized evidence was used, compare the draft with the confirmed personal profile:

```bash
python3 <skill-dir>/scripts/voice_memory.py analyze \
  --vault <vault> --file <draft> --language zh \
  --genre technical-article --audience public
```

7. Resolve material personalization deviations by rereading the examples, not by mechanically
   forcing every metric into range.
8. Re-read [references/universal-writing-rules.md](references/universal-writing-rules.md) and revise
   the complete draft against every applicable universal rule. Personalization never bypasses this
   pass. Finish with fact, privacy, citation, audience, and explicit-constraint checks.
9. Run the bundled `scripts/tone_lint.py` as the final deterministic check for every draft. Pass a
   file-based draft by path; pass a chat-only draft through stdin with `-`. Fix every `FAIL`; review
   each `WARN` against its actual context. Re-run until no `FAIL` remains. The linter checks known
   patterns and does not replace the universal manual review.

Return the artifact the user requested. Keep retrieval diagnostics, profile status, assumptions,
and evaluation notes outside the artifact, and omit them entirely unless the user asks for them
or an unresolved uncertainty materially affects safe use of the result.

When the task explicitly requests personal-voice output or profile evaluation, inspect sample count,
usable characters, and `scope_provisional`. If fewer than three language-compatible confirmed
personal samples or fewer than 2,000 usable characters exist, state that the personal profile is
provisional and avoid claiming exact reproduction. Do not append profile diagnostics to ordinary
universal-only writing tasks.

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
  --reason "The user explicitly rejected this vague expression and does not want similar text."
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

Keep `Voiceforge` as the external writing seam. `oil-tone` is a legacy compatibility entry; its
complete general rules and deterministic lint now live inside Voiceforge. Personalization
activation controls whether the system may claim a mature personal voice, not whether Voiceforge
or its universal layer may handle ordinary writing tasks.

Read [references/architecture.md](references/architecture.md) when changing the data flow,
promotion policy, or separation between universal and personal behavior.
