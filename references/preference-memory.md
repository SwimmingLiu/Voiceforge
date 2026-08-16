# Preference memory

## Contents

1. Store durable preferences
2. Promote with evidence
3. Supersede obsolete preferences
4. Retrieve and apply

## Store durable preferences

Store confirmed preference records in `05-areas/writing-style/Voice Profile.md`. Keep the
human-readable profile and an append-only `jsonl` block in the same note. Treat Markdown as
canonical and generated retrieval output as disposable.

Use this record shape:

```jsonl
{"kind":"preference","id":"preference-example","text":"先说明机制，再给出例子。","status":"confirmed","approval":"user-confirmed","basis":"explicit-user-statement","evidence":[],"language":"zh","genre":"technical-article","audience":"public","created":"2026-08-15"}
```

Keep `text` as a concrete instruction. Scope it only as narrowly as the evidence supports.
Never store task facts, inferred identity, or a model-generated phrase as a preference.

## Promote with evidence

Apply these gates:

| Basis | Evidence gate | Confirmation gate |
| --- | --- | --- |
| `explicit-user-statement` | Preserve an evidence link when one exists | Require the user's explicit confirmation |
| `repeated-feedback` | Cite at least three distinct records under `08-journal/writing-feedback/` | Require the user to review and confirm the inferred preference |

Preview before writing:

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-preference \
  --vault <vault> --text "<durable preference>" \
  --language zh --genre technical-article --audience public \
  --basis repeated-feedback \
  --evidence <feedback-1> --evidence <feedback-2> --evidence <feedback-3>
```

Add `--user-confirmed --write` only after receiving that confirmation. Do not infer the flag
from silence, lack of further edits, or a model's judgment. Repeat the same command safely;
the record ID is deterministic and duplicate writes are no-ops. For `repeated-feedback`, every
evidence file must itself be a verified journal with `reviewer: user` and
`reviewer_confirmed: true`; manually supplied or legacy unconfirmed paths are rejected.

## Supersede obsolete preferences

Preserve history instead of editing an old record. Promote the replacement with
`--supersedes <old-preference-id>`. Let retrieval ignore the superseded record. Keep the old
record so later review can reconstruct when and why the preference changed.

## Retrieve and apply

Read `confirmed_preferences` from the `context` command before drafting. Apply an exact scope
match before a partial or fallback match. Treat a fallback preference as weak evidence and
resolve conflicts in this order:

1. Follow the user's latest instruction for the current task.
2. Follow a directly confirmed scoped preference.
3. Follow confirmed personal samples.
4. Use human references for techniques not settled above.

Never use a preference record as evidence for a factual claim.
