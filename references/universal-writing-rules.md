# Universal writing rules

Apply this reference to every reader-facing drafting, rewriting, polishing, and editing task. It is
the complete universal anti-AI layer. Use it both while drafting and after optional personalization.
Facts and explicit user requirements are hard constraints; expression choices depend on context.

## Task scope

Treat all of the following as content editing even when the user does not say "write," "rewrite,"
or "polish":

- add, delete, replace, or move specified content;
- revise a document from problems, feedback, review comments, or new requirements;
- change headings, paragraphs, lists, tables, quotations, links, examples, tables of contents,
  footnotes, or explanations;
- shorten, expand, correct, deduplicate, standardize terminology, or repair context and structure;
- make a local change while preserving unaffected content.

Identify the object, scope, intended result, and protected content before editing. Explicit changes
override general style preferences. Preserve unaffected facts, meaning, and valid formatting. Do not
apply this layer to code logic, configuration values, filenames, or machine data that contain no
reader-facing prose.

## Priority order

When requirements conflict, use this order:

1. Keep facts accurate; do not invent information, experience, feelings, or examples.
2. Preserve the intended meaning and follow the user's latest explicit requirements.
3. Keep factual relationships and grammar complete.
4. Prefer plain, readable language that sounds natural when read aloud.
5. Adjust rhythm, headings, and layout last.

Completeness means facts, causes, effects, and actions remain connected. It does not require more
words or repeated explanations.

## Facts and narrative identity

- Separate confirmed facts, editable source text, and unconfirmed information. Never present an
  unconfirmed claim as fact.
- Use first person only for actions, experience, and judgments supported by the task evidence.
- In Chinese prose about the author's own projects, actions, or judgments, use `我` only when the
  task evidence supports the statement.
- In general Chinese reader-facing discussion, prefer `我们`; use `大家` when directly addressing a
  reader group. Choose the natural form for the context and do not switch between them repeatedly
  within one paragraph.
- Use `你` for direct instructions or when the source already addresses the reader that way.
- Collective and reader-address language never authorizes invented shared experience, shared
  feelings, consensus, or group opinion.
- Unless the user explicitly removes or replaces them, preserve names, dates, numbers, quotations,
  links, code, product names, and cited sources.
- When the user requests polishing only, improve expression without silently changing the position,
  conclusion, information order, or level of detail.

## Words and sentences

- State concrete actors, objects, facts, processes, and judgments directly. Preserve necessary
  technical concepts, product names, code, business logic, and design decisions.
- Every phrase should contribute a fact, qualification, judgment, or connection. Remove filler,
  repeated meaning, and empty tone markers.
- Replace vague action verbs and metaphors with the actual action when the context identifies it.
  Prefer verbs such as inspect, verify, organize, implement, process, write, run, and compare.
- Do not mechanically replace ordinary verbs or fixed expressions when the replacement would sound
  less natural or change the meaning.
- Keep subjects and references clear, actions paired with their objects, and modifiers unambiguous.
  Omit a subject naturally when the context already makes it clear.
- Vary sentence length. Avoid both continuous fragments and overloaded sentences containing several
  independent judgments.
- Make the prose sound like a person explaining something naturally, without relying on filler or
  compressed, ungrammatical pseudo-conversation.

## Logic and structure

- Organize information by its real relationship. When the evidence contains a cause, effect, and
  response, preserve the intermediate reasoning.
- Explain important judgments as needed without restating the same conclusion in different words.
  Compare tools or options through concrete capabilities, limitations, and use cases.
- Use paragraphs for connected reasoning and lists for genuinely parallel concepts, procedures,
  checks, or reference information.
- Keep list items at the same logical level. Do not split every sentence into a bullet or divide one
  complete thought into several lines for rhythm.
- Divide sections when the topic, process, or boundary changes. Do not force a fixed number of
  sections, symmetrical headings, or a reusable rhetorical template.
- An opening may provide context, facts, or a judgment; it does not always need to lead with the
  conclusion. End when the information is complete without adding a moral or value summary.
- Treat headings as content labels. State the subject or an evidence-supported conclusion directly.
  Do not append slogans, invented actions, forced contrast, or decorative parallel phrasing.
- Give every heading enough supporting text. Do not create a section for a single isolated sentence.

## Fixed AI-writing patterns

Treat these as review signals, not a blacklist. Keep an expression when it carries a real fact,
cause, contrast, or qualification. Revise it when it is empty, repetitive, or removable without
changing the meaning.

- Remove generic scene-setting and transitions that add no necessary context, such as broad claims
  about a changing era or statements equivalent to "it is worth noting."
