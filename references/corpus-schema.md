# Corpus registry schema

## Contents

1. Location and format
2. Required fields
3. Roles and status
4. Human Technique Index
5. Example
6. Classification rules

## Location and format

Store the default registry at:

`05-areas/writing-style/Corpus Registry.md`

Keep one JSON object per line inside a fenced `jsonl` block. Paths are relative to the vault.
The Markdown file is canonical; generated statistics and retrieval output are disposable.

## Required fields

| Field | Allowed values or meaning |
| --- | --- |
| `id` | Stable unique identifier |
| `path` | Relative Markdown path inside the vault |
| `role` | `personal`, `human-reference`, `negative`, or `holdout` |
| `status` | `candidate`, `confirmed`, or `rejected` |
| `authorship` | `user`, `third-party`, `mixed`, or `unknown` |
| `approval` | `user-confirmed`, `curator-confirmed`, or `unreviewed` |
| `language` | Usually `zh`, `en`, or `mixed` |
| `genre` | Stable local label such as `technical-article` |
| `audience` | Stable local label such as `public` or `internal` |
| `weight` | Number from `0` to `2`; default `1` |
| `origin_claim` | `user-authored`, `pre-generative-ai`, `attributed-human`, `human-edited`, `mixed`, or `unknown` |
| `origin_confidence` | `high`, `medium`, `low`, or `unknown` |

Optional fields include `channel`, `purpose`, `author`, `rights`, `license_id`, `allowed_uses`,
`origin_basis`, `confirmation_evidence`, `notes`, and `created`. `origin_basis`, `author`,
`rights`, `license_id`, and a non-empty `allowed_uses` list become required when a human reference
is confirmed. Allowed use values are `private`, `noncommercial`, and `commercial`. Confirmed
personal and holdout entries require a `user-authored` claim with at least medium confidence and
`confirmation_evidence` pointing to an existing source or journal record inside the vault.

Documents whose frontmatter declares `sensitivity: secret` must not be registered in any
writing-memory role, even when a curator or user otherwise confirms the entry; the validator and
promotion commands reject them before retrieval or journal writing.

For a human reference, use a stable license identifier such as `CC-BY-SA-4.0` in `license_id`,
list the permitted task uses in `allowed_uses`, and put attribution, noncommercial, share-alike,
passage-reuse, or other material limits in `rights` and `notes`. The `context` command returns
these fields with the excerpt. It excludes a source when the declared intended use is not allowed;
`unknown` is compatible only with a source allowed for private, noncommercial, and commercial use.

Keep durable writing preferences out of this registry. Store them in `Voice Profile.md` by
following [preference-memory.md](preference-memory.md); registry entries describe documents,
while preference records describe confirmed behavior.

## Human Technique Index

Store curator-inferred writing methods separately at
`05-areas/writing-style/Human Technique Index.md`. The registry remains the source record's
identity, provenance, rights, and scope; the technique index is a derived retrieval aid and must
never be copied into the source text or treated as an author's own rule.

Each active card is one JSON object inside a `jsonl` block:

```jsonl
{"kind":"human-technique","id":"technique-example","corpus_id":"human-example","status":"confirmed","approval":"curator-confirmed","collection_id":"example-book","techniques":["先解释机制存在的理由","把例外放在对应规则附近"],"technique_basis":"Codex curator inference from the preserved source; retrieval cue only.","created":"2026-08-15"}
```

`corpus_id` must point to a confirmed `human-reference`. `techniques` contains at most 12 short
labels, each no longer than 120 characters. `technique_basis` records that the labels are a
curator inference. `collection_id` groups chapters or related pages so retrieval can diversify
the returned evidence. The `context` command returns these fields with
`technique_status: curator-inference`; it still returns the source excerpt and rights metadata
as the authoritative evidence.

## Roles and status

- `personal`: May shape the user's voice. A confirmed entry must use `authorship: user`,
  `approval: user-confirmed`, and `status: confirmed`.
- `human-reference`: May teach writing technique but never personal identity or task facts.
- A confirmed `human-reference` must have `third-party` authorship, curator approval, an allowed
  reference use, an external source URL, and a medium/high-confidence origin claim of
  `pre-generative-ai`, `attributed-human`, or `human-edited`.
- `negative`: Rejected or known-unwanted writing used as contrastive evidence.
- `holdout`: Confirmed personal writing reserved for evaluation and never returned by `context`.
- `candidate`: Discoverable but excluded from normal retrieval.
- `rejected`: Preserved for traceability and excluded from positive retrieval.

## Example

```jsonl
{"id":"personal-agent-article-01","path":"06-output/published/Agent Memory.md","role":"personal","status":"confirmed","authorship":"user","approval":"user-confirmed","origin_claim":"user-authored","origin_confidence":"high","origin_basis":"user confirmed authorship and current representativeness","confirmation_evidence":"02-sources/2026-08-15 Personal sample confirmation.md","language":"zh","genre":"technical-article","audience":"public","weight":1.2,"rights":"owned"}
{"id":"human-compaction-01","path":"02-sources/How Compaction Works.md","role":"human-reference","status":"confirmed","authorship":"third-party","approval":"curator-confirmed","origin_claim":"attributed-human","origin_confidence":"medium","origin_basis":"named publisher, dated original page, and curator review","language":"en","genre":"technical-article","audience":"technical-practitioner","weight":1.0,"author":"Example Publisher","rights":"public reference; no passage reuse","license_id":"public-reference-no-reuse","allowed_uses":["private"]}
{"id":"personal-holdout-01","path":"06-output/published/RAG Evaluation.md","role":"holdout","status":"confirmed","authorship":"user","approval":"user-confirmed","origin_claim":"user-authored","origin_confidence":"high","origin_basis":"user confirmed authorship and reserved the sample for evaluation","confirmation_evidence":"02-sources/2026-08-15 Holdout confirmation.md","language":"zh","genre":"technical-article","audience":"public","weight":1.0,"rights":"owned"}
```

## Classification rules

1. Register source provenance before style interpretation.
2. Do not infer authorship from a filename, account owner, or publication location alone.
3. Mark edited model output as `mixed` until the user confirms it represents their final voice.
4. Keep third-party excerpts short in generated context and do not copy distinctive phrases.
5. Use separate entries when one document contains materially different genres or authors.
6. Reserve about 10–20% of mature personal samples as `holdout` once enough material exists.
7. Treat `catalog` origin fields as suggestions. Metadata can justify candidacy, not human
   authorship or current personal-voice representativeness by itself.
8. Do not expose candidate entries through drafting retrieval. Inspect them only in the registry
   while deciding whether the user or curator can confirm them.
9. Do not infer personal voice from account ownership or frontmatter author alone. Treat a document
   dominated by quotations, translations, interview-question compilations, or copied source text
   as mixed until the user's own contribution can be separated and confirmed.
10. Use `promote-sample` for personal and holdout confirmation. Preview first; persist only with
    both explicit confirmation flags and a source or journal record that preserves the evidence.
11. Keep technique cards in the separate index. Do not add them to the corpus registry or promote
    them into universal hard rules without cross-genre regression evidence.
12. Use `promote-negative` for a rejected draft or expression only after the user explicitly
    identifies it as something to avoid. Negative entries use `status: rejected`, remain outside
    the personal profile, and are returned only in the separate negative context channel.
