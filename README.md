<div align="center">
  <h1>Voiceforge</h1>
  <p><em>Reduce generic AI phrasing. Learn personal expression.</em></p>
</div>

Voiceforge reduces generic AI writing in Chinese and English through two cumulative layers. Its
universal layer contains a complete fixed writing and editing baseline. Its optional personalized
layer retrieves user-confirmed samples, preferences, and feedback from a Markdown knowledge base.

It applies a personal voice only when authorship and current representativeness are confirmed.
Account ownership, publication location, and silence are not treated as proof of a writing style.

The repository contains reusable Skill instructions and deterministic Python tooling. It does not
contain a user's articles, voice profile, corpus registry, feedback journal, or holdout samples.

<p align="center">
  <img src="assets/voiceforge-intro-en.png" alt="Voiceforge reduces generic AI phrasing and learns personal expression" width="100%" />
</p>

## What It Is For

Use Voiceforge when a writing task needs more than a generic style prompt:

- apply a complete universal anti-AI writing baseline to every draft or edit;
- make targeted additions, deletions, replacements, moves, structural changes, corrections, or
  feedback-driven edits without changing unaffected content;
- reduce generic AI phrasing while preserving facts and user constraints;
- learn personalized expression from confirmed writing samples and explicit preferences;
- maintain universal writing techniques from provenance-reviewed human references;
- draft, revise, and compare text against approved writing;
- preserve explicit feedback without turning unconfirmed signals into permanent rules.

## Why It Exists

A generic style prompt can make prose sound polished without making it sound like a particular
person. Voiceforge treats personal expression as evidence that must be confirmed, scoped, and
updated through explicit feedback.

The system keeps different kinds of writing evidence in separate channels:

- **Task evidence** supplies claims, examples, and conclusions.
- **Confirmed personal samples** shape voice, rhythm, structure, and recurring preferences.
- **Human references** support curator research for the universal layer; they do not directly shape
  task output or contribute the user's identity, opinions, or facts.
- **Feedback and negative samples** record what the user explicitly prefers or rejects.

The system does not infer personal authorship from an account name, publication location, or
silence. Candidate samples stay out of drafting context until the user confirms authorship and
current representativeness. Secret records and human references whose rights do not match the
intended use are excluded before retrieval.

## Quick Start

Link a local checkout into the shared Agent Skills directory:

```bash
mkdir -p ~/.agents/skills
ln -sfn /path/to/Voiceforge ~/.agents/skills/voiceforge
```

Validate the knowledge base before using it:

```bash
python3 scripts/voice_memory.py validate --vault /path/to/knowledge-base
```

Retrieve scoped style evidence for a writing task:

```bash
python3 scripts/voice_memory.py context \
  --vault /path/to/knowledge-base \
  --language zh --genre technical-article --audience public \
  --intended-use unknown --query "topic and writing purpose"
```

When the task facts already exist in a source or journal record, prepare them separately from
the style context:

```bash
python3 scripts/voice_memory.py prepare \
  --vault /path/to/knowledge-base \
  --fact-packet 02-sources/fact-packet.md \
  --language zh --genre technical-article --audience public \
  --intended-use unknown --query "topic and writing purpose"
```

## How It Works

1. Read and apply the complete universal rules in `references/universal-writing-rules.md`.
2. Look for a valid Markdown vault and classify the request by language, genre, audience, channel,
   purpose, and intended use. A missing vault is valid.
3. When eligible personal evidence exists, retrieve a small, scope-aware context and use it to shape
   voice, rhythm, and structure. Candidate personal samples never act as fallback evidence.
4. When personal evidence is absent, draft directly from task facts and the universal layer.
5. In both paths, review the result against the complete universal rules and run the bundled
   `scripts/tone_lint.py`, using a file path or stdin for chat-only output. Personalization never
   bypasses this final pass.
6. Record feedback only after an explicit user revision, acceptance, rejection, or preference.

Voiceforge and its universal layer remain available in every activation mode. `shadow` means only
that the personal profile is provisional and must not be described as mature. A healthy registry
means the data follows the schema; it does not by itself prove that personalization is mature.

## What It Contains

| Layer | Role |
| --- | --- |
| Universal writing layer | Contains the complete task, fact, wording, sentence, structure, format, deletion, and anti-AI expression rules |
| Human writing library | Stores provenance, rights, scope, and short technique evidence |
| Human Technique Index | Provides curator-maintained retrieval cues without becoming a hidden prompt |
| Personal voice profile | Stores only user-confirmed samples and durable preferences |
| Scoped retrieval | Selects evidence for the current language, genre, audience, and intended use |
| Feedback memory | Keeps append-only before/after records and explicit negative evidence |
| Holdout evaluation | Measures factual fidelity, constraint fidelity, editing burden, and generalization |

## Per-user Data

Each user supplies a private Markdown vault. The usual records are:

```text
05-areas/writing-style/Corpus Registry.md
05-areas/writing-style/Voice Profile.md
05-areas/writing-style/Human Technique Index.md
08-journal/writing-feedback/
08-journal/writing-sample-confirmations/
```

The registry stores paths and metadata, not a copied corpus. A user can run Voiceforge without
confirmed personal samples; the Skill then uses the complete universal layer and treats the
personal profile as provisional.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Runtime instructions, evidence boundaries, and routing policy |
| `agents/openai.yaml` | Display metadata and the default prompt |
| `references/architecture.md` | Data flow and separation between evidence channels |
| `references/corpus-schema.md` | Registry and Human Technique Index schema |
| `references/evaluation.md` | Test sets, rollout gates, and promotion criteria |
| `references/preference-memory.md` | Confirmed preference storage and supersession rules |
| `references/universal-writing-rules.md` | Complete universal anti-AI writing and editing baseline |
| `scripts/voice_memory.py` | Deterministic registry, retrieval, feedback, and evaluation CLI |
| `scripts/tone_lint.py` | Deterministic final lint for known universal writing failures and warnings |
| `tests/test_voice_memory.py` | Regression tests for the CLI and memory rules |
| `tests/test_tone_lint.py` | Regression tests for the bundled universal lint |

## Common Commands

Inspect a draft against the confirmed profile:

```bash
python3 scripts/voice_memory.py analyze \
  --vault /path/to/knowledge-base --file /path/to/draft.md \
  --language zh --genre technical-article --audience public
```

Preview a feedback record before writing it:

```bash
python3 scripts/voice_memory.py feedback \
  --vault /path/to/knowledge-base \
  --before /path/to/draft.md --after /path/to/user-final.md \
  --verdict revised --task-id example-task \
  --language zh --genre technical-article --audience public
```

Run the regression suite from the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Relationship With oil-tone

Voiceforge now contains the complete capabilities previously supplied by `oil-tone`: the universal
writing rules and deterministic lint are bundled as its required final layer. `oil-tone` remains a
legacy compatibility entry that delegates writing work to Voiceforge. It is not a separate stage or
an external dependency of the Voiceforge pipeline.

## Boundaries

Voiceforge does not fine-tune a model, place an entire writing library in a static prompt, or
reproduce a living writer's distinctive expression. Style examples are not factual sources, and
semantic similarity is not proof of stylistic similarity. Personal data stays in the user's
private vault; only reusable implementation belongs in this repository.

## License

MIT. See [LICENSE](LICENSE).