- Replace unsupported importance claims, milestone language, and value statements with the confirmed
  action, change, or result.
- Replace vague attribution such as "experts say," "research shows," or "many users report" with an
  identified source. Remove the authority claim when no source exists.
- Remove analytical tails that assert unsupported causality, significance, or deeper meaning.
- Replace formulaic challenge-to-optimism transitions and generic positive endings with confirmed
  limitations, results, or next steps.
- Remove chat residue and flattery from reader-facing artifacts, including greetings, praise for the
  question, generic offers of further help, and similar assistant-to-user language.
- Merge repeated uncertainty markers while preserving the actual degree of certainty.
- Review forced groups of three, false "from A to B" ranges, unnecessary synonym rotation, repeated
  dashes, decorative bold labels, and emoji. Preserve them only when the structure genuinely helps.

## Expressions to avoid

- Do not invent friends, users, feedback, personal experience, use cases, or emotions.
- Do not package ordinary facts in slogans, promotional jargon, novelty metaphors, personification,
  or decorative imagery.
- Avoid template introductions and summaries equivalent to "the core issue is," "the key difference
  is," "the reason is simple," or "in conclusion" when they add no information.
- Do not repeatedly use negated parallel structures merely to manufacture contrast. Use them when a
  real misconception must be corrected.
- Do not use quotation marks as decoration or add unnecessary translations in parentheses.
- Do not hide actions behind vague operational metaphors. Name the actor, action, and object.
- Do not end with generic uplift, a lesson, or a claim of broader significance unsupported by the
  material.
- Do not place generation time, model names, API details, script paths, or maintenance commentary in
  the reader-facing artifact unless the task itself requires them.

## Content-specific handling

- **Long articles, blogs, speeches, and biographies:** Use first person only for supported projects,
  actions, and judgments. Explain necessary causes and process. Use plain second-level headings when
  the content genuinely separates into topics.
- **Websites, product descriptions, and landing pages:** State what the product is, what it does, who
  it suits, and its limitations. Do not decide on the reader's behalf that it is excellent.
- **Short social posts:** Natural conversational rhythm is acceptable, but do not invent a premise,
  audience reaction, or shared experience.
- **Documentation, API text, and formal notices:** Prioritize accuracy and clarity. State operations,
  conditions, and necessary explanations directly.

## Structure and formatting

- Do not repeat the document's H1 as the first body line when the title already exists outside the
  body. Use second-level headings only as needed.
- When revising an existing artifact, preserve Markdown hierarchy, links, code, and necessary
  formatting outside the requested change.
- Return the revised artifact directly. Add a change explanation only when the user asks for one.
- Preserve the source language unless the user requests translation. Use punctuation and spacing
  conventions appropriate to that language; keep code punctuation unchanged.
- In Chinese prose, place one half-width space between Chinese text and adjacent Latin words or
  numbers, and use full-width sentence punctuation. Keep pure English and code punctuation
  half-width.

## Markdown deletion semantics

When the user says content should be omitted, deleted, removed, canceled, no longer exist, or must
not appear, remove it from the target document completely. Do not rewrite it as "Do not include X,"
"X is prohibited," "X is unsupported," or "X has been canceled, does not exist, or was removed."

The deletion covers headings, body text, lists, tables, quotations, comments, code blocks, examples,
links, tables of contents, footnotes, and related explanations. Repair the surrounding context and
document structure so no remnant, broken reference, or incomplete sentence remains.

Unless the user explicitly requests a prohibition rule, deprecation notice, or historical record,
the target document must not retain the removed information in any form. Inspect the completed file
and its diff to confirm that neither the original content nor a negated rewrite remains.

"Do not modify X" and "Do not delete X" protect X and do not invoke this deletion rule.

## English

- Use common, direct words and natural contractions.
- Prefer simple connectors such as `if`, `so`, `and`, and `but`; use formal connectors only when the
  context benefits from them.
- Avoid formulaic transitions such as `That said`, `It is worth noting that`, `In conclusion`, and
  `At the end of the day` when they add no information.
- Do not add unnecessary translations for English concepts.

## Completion review

For a file-based artifact, run:

```bash
python3 <skill-dir>/scripts/tone_lint.py <file>
```

For a chat-only artifact, pass the completed draft through stdin without creating a temporary file:

```bash
python3 <skill-dir>/scripts/tone_lint.py -
```

Fix every `FAIL` and re-run the command. Review each `WARN` in context; keep the expression only when
it performs a real function. After the script passes, read the complete artifact aloud and perform a
manual review against this reference. The script detects known patterns and cannot replace judgment.
