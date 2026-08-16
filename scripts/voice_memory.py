#!/usr/bin/env python3
"""Retrieve, measure, and record evidence for a knowledge-backed writing voice."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


DEFAULT_REGISTRY = Path("05-areas/writing-style/Corpus Registry.md")
DEFAULT_VOICE_PROFILE = Path("05-areas/writing-style/Voice Profile.md")
DEFAULT_TECHNIQUE_INDEX = Path("05-areas/writing-style/Human Technique Index.md")
FEEDBACK_DIR = Path("08-journal/writing-feedback")
SAMPLE_CONFIRMATION_DIR = Path("08-journal/writing-sample-confirmations")
NEGATIVE_CONFIRMATION_DIR = Path("08-journal/writing-negative-confirmations")
HUMAN_REFERENCE_CONFIRMATION_DIR = Path("08-journal/writing-human-reference-confirmations")
ROLLOUT_EVALUATION_DIR = Path("08-journal/writing-rollout-evaluations")
ROLES = {"personal", "human-reference", "negative", "holdout"}
STATUSES = {"candidate", "confirmed", "rejected"}
AUTHORSHIP = {"user", "third-party", "mixed", "unknown"}
APPROVALS = {"user-confirmed", "curator-confirmed", "unreviewed"}
ORIGIN_CLAIMS = {
    "user-authored",
    "pre-generative-ai",
    "attributed-human",
    "human-edited",
    "mixed",
    "unknown",
}
ORIGIN_CONFIDENCES = {"high", "medium", "low", "unknown"}
CONFIRMED_HUMAN_ORIGINS = {"pre-generative-ai", "attributed-human", "human-edited"}
INTENDED_USES = {"private", "noncommercial", "commercial", "unknown"}
ALLOWED_USES = INTENDED_USES - {"unknown"}
MIN_HUMAN_REFERENCE_DOCUMENTS = 6
MIN_HUMAN_REFERENCE_GENRES = 3
HUMAN_COLLECTION_DIVERSITY_PENALTY = 2.0
HUMAN_AUTHOR_DIVERSITY_PENALTY = 0.5
HUMAN_TECHNIQUE_DIVERSITY_PENALTY = 1.5
HUMAN_ORIGIN_CONFIDENCE_PENALTY = {
    "high": 0.0,
    "medium": 0.75,
}
STYLE_DELTA_THRESHOLDS = {
    "characters_ratio": 0.05,
    "avg_sentence_chars": 1.0,
    "median_sentence_chars": 1.0,
    "p90_sentence_chars": 2.0,
    "avg_paragraph_chars": 5.0,
    "headings_per_1000": 0.15,
    "list_items_per_1000": 0.25,
    "questions_per_1000": 0.15,
    "first_person_per_1000": 0.15,
    "we_per_1000": 0.15,
    "reader_address_per_1000": 0.15,
    "english_tokens_per_1000": 0.5,
    "colons_per_1000": 0.2,
    "parentheses_per_1000": 0.2,
    "bold_per_1000": 0.15,
    "connectors_per_1000": 0.2,
}
# These cues are used only to rank excerpts from third-party human references. They are
# evidence-hygiene signals, not universal writing rules and never lint the user's draft.
REFERENCE_EXCERPT_RISK_PATTERNS: tuple[tuple[re.Pattern[str], float, str], ...] = (
    (
        re.compile(r"(?:吊打|碾压|秒杀|无敌|神器|牛逼|6\s*到\s*飞起|一图胜千言)"),
        3.0,
        "promotional-hyperbole",
    ),
    (
        re.compile(r"(?:这里附上一张|如下图|见下图|点击(?:这里|此处)|扒拉)"),
        1.5,
        "presentation-meta",
    ),
    (
        re.compile(r"(?:哈哈|嘿嘿|大家好|小伙伴)"),
        1.5,
        "chat-residue",
    ),
)
SCOPE_FIELDS = ("language", "genre", "audience", "channel", "purpose")
SCOPE_MATCH_POINTS = {
    "language": 6.0,
    "genre": 8.0,
    "audience": 4.0,
    "channel": 2.0,
    "purpose": 2.0,
}
SCOPE_MISMATCH_PENALTIES = {
    "language": 5.0,
    "genre": 2.0,
    "audience": 1.0,
    "channel": 0.5,
    "purpose": 0.5,
}
PREFERENCE_BASES = {"explicit-user-statement", "repeated-feedback"}
REQUIRED_FIELDS = (
    "id",
    "path",
    "role",
    "status",
    "authorship",
    "approval",
    "language",
    "genre",
    "audience",
)


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def is_external_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def slugify(value: str) -> str:
    value = normalize(value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value or "writing-task"


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, raw = line.split(":", 1)
        fields[key.strip()] = raw.strip().strip('"').strip("'")
    return fields


def without_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text[end + 5 :] if end >= 0 else text


def source_body(text: str) -> str:
    body = without_frontmatter(text)
    match = re.search(
        r"^## Preserved Content\s*$\n(.*?)(?=^## (?:Provenance|Processing Notes)\s*$|\Z)",
        body,
        flags=re.MULTILINE | re.DOTALL,
    )
    selected = match.group(1).strip() if match else body.strip()
    return without_frontmatter(selected).strip()


def clean_markdown(text: str) -> str:
    """Return visible prose while excluding code and presentation markup."""
    text = source_body(text)
    kept: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^\s*<(script|style)\b", raw, flags=re.IGNORECASE):
            continue
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"<[^>]+>", " ", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"\s*\{#[^}]+\}\s*$", "", line)
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", line)
        line = html.unescape(line)
        line = re.sub(r"[*_~]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if re.fullmatch(r"[:|\- ]+", line):
            line = ""
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def paragraphs(text: str) -> list[str]:
    clean = clean_markdown(text)
    values = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n\s*\n", clean)]
    return [item for item in values if len(re.sub(r"\s+", "", item)) >= 20]


def tokenize(text: str) -> set[str]:
    lowered = normalize(text)
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_+.#/-]*", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return float(ordered[index])


def weighted_median(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(max(weight, 0.0) for _, weight in ordered)
    if total <= 0:
        return statistics.median(values)
    threshold = total / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += max(weight, 0.0)
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def per_thousand(count: int | float, characters: int) -> float:
    return round(float(count) * 1000 / max(characters, 1), 3)


def document_features(text: str) -> dict[str, float | int]:
    body = source_body(text)
    visible = clean_markdown(text)
    characters = len(re.sub(r"\s+", "", visible))
    sentence_values = [
        len(re.sub(r"\s+", "", part))
        for part in re.split(r"(?<=[。！？!?；;])|\n+", visible)
        if len(re.sub(r"\s+", "", part)) >= 2
    ]
    paragraph_values = [len(re.sub(r"\s+", "", item)) for item in paragraphs(text)]
    headings = len(re.findall(r"^\s{0,3}#{1,6}\s+", body, flags=re.MULTILINE))
    list_items = len(re.findall(r"^\s*(?:[-+*]|\d+[.)])\s+", body, flags=re.MULTILINE))
    english_tokens = len(re.findall(r"\b[A-Za-z][A-Za-z0-9_+.#/-]*\b", visible))
    connector_terms = ("其实", "所以", "不过", "比如", "例如", "首先", "其次", "最后", "因此")
    connectors = sum(visible.count(term) for term in connector_terms)
    return {
        "characters": characters,
        "sentences": len(sentence_values),
        "paragraphs": len(paragraph_values),
        "avg_sentence_chars": round(statistics.fmean(sentence_values), 3) if sentence_values else 0.0,
        "median_sentence_chars": round(statistics.median(sentence_values), 3) if sentence_values else 0.0,
        "p90_sentence_chars": round(quantile([float(item) for item in sentence_values], 0.9), 3),
        "avg_paragraph_chars": round(statistics.fmean(paragraph_values), 3) if paragraph_values else 0.0,
        "headings_per_1000": per_thousand(headings, characters),
        "list_items_per_1000": per_thousand(list_items, characters),
        "questions_per_1000": per_thousand(visible.count("？") + visible.count("?"), characters),
        "first_person_per_1000": per_thousand(visible.count("我") - visible.count("我们"), characters),
        "we_per_1000": per_thousand(visible.count("我们"), characters),
        "reader_address_per_1000": per_thousand(visible.count("你") + visible.count("大家"), characters),
        "english_tokens_per_1000": per_thousand(english_tokens, characters),
        "colons_per_1000": per_thousand(visible.count("：") + visible.count(":"), characters),
        "parentheses_per_1000": per_thousand(
            visible.count("（") + visible.count("(") + visible.count("【"), characters
        ),
        "bold_per_1000": per_thousand(len(re.findall(r"\*\*[^*]+\*\*", body)), characters),
        "connectors_per_1000": per_thousand(connectors, characters),
    }


def style_delta(before: str, after: str) -> dict[str, float]:
    before_features = document_features(before)
    after_features = document_features(after)
    before_characters = max(float(before_features["characters"]), 1.0)
    delta = {
        "characters_ratio": round(
            (float(after_features["characters"]) - float(before_features["characters"]))
            / before_characters,
            4,
        )
    }
    for name in STYLE_DELTA_THRESHOLDS:
        if name == "characters_ratio":
            continue
        delta[name] = round(float(after_features[name]) - float(before_features[name]), 4)
    return delta


def registry_path(vault: Path, value: str | None) -> Path:
    path = Path(value) if value else DEFAULT_REGISTRY
    return path.resolve() if path.is_absolute() else (vault / path).resolve()


def voice_profile_path(vault: Path, value: str | None = None) -> Path:
    path = Path(value) if value else DEFAULT_VOICE_PROFILE
    return path.resolve() if path.is_absolute() else (vault / path).resolve()


def technique_index_path(vault: Path, value: str | None = None) -> Path:
    path = Path(value) if value else DEFAULT_TECHNIQUE_INDEX
    return path.resolve() if path.is_absolute() else (vault / path).resolve()


def jsonl_blocks(text: str) -> list[str]:
    return re.findall(r"```jsonl\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)


def read_registry(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        return [], [f"registry not found: {path}"]
    blocks = jsonl_blocks(path.read_text(encoding="utf-8"))
    if not blocks:
        return [], [f"registry has no jsonl block: {path}"]
    entries: list[dict[str, Any]] = []
    issues: list[str] = []
    for number, line in enumerate(blocks[0].splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append(f"registry jsonl line {number}: {error.msg}")
            continue
        if not isinstance(value, dict):
            issues.append(f"registry jsonl line {number}: entry must be an object")
            continue
        entries.append(value)
    return entries, issues


def write_registry(path: Path, entries: list[dict[str, Any]]) -> None:
    text = path.read_text(encoding="utf-8")
    body = "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries)
    pattern = re.compile(r"(```jsonl\s*\n)(.*?)(\n```)", flags=re.DOTALL | re.IGNORECASE)
    updated, count = pattern.subn(lambda match: match.group(1) + body + match.group(3), text, count=1)
    if count != 1:
        raise ValueError(f"registry has no writable jsonl block: {path}")
    if updated.startswith("---\n"):
        updated = re.sub(
            r"(?m)^updated:\s*.*$", f"updated: {date.today().isoformat()}", updated, count=1
        )
    path.write_text(updated, encoding="utf-8")


def inside_vault(vault: Path, relative: str) -> tuple[Path | None, str | None]:
    candidate = (vault / relative).resolve()
    try:
        candidate.relative_to(vault.resolve())
    except ValueError:
        return None, f"path escapes vault: {relative}"
    return candidate, None


def read_technique_records(
    vault: Path,
    entries: list[dict[str, Any]],
    path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    selected = path or technique_index_path(vault)
    if not selected.is_file():
        return [], []
    blocks = jsonl_blocks(selected.read_text(encoding="utf-8"))
    if not blocks:
        return [], [f"human technique index has no jsonl block: {selected}"]
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for number, line in enumerate(blocks[0].splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append(f"human technique jsonl line {number}: {error.msg}")
            continue
        if not isinstance(value, dict):
            issues.append(f"human technique jsonl line {number}: record must be an object")
            continue
        records.append(value)

    entries_by_id = {str(entry.get("id")): entry for entry in entries}
    seen_ids: set[str] = set()
    seen_corpus_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        label = str(record.get("id") or f"human-technique-{index}")
        if label in seen_ids:
            issues.append(f"{label}: duplicate human technique id")
        seen_ids.add(label)
        for field in (
            "id",
            "kind",
            "corpus_id",
            "status",
            "approval",
            "techniques",
            "technique_basis",
            "created",
        ):
            if record.get(field) in (None, ""):
                issues.append(f"{label}: missing {field}")
        if record.get("kind") != "human-technique":
            issues.append(f"{label}: invalid kind {record.get('kind')!r}")
        if record.get("status") != "confirmed" or record.get("approval") != "curator-confirmed":
            issues.append(
                f"{label}: human technique cards require confirmed status and curator approval"
            )
        corpus_id = str(record.get("corpus_id", ""))
        if corpus_id in seen_corpus_ids:
            issues.append(f"{label}: duplicate active technique card for corpus_id {corpus_id}")
        seen_corpus_ids.add(corpus_id)
        entry = entries_by_id.get(corpus_id)
        if (
            entry is None
            or entry.get("role") != "human-reference"
            or entry.get("status") != "confirmed"
        ):
            issues.append(
                f"{label}: corpus_id must reference a confirmed human-reference entry"
            )
        collection_id = record.get("collection_id")
        if collection_id is not None and (
            not isinstance(collection_id, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", collection_id)
        ):
            issues.append(f"{label}: collection_id must be a stable lowercase identifier")
        techniques = record.get("techniques")
        if not isinstance(techniques, list) or not techniques:
            issues.append(f"{label}: techniques must be a non-empty list")
            techniques = []
        if len(techniques) > 12:
            issues.append(f"{label}: techniques must contain at most 12 items")
        normalized_techniques: list[str] = []
        for technique in techniques:
            if not isinstance(technique, str) or not technique.strip():
                issues.append(f"{label}: techniques must contain non-empty strings")
                continue
            if len(technique.strip()) > 120:
                issues.append(f"{label}: technique is longer than 120 characters")
            normalized_techniques.append(normalize(technique))
        if len(normalized_techniques) != len(set(normalized_techniques)):
            issues.append(f"{label}: techniques contains duplicates")
        if not str(record.get("technique_basis", "")).strip():
            issues.append(f"{label}: missing curator-written technique_basis")
    return records, issues


def enrich_human_techniques(
    entries: list[dict[str, Any]], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_corpus_id = {str(record["corpus_id"]): record for record in records}
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        copy = dict(entry)
        record = by_corpus_id.get(str(entry.get("id")))
        if record is not None:
            copy.update(
                {
                    "collection_id": record.get("collection_id"),
                    "techniques": list(record.get("techniques", [])),
                    "technique_basis": record.get("technique_basis"),
                    "technique_card_id": record.get("id"),
                }
            )
        enriched.append(copy)
    return enriched


def technique_card_record(
    entries: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    matches = [
        entry
        for entry in entries
        if str(entry.get("id")) == str(args.corpus_id)
    ]
    if len(matches) != 1:
        raise ValueError(
            "--corpus-id must reference exactly one registry entry: " + args.corpus_id
        )
    entry = matches[0]
    if entry.get("role") != "human-reference" or entry.get("status") != "confirmed":
        raise ValueError("technique cards can only reference confirmed human-reference entries")
    techniques = [str(item).strip() for item in args.technique if str(item).strip()]
    if not techniques:
        raise ValueError("at least one non-empty --technique is required")
    if len(techniques) > 12 or any(len(item) > 120 for item in techniques):
        raise ValueError("technique cards allow at most 12 labels of 120 characters each")
    if len({normalize(item) for item in techniques}) != len(techniques):
        raise ValueError("--technique values must be distinct")
    if not args.technique_basis.strip():
        raise ValueError("--technique-basis must explain the curator inference")
    if args.collection_id and not re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{0,79}", args.collection_id
    ):
        raise ValueError("--collection-id must be a stable lowercase identifier")
    identity = {
        "corpus_id": args.corpus_id,
        "collection_id": args.collection_id or "",
        "techniques": techniques,
        "technique_basis": args.technique_basis.strip(),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:10]
    record: dict[str, Any] = {
        "kind": "human-technique",
        "id": f"technique-{slugify(args.corpus_id)[:44]}-{digest}",
        "corpus_id": args.corpus_id,
        "status": "confirmed" if args.curator_confirmed else "proposed",
        "approval": "curator-confirmed" if args.curator_confirmed else "unreviewed",
        "techniques": techniques,
        "technique_basis": args.technique_basis.strip(),
        "created": date.today().isoformat(),
    }
    if args.collection_id:
        record["collection_id"] = args.collection_id
    return record


def write_technique_record(
    vault: Path, entries: list[dict[str, Any]], record: dict[str, Any]
) -> bool:
    path = technique_index_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        today = date.today().isoformat()
        path.write_text(
            "---\n"
            "id: human-writing-technique-index\n"
            "type: area\n"
            "status: active\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            "sensitivity: private\n"
            "---\n\n"
            "# Human Technique Index\n\n"
            "Curator-inferred retrieval cues for confirmed human-reference sources.\n\n"
            "```jsonl\n"
            + json.dumps(record, ensure_ascii=False)
            + "\n```\n",
            encoding="utf-8",
        )
        return True
    current_records, issues = read_technique_records(vault, entries)
    if issues:
        raise ValueError("invalid human technique index:\n- " + "\n- ".join(issues))
    existing = next(
        (item for item in current_records if item.get("corpus_id") == record.get("corpus_id")),
        None,
    )
    if existing is not None:
        if existing == record:
            return False
        raise ValueError(
            "a technique card already exists for this corpus_id; preserve it and review manually"
        )
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(```jsonl\s*\n)(.*?)(\n```)", flags=re.DOTALL | re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"human technique index has no writable jsonl block: {path}")
    current = match.group(2).rstrip()
    replacement = (current + "\n" if current else "") + json.dumps(record, ensure_ascii=False)
    updated = text[: match.start(2)] + replacement + text[match.end(2) :]
    updated = re.sub(
        r"(?m)^updated:\s*.*$", f"updated: {date.today().isoformat()}", updated, count=1
    )
    path.write_text(updated, encoding="utf-8")
    return True


def read_preference_records(vault: Path, path: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    selected = path or voice_profile_path(vault)
    if not selected.is_file():
        return [], []
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for block_number, block in enumerate(jsonl_blocks(selected.read_text(encoding="utf-8")), start=1):
        for line_number, line in enumerate(block.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                issues.append(
                    f"voice profile jsonl block {block_number} line {line_number}: {error.msg}"
                )
                continue
            if isinstance(value, dict) and value.get("kind") == "preference":
                records.append(value)
    issues.extend(validate_preference_records(vault, records))
    return records, issues


def validate_preference_records(vault: Path, records: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    ids = {str(item.get("id", "")) for item in records if item.get("id")}
    for index, record in enumerate(records, start=1):
        label = str(record.get("id") or f"preference-{index}")
        if label in seen:
            issues.append(f"{label}: duplicate preference id")
        seen.add(label)
        for field in ("id", "text", "status", "approval", "basis", "created"):
            if record.get(field) in (None, ""):
                issues.append(f"{label}: missing {field}")
        if record.get("status") != "confirmed" or record.get("approval") != "user-confirmed":
            issues.append(f"{label}: durable preferences require confirmed status and user confirmation")
        if record.get("basis") not in PREFERENCE_BASES:
            issues.append(f"{label}: invalid preference basis {record.get('basis')!r}")
        evidence = record.get("evidence", [])
        if not isinstance(evidence, list):
            issues.append(f"{label}: evidence must be a list")
            evidence = []
        if record.get("basis") == "repeated-feedback" and len(set(map(str, evidence))) < 3:
            issues.append(f"{label}: repeated-feedback preference requires three evidence records")
        for raw_path in evidence:
            target, problem = inside_vault(vault, str(raw_path))
            if problem:
                issues.append(f"{label}: {problem}")
            elif target is None or not target.is_file():
                issues.append(f"{label}: evidence file not found: {raw_path}")
            elif record.get("basis") == "repeated-feedback":
                relative = target.relative_to(vault).as_posix()
                fields = parse_frontmatter(target.read_text(encoding="utf-8"))
                if (
                    not relative.startswith(FEEDBACK_DIR.as_posix() + "/")
                    or fields.get("type") != "journal"
                    or fields.get("status") != "verified"
                    or fields.get("reviewer") != "user"
                    or normalize(fields.get("reviewer_confirmed", "")) != "true"
                ):
                    issues.append(
                        f"{label}: repeated-feedback evidence is not a verified "
                        f"user-confirmed feedback record: {raw_path}"
                    )
        supersedes = str(record.get("supersedes", "")).strip()
        if supersedes and supersedes not in ids:
            issues.append(f"{label}: superseded preference not found: {supersedes}")
        if supersedes == label:
            issues.append(f"{label}: preference cannot supersede itself")
    return issues


def active_preference_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {
        str(item.get("supersedes"))
        for item in records
        if item.get("status") == "confirmed" and item.get("supersedes")
    }
    return [
        item
        for item in records
        if item.get("status") == "confirmed"
        and item.get("approval") == "user-confirmed"
        and str(item.get("id")) not in superseded
    ]


def select_preferences(
    records: list[dict[str, Any]], args: argparse.Namespace, limit: int = 8
) -> list[dict[str, Any]]:
    scope = {key: getattr(args, key, None) for key in SCOPE_FIELDS}
    ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for record in active_preference_records(records):
        match = scope_match_details(record, scope)
        score = 0.0
        score += sum(SCOPE_MATCH_POINTS[key] for key in match["exact_fields"])
        score += sum(SCOPE_MATCH_POINTS[key] / 2 for key in match["compatible_fields"])
        score -= sum(SCOPE_MISMATCH_PENALTIES[key] for key in match["fallback_fields"])
        ranked.append((score, record, match))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id", ""))))
    return [
        {
            "id": record["id"],
            "text": record["text"],
            "basis": record["basis"],
            "evidence": record.get("evidence", []),
            "scope": {key: record.get(key) for key in SCOPE_FIELDS if record.get(key)},
            "match_quality": match["quality"],
            "fallback_fields": match["fallback_fields"],
        }
        for _, record, match in ranked[:limit]
    ]


def validate_entries(vault: Path, entries: list[dict[str, Any]], initial: Iterable[str] = ()) -> list[str]:
    issues = list(initial)
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        label = str(entry.get("id") or f"entry-{index}")
        for field in REQUIRED_FIELDS:
            if entry.get(field) in (None, ""):
                issues.append(f"{label}: missing {field}")
        if label in seen:
            issues.append(f"{label}: duplicate id")
        seen.add(label)
        role = entry.get("role")
        status = entry.get("status")
        authorship = entry.get("authorship")
        approval = entry.get("approval")
        origin_claim = entry.get("origin_claim", "unknown")
        origin_confidence = entry.get("origin_confidence", "unknown")
        if role not in ROLES:
            issues.append(f"{label}: invalid role {role!r}")
        if status not in STATUSES:
            issues.append(f"{label}: invalid status {status!r}")
        if authorship not in AUTHORSHIP:
            issues.append(f"{label}: invalid authorship {authorship!r}")
        if approval not in APPROVALS:
            issues.append(f"{label}: invalid approval {approval!r}")
        if origin_claim not in ORIGIN_CLAIMS:
            issues.append(f"{label}: invalid origin_claim {origin_claim!r}")
        if origin_confidence not in ORIGIN_CONFIDENCES:
            issues.append(f"{label}: invalid origin_confidence {origin_confidence!r}")
        try:
            weight = float(entry.get("weight", 1.0))
            if not 0 <= weight <= 2:
                issues.append(f"{label}: weight must be between 0 and 2")
        except (TypeError, ValueError):
            issues.append(f"{label}: weight must be numeric")
        if any(
            key in entry
            for key in ("collection_id", "techniques", "technique_basis", "technique_card_id")
        ):
            issues.append(
                f"{label}: technique metadata belongs in Human Technique Index, not the corpus registry"
            )
        relative = entry.get("path")
        if isinstance(relative, str) and relative:
            target, problem = inside_vault(vault, relative)
            if problem:
                issues.append(f"{label}: {problem}")
            elif target is not None and (not target.is_file() or target.suffix.lower() != ".md"):
                issues.append(f"{label}: Markdown file not found: {relative}")
            elif target is not None and role in {"personal", "holdout", "negative", "human-reference"}:
                target_fields = parse_frontmatter(target.read_text(encoding="utf-8"))
                if normalize(target_fields.get("sensitivity", "unknown")) == "secret":
                    issues.append(
                        f"{label}: secret documents cannot be registered in writing-style memory"
                    )
        if role in {"personal", "holdout"} and status == "confirmed":
            if authorship != "user" or approval != "user-confirmed":
                issues.append(
                    f"{label}: confirmed {role} requires authorship=user and approval=user-confirmed"
                )
            if origin_claim != "user-authored" or origin_confidence not in {"medium", "high"}:
                issues.append(
                    f"{label}: confirmed {role} requires origin_claim=user-authored and medium/high confidence"
                )
            confirmation_evidence = entry.get("confirmation_evidence")
            if not isinstance(confirmation_evidence, str) or not confirmation_evidence.strip():
                issues.append(f"{label}: confirmed {role} requires confirmation_evidence")
            else:
                evidence_target, evidence_problem = inside_vault(vault, confirmation_evidence)
                if evidence_problem:
                    issues.append(f"{label}: {evidence_problem}")
                elif evidence_target is None or not evidence_target.is_file():
                    issues.append(
                        f"{label}: confirmation evidence not found: {confirmation_evidence}"
                    )
                else:
                    evidence_type = parse_frontmatter(
                        evidence_target.read_text(encoding="utf-8")
                    ).get("type")
                    if evidence_type not in {"source", "journal"}:
                        issues.append(
                            f"{label}: confirmation evidence must be a source or journal record"
                        )
        if role == "negative":
            if status != "rejected":
                issues.append(f"{label}: negative evidence must use status=rejected")
            if approval != "user-confirmed":
                issues.append(
                    f"{label}: negative evidence requires explicit user confirmation"
                )
            if not str(entry.get("negative_reason", "")).strip():
                issues.append(f"{label}: negative evidence requires negative_reason")
            if isinstance(relative, str) and relative:
                target, target_problem = inside_vault(vault, relative)
                if not target_problem and target is not None and target.is_file():
                    if parse_frontmatter(target.read_text(encoding="utf-8")).get("sensitivity") == "secret":
                        issues.append(f"{label}: secret documents cannot be negative style evidence")
            confirmation_evidence = entry.get("confirmation_evidence")
            if not isinstance(confirmation_evidence, str) or not confirmation_evidence.strip():
                issues.append(f"{label}: negative evidence requires confirmation_evidence")
            else:
                evidence_target, evidence_problem = inside_vault(vault, confirmation_evidence)
                if evidence_problem:
                    issues.append(f"{label}: {evidence_problem}")
                elif evidence_target is None or not evidence_target.is_file():
                    issues.append(
                        f"{label}: confirmation evidence not found: {confirmation_evidence}"
                    )
                else:
                    evidence_type = parse_frontmatter(
                        evidence_target.read_text(encoding="utf-8")
                    ).get("type")
                    if evidence_type not in {"source", "journal"}:
                        issues.append(
                            f"{label}: negative confirmation evidence must be a source or journal record"
                        )
        if role == "human-reference" and status == "confirmed":
            if authorship != "third-party" or approval != "curator-confirmed":
                issues.append(
                    f"{label}: confirmed human-reference requires third-party authorship and curator confirmation"
                )
            if origin_claim not in CONFIRMED_HUMAN_ORIGINS or origin_confidence not in {"medium", "high"}:
                issues.append(
                    f"{label}: confirmed human-reference needs an attributed/pre-generative/human-edited origin with medium/high confidence"
                )
            for field in ("author", "origin_basis", "rights", "license_id"):
                if not str(entry.get(field, "")).strip():
                    issues.append(f"{label}: confirmed human-reference missing {field}")
            allowed_uses = entry.get("allowed_uses")
            if not isinstance(allowed_uses, list) or not allowed_uses:
                issues.append(f"{label}: confirmed human-reference needs non-empty allowed_uses")
                allowed_uses = []
            normalized_uses = [str(item) for item in allowed_uses]
            invalid_uses = sorted(set(normalized_uses) - ALLOWED_USES)
            if invalid_uses:
                issues.append(f"{label}: invalid allowed_uses {invalid_uses}")
            if len(normalized_uses) != len(set(normalized_uses)):
                issues.append(f"{label}: allowed_uses contains duplicates")
            license_id = str(entry.get("license_id", "")).upper()
            if re.search(r"(?:^|-)NC(?:-|$)", license_id) and "commercial" in normalized_uses:
                issues.append(f"{label}: noncommercial license cannot allow commercial use")
            if isinstance(relative, str) and relative:
                target, problem = inside_vault(vault, relative)
                if not problem and target is not None and target.is_file():
                    source_fields = parse_frontmatter(target.read_text(encoding="utf-8"))
                    if target.parent == vault / "02-sources" and not is_external_url(
                        str(source_fields.get("source_url", ""))
                    ):
                        issues.append(
                            f"{label}: confirmed human-reference source must have an http(s) source_url"
                        )
    return issues


def corpus_coverage(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    for entry in entries:
        key = (
            str(entry.get("role", "unknown")),
            str(entry.get("status", "unknown")),
            str(entry.get("language", "unknown")),
            str(entry.get("genre", "unknown")),
            str(entry.get("audience", "unknown")),
        )
        counts[key] += 1
    return [
        {
            "role": key[0],
            "status": key[1],
            "language": key[2],
            "genre": key[3],
            "audience": key[4],
            "documents": count,
        }
        for key, count in sorted(counts.items())
    ]


def document_edit_ratio(source: str, target: str) -> float:
    source_text = clean_markdown(source)
    target_text = clean_markdown(target)
    if not source_text and not target_text:
        return 0.0
    similarity = difflib.SequenceMatcher(
        None, source_text, target_text, autojunk=False
    ).ratio()
    return round(1.0 - similarity, 4)


def rollout_metrics(
    baseline_text: str,
    candidate_text: str,
    final_text: str,
    values: dict[str, int],
) -> dict[str, int | float]:
    baseline_ratio = document_edit_ratio(baseline_text, final_text)
    candidate_ratio = document_edit_ratio(candidate_text, final_text)
    return {
        "baseline_edit_ratio": baseline_ratio,
        "candidate_edit_ratio": candidate_ratio,
        "editing_improvement": round(baseline_ratio - candidate_ratio, 4),
        "baseline_substantive_edits": values["baseline_substantive_edits"],
        "candidate_substantive_edits": values["candidate_substantive_edits"],
        "baseline_factual_errors": values["baseline_factual_errors"],
        "candidate_factual_errors": values["candidate_factual_errors"],
        "baseline_constraint_errors": values["baseline_constraint_errors"],
        "candidate_constraint_errors": values["candidate_constraint_errors"],
    }


def rollout_passes(metrics: dict[str, Any]) -> bool:
    return (
        metrics.get("candidate_factual_errors") == 0
        and metrics.get("candidate_constraint_errors") == 0
        and float(metrics.get("candidate_edit_ratio", 1.0))
        < float(metrics.get("baseline_edit_ratio", 0.0))
        and int(metrics.get("candidate_substantive_edits", 0))
        < int(metrics.get("baseline_substantive_edits", 0))
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollout_identity_payload(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "task_id",
        "language",
        "genre",
        "audience",
        "reviewer",
        "baseline_path",
        "candidate_path",
        "final_path",
        "holdout_id",
        "fact_packet",
        "review_evidence",
        "baseline_sha256",
        "candidate_sha256",
        "final_sha256",
        "fact_packet_sha256",
        "review_evidence_sha256",
        "baseline_substantive_edits",
        "candidate_substantive_edits",
        "baseline_factual_errors",
        "candidate_factual_errors",
        "baseline_constraint_errors",
        "candidate_constraint_errors",
    )
    return {key: record.get(key) for key in keys}


def rollout_record_id(record: dict[str, Any]) -> str:
    serialized = json.dumps(
        rollout_identity_payload(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
    return f"rollout-evaluation-{slugify(str(record.get('task_id', 'writing-task')))[:40]}-{digest}"


def rollout_evaluation_events(
    vault: Path,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    directory = vault / ROLLOUT_EVALUATION_DIR
    if not directory.is_dir():
        return [], []
    holdouts_by_path = {
        str(item.get("path")): item
        for item in entries
        if item.get("role") == "holdout" and item.get("status") == "confirmed"
    }
    events: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        if path.name == "Rollout Evaluations Index.md":
            continue
        label = path.relative_to(vault).as_posix()
        text = path.read_text(encoding="utf-8")
        fields = parse_frontmatter(text)
        local_issues: list[str] = []
        if fields.get("type") != "journal" or fields.get("status") != "verified":
            local_issues.append(f"{label}: rollout evaluation must be a verified journal")
        records: list[dict[str, Any]] = []
        for block in jsonl_blocks(text):
            for line in block.splitlines():
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    local_issues.append(f"{label}: invalid evaluation JSON: {error.msg}")
                    continue
                if isinstance(value, dict) and value.get("kind") == "rollout-evaluation":
                    records.append(value)
        if len(records) != 1:
            local_issues.append(f"{label}: expected exactly one rollout-evaluation record")
            issues.extend(local_issues)
            continue
        record = records[0]
        record_id = str(record.get("id", ""))
        if not record_id:
            local_issues.append(f"{label}: evaluation record is missing id")
        elif record_id in seen:
            local_issues.append(f"{label}: duplicate rollout evaluation id {record_id}")
        seen.add(record_id)
        for key in ("id", "task_id", "language", "genre", "audience", "reviewer"):
            if str(fields.get(key, "")) != str(record.get(key, "")):
                local_issues.append(f"{label}: frontmatter {key} does not match the record")
        if record.get("reviewer_confirmed") is not True:
            local_issues.append(f"{label}: evaluation requires reviewer confirmation")
        if record.get("reviewer") not in {"user", "curator"}:
            local_issues.append(f"{label}: invalid reviewer {record.get('reviewer')!r}")
        for key in ("task_id", "language", "genre", "audience", "holdout_id"):
            if not isinstance(record.get(key), str) or not str(record.get(key)).strip():
                local_issues.append(f"{label}: missing {key}")

        resolved: dict[str, Path] = {}
        for key in (
            "baseline_path",
            "candidate_path",
            "final_path",
            "fact_packet",
            "review_evidence",
        ):
            raw = record.get(key)
            if not isinstance(raw, str) or not raw:
                local_issues.append(f"{label}: missing {key}")
                continue
            target, problem = inside_vault(vault, raw)
            if problem:
                local_issues.append(f"{label}: {problem}")
            elif target is None or not target.is_file():
                local_issues.append(f"{label}: file not found for {key}: {raw}")
            else:
                resolved[key] = target
        final_path = str(record.get("final_path", ""))
        holdout = holdouts_by_path.get(final_path)
        if final_path and holdout is None:
            local_issues.append(f"{label}: final_path is not a confirmed holdout")
        elif holdout is not None:
            if record.get("holdout_id") != holdout.get("id"):
                local_issues.append(f"{label}: holdout_id does not match final_path")
            for key in ("language", "genre", "audience"):
                if normalize(str(record.get(key, ""))) != normalize(str(holdout.get(key, ""))):
                    local_issues.append(f"{label}: {key} does not match the confirmed holdout")
        for key in ("fact_packet", "review_evidence"):
            target = resolved.get(key)
            if target is not None:
                record_type = parse_frontmatter(target.read_text(encoding="utf-8")).get("type")
                if record_type not in {"source", "journal"}:
                    local_issues.append(f"{label}: {key} must be a source or journal record")

        count_keys = (
            "baseline_substantive_edits",
            "candidate_substantive_edits",
            "baseline_factual_errors",
            "candidate_factual_errors",
            "baseline_constraint_errors",
            "candidate_constraint_errors",
        )
        counts: dict[str, int] = {}
        for key in count_keys:
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                local_issues.append(f"{label}: {key} must be a non-negative integer")
            else:
                counts[key] = value

        hash_fields = {
            "baseline_path": "baseline_sha256",
            "candidate_path": "candidate_sha256",
            "final_path": "final_sha256",
            "fact_packet": "fact_packet_sha256",
            "review_evidence": "review_evidence_sha256",
        }
        for path_key, hash_key in hash_fields.items():
            target = resolved.get(path_key)
            if target is not None and record.get(hash_key) != sha256_file(target):
                local_issues.append(f"{label}: {hash_key} does not match the referenced document")

        if record_id and record_id != rollout_record_id(record):
            local_issues.append(f"{label}: evaluation id does not match its evidence")

        if all(
            key in resolved for key in ("baseline_path", "candidate_path", "final_path")
        ) and len(counts) == len(count_keys):
            expected = rollout_metrics(
                resolved["baseline_path"].read_text(encoding="utf-8"),
                resolved["candidate_path"].read_text(encoding="utf-8"),
                resolved["final_path"].read_text(encoding="utf-8"),
                counts,
            )
            for key in ("baseline_edit_ratio", "candidate_edit_ratio", "editing_improvement"):
                actual = record.get(key)
                if not isinstance(actual, (int, float)) or abs(float(actual) - float(expected[key])) > 0.0001:
                    local_issues.append(f"{label}: {key} does not match the referenced documents")
            expected_passed = rollout_passes(expected)
            if record.get("passed") is not expected_passed:
                local_issues.append(f"{label}: passed does not match the recorded evidence")
            expected_qualifying = (
                expected_passed
                and record.get("reviewer") == "user"
                and record.get("reviewer_confirmed") is True
            )
            if record.get("qualifies_for_activation") is not expected_qualifying:
                local_issues.append(
                    f"{label}: qualifies_for_activation does not match the recorded evidence"
                )
        if local_issues:
            issues.extend(local_issues)
            continue
        events.append({"path": label, "fields": fields, "record": record})
    return events, issues


def corpus_readiness(
    vault: Path,
    entries: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    technique_records: list[dict[str, Any]],
) -> dict[str, Any]:
    personal = [
        item
        for item in entries
        if item.get("role") == "personal" and item.get("status") == "confirmed"
    ]
    holdout = [
        item
        for item in entries
        if item.get("role") == "holdout" and item.get("status") == "confirmed"
    ]
    human = [
        item
        for item in entries
        if item.get("role") == "human-reference" and item.get("status") == "confirmed"
    ]
    personal_characters = sum(document_features(entry_text(vault, item))["characters"] for item in personal)
    all_feedback = feedback_events(vault)
    confirmed_feedback = [
        event
        for event in all_feedback
        if event["fields"].get("reviewer") == "user"
        and normalize(event["fields"].get("reviewer_confirmed", "")) == "true"
    ]
    human_genres = sorted({str(item.get("genre", "unknown")) for item in human})
    human_languages = sorted({str(item.get("language", "unknown")) for item in human})
    human_use_coverage = Counter(
        str(use)
        for item in human
        for use in item.get("allowed_uses", [])
        if str(use) in ALLOWED_USES
    )
    personal_ready = len(personal) >= 3 and personal_characters >= 2000
    human_ready = (
        len(human) >= MIN_HUMAN_REFERENCE_DOCUMENTS
        and len(human_genres) >= MIN_HUMAN_REFERENCE_GENRES
    )
    holdout_ready = bool(holdout)
    feedback_observed = bool(confirmed_feedback)
    qualifying_evaluations = [
        event
        for event in evaluations
        if event["record"].get("passed") is True
        and event["record"].get("reviewer") == "user"
        and event["record"].get("reviewer_confirmed") is True
    ]
    activation_ready = all(
        (
            personal_ready,
            human_ready,
            holdout_ready,
            feedback_observed,
            bool(qualifying_evaluations),
        )
    )
    next_gates = []
    if not personal_ready:
        next_gates.append("confirm at least three personal documents with 2,000 usable characters")
    if not human_ready:
        next_gates.append(
            "confirm at least "
            f"{MIN_HUMAN_REFERENCE_DOCUMENTS} human references across "
            f"{MIN_HUMAN_REFERENCE_GENRES} genres"
        )
    if not holdout_ready:
        next_gates.append("reserve at least one confirmed personal holdout document")
    if not feedback_observed:
        next_gates.append("record a real user-reviewed before/after writing event")
    if not qualifying_evaluations:
        next_gates.append(
            "record a user-confirmed holdout rollout evaluation with no factual errors and lower editing burden"
        )
    return {
        "personal": {
            "documents": len(personal),
            "characters": personal_characters,
            "profile_ready": personal_ready,
        },
        "human_reference": {
            "documents": len(human),
            "technique_cards": len(technique_records),
            "technique_coverage": round(
                len(technique_records) / max(len(human), 1), 3
            ),
            "languages": human_languages,
            "genres": human_genres,
            "license_ids": sorted({str(item.get("license_id", "unknown")) for item in human}),
            "allowed_use_coverage": dict(sorted(human_use_coverage.items())),
            "library_ready": human_ready,
        },
        "holdout": {"documents": len(holdout), "available": holdout_ready},
        "feedback": {
            "events": len(all_feedback),
            "user_confirmed": len(confirmed_feedback),
            "observed": feedback_observed,
        },
        "rollout_evaluation": {
            "records": len(evaluations),
            "qualifying": len(qualifying_evaluations),
            "observed": bool(evaluations),
        },
        "activation": {
            "ready": activation_ready,
            "mode": "active" if activation_ready else "shadow",
        },
        "confirmed_preferences": len(active_preference_records(preferences)),
        "next_gates": next_gates,
    }


def metadata_matches(entry: dict[str, Any], key: str, value: str | None) -> bool:
    if not value:
        return True
    actual = normalize(str(entry.get(key, "")))
    return not actual or actual == normalize(value)


def entry_text(vault: Path, entry: dict[str, Any]) -> str:
    target, problem = inside_vault(vault, str(entry["path"]))
    if problem or target is None:
        raise ValueError(problem or "invalid path")
    return target.read_text(encoding="utf-8")


def human_reference_allows(entry: dict[str, Any], intended_use: str) -> bool:
    allowed = {str(item) for item in entry.get("allowed_uses", [])}
    if intended_use == "unknown":
        return ALLOWED_USES.issubset(allowed)
    return intended_use in allowed


def entry_technique_tokens(entry: dict[str, Any]) -> set[str]:
    techniques = entry.get("techniques", [])
    if not isinstance(techniques, list):
        return set()
    return tokenize(" ".join(str(item) for item in techniques))


def profile_personal_entries(
    entries: list[dict[str, Any]], language: str | None, genre: str | None, audience: str | None
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    scope = {"language": language, "genre": genre, "audience": audience}
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    requested_language = normalize(language or "")
    for item in entries:
        if item.get("role") != "personal" or item.get("status") != "confirmed":
            continue
        actual_language = normalize(str(item.get("language", "")))
        if (
            requested_language
            and actual_language not in {"", "unknown", "mixed", requested_language}
        ):
            continue
        selected.append((item, scope_match_details(item, scope)))
    quality_order = {"exact": 0, "partial": 1, "fallback": 2, "unspecified": 3}
    selected.sort(
        key=lambda pair: (
            quality_order[pair[1]["quality"]],
            len(pair[1]["fallback_fields"]),
            -float(pair[0].get("weight", 1.0)),
            str(pair[0].get("id", "")),
        )
    )
    return selected


def profile_for(
    vault: Path,
    entries: list[dict[str, Any]],
    language: str | None = None,
    genre: str | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    selected = profile_personal_entries(entries, language, genre, audience)
    documents: list[dict[str, Any]] = []
    for entry, match in selected:
        features = document_features(entry_text(vault, entry))
        documents.append(
            {
                "id": entry["id"],
                "path": entry["path"],
                "weight": float(entry.get("weight", 1.0)),
                "match": match,
                "features": features,
            }
        )
    characters = sum(int(item["features"]["characters"]) for item in documents)
    exact_documents = [item for item in documents if item["match"]["quality"] == "exact"]
    exact_characters = sum(int(item["features"]["characters"]) for item in exact_documents)
    metric_names = [
        "avg_sentence_chars",
        "median_sentence_chars",
        "p90_sentence_chars",
        "avg_paragraph_chars",
        "headings_per_1000",
        "list_items_per_1000",
        "questions_per_1000",
        "first_person_per_1000",
        "we_per_1000",
        "reader_address_per_1000",
        "english_tokens_per_1000",
        "colons_per_1000",
        "parentheses_per_1000",
        "bold_per_1000",
        "connectors_per_1000",
    ]
    metrics: dict[str, Any] = {}
    for name in metric_names:
        values = [float(item["features"][name]) for item in documents]
        weights = [float(item["weight"]) for item in documents]
        if not values:
            continue
        median = weighted_median(values, weights)
        mad = weighted_median([abs(value - median) for value in values], weights)
        metrics[name] = {
            "median": round(median, 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "mad": round(mad, 3),
        }
    provisional = len(documents) < 3 or characters < 2000
    scoped = any((language, genre, audience))
    scope_provisional = provisional or (
        scoped and (len(exact_documents) < 2 or exact_characters < 1000)
    )
    return {
        "scope": {"language": language, "genre": genre, "audience": audience},
        "documents": len(documents),
        "characters": characters,
        "exact_documents": len(exact_documents),
        "exact_characters": exact_characters,
        "provisional": provisional,
        "scope_provisional": scope_provisional,
        "basis": (
            "exact-scope"
            if documents and len(exact_documents) == len(documents)
            else "language-compatible-fallback"
            if documents
            else "no-confirmed-personal-evidence"
        ),
        "metrics": metrics,
        "samples": [
            {
                "id": item["id"],
                "path": item["path"],
                "weight": item["weight"],
                "match_quality": item["match"]["quality"],
                "fallback_fields": item["match"]["fallback_fields"],
            }
            for item in documents
        ],
    }


def candidate_profile_for(
    vault: Path,
    entries: list[dict[str, Any]],
    language: str | None = None,
    genre: str | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    """Return a review-only report for unconfirmed personal samples.

    Candidate material is intentionally summarized as metadata and measurable features.  This
    command exists to help a user decide what to confirm; it must never become an alternate
    drafting retrieval path or silently turn a candidate into a profile sample.
    """
    scope = {"language": language, "genre": genre, "audience": audience}
    requested_language = normalize(language or "")
    documents: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("role") != "personal" or entry.get("status") != "candidate":
            continue
        actual_language = normalize(str(entry.get("language", "")))
        if (
            requested_language
            and actual_language not in {"", "unknown", "mixed", requested_language}
        ):
            continue
        match = scope_match_details(entry, scope)
        features = document_features(entry_text(vault, entry))
        documents.append(
            {
                "id": entry["id"],
                "path": entry["path"],
                "status": entry.get("status"),
                "author": entry.get("author", "unknown"),
                "authorship": entry.get("authorship", "unknown"),
                "approval": entry.get("approval", "unreviewed"),
                "origin_claim": entry.get("origin_claim", "unknown"),
                "origin_confidence": entry.get("origin_confidence", "unknown"),
                "language": entry.get("language"),
                "genre": entry.get("genre"),
                "audience": entry.get("audience"),
                "weight": float(entry.get("weight", 1.0)),
                "match": match,
                "characters": int(features["characters"]),
                "features": features,
                "notes": entry.get("notes"),
            }
        )
    quality_order = {"exact": 0, "partial": 1, "fallback": 2, "unspecified": 3}
    documents.sort(
        key=lambda item: (
            quality_order[item["match"]["quality"]],
            len(item["match"]["fallback_fields"]),
            -item["characters"],
            item["id"],
        )
    )
    exact_documents = [item for item in documents if item["match"]["quality"] == "exact"]
    return {
        "scope": {"language": language, "genre": genre, "audience": audience},
        "documents": len(documents),
        "characters": sum(item["characters"] for item in documents),
        "exact_documents": len(exact_documents),
        "generation_eligible": False,
        "review_gates": {
            "authorship_confirmation": True,
            "representativeness_confirmation": True,
            "confirmation_command": "promote-sample",
        },
        "documents_detail": documents,
        "recommendations": candidate_recommendations(documents),
        "warning": (
            "候选个人样本只用于人工审阅；它们不会进入 context、个人画像或 holdout 评测，"
            "直到用户明确确认作者身份和当前代表性。"
        ),
    }


def candidate_recommendations(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Suggest metadata-only review order without promoting any candidate.

    The recommendation is deliberately conservative: only entries already classified as
    user-authored with at least medium origin confidence can be suggested for a personal
    profile.  Mixed or low-confidence documents remain visible in ``documents_detail`` but
    cannot become training or holdout recommendations.  The result contains no document text
    and never changes the registry.
    """
    quality_order = {"exact": 0, "partial": 1, "fallback": 2, "unspecified": 3}
    confidence_order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    eligible = [
        item
        for item in documents
        if item.get("authorship") == "user"
        and item.get("origin_confidence") in {"high", "medium"}
    ]
    eligible.sort(
        key=lambda item: (
            quality_order.get(str(item.get("match", {}).get("quality")), 3),
            confidence_order.get(str(item.get("origin_confidence")), 3),
            -(1 if int(item.get("characters", 0)) >= 2000 else 0),
            -int(item.get("characters", 0)),
            str(item.get("id", "")),
        )
    )

    def summary(item: dict[str, Any], role: str) -> dict[str, Any]:
        quality = str(item.get("match", {}).get("quality", "unspecified"))
        reasons = [
            "用户确认作者身份和当前代表性后才可晋升",
            f"范围匹配：{quality}",
        ]
        if int(item.get("characters", 0)) < 2000:
            reasons.append("篇幅低于 2,000 字，建议作为补充证据")
        return {
            "id": item["id"],
            "path": item["path"],
            "role": role,
            "language": item.get("language"),
            "genre": item.get("genre"),
            "audience": item.get("audience"),
            "characters": item.get("characters", 0),
            "match_quality": quality,
            "reasons": reasons,
            "generation_eligible": False,
        }

    # Prefer distinct genres when the user has supplied enough compatible candidates.  This
    # improves profile coverage while keeping the decision visibly human-reviewed.
    training: list[dict[str, Any]] = []
    seen_genres: set[str] = set()
    for item in eligible:
        genre = str(item.get("genre") or "unknown")
        if genre in seen_genres:
            continue
        training.append(summary(item, "personal-review"))
        seen_genres.add(genre)
        if len(training) == 3:
            break
    if len(training) < 3:
        selected = {item["id"] for item in training}
        for item in eligible:
            if item["id"] in selected:
                continue
            training.append(summary(item, "personal-review"))
            if len(training) == 3:
                break

    selected = {item["id"] for item in training}
    holdout = next(
        (summary(item, "holdout-review") for item in eligible if item["id"] not in selected),
        None,
    )
    return {
        "training": training,
        "holdout": holdout,
        "training_ready": len(training) >= 3,
        "holdout_available": holdout is not None,
        "requires_user_confirmation": True,
        "warning": (
            "这些只是基于元数据的审阅顺序建议；不会自动晋升、进入 context 或改变 holdout 隔离。"
        ),
    }


def entry_score(
    vault: Path,
    entry: dict[str, Any],
    query_tokens: set[str],
    language: str | None,
    genre: str | None,
    audience: str | None,
    channel: str | None,
    purpose: str | None,
) -> float:
    score = float(entry.get("weight", 1.0))
    scope = {
        "language": language,
        "genre": genre,
        "audience": audience,
        "channel": channel,
        "purpose": purpose,
    }
    details = scope_match_details(entry, scope)
    for key in details["exact_fields"]:
        score += SCOPE_MATCH_POINTS[key]
    for key in details["compatible_fields"]:
        score += SCOPE_MATCH_POINTS[key] / 2
    for key in details["fallback_fields"]:
        score -= SCOPE_MISMATCH_PENALTIES[key]
    if query_tokens:
        text = entry_text(vault, entry)
        document_tokens = tokenize(clean_markdown(text))
        query_coverage = len(query_tokens & document_tokens) / len(query_tokens)
        paragraph_precision = max(
            (
                len(query_tokens & tokens) / max(len(tokens), 1)
                for tokens in (tokenize(item) for item in paragraphs(text))
            ),
            default=0.0,
        )
        score += 4.0 * query_coverage + 1.5 * paragraph_precision
        technique_tokens = entry_technique_tokens(entry)
        if technique_tokens:
            matches = query_tokens & technique_tokens
            technique_coverage = len(matches) / len(query_tokens)
            technique_precision = len(matches) / len(technique_tokens)
            score += 5.0 * technique_coverage + 3.0 * technique_precision
    return round(score, 4)


def human_diversity_penalty(
    entry: dict[str, Any], selected: list[dict[str, Any]]
) -> float:
    if not selected:
        return 0.0
    penalty = 0.0
    collection_id = normalize(str(entry.get("collection_id", "")))
    if collection_id and any(
        normalize(str(item.get("collection_id", ""))) == collection_id
        for item in selected
    ):
        penalty += HUMAN_COLLECTION_DIVERSITY_PENALTY
    author = normalize(str(entry.get("author", "")))
    if author and any(normalize(str(item.get("author", ""))) == author for item in selected):
        penalty += HUMAN_AUTHOR_DIVERSITY_PENALTY
    technique_tokens = entry_technique_tokens(entry)
    if technique_tokens:
        similarity = max(
            (
                len(technique_tokens & other_tokens)
                / max(len(technique_tokens | other_tokens), 1)
                for other_tokens in (entry_technique_tokens(item) for item in selected)
                if other_tokens
            ),
            default=0.0,
        )
        penalty += HUMAN_TECHNIQUE_DIVERSITY_PENALTY * similarity
    return round(penalty, 4)


def human_origin_confidence_penalty(entry: dict[str, Any]) -> float:
    """Prefer stronger human-origin evidence when scope and relevance are comparable."""
    return HUMAN_ORIGIN_CONFIDENCE_PENALTY.get(
        normalize(str(entry.get("origin_confidence", "unknown"))),
        2.0,
    )


def scope_match_details(entry: dict[str, Any], scope: dict[str, str | None]) -> dict[str, Any]:
    exact_fields: list[str] = []
    compatible_fields: list[str] = []
    fallback_fields: list[str] = []
    unknown_fields: list[str] = []
    for key in SCOPE_FIELDS:
        requested = normalize(str(scope.get(key) or ""))
        if not requested:
            continue
        actual = normalize(str(entry.get(key, "")))
        if not actual or actual == "unknown":
            unknown_fields.append(key)
        elif actual == requested:
            exact_fields.append(key)
        elif key == "language" and actual == "mixed" and requested in {"zh", "en"}:
            compatible_fields.append(key)
        else:
            fallback_fields.append(key)
    if fallback_fields:
        quality = "fallback"
    elif unknown_fields or compatible_fields:
        quality = "partial"
    elif exact_fields:
        quality = "exact"
    else:
        quality = "unspecified"
    return {
        "quality": quality,
        "exact_fields": exact_fields,
        "compatible_fields": compatible_fields,
        "fallback_fields": fallback_fields,
        "unknown_fields": unknown_fields,
    }


def paragraph_language_affinity(value: str, requested: str | None) -> float:
    language = normalize(requested or "")
    if not language or language == "mixed":
        return 0.0
    han = len(re.findall(r"[\u4e00-\u9fff]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    if language.startswith("zh"):
        if han < 8 or han * 2 < latin:
            return 0.0
        simplified_markers = sum(value.count(char) for char in "这为们个与后里发边应将进书标台设置")
        traditional_markers = sum(value.count(char) for char in "這為們個與後裡發邊應將進書標臺設置")
        wants_traditional = language in {"zh-hant", "zh-tw", "zh-hk"}
        if wants_traditional:
            return 2.0 if traditional_markers >= simplified_markers else 0.25
        return 2.0 if simplified_markers >= traditional_markers else 0.25
    if language.startswith("en"):
        return 1.0 if latin >= 20 and latin >= han * 2 else 0.0
    return 0.0


def reference_excerpt_risk(value: str) -> tuple[float, list[str]]:
    """Score accidental style baggage in a third-party reference excerpt.

    The score is deliberately local to retrieval. It does not decide whether a phrase is
    acceptable in the user's own writing and it never becomes a draft lint rule.
    """
    score = 0.0
    flags: list[str] = []
    for pattern, weight, label in REFERENCE_EXCERPT_RISK_PATTERNS:
        if pattern.search(value):
            score += weight
            flags.append(label)
    if re.search(r"[!！]{2,}", value):
        score += 1.0
        flags.append("excessive-exclamation")
    return round(score, 3), flags


def excerpt_for(
    text: str,
    query_tokens: set[str],
    limit: int,
    language: str | None = None,
    risk_aware: bool = False,
) -> str:
    items = paragraphs(text)
    if not items:
        return clean_markdown(text)[:limit]

    generic_tokens = tokenize(
        "解释 说明 介绍 为什么 如何 怎么 例子 示例 风险 作用 方法 内容 "
        "explain describe introduction why how example risk method content"
    )
    effective_query = query_tokens - generic_tokens
    if not effective_query:
        effective_query = query_tokens
    item_tokens = [tokenize(item) for item in items]
    document_frequency: Counter[str] = Counter()
    for tokens in item_tokens:
        document_frequency.update(tokens)

    def relevance(tokens: set[str], selected_query: set[str]) -> float:
        matches = tokens & selected_query
        return sum(
            1.0 + math.log((len(items) + 1) / (document_frequency[token] + 1))
            for token in matches
        )

    def prose_quality(value: str) -> float:
        stripped = value.strip()
        if re.match(r"^(?:date|from|to|subject|author|copyright)\s*:", stripped, re.IGNORECASE):
            return -10.0
        characters = len(re.sub(r"\s+", "", stripped))
        sentence_marks = len(re.findall(r"[。！？.!?]", stripped))
        quality = min(characters, 300) / 100 + min(sentence_marks, 3)
        if stripped.endswith(("?", "？")) and sentence_marks <= 1:
            quality -= 2.0
        if risk_aware:
            risk, _ = reference_excerpt_risk(stripped)
            quality -= risk
        return quality

    def structure_factor(value: str) -> float:
        stripped = value.strip()
        characters = len(re.sub(r"\s+", "", stripped))
        sentence_marks = len(re.findall(r"[。！？.!?]", stripped))
        if sentence_marks == 0 and characters < 120:
            return 0.35
        if stripped.endswith(("?", "？")) and sentence_marks <= 1:
            return 0.65
        return 1.0

    relevance_scores = [
        relevance(tokens, effective_query) * structure_factor(item)
        for tokens, item in zip(item_tokens, items, strict=True)
    ]
    support_scores = [
        relevance(tokens, query_tokens) * structure_factor(item)
        for tokens, item in zip(item_tokens, items, strict=True)
    ]
    quality_scores = [prose_quality(item) for item in items]
    risk_scores = [
        reference_excerpt_risk(item)[0] if risk_aware else 0.0 for item in items
    ]
    language_scores = [paragraph_language_affinity(item, language) for item in items]
    ranked = sorted(
        range(len(items)),
        key=lambda index: (
            -relevance_scores[index],
            -(relevance_scores[index] / max(math.sqrt(len(item_tokens[index])), 1.0)),
            -language_scores[index],
            -quality_scores[index],
            index,
        ),
    )
    anchor = ranked[0]
    neighbors = [
        index
        for index in range(max(0, anchor - 4), min(len(items), anchor + 5))
        if index != anchor
    ]
    chosen = [anchor]
    if neighbors:
        def companion_score(index: int) -> tuple[float, int, int]:
            similarity = difflib.SequenceMatcher(
                None, normalize(items[anchor]), normalize(items[index])
            ).ratio()
            overlap_penalty = 4.0 if similarity >= 0.65 else similarity * 0.5
            return (
                support_scores[index]
                + quality_scores[index] * 0.2
                + language_scores[index]
                - risk_scores[index] * 0.2
                - abs(index - anchor) * 0.25
                - overlap_penalty,
                -abs(index - anchor),
                -index,
            )

        companion = max(
            neighbors,
            key=companion_score,
        )
        chosen.append(companion)
    chosen.sort()
    excerpt = "\n\n".join(items[index] for index in chosen)
    return excerpt if len(excerpt) <= limit else excerpt[: limit - 1].rstrip() + "…"


def select_context(
    vault: Path,
    entries: list[dict[str, Any]],
    role: str,
    limit: int,
    query_tokens: set[str],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    selected: list[tuple[float, dict[str, Any]]] = []
    scope = {key: getattr(args, key, None) for key in SCOPE_FIELDS}
    for entry in entries:
        if entry.get("role") != role:
            continue
        status = entry.get("status")
        allowed = status == "confirmed" or (role == "negative" and status == "rejected")
        if not allowed:
            continue
        if role == "human-reference" and not human_reference_allows(
            entry, args.intended_use
        ):
            continue
        score = entry_score(
            vault,
            entry,
            query_tokens,
            args.language,
            args.genre,
            args.audience,
            args.channel,
            args.purpose,
        )
        if role == "human-reference":
            score -= human_origin_confidence_penalty(entry)
        selected.append((score, entry))
    selected.sort(key=lambda pair: (-pair[0], str(pair[1]["id"])))
    ranked: list[tuple[float, float, dict[str, Any]]] = []
    if role == "human-reference":
        remaining = list(selected)
        chosen_entries: list[dict[str, Any]] = []
        while remaining and len(ranked) < limit:
            candidates = []
            for base_score, entry in remaining:
                if chosen_entries:
                    quality_order = {
                        "exact": 0,
                        "partial": 1,
                        "fallback": 2,
                        "unspecified": 3,
                    }
                    best_quality = scope_match_details(chosen_entries[0], scope)["quality"]
                    candidate_quality = scope_match_details(entry, scope)["quality"]
                    if quality_order[candidate_quality] > quality_order[best_quality]:
                        continue
                penalty = human_diversity_penalty(entry, chosen_entries)
                candidates.append((base_score - penalty, base_score, penalty, entry))
            if not candidates:
                break
            candidates.sort(
                key=lambda item: (-item[0], -item[1], str(item[3].get("id", "")))
            )
            _, base_score, penalty, entry = candidates[0]
            ranked.append((base_score, penalty, entry))
            chosen_entries.append(entry)
            remaining = [pair for pair in remaining if pair[1] is not entry]
    else:
        ranked = [(score, 0.0, entry) for score, entry in selected[:limit]]
    output = []
    excerpt_limit = 900 if role == "personal" else 600
    for base_score, diversity_penalty, entry in ranked:
        excerpt = excerpt_for(
            entry_text(vault, entry),
            query_tokens,
            excerpt_limit,
            args.language,
            risk_aware=role == "human-reference",
        )
        match = scope_match_details(entry, scope)
        item = {
            "id": entry["id"],
            "path": entry["path"],
            "score": round(base_score - diversity_penalty, 4),
            "base_score": base_score,
            "diversity_penalty": diversity_penalty,
            "status": entry["status"],
            "genre": entry.get("genre"),
            "audience": entry.get("audience"),
            "match_quality": match["quality"],
            "fallback_fields": match["fallback_fields"],
            "unknown_fields": match["unknown_fields"],
            "excerpt": excerpt,
        }
        if role == "human-reference":
            excerpt_risk, excerpt_risk_flags = reference_excerpt_risk(excerpt)
            item.update(
                {
                    "author": entry.get("author"),
                    "rights": entry.get("rights"),
                    "license_id": entry.get("license_id"),
                    "allowed_uses": entry.get("allowed_uses", []),
                    "usage_notes": entry.get("notes"),
                    "origin_claim": entry.get("origin_claim"),
                    "origin_confidence": entry.get("origin_confidence"),
                    "collection_id": entry.get("collection_id"),
                    "techniques": entry.get("techniques", []),
                    "technique_basis": entry.get("technique_basis"),
                    "technique_card_id": entry.get("technique_card_id"),
                    "technique_status": (
                        "curator-inference" if entry.get("techniques") else None
                    ),
                    "excerpt_risk": excerpt_risk,
                    "excerpt_risk_flags": excerpt_risk_flags,
                    "copy_policy": "analysis-only; do not reuse distinctive wording or source facts",
                }
            )
        output.append(item)
    return output


def feedback_events(vault: Path) -> list[dict[str, Any]]:
    directory = vault / FEEDBACK_DIR
    if not directory.is_dir():
        return []
    events: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md"), reverse=True):
        if path.name == "Feedback Index.md":
            continue
        text = path.read_text(encoding="utf-8")
        fields = parse_frontmatter(text)
        changes: list[dict[str, Any]] = []
        preferences: list[str] = []
        recorded_style_delta: dict[str, float] = {}
        for block in jsonl_blocks(text):
            for line in block.splitlines():
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    if value.get("kind") == "style-delta" and isinstance(value.get("metrics"), dict):
                        recorded_style_delta = {
                            str(key): float(metric)
                            for key, metric in value["metrics"].items()
                            if isinstance(metric, (int, float))
                        }
                    else:
                        changes.append(value)
        match = re.search(
            r"^## Explicit preferences\s*$\n(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if match:
            preferences = [
                line.strip()[2:].strip()
                for line in match.group(1).splitlines()
                if line.strip().startswith("- ")
            ]
        events.append(
            {
                "path": path.relative_to(vault).as_posix(),
                "fields": fields,
                "changes": changes,
                "preferences": preferences,
                "style_delta": recorded_style_delta,
            }
        )
    return events


def user_confirmed_feedback_events(vault: Path) -> list[dict[str, Any]]:
    return [
        event
        for event in feedback_events(vault)
        if event["fields"].get("reviewer") == "user"
        and normalize(event["fields"].get("reviewer_confirmed", "")) == "true"
    ]


def context_feedback(vault: Path, args: argparse.Namespace, limit: int = 3) -> list[dict[str, Any]]:
    output = []
    for event in user_confirmed_feedback_events(vault):
        fields = event["fields"]
        if any(
            value and normalize(fields.get(key, "")) != normalize(value)
            for key, value in (("language", args.language), ("genre", args.genre), ("audience", args.audience))
        ):
            continue
        output.append(
            {
                "path": event["path"],
                "verdict": fields.get("verdict"),
                "task_id": fields.get("task_id"),
                "preferences": event["preferences"],
                "style_delta": event["style_delta"],
                "changes": event["changes"][:4],
            }
        )
        if len(output) >= limit:
            break
    return output


def command_validate(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    path = registry_path(vault, args.registry)
    entries, parse_issues = read_registry(path)
    issues = validate_entries(vault, entries, parse_issues)
    technique_records, technique_issues = read_technique_records(vault, entries)
    issues.extend(technique_issues)
    preferences, preference_issues = read_preference_records(vault)
    issues.extend(preference_issues)
    evaluations, evaluation_issues = rollout_evaluation_events(vault, entries)
    issues.extend(evaluation_issues)
    counts = Counter(str(item.get("role", "unknown")) for item in entries)
    report = {
        "healthy": not issues,
        "vault": str(vault),
        "registry": str(path),
        "entries": len(entries),
        "roles": dict(sorted(counts.items())),
        "origin_confidence": dict(
            sorted(Counter(str(item.get("origin_confidence", "unknown")) for item in entries).items())
        ),
        "coverage": corpus_coverage(entries),
        "human_technique_cards": len(technique_records),
        "confirmed_preferences": len(active_preference_records(preferences)),
        "rollout_evaluations": len(evaluations),
        "readiness": (
            corpus_readiness(
                vault, entries, preferences, evaluations, technique_records
            )
            if not issues
            else None
        ),
        "issues": issues,
    }
    print(json_dump(report))
    return 0 if not issues else 1


def load_validated(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    vault = Path(args.vault).expanduser().resolve()
    entries, parse_issues = read_registry(registry_path(vault, args.registry))
    issues = validate_entries(vault, entries, parse_issues)
    if issues:
        raise ValueError("invalid corpus registry:\n- " + "\n- ".join(issues))
    return vault, entries


def command_profile(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    print(json_dump(profile_for(vault, entries, args.language, args.genre, args.audience)))
    return 0


def command_review_candidates(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    print(
        json_dump(
            candidate_profile_for(vault, entries, args.language, args.genre, args.audience)
        )
    )
    return 0


def activation_plan_payload(
    vault: Path,
    entries: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Build a read-only activation checklist without changing registry state."""
    technique_records, technique_issues = read_technique_records(vault, entries)
    if technique_issues:
        raise ValueError(
            "invalid human technique index:\n- " + "\n- ".join(technique_issues)
        )
    preferences, preference_issues = read_preference_records(vault)
    if preference_issues:
        raise ValueError(
            "invalid voice profile preferences:\n- " + "\n- ".join(preference_issues)
        )
    evaluations, evaluation_issues = rollout_evaluation_events(vault, entries)
    if evaluation_issues:
        raise ValueError(
            "invalid rollout evaluation history:\n- " + "\n- ".join(evaluation_issues)
        )

    readiness = corpus_readiness(
        vault, entries, preferences, evaluations, technique_records
    )
    candidate_report = candidate_profile_for(
        vault, entries, args.language, args.genre, args.audience
    )
    recommendations = candidate_report["recommendations"]
    actions: list[dict[str, Any]] = []

    def add_action(
        action_id: str,
        ready: bool,
        requirement: str,
        evidence: str,
        **extra: Any,
    ) -> None:
        action: dict[str, Any] = {
            "id": action_id,
            "status": "complete" if ready else "pending",
            "owner": "system" if ready else "user",
            "requirement": requirement,
            "evidence": evidence,
        }
        action.update(extra)
        actions.append(action)

    add_action(
        "human-library",
        bool(readiness["human_reference"]["library_ready"]),
        "达到最少的人类参考来源和体裁覆盖",
        f"{readiness['human_reference']['documents']} 个来源，"
        f"{len(readiness['human_reference']['genres'])} 种体裁",
    )
    add_action(
        "personal-profile",
        bool(readiness["personal"]["profile_ready"]),
        "确认至少 3 篇个人样本，合计至少 2,000 个可用字符",
        f"{readiness['personal']['documents']} 篇，"
        f"{readiness['personal']['characters']} 个字符",
        recommended_training=recommendations["training"],
    )
    add_action(
        "personal-holdout",
        bool(readiness["holdout"]["available"]),
        "确认至少 1 篇独立个人 holdout，并排除出生成检索",
        f"{readiness['holdout']['documents']} 篇已确认 holdout",
        recommended_holdout=recommendations["holdout"],
    )
    add_action(
        "confirmed-feedback",
        bool(readiness["feedback"]["observed"]),
        "保存至少 1 次用户确认的 before/after 写作反馈",
        f"{readiness['feedback']['user_confirmed']} 次用户确认反馈",
    )
    add_action(
        "rollout-evaluation",
        bool(readiness["rollout_evaluation"]["qualifying"]),
        "通过 1 次用户确认的 rollout 对照评测",
        f"{readiness['rollout_evaluation']['qualifying']} 次评测满足激活条件",
    )

    return {
        "read_only": True,
        "scope": {
            "language": args.language,
            "genre": args.genre,
            "audience": args.audience,
        },
        "activation": readiness["activation"],
        "readiness": readiness,
        "candidate_review": {
            "documents": candidate_report["documents"],
            "characters": candidate_report["characters"],
            "generation_eligible": False,
            "recommendations": recommendations,
        },
        "next_actions": actions,
        "boundaries": [
            "此报告只汇总门禁和候选元数据，不会写入注册表或确认日志。",
            "候选个人样本、未完成草稿和 holdout 不会进入生成上下文。",
            "用户必须明确确认作者身份和当前代表性，模型不能代替确认。",
        ],
    }


def command_activation_plan(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    print(json_dump(activation_plan_payload(vault, entries, args)))
    return 0


def context_payload(
    vault: Path, entries: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    technique_records, technique_issues = read_technique_records(vault, entries)
    if technique_issues:
        raise ValueError(
            "invalid human technique index:\n- " + "\n- ".join(technique_issues)
        )
    entries = enrich_human_techniques(entries, technique_records)
    preferences, preference_issues = read_preference_records(vault)
    if preference_issues:
        raise ValueError("invalid voice profile preferences:\n- " + "\n- ".join(preference_issues))
    query_tokens = tokenize(args.query or "")
    personal = select_context(
        vault, entries, "personal", args.personal_limit, query_tokens, args
    )
    human_reference = select_context(
        vault, entries, "human-reference", args.human_limit, query_tokens, args
    )
    negative = select_context(
        vault, entries, "negative", args.negative_limit, query_tokens, args
    )
    rights_excluded = [
        str(entry.get("id"))
        for entry in entries
        if entry.get("role") == "human-reference"
        and entry.get("status") == "confirmed"
        and not human_reference_allows(entry, args.intended_use)
    ]
    result = {
        "scope": {
            "language": args.language,
            "genre": args.genre,
            "audience": args.audience,
            "channel": args.channel,
            "purpose": args.purpose,
            "intended_use": args.intended_use,
            "query": args.query,
        },
        "profile": profile_for(vault, entries, args.language, args.genre, args.audience),
        "confirmed_preferences": select_preferences(
            preferences, args, args.preference_limit
        ),
        "personal": personal,
        "human_reference": human_reference,
        "negative": negative,
        "feedback": context_feedback(vault, args),
        "retrieval": {
            "personal": {
                "returned": len(personal),
                "fallback": sum(item["match_quality"] == "fallback" for item in personal),
            },
            "human_reference": {
                "returned": len(human_reference),
                "fallback": sum(
                    item["match_quality"] == "fallback" for item in human_reference
                ),
                "distinct_collections": len(
                    {
                        item.get("collection_id") or item["id"]
                        for item in human_reference
                    }
                ),
                "technique_annotated": sum(
                    bool(item.get("techniques")) for item in human_reference
                ),
                "diversity_penalty": round(
                    sum(float(item.get("diversity_penalty", 0.0)) for item in human_reference),
                    4,
                ),
                "rights_excluded": len(rights_excluded),
                "rights_excluded_ids": rights_excluded,
            },
            "negative": {
                "returned": len(negative),
                "fallback": sum(item["match_quality"] == "fallback" for item in negative),
            },
        },
        "boundaries": [
            "Use task evidence, not style samples, for factual claims.",
            "Use human references for technique, not personal identity or distinctive wording.",
            "Treat technique tags as curator retrieval cues, not rules or source claims.",
            "Human references incompatible with the declared intended use were excluded before retrieval.",
            "Use confirmed preferences as style guidance, never as task facts.",
            "Treat fallback evidence as weaker than an exact scope match.",
            "When scope and topic relevance are comparable, prefer high-confidence human origin over medium-confidence attribution.",
            "Treat a provisional profile as weak evidence.",
        ],
    }
    return result


def command_context(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    print(json_dump(context_payload(vault, entries, args)))
    return 0


FACT_PACKET_TYPES = {"source", "journal", "concept", "project", "area", "reference"}


def fact_packet_record(
    vault: Path,
    raw_path: str,
    query_tokens: set[str],
    language: str | None,
    limit: int,
) -> dict[str, Any]:
    if limit < 200:
        raise ValueError("--fact-limit must be at least 200 characters")
    target = resolve_document(vault, raw_path)
    text = target.read_text(encoding="utf-8")
    fields = parse_frontmatter(text)
    record_type = fields.get("type", "")
    if record_type not in FACT_PACKET_TYPES:
        raise ValueError(
            "fact packet must have a source-like type ("
            + ", ".join(sorted(FACT_PACKET_TYPES))
            + "): "
            + target.relative_to(vault).as_posix()
        )
    sensitivity = normalize(fields.get("sensitivity", "unknown"))
    if sensitivity == "secret":
        raise ValueError(
            "secret fact packets cannot be included in a generated context: "
            + target.relative_to(vault).as_posix()
        )
    visible = clean_markdown(text)
    characters = len(re.sub(r"\s+", "", visible))
    truncated = len(visible) > limit
    excerpt = excerpt_for(text, query_tokens, limit, language) if truncated else visible
    return {
        "path": target.relative_to(vault).as_posix(),
        "type": record_type,
        "title": fields.get("title") or note_title(target, text),
        "author": fields.get("author"),
        "published": fields.get("published") or fields.get("date"),
        "source_url": fields.get("source_url"),
        "sensitivity": fields.get("sensitivity", "unknown"),
        "characters": characters,
        "truncated": truncated,
        "excerpt": excerpt,
    }


def command_prepare(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    query_tokens = tokenize(args.query or "")
    seen: set[str] = set()
    fact_evidence: list[dict[str, Any]] = []
    for raw_path in args.fact_packet:
        target = resolve_document(vault, raw_path)
        relative = target.relative_to(vault).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        fact_evidence.append(
            fact_packet_record(
                vault,
                relative,
                query_tokens,
                args.language,
                args.fact_limit,
            )
        )
    style_context = context_payload(vault, entries, args)
    warnings: list[str] = []
    if style_context["profile"]["provisional"]:
        warnings.append(
            "没有足够的 confirmed personal 样本；不能声称输出已经模拟用户个人文风。"
        )
    if style_context["profile"]["scope_provisional"]:
        warnings.append("当前任务范围缺少足够的 exact personal evidence。")
    if any(item["truncated"] for item in fact_evidence):
        warnings.append(
            "至少一个事实来源只返回了相关摘录；生成前仍需打开对应 source/journal 原文核对。"
        )
    result = {
        "task": style_context["scope"],
        "fact_evidence": fact_evidence,
        "style_context": style_context,
        "generation_contract": [
            "事实、数字、引文和结论只能来自 fact_evidence 或用户当前明确提供的材料。",
            "confirmed personal 只决定声音、节奏和结构，不提供当前任务事实。",
            "human_reference 只提供适合当前体裁的写作方法，不复制原句、作者经历或来源观点。",
            "candidate personal、holdout 和模型未修改输出不能进入生成上下文。",
            "如果证据不足，保留不确定性并提出问题，不用风格样本补齐事实。",
        ],
        "warnings": warnings,
    }
    print(json_dump(result))
    return 0


def command_audit_corpus(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    technique_records, technique_issues = read_technique_records(vault, entries)
    if technique_issues:
        raise ValueError(
            "invalid human technique index:\n- " + "\n- ".join(technique_issues)
        )
    entries = enrich_human_techniques(entries, technique_records)
    human = [
        entry
        for entry in entries
        if entry.get("role") == "human-reference" and entry.get("status") == "confirmed"
    ]
    candidates = [
        entry
        for entry in entries
        if entry.get("role") == "human-reference" and entry.get("status") == "candidate"
    ]
    scope = {
        key: getattr(args, key, None)
        for key in SCOPE_FIELDS
    }
    requested_fields = [key for key, value in scope.items() if value]
    matched: list[dict[str, Any]] = []
    rights_excluded: list[str] = []
    for entry in human:
        match = scope_match_details(entry, scope)
        allowed = human_reference_allows(entry, args.intended_use)
        if not allowed:
            rights_excluded.append(str(entry.get("id")))
        if not requested_fields or match["quality"] != "fallback":
            matched.append(
                {
                    "id": entry["id"],
                    "path": entry["path"],
                    "match_quality": match["quality"],
                    "fallback_fields": match["fallback_fields"],
                    "allowed_for_intended_use": allowed,
                    "author": entry.get("author"),
                    "genre": entry.get("genre"),
                    "audience": entry.get("audience"),
                    "language": entry.get("language"),
                    "collection_id": entry.get("collection_id"),
                    "technique_card_id": entry.get("technique_card_id"),
                }
            )
    quality_order = {"exact": 0, "partial": 1, "fallback": 2, "unspecified": 3}
    matched.sort(
        key=lambda item: (
            quality_order.get(str(item["match_quality"]), 4),
            not bool(item["allowed_for_intended_use"]),
            str(item["id"]),
        )
    )
    exact = [item for item in matched if item["match_quality"] == "exact"]
    partial = [item for item in matched if item["match_quality"] == "partial"]
    missing_cards = [
        str(entry["id"])
        for entry in human
        if not entry.get("technique_card_id")
    ]
    low_confidence = [
        {
            "id": entry["id"],
            "origin_confidence": entry.get("origin_confidence"),
            "origin_claim": entry.get("origin_claim"),
        }
        for entry in human
        if entry.get("origin_confidence") not in {"high"}
    ]
    by_language = Counter(str(entry.get("language", "unknown")) for entry in human)
    by_genre = Counter(str(entry.get("genre", "unknown")) for entry in human)
    by_audience = Counter(str(entry.get("audience", "unknown")) for entry in human)
    recommendations: list[str] = []
    if requested_fields and not exact:
        recommendations.append(
            "为请求的语言、体裁和受众补充至少一篇 exact human-reference；当前结果只能使用 partial 或通用基线。"
        )
    if args.intended_use != "unknown" and not [
        item for item in exact + partial if item["allowed_for_intended_use"]
    ]:
        recommendations.append(
            "当前用途没有 rights-compatible 的匹配来源；先补充许可允许该用途的来源，再扩大召回。"
        )
    if missing_cards:
        recommendations.append("为已确认但尚无技术卡片的来源完成 curator review；不要自动从文本晋升规则。")
    if low_confidence:
        recommendations.append("复核 origin_confidence 较低的来源，必要时降回 candidate，而不是仅按文风质量保留。")
    if not recommendations:
        recommendations.append("当前请求范围已有可用覆盖；继续用真实任务的评测结果决定是否补充同类来源。")
    print(
        json_dump(
            {
                "scope": {
                    **scope,
                    "intended_use": args.intended_use,
                },
                "summary": {
                    "confirmed_human_references": len(human),
                    "candidate_human_references": len(candidates),
                    "technique_cards": len(technique_records),
                    "technique_coverage": round(
                        (len(human) - len(missing_cards)) / max(len(human), 1), 3
                    ),
                    "languages": dict(sorted(by_language.items())),
                    "genres": dict(sorted(by_genre.items())),
                    "audiences": dict(sorted(by_audience.items())),
                },
                "scope_coverage": {
                    "requested_fields": requested_fields,
                    "exact": len(exact),
                    "partial": len(partial),
                    "rights_excluded_ids": sorted(rights_excluded),
                    "matched": matched,
                },
                "quality": {
                    "missing_technique_card_ids": missing_cards,
                    "low_confidence_confirmed": low_confidence,
                    "candidate_ids": [str(entry.get("id")) for entry in candidates],
                },
                "recommendations": recommendations,
            }
        )
    )
    return 0


def command_curate_technique_card(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    existing, issues = read_technique_records(vault, entries)
    if issues:
        raise ValueError("invalid human technique index:\n- " + "\n- ".join(issues))
    record = technique_card_record(entries, args)
    existing_for_corpus = next(
        (item for item in existing if item.get("corpus_id") == args.corpus_id),
        None,
    )
    action = "unchanged" if existing_for_corpus == record else "created"
    if existing_for_corpus is not None and action != "unchanged":
        raise ValueError(
            "a technique card already exists for this corpus_id; preserve it and review manually"
        )
    if not args.write:
        print(
            json_dump(
                {
                    "preview": True,
                    "requires_curator_confirmation": not args.curator_confirmed,
                    "action": action,
                    "record": record,
                }
            )
        )
        return 0
    if not args.curator_confirmed:
        raise ValueError("--write requires an explicit --curator-confirmed signal")
    if action == "unchanged":
        print(
            json_dump(
                {
                    "created": False,
                    "index": technique_index_path(vault).relative_to(vault).as_posix(),
                    "record": record,
                }
            )
        )
        return 0
    created = write_technique_record(vault, entries, record)
    _, validation_issues = read_technique_records(vault, entries)
    if validation_issues:
        raise ValueError(
            "written human technique index is invalid:\n- "
            + "\n- ".join(validation_issues)
        )
    print(
        json_dump(
            {
                "created": created,
                "index": technique_index_path(vault).relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def robust_deviations(features: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    if profile["provisional"] or profile["documents"] < 3:
        return []
    floors = {
        "avg_sentence_chars": 4.0,
        "median_sentence_chars": 4.0,
        "p90_sentence_chars": 8.0,
        "avg_paragraph_chars": 30.0,
    }
    output = []
    for name, stats in profile["metrics"].items():
        value = float(features.get(name, 0.0))
        median = float(stats["median"])
        tolerance = max(3 * float(stats["mad"]), floors.get(name, 0.75))
        if abs(value - median) > tolerance:
            output.append(
                {
                    "metric": name,
                    "value": round(value, 3),
                    "profile_median": round(median, 3),
                    "tolerance": round(tolerance, 3),
                    "direction": "above" if value > median else "below",
                }
            )
    return output


def resolve_document(vault: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (vault / raw).resolve()
    try:
        candidate.relative_to(vault)
    except ValueError as error:
        raise ValueError(f"document must be inside vault: {value}") from error
    if not candidate.is_file():
        raise ValueError(f"document not found: {value}")
    return candidate


def command_analyze(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    target = resolve_document(vault, args.file)
    features = document_features(target.read_text(encoding="utf-8"))
    profile = profile_for(vault, entries, args.language, args.genre, args.audience)
    result = {
        "file": target.relative_to(vault).as_posix(),
        "features": features,
        "profile": profile,
        "deviations": robust_deviations(features, profile),
        "interpretation": (
            "Personal evidence is insufficient; use explicit preferences and retrieved examples."
            if profile["provisional"]
            else "The general personal baseline is usable, but this task scope has weak exact evidence."
            if profile["scope_provisional"]
            else "Metrics are diagnostics. Review material deviations against the actual examples."
        ),
    }
    print(json_dump(result))
    return 0


def changed_pairs(before: str, after: str) -> list[dict[str, str]]:
    before_parts = paragraphs(before)
    after_parts = paragraphs(after)
    matcher = difflib.SequenceMatcher(a=before_parts, b=after_parts, autojunk=False)
    output: list[dict[str, str]] = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = "\n\n".join(before_parts[a1:a2]).strip()
        new = "\n\n".join(after_parts[b1:b2]).strip()
        if normalize(old) == normalize(new):
            continue
        output.append(
            {
                "kind": tag,
                "before": old[:800],
                "after": new[:800],
            }
        )
    return output


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def feedback_markdown(
    vault: Path,
    before_path: Path,
    after_path: Path,
    args: argparse.Namespace,
) -> tuple[str, str, list[dict[str, str]]]:
    before_fields = parse_frontmatter(before_path.read_text(encoding="utf-8"))
    after_fields = parse_frontmatter(after_path.read_text(encoding="utf-8"))
    if any(
        normalize(fields.get("sensitivity", "unknown")) == "secret"
        for fields in (before_fields, after_fields)
    ):
        raise ValueError("secret documents cannot be recorded as writing feedback")
    before_text = before_path.read_text(encoding="utf-8")
    after_text = after_path.read_text(encoding="utf-8")
    changes = changed_pairs(before_text, after_text)
    recorded_style_delta = style_delta(before_text, after_text)
    digest = hashlib.sha256(
        (str(before_path) + "\0" + str(after_path) + "\0" + after_text).encode("utf-8")
    ).hexdigest()[:8]
    today = date.today().isoformat()
    task_slug = slugify(args.task_id)[:48]
    record_id = f"writing-feedback-{today.replace('-', '')}-{task_slug}-{digest}"
    relative_before = before_path.relative_to(vault).as_posix()
    relative_after = after_path.relative_to(vault).as_posix()
    preferences = [item.strip() for item in args.preference if item.strip()]
    lines = [
        "---",
        f"id: {record_id}",
        "type: journal",
        "status: verified",
        f"created: {today}",
        f"updated: {today}",
        "sensitivity: private",
        f"task_id: {yaml_string(args.task_id)}",
        f"verdict: {args.verdict}",
        f"language: {yaml_string(args.language)}",
        f"genre: {yaml_string(args.genre)}",
        f"audience: {yaml_string(args.audience)}",
        "reviewer: user",
        f"reviewer_confirmed: {'true' if args.reviewer_confirmed else 'false'}",
        f"before_path: {yaml_string(relative_before)}",
        f"after_path: {yaml_string(relative_after)}",
        "---",
        "",
        f"# Writing feedback: {args.task_id}",
        "",
        "## Signal",
        "",
        f"- Verdict: `{args.verdict}`",
        f"- Before: `{relative_before}`",
        f"- After: `{relative_after}`",
    ]
    if args.note:
        lines.append(f"- Note: {args.note}")
    if preferences:
        lines.extend(("", "## Explicit preferences", ""))
        lines.extend(f"- {item}" for item in preferences)
    lines.extend(("", "## Change pairs", "", "```jsonl"))
    lines.append(
        json.dumps(
            {"kind": "style-delta", "metrics": recorded_style_delta},
            ensure_ascii=False,
        )
    )
    lines.extend(json.dumps(item, ensure_ascii=False) for item in changes)
    lines.extend(("```", ""))
    return record_id, "\n".join(lines), changes


def command_feedback(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    before_path = resolve_document(vault, args.before)
    after_path = resolve_document(vault, args.after)
    record_id, markdown, changes = feedback_markdown(vault, before_path, after_path, args)
    if not args.write:
        print(markdown)
        return 0
    if not args.reviewer_confirmed:
        raise ValueError("--write requires an explicit --reviewer-confirmed signal")
    directory = vault / FEEDBACK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{date.today().isoformat()} {slugify(args.task_id)[:48]} {record_id[-8:]}.md"
    if output.exists():
        raise ValueError(f"feedback record already exists: {output.relative_to(vault)}")
    output.write_text(markdown, encoding="utf-8")
    index = directory / "Feedback Index.md"
    if not index.exists():
        index.write_text(
            "---\ntype: index\nstatus: active\ncreated: "
            + date.today().isoformat()
            + "\nupdated: "
            + date.today().isoformat()
            + "\n---\n\n# Writing Feedback Index\n\n",
            encoding="utf-8",
        )
    link = f"[[{output.relative_to(vault).with_suffix('').as_posix()}]]"
    current = index.read_text(encoding="utf-8")
    if link not in current:
        index.write_text(current.rstrip() + f"\n\n- {link}\n", encoding="utf-8")
    print(
        json_dump(
            {
                "created": output.relative_to(vault).as_posix(),
                "record_id": record_id,
                "change_pairs": len(changes),
            }
        )
    )
    return 0


def build_rollout_evaluation(
    vault: Path,
    entries: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    paths = {
        "baseline_path": resolve_document(vault, args.baseline),
        "candidate_path": resolve_document(vault, args.candidate),
        "final_path": resolve_document(vault, args.final),
        "fact_packet": resolve_document(vault, args.fact_packet),
        "review_evidence": resolve_document(vault, args.review_evidence),
    }
    relative_paths = {
        key: target.relative_to(vault).as_posix() for key, target in paths.items()
    }
    for key, target in paths.items():
        fields = parse_frontmatter(target.read_text(encoding="utf-8"))
        if normalize(fields.get("sensitivity", "unknown")) == "secret":
            raise ValueError(
                f"secret documents cannot be included in rollout evidence: {relative_paths[key]}"
            )
    holdouts = [
        entry
        for entry in entries
        if entry.get("role") == "holdout"
        and entry.get("status") == "confirmed"
        and entry.get("path") == relative_paths["final_path"]
    ]
    if len(holdouts) != 1:
        raise ValueError("--final must be exactly one confirmed holdout in the corpus registry")
    holdout = holdouts[0]
    for key in ("language", "genre", "audience"):
        if normalize(str(getattr(args, key))) != normalize(str(holdout.get(key, ""))):
            raise ValueError(f"--{key} must match the confirmed holdout")
    for key in ("fact_packet", "review_evidence"):
        fields = parse_frontmatter(paths[key].read_text(encoding="utf-8"))
        if fields.get("type") not in {"source", "journal"}:
            raise ValueError(f"--{key.replace('_', '-')} must point to a source or journal record")

    count_keys = (
        "baseline_substantive_edits",
        "candidate_substantive_edits",
        "baseline_factual_errors",
        "candidate_factual_errors",
        "baseline_constraint_errors",
        "candidate_constraint_errors",
    )
    counts = {key: getattr(args, key) for key in count_keys}
    invalid_counts = [key for key, value in counts.items() if value < 0]
    if invalid_counts:
        raise ValueError(
            "rollout evaluation counts must be non-negative: " + ", ".join(invalid_counts)
        )
    metrics = rollout_metrics(
        paths["baseline_path"].read_text(encoding="utf-8"),
        paths["candidate_path"].read_text(encoding="utf-8"),
        paths["final_path"].read_text(encoding="utf-8"),
        counts,
    )
    passed = rollout_passes(metrics)
    record: dict[str, Any] = {
        "kind": "rollout-evaluation",
        "task_id": args.task_id,
        "language": args.language,
        "genre": args.genre,
        "audience": args.audience,
        "reviewer": args.reviewer,
        "reviewer_confirmed": bool(args.reviewer_confirmed),
        **relative_paths,
        "holdout_id": holdout["id"],
        "baseline_sha256": sha256_file(paths["baseline_path"]),
        "candidate_sha256": sha256_file(paths["candidate_path"]),
        "final_sha256": sha256_file(paths["final_path"]),
        "fact_packet_sha256": sha256_file(paths["fact_packet"]),
        "review_evidence_sha256": sha256_file(paths["review_evidence"]),
        **metrics,
        "passed": passed,
        "qualifies_for_activation": (
            passed and args.reviewer == "user" and bool(args.reviewer_confirmed)
        ),
        "created": date.today().isoformat(),
    }
    record["id"] = rollout_record_id(record)
    return record


def rollout_evaluation_markdown(record: dict[str, Any]) -> str:
    created = str(record["created"])
    fact_link = Path(str(record["fact_packet"])).with_suffix("").as_posix()
    review_link = Path(str(record["review_evidence"])).with_suffix("").as_posix()
    final_link = Path(str(record["final_path"])).with_suffix("").as_posix()
    outcome = "passed" if record["passed"] else "failed"
    qualification = "yes" if record["qualifies_for_activation"] else "no"
    return "\n".join(
        [
            "---",
            f"id: {record['id']}",
            "type: journal",
            "status: verified",
            f"created: {created}",
            f"updated: {created}",
            "sensitivity: private",
            f"task_id: {yaml_string(str(record['task_id']))}",
            f"language: {yaml_string(str(record['language']))}",
            f"genre: {yaml_string(str(record['genre']))}",
            f"audience: {yaml_string(str(record['audience']))}",
            f"reviewer: {record['reviewer']}",
            "sources:",
            f'  - "[[{fact_link}]]"',
            f'  - "[[{review_link}]]"',
            f'  - "[[{final_link}]]"',
            "---",
            "",
            f"# Rollout evaluation: {record['task_id']}",
            "",
            "## Result",
            "",
            f"- Outcome: `{outcome}`",
            f"- Qualifies for activation: `{qualification}`",
            f"- Reviewer: `{record['reviewer']}` (explicitly confirmed)",
            f"- Baseline edit ratio: `{record['baseline_edit_ratio']}`",
            f"- Candidate edit ratio: `{record['candidate_edit_ratio']}`",
            f"- Editing improvement: `{record['editing_improvement']}`",
            "",
            "## Evidence",
            "",
            f"- Fact packet: [[{fact_link}]]",
            f"- Review evidence: [[{review_link}]]",
            f"- Confirmed holdout: [[{final_link}]]",
            "",
            "## Machine record",
            "",
            "```jsonl",
            json.dumps(record, ensure_ascii=False),
            "```",
            "",
        ]
    )


def evaluation_record_from_text(text: str, record_id: str) -> dict[str, Any] | None:
    for block in jsonl_blocks(text):
        for line in block.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and value.get("kind") == "rollout-evaluation"
                and value.get("id") == record_id
            ):
                return value
    return None


def write_rollout_evaluation(vault: Path, record: dict[str, Any]) -> tuple[Path, bool]:
    directory = vault / ROLLOUT_EVALUATION_DIR
    directory.mkdir(parents=True, exist_ok=True)
    matching: list[tuple[Path, dict[str, Any]]] = []
    for path in directory.glob("*.md"):
        if path.name == "Rollout Evaluations Index.md":
            continue
        existing = evaluation_record_from_text(
            path.read_text(encoding="utf-8"), str(record["id"])
        )
        if existing is not None:
            matching.append((path, existing))
    if len(matching) > 1:
        raise ValueError(f"duplicate rollout evaluation id: {record['id']}")

    created = not matching
    if matching:
        output, existing_record = matching[0]
        expected_record = dict(record)
        expected_record["created"] = existing_record.get("created", record["created"])
        expected_markdown = rollout_evaluation_markdown(expected_record)
        if output.read_text(encoding="utf-8") != expected_markdown:
            raise ValueError(
                f"existing rollout evaluation differs: {output.relative_to(vault)}"
            )
        record.clear()
        record.update(expected_record)
    else:
        output = directory / (
            f"{record['created']} {slugify(str(record['task_id']))[:48]} "
            f"{str(record['id'])[-12:]}.md"
        )
        if output.exists():
            raise ValueError(f"rollout evaluation path already exists: {output.relative_to(vault)}")
        output.write_text(rollout_evaluation_markdown(record), encoding="utf-8")

    index = directory / "Rollout Evaluations Index.md"
    today = date.today().isoformat()
    if not index.exists():
        index.write_text(
            f"---\ntype: index\nstatus: active\ncreated: {today}\nupdated: {today}\n---\n\n"
            "# Writing Rollout Evaluations Index\n",
            encoding="utf-8",
        )
    link = f"[[{output.relative_to(vault).with_suffix('').as_posix()}]]"
    current = index.read_text(encoding="utf-8")
    if link not in current:
        updated = current.rstrip() + f"\n\n- {link}\n"
        updated = re.sub(r"(?m)^updated:\s*.*$", f"updated: {today}", updated, count=1)
        index.write_text(updated, encoding="utf-8")
    return output, created


def command_evaluate_rollout(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    existing_evaluations, evaluation_issues = rollout_evaluation_events(vault, entries)
    if evaluation_issues:
        raise ValueError(
            "invalid rollout evaluation history:\n- " + "\n- ".join(evaluation_issues)
        )
    record = build_rollout_evaluation(vault, entries, args)
    if not args.write:
        print(
            json_dump(
                {
                    "preview": True,
                    "requires_reviewer_confirmation": not args.reviewer_confirmed,
                    "existing_evaluations": len(existing_evaluations),
                    "record": record,
                }
            )
        )
        return 0
    if not args.reviewer_confirmed:
        raise ValueError("--write requires an explicit --reviewer-confirmed signal")
    output, created = write_rollout_evaluation(vault, record)
    _, validation_issues = rollout_evaluation_events(vault, entries)
    if validation_issues:
        raise ValueError(
            "written rollout evaluation is invalid:\n- " + "\n- ".join(validation_issues)
        )
    print(
        json_dump(
            {
                "created": created,
                "path": output.relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def sample_entry(
    vault: Path,
    entries: list[dict[str, Any]],
    target: Path,
    evidence: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not args.confirmation_note.strip():
        raise ValueError("confirmation note must describe the user's explicit confirmation")
    relative = target.relative_to(vault).as_posix()
    matches = [entry for entry in entries if entry.get("path") == relative]
    if len(matches) > 1:
        raise ValueError(f"multiple registry entries already use sample path: {relative}")
    existing = matches[0] if matches else None
    if existing and existing.get("role") not in {"personal", "holdout"}:
        raise ValueError(
            f"sample path is registered as {existing.get('role')}; do not repurpose that evidence"
        )
    sample_fields = parse_frontmatter(target.read_text(encoding="utf-8"))
    if sample_fields.get("sensitivity") == "secret":
        raise ValueError("secret documents cannot be promoted into writing-style memory")
    evidence_fields = parse_frontmatter(evidence.read_text(encoding="utf-8"))
    if evidence_fields.get("type") not in {"source", "journal"}:
        raise ValueError("confirmation evidence must be a source or journal record")
    if evidence == target:
        raise ValueError("the writing sample cannot serve as its own confirmation evidence")
    relative_evidence = evidence.relative_to(vault).as_posix()
    digest = hashlib.sha256(
        (relative + "\0" + target.read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()[:10]
    record = dict(existing or {})
    record.update(
        {
            "id": (
                str(existing["id"])
                if existing
                else f"{args.role}-{slugify(target.stem)[:40]}-{digest}"
            ),
            "path": relative,
            "role": args.role,
            "status": "confirmed",
            "authorship": "user",
            "approval": "user-confirmed",
            "origin_claim": "user-authored",
            "origin_confidence": "high",
            "origin_basis": (
                f"user confirmed authorship and current representativeness in "
                f"{relative_evidence}: {args.confirmation_note.strip()}"
            ),
            "confirmation_evidence": relative_evidence,
            "language": args.language,
            "genre": args.genre,
            "audience": args.audience,
            "weight": args.weight,
            "confirmed": existing.get("confirmed", date.today().isoformat())
            if existing
            else date.today().isoformat(),
        }
    )
    for key in ("channel", "purpose"):
        value = getattr(args, key)
        if value:
            record[key] = value
        else:
            record.pop(key, None)
    if args.author:
        record["author"] = args.author
    if args.rights:
        record["rights"] = args.rights
    return record, existing


def sample_confirmation_markdown(
    vault: Path,
    record: dict[str, Any],
    confirmation_note: str,
) -> str:
    confirmed_on = str(record.get("confirmed") or date.today().isoformat())
    evidence = str(record["confirmation_evidence"])
    evidence_link = Path(evidence).with_suffix("").as_posix()
    sample_link = Path(str(record["path"])).with_suffix("").as_posix()
    journal_id = f"sample-confirmation-{confirmed_on.replace('-', '')}-{record['id']}"
    return "\n".join(
        [
            "---",
            f"id: {journal_id}",
            "type: journal",
            "status: verified",
            f"created: {confirmed_on}",
            f"updated: {confirmed_on}",
            "sensitivity: private",
            "sources:",
            f'  - "[[{evidence_link}]]"',
            f"corpus_id: {yaml_string(str(record['id']))}",
            f"sample_path: {yaml_string(str(record['path']))}",
            f"sample_role: {record['role']}",
            "---",
            "",
            f"# Writing sample confirmation: {record['id']}",
            "",
            f"- Sample: [[{sample_link}]]",
            f"- Evidence: [[{evidence_link}]]",
            f"- Confirmation: {confirmation_note.strip()}",
            "- The user confirmed both authorship and current representativeness.",
            "",
            "## Registry record",
            "",
            "```jsonl",
            json.dumps(record, ensure_ascii=False),
            "```",
            "",
        ]
    )


def write_sample_confirmation(
    vault: Path,
    record: dict[str, Any],
    confirmation_note: str,
) -> Path:
    directory = vault / SAMPLE_CONFIRMATION_DIR
    directory.mkdir(parents=True, exist_ok=True)
    confirmed_on = str(record.get("confirmed") or date.today().isoformat())
    filename = (
        f"{confirmed_on} {slugify(str(record['id']))[:72]}.md"
    )
    output = directory / filename
    markdown = sample_confirmation_markdown(vault, record, confirmation_note)
    if output.exists():
        if output.read_text(encoding="utf-8") != markdown:
            raise ValueError(f"sample confirmation record already differs: {output.relative_to(vault)}")
    else:
        output.write_text(markdown, encoding="utf-8")
    index = directory / "Sample Confirmations Index.md"
    today = date.today().isoformat()
    if not index.exists():
        index.write_text(
            f"---\ntype: index\nstatus: active\ncreated: {today}\nupdated: {today}\n---\n\n"
            "# Writing Sample Confirmations Index\n",
            encoding="utf-8",
        )
    link = f"[[{output.relative_to(vault).with_suffix('').as_posix()}]]"
    current = index.read_text(encoding="utf-8")
    if link not in current:
        updated = current.rstrip() + f"\n\n- {link}\n"
        updated = re.sub(r"(?m)^updated:\s*.*$", f"updated: {today}", updated, count=1)
        index.write_text(updated, encoding="utf-8")
    return output


def negative_entry(
    vault: Path,
    entries: list[dict[str, Any]],
    target: Path,
    evidence: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not args.reason.strip():
        raise ValueError("negative reason must describe what the user rejected")
    relative = target.relative_to(vault).as_posix()
    matches = [entry for entry in entries if entry.get("path") == relative]
    if len(matches) > 1:
        raise ValueError(f"multiple registry entries already use negative sample path: {relative}")
    existing = matches[0] if matches else None
    if existing and existing.get("role") != "negative":
        raise ValueError(
            f"negative sample path is registered as {existing.get('role')}; do not repurpose that evidence"
        )
    sample_fields = parse_frontmatter(target.read_text(encoding="utf-8"))
    if sample_fields.get("sensitivity") == "secret":
        raise ValueError("secret documents cannot be promoted into writing-style memory")
    evidence_fields = parse_frontmatter(evidence.read_text(encoding="utf-8"))
    if evidence_fields.get("type") not in {"source", "journal"}:
        raise ValueError("negative confirmation evidence must be a source or journal record")
    if evidence == target:
        raise ValueError("the negative sample cannot serve as its own confirmation evidence")
    relative_evidence = evidence.relative_to(vault).as_posix()
    digest = hashlib.sha256(
        (relative + "\0" + target.read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()[:10]
    record = dict(existing or {})
    record.update(
        {
            "id": (
                str(existing["id"])
                if existing
                else f"negative-{slugify(target.stem)[:40]}-{digest}"
            ),
            "path": relative,
            "role": "negative",
            "status": "rejected",
            "authorship": "mixed",
            "approval": "user-confirmed",
            "origin_claim": "mixed",
            "origin_confidence": "medium",
            "origin_basis": "user explicitly rejected this writing as style evidence",
            "confirmation_evidence": relative_evidence,
            "negative_reason": args.reason.strip(),
            "language": args.language,
            "genre": args.genre,
            "audience": args.audience,
            "weight": args.weight,
        }
    )
    for key in ("channel", "purpose"):
        value = getattr(args, key)
        if value:
            record[key] = value
        else:
            record.pop(key, None)
    return record, existing


def negative_confirmation_markdown(
    record: dict[str, Any],
    reason: str,
) -> str:
    confirmed_on = date.today().isoformat()
    sample_link = Path(str(record["path"])).with_suffix("").as_posix()
    evidence_link = Path(str(record["confirmation_evidence"])).with_suffix("").as_posix()
    journal_id = f"negative-confirmation-{confirmed_on.replace('-', '')}-{record['id']}"
    return "\n".join(
        [
            "---",
            f"id: {journal_id}",
            "type: journal",
            "status: verified",
            f"created: {confirmed_on}",
            f"updated: {confirmed_on}",
            "sensitivity: private",
            "sources:",
            f'  - "[[{sample_link}]]"',
            f'  - "[[{evidence_link}]]"',
            f"corpus_id: {yaml_string(str(record['id']))}",
            f"sample_path: {yaml_string(str(record['path']))}",
            "sample_role: negative",
            "reviewer: user",
            "reviewer_confirmed: true",
            "---",
            "",
            f"# Negative writing sample confirmation: {record['id']}",
            "",
            f"- Sample: [[{sample_link}]]",
            f"- Evidence: [[{evidence_link}]]",
            f"- Rejection reason: {reason.strip()}",
            "- The user confirmed that this sample is negative style evidence and must not shape positive voice retrieval.",
            "",
            "## Registry record",
            "",
            "```jsonl",
            json.dumps(record, ensure_ascii=False),
            "```",
            "",
        ]
    )


def write_negative_confirmation(
    vault: Path,
    record: dict[str, Any],
    reason: str,
) -> Path:
    directory = vault / NEGATIVE_CONFIRMATION_DIR
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()} {slugify(str(record['id']))[:72]}.md"
    output = directory / filename
    markdown = negative_confirmation_markdown(record, reason)
    if output.exists():
        if output.read_text(encoding="utf-8") != markdown:
            raise ValueError(
                f"negative confirmation record already differs: {output.relative_to(vault)}"
            )
    else:
        output.write_text(markdown, encoding="utf-8")
    index = directory / "Negative Confirmations Index.md"
    today = date.today().isoformat()
    if not index.exists():
        index.write_text(
            f"---\ntype: index\nstatus: active\ncreated: {today}\nupdated: {today}\n---\n\n"
            "# Negative Writing Confirmations Index\n",
            encoding="utf-8",
        )
    link = f"[[{output.relative_to(vault).with_suffix('').as_posix()}]]"
    current = index.read_text(encoding="utf-8")
    if link not in current:
        updated = current.rstrip() + f"\n\n- {link}\n"
        updated = re.sub(r"(?m)^updated:\s*.*$", f"updated: {today}", updated, count=1)
        index.write_text(updated, encoding="utf-8")
    return output


def human_reference_entry(
    vault: Path,
    entries: list[dict[str, Any]],
    target: Path,
    evidence: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not args.confirmation_note.strip():
        raise ValueError("confirmation note must describe the curator's explicit review")
    try:
        target.relative_to(vault / "02-sources")
    except ValueError as error:
        raise ValueError("human references must be preserved under 02-sources") from error
    source_fields = parse_frontmatter(target.read_text(encoding="utf-8"))
    if source_fields.get("type") != "source":
        raise ValueError("--path must point to a source record with type: source")
    if normalize(source_fields.get("sensitivity", "unknown")) == "secret":
        raise ValueError("secret sources cannot be promoted into human-reference memory")
    if not is_external_url(str(source_fields.get("source_url", ""))):
        raise ValueError("human reference source must have an external http(s) source_url")
    evidence_fields = parse_frontmatter(evidence.read_text(encoding="utf-8"))
    if evidence_fields.get("type") not in {"source", "journal"}:
        raise ValueError("confirmation evidence must be a source or journal record")
    if evidence == target:
        raise ValueError("the source cannot serve as its own confirmation evidence")
    relative = target.relative_to(vault).as_posix()
    relative_evidence = evidence.relative_to(vault).as_posix()
    matches = [entry for entry in entries if entry.get("path") == relative]
    if len(matches) > 1:
        raise ValueError(f"multiple registry entries already use source path: {relative}")
    existing = matches[0] if matches else None
    if existing and existing.get("role") != "human-reference":
        raise ValueError(
            f"source path is registered as {existing.get('role')}; do not repurpose that evidence"
        )
    digest = hashlib.sha256(
        (relative + "\0" + target.read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()[:10]
    allowed_uses = list(dict.fromkeys(str(item) for item in args.allowed_use))
    record = dict(existing or {})
    record.update(
        {
            "id": str(existing["id"])
            if existing
            else f"human-{slugify(target.stem)[:40]}-{digest}",
            "path": relative,
            "role": "human-reference",
            "status": "confirmed",
            "authorship": "third-party",
            "approval": "curator-confirmed",
            "origin_claim": args.origin_claim,
            "origin_confidence": args.origin_confidence,
            "origin_basis": args.origin_basis.strip(),
            "confirmation_evidence": relative_evidence,
            "language": args.language,
            "genre": args.genre,
            "audience": args.audience,
            "weight": args.weight,
            "author": args.author,
            "rights": args.rights,
            "license_id": args.license_id,
            "allowed_uses": allowed_uses,
            "confirmed": existing.get("confirmed", date.today().isoformat())
            if existing
            else date.today().isoformat(),
        }
    )
    notes = args.notes.strip() or str(existing.get("notes", "")) if existing else args.notes.strip()
    if notes:
        record["notes"] = notes
    else:
        record.pop("notes", None)
    return record, existing


def human_reference_confirmation_markdown(
    vault: Path,
    record: dict[str, Any],
    confirmation_note: str,
) -> str:
    confirmed_on = str(record.get("confirmed") or date.today().isoformat())
    source_link = Path(str(record["path"])).with_suffix("").as_posix()
    evidence_link = Path(str(record["confirmation_evidence"])).with_suffix("").as_posix()
    journal_id = f"human-reference-confirmation-{confirmed_on.replace('-', '')}-{record['id']}"
    return "\n".join(
        [
            "---",
            f"id: {journal_id}",
            "type: journal",
            "status: verified",
            f"created: {confirmed_on}",
            f"updated: {confirmed_on}",
            "sensitivity: private",
            "sources:",
            f'  - "[[{source_link}]]"',
            f'  - "[[{evidence_link}]]"',
            f"corpus_id: {yaml_string(str(record['id']))}",
            f"source_path: {yaml_string(str(record['path']))}",
            "---",
            "",
            f"# Human reference confirmation: {record['id']}",
            "",
            f"- Source: [[{source_link}]]",
            f"- Review evidence: [[{evidence_link}]]",
            f"- Confirmation: {confirmation_note.strip()}",
            "- The curator confirmed provenance, rights, human origin, scope, and technique suitability.",
            "",
            "## Registry record",
            "",
            "```jsonl",
            json.dumps(record, ensure_ascii=False),
            "```",
            "",
        ]
    )


def write_human_reference_confirmation(
    vault: Path,
    record: dict[str, Any],
    confirmation_note: str,
) -> Path:
    directory = vault / HUMAN_REFERENCE_CONFIRMATION_DIR
    directory.mkdir(parents=True, exist_ok=True)
    confirmed_on = str(record.get("confirmed") or date.today().isoformat())
    output = directory / (
        f"{confirmed_on} {slugify(str(record['id']))[:72]}.md"
    )
    markdown = human_reference_confirmation_markdown(vault, record, confirmation_note)
    if output.exists():
        if output.read_text(encoding="utf-8") != markdown:
            raise ValueError(
                f"human reference confirmation differs: {output.relative_to(vault)}"
            )
    else:
        output.write_text(markdown, encoding="utf-8")
    index = directory / "Human Reference Confirmations Index.md"
    today = date.today().isoformat()
    if not index.exists():
        index.write_text(
            f"---\ntype: index\nstatus: active\ncreated: {today}\nupdated: {today}\n---\n\n"
            "# Human Reference Confirmations Index\n",
            encoding="utf-8",
        )
    link = f"[[{output.relative_to(vault).with_suffix('').as_posix()}]]"
    current = index.read_text(encoding="utf-8")
    if link not in current:
        updated = current.rstrip() + f"\n\n- {link}\n"
        updated = re.sub(r"(?m)^updated:\s*.*$", f"updated: {today}", updated, count=1)
        index.write_text(updated, encoding="utf-8")
    return output


def command_promote_human_reference(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    target = resolve_document(vault, args.path)
    evidence = resolve_document(vault, args.evidence)
    record, existing = human_reference_entry(vault, entries, target, evidence, args)
    action = "unchanged" if existing == record else "updated" if existing else "created"
    proposed = [record if item is existing else item for item in entries]
    if existing is None:
        proposed.append(record)
    issues = validate_entries(vault, proposed)
    if issues:
        raise ValueError("promoted registry would be invalid:\n- " + "\n- ".join(issues))
    preview = {
        "preview": not args.write,
        "requires_curator_confirmation": not args.curator_confirmed,
        "action": action,
        "record": record,
    }
    if not args.write:
        print(json_dump(preview))
        return 0
    if not args.curator_confirmed:
        raise ValueError("--write requires an explicit --curator-confirmed signal")
    if existing and existing.get("status") == "confirmed" and existing != record:
        raise ValueError("confirmed human reference metadata differs; preserve history and review manually")
    registry = registry_path(vault, args.registry)
    if action != "unchanged":
        write_registry(registry, proposed)
    confirmation_path = write_human_reference_confirmation(
        vault, record, args.confirmation_note
    )
    print(
        json_dump(
            {
                "action": action,
                "registry": registry.relative_to(vault).as_posix(),
                "confirmation": confirmation_path.relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def command_promote_sample(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    target = resolve_document(vault, args.path)
    evidence = resolve_document(vault, args.evidence)
    record, existing = sample_entry(vault, entries, target, evidence, args)
    action = "unchanged" if existing == record else "updated" if existing else "created"
    proposed = [record if item is existing else item for item in entries]
    if existing is None:
        proposed.append(record)
    issues = validate_entries(vault, proposed)
    if issues:
        raise ValueError("promoted registry would be invalid:\n- " + "\n- ".join(issues))
    preview = {
        "preview": not args.write,
        "requires_authorship_confirmation": not args.authorship_confirmed,
        "requires_representativeness_confirmation": not args.representative_confirmed,
        "action": action,
        "record": record,
    }
    if not args.write:
        print(json_dump(preview))
        return 0
    if not args.authorship_confirmed or not args.representative_confirmed:
        raise ValueError(
            "--write requires both --authorship-confirmed and --representative-confirmed"
        )
    if existing and existing.get("status") == "confirmed" and existing != record:
        raise ValueError("confirmed sample metadata differs; preserve history and review manually")
    registry = registry_path(vault, args.registry)
    if action != "unchanged":
        write_registry(registry, proposed)
    confirmation_path = write_sample_confirmation(vault, record, args.confirmation_note)
    print(
        json_dump(
            {
                "action": action,
                "registry": registry.relative_to(vault).as_posix(),
                "confirmation": confirmation_path.relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def command_promote_negative(args: argparse.Namespace) -> int:
    vault, entries = load_validated(args)
    target = resolve_document(vault, args.path)
    evidence = resolve_document(vault, args.evidence)
    record, existing = negative_entry(vault, entries, target, evidence, args)
    action = "unchanged" if existing == record else "updated" if existing else "created"
    proposed = [record if item is existing else item for item in entries]
    if existing is None:
        proposed.append(record)
    issues = validate_entries(vault, proposed)
    if issues:
        raise ValueError("promoted registry would be invalid:\n- " + "\n- ".join(issues))
    preview = {
        "preview": not args.write,
        "requires_reviewer_confirmation": not args.reviewer_confirmed,
        "action": action,
        "record": record,
    }
    if not args.write:
        print(json_dump(preview))
        return 0
    if not args.reviewer_confirmed:
        raise ValueError("--write requires an explicit --reviewer-confirmed signal")
    if existing and existing.get("status") == "rejected" and existing != record:
        raise ValueError("confirmed negative metadata differs; preserve history and review manually")
    registry = registry_path(vault, args.registry)
    if action != "unchanged":
        write_registry(registry, proposed)
    confirmation_path = write_negative_confirmation(vault, record, args.reason)
    print(
        json_dump(
            {
                "action": action,
                "registry": registry.relative_to(vault).as_posix(),
                "confirmation": confirmation_path.relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def command_feedback_candidates(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    pair_events: dict[tuple[str, str], set[str]] = {}
    preference_events: dict[str, set[str]] = {}
    style_events: dict[tuple[str, str, str, str], list[tuple[str, float]]] = {}
    for event in user_confirmed_feedback_events(vault):
        event_id = event["path"]
        fields = event["fields"]
        for item in event["changes"]:
            before = normalize(str(item.get("before", "")))
            after = normalize(str(item.get("after", "")))
            if before or after:
                pair_events.setdefault((before, after), set()).add(event_id)
        for raw_preference in event["preferences"]:
            preference = normalize(raw_preference)
            preference_events.setdefault(preference, set()).add(event_id)
        for metric, delta in event["style_delta"].items():
            threshold = STYLE_DELTA_THRESHOLDS.get(metric)
            if threshold is not None and abs(float(delta)) >= threshold:
                scope_key = (
                    metric,
                    fields.get("language", "unknown"),
                    fields.get("genre", "unknown"),
                    fields.get("audience", "unknown"),
                )
                style_events.setdefault(scope_key, []).append((event_id, float(delta)))
    pairs = [
        {
            "before": before,
            "after": after,
            "events": len(events),
            "evidence": sorted(events),
        }
        for (before, after), events in pair_events.items()
        if len(events) >= args.min_count
    ]
    preferences = [
        {
            "preference": preference,
            "events": len(events),
            "evidence": sorted(events),
        }
        for preference, events in preference_events.items()
        if len(events) >= args.min_count
    ]
    style_signals = []
    for (metric, language, genre, audience), values in style_events.items():
        by_event: dict[str, float] = {}
        for event_id, delta in values:
            by_event[event_id] = delta
        positive = [(event_id, value) for event_id, value in by_event.items() if value > 0]
        negative = [(event_id, value) for event_id, value in by_event.items() if value < 0]
        dominant = positive if len(positive) >= len(negative) else negative
        considered = len(positive) + len(negative)
        if len(dominant) < args.min_count or not considered:
            continue
        consistency = len(dominant) / considered
        if consistency < args.min_consistency:
            continue
        style_signals.append(
            {
                "metric": metric,
                "direction": "increase" if dominant[0][1] > 0 else "decrease",
                "events": len(dominant),
                "considered_events": considered,
                "consistency": round(consistency, 3),
                "median_delta": round(
                    statistics.median(value for _, value in dominant), 4
                ),
                "scope": {
                    "language": language,
                    "genre": genre,
                    "audience": audience,
                },
                "evidence": sorted(event_id for event_id, _ in dominant),
            }
        )
    pairs.sort(key=lambda item: (-item["events"], item["before"], item["after"]))
    preferences.sort(key=lambda item: (-item["events"], item["preference"]))
    style_signals.sort(key=lambda item: (-item["events"], item["metric"]))
    print(
        json_dump(
            {
                "min_count": args.min_count,
                "min_consistency": args.min_consistency,
                "edit_pairs": pairs,
                "preferences": preferences,
                "style_signals": style_signals,
            }
        )
    )
    return 0


def preference_record(args: argparse.Namespace, vault: Path) -> dict[str, Any]:
    evidence: list[str] = []
    for raw_path in args.evidence:
        target = resolve_document(vault, raw_path)
        relative = target.relative_to(vault).as_posix()
        if relative not in evidence:
            evidence.append(relative)
    if args.basis == "repeated-feedback":
        feedback_prefix = FEEDBACK_DIR.as_posix() + "/"
        if len(evidence) < 3 or any(not item.startswith(feedback_prefix) for item in evidence):
            raise ValueError(
                "repeated-feedback promotion requires three distinct writing-feedback records"
            )
        unconfirmed = []
        for relative in evidence:
            target = vault / relative
            fields = parse_frontmatter(target.read_text(encoding="utf-8"))
            if (
                fields.get("type") != "journal"
                or fields.get("status") != "verified"
                or fields.get("reviewer") != "user"
                or normalize(fields.get("reviewer_confirmed", "")) != "true"
            ):
                unconfirmed.append(relative)
        if unconfirmed:
            raise ValueError(
                "repeated-feedback promotion requires verified user-confirmed records: "
                + ", ".join(unconfirmed)
            )
    scope = {key: getattr(args, key, None) for key in SCOPE_FIELDS}
    identity = "\0".join(
        [normalize(args.text)] + [normalize(str(scope.get(key) or "")) for key in SCOPE_FIELDS]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    record: dict[str, Any] = {
        "kind": "preference",
        "id": f"preference-{slugify(args.text)[:36]}-{digest}",
        "text": args.text.strip(),
        "status": "confirmed" if args.user_confirmed else "proposed",
        "approval": "user-confirmed" if args.user_confirmed else "unreviewed",
        "basis": args.basis,
        "evidence": evidence,
        "created": date.today().isoformat(),
    }
    for key, value in scope.items():
        if value:
            record[key] = value
    if args.supersedes:
        record["supersedes"] = args.supersedes
    return record


def append_preference_record(vault: Path, path: Path, record: dict[str, Any]) -> bool:
    existing, issues = read_preference_records(vault, path)
    if issues:
        raise ValueError("invalid voice profile preferences:\n- " + "\n- ".join(issues))
    if any(item.get("id") == record["id"] for item in existing):
        return False
    validation = validate_preference_records(vault, existing + [record])
    if validation:
        raise ValueError("invalid preference record:\n- " + "\n- ".join(validation))
    text = path.read_text(encoding="utf-8")
    serialized = json.dumps(record, ensure_ascii=False)
    pattern = re.compile(
        r"(## Confirmed preference records\s*\n+```jsonl\s*\n)(.*?)(\n```)",
        flags=re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        current = match.group(2).rstrip()
        replacement = (current + "\n" if current else "") + serialized
        updated = text[: match.start(2)] + replacement + text[match.end(2) :]
    else:
        updated = (
            text.rstrip()
            + "\n\n## Confirmed preference records\n\n```jsonl\n"
            + serialized
            + "\n```\n"
        )
    if updated.startswith("---\n"):
        updated = re.sub(
            r"(?m)^updated:\s*.*$", f"updated: {date.today().isoformat()}", updated, count=1
        )
    path.write_text(updated, encoding="utf-8")
    return True


def command_promote_preference(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    profile = voice_profile_path(vault, args.profile)
    try:
        profile.relative_to(vault)
    except ValueError as error:
        raise ValueError("voice profile must be inside the vault") from error
    if not profile.is_file():
        raise ValueError(f"voice profile not found: {profile}")
    record = preference_record(args, vault)
    existing, issues = read_preference_records(vault, profile)
    if issues:
        raise ValueError("invalid voice profile preferences:\n- " + "\n- ".join(issues))
    if args.supersedes and not any(item.get("id") == args.supersedes for item in existing):
        raise ValueError(f"superseded preference not found: {args.supersedes}")
    if not args.write:
        print(
            json_dump(
                {
                    "preview": True,
                    "requires_user_confirmation": not args.user_confirmed,
                    "profile": profile.relative_to(vault).as_posix(),
                    "record": record,
                }
            )
        )
        return 0
    if not args.user_confirmed:
        raise ValueError("--write requires an explicit --user-confirmed signal")
    created = append_preference_record(vault, profile, record)
    print(
        json_dump(
            {
                "created": created,
                "profile": profile.relative_to(vault).as_posix(),
                "record": record,
            }
        )
    )
    return 0


def note_title(path: Path, text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def blockquote_ratio(text: str) -> float:
    body = without_frontmatter(text)
    total = len(re.sub(r"\s+", "", clean_markdown(body)))
    quoted_text = "\n".join(
        re.sub(r"^\s*>+\s?", "", line)
        for line in body.splitlines()
        if re.match(r"^\s*>", line)
    )
    quoted = len(re.sub(r"\s+", "", clean_markdown(quoted_text)))
    return round(min(quoted / max(total, 1), 1.0), 3)


def personal_author_state(author: str, personal_names: list[str]) -> str:
    normalized = normalize(author)
    if not personal_names or normalized in {"", "unknown"}:
        return "none"
    if normalized in personal_names:
        return "exact"
    try:
        parsed = json.loads(author)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        identities = [normalize(str(item)) for item in parsed if normalize(str(item))]
        if identities and all(identity in personal_names for identity in identities):
            return "exact"
        if any(identity in personal_names for identity in identities):
            return "mixed"
    if any(name and name in normalized for name in personal_names):
        return "mixed"
    return "none"


def origin_suggestion(fields: dict[str, str], personal_state: str) -> tuple[str, str, str]:
    author = normalize(fields.get("author", "unknown"))
    published = fields.get("published") or fields.get("date", "")
    source_url = fields.get("source_url", "")
    if personal_state == "exact":
        return (
            "user-authored",
            "medium",
            "author metadata matches a supplied personal identity; user confirmation is still required",
        )
    if personal_state == "mixed":
        return (
            "mixed",
            "low",
            "personal identity appears with other authors or curators; contribution boundaries need review",
        )
    year_match = re.match(r"(\d{4})", published)
    if year_match and int(year_match.group(1)) <= 2022:
        return (
            "pre-generative-ai",
            "high",
            "publication date predates widespread generative-AI writing tools",
        )
    if author not in {"", "unknown"} and source_url not in {"", "unknown"}:
        return (
            "attributed-human",
            "low",
            "named author and public provenance exist, but recent authorship cannot be verified from metadata alone",
        )
    return ("unknown", "low", "authorship or publication provenance is incomplete")


def command_catalog(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    personal_names = [normalize(item) for item in args.personal_author]
    registry_entries, registry_issues = read_registry(registry_path(vault, None))
    registered_by_path = {
        str(entry.get("path")): entry for entry in registry_entries if entry.get("path")
    }
    results = []
    skipped_directories = {
        ".git",
        ".idea",
        ".obsidian",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
        "public",
        "site-packages",
        "themes",
        "venv",
    }
    scan_roots: list[tuple[str, Path]] = [
        ("vault", vault / root_name) for root_name in ("02-sources", "06-output")
    ]
    scan_roots.extend(
        ("external", Path(raw).expanduser().resolve()) for raw in args.external_root
    )
    truncated = False
    for location, root in scan_roots:
        if not root.is_dir():
            continue
        paths = sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".markdown", ".txt"}
            and not any(part in skipped_directories for part in path.relative_to(root).parts)
        )
        for path in paths:
            if len(results) >= args.max_documents:
                truncated = True
                break
            if path.name.endswith("Index.md") or path.name == "AGENTS.md":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            fields = parse_frontmatter(text)
            author = fields.get("author", "unknown")
            author_state = personal_author_state(author, personal_names)
            quoted_ratio = blockquote_ratio(text)
            likely_quoted_compilation = author_state == "exact" and quoted_ratio >= 0.4
            effective_author_state = "mixed" if likely_quoted_compilation else author_state
            source_type = normalize(fields.get("source_type", ""))
            likely_non_prose = any(
                marker in source_type
                for marker in (
                    "catalog",
                    "decision",
                    "fragment",
                    "repository",
                    "research",
                    "requirement",
                    "snapshot",
                )
            )
            relative_path = (
                path.relative_to(vault).as_posix() if location == "vault" else path.as_posix()
            )
            registered = registered_by_path.get(relative_path) if location == "vault" else None
            if registered:
                suggested_role = str(registered.get("role", "unclassified"))
                suggested_status = str(registered.get("status", "candidate"))
                reason = "already registered; registry role and status take precedence"
            elif likely_quoted_compilation:
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = "large quoted proportion; personal authorship of the prose is not established"
            elif author_state == "exact" and not likely_non_prose:
                suggested_role = "personal"
                suggested_status = "candidate"
                reason = "author metadata matches a supplied personal author; confirmation still required"
            elif author_state == "mixed":
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = "personal identity appears with other authors or curators"
            elif (
                location == "vault"
                and path.is_relative_to(vault / "02-sources")
                and normalize(author) not in {"", "unknown"}
                and not likely_non_prose
            ):
                suggested_role = "human-reference"
                suggested_status = "candidate"
                reason = "external source with author metadata"
            else:
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = (
                    "source type is not a natural-prose sample"
                    if likely_non_prose
                    else "authorship or suitability needs review"
                )
            origin_claim, origin_confidence, origin_basis = origin_suggestion(
                fields, effective_author_state
            )
            features = document_features(text)
            results.append(
                {
                    "path": relative_path,
                    "location": location,
                    "scan_root": root.as_posix(),
                    "title": fields.get("title") or note_title(path, text),
                    "author": author,
                    "published": fields.get("published") or fields.get("date", "unknown"),
                    "source_url": fields.get("source_url", "unknown"),
                    "source_type": fields.get("source_type", "unknown"),
                    "characters": features["characters"],
                    "blockquote_ratio": quoted_ratio,
                    "suggested_role": suggested_role,
                    "suggested_status": suggested_status,
                    "registered_id": registered.get("id") if registered else None,
                    "origin_claim": origin_claim,
                    "origin_confidence": origin_confidence,
                    "origin_basis": origin_basis,
                    "reason": reason,
                }
            )
        if truncated:
            break
    print(
        json_dump(
            {
                "vault": str(vault),
                "documents": len(results),
                "truncated": truncated,
                "registry_issues": registry_issues,
                "candidates": results,
            }
        )
    )
    return 0


def add_registry_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", required=True)
    parser.add_argument("--registry")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate the corpus registry")
    add_registry_arguments(validate)
    validate.set_defaults(handler=command_validate)

    profile = commands.add_parser("profile", help="measure confirmed personal samples")
    add_registry_arguments(profile)
    profile.add_argument("--language")
    profile.add_argument("--genre")
    profile.add_argument("--audience")
    profile.set_defaults(handler=command_profile)

    review_candidates = commands.add_parser(
        "review-candidates",
        help="summarize unconfirmed personal samples for manual review without retrieval",
    )
    add_registry_arguments(review_candidates)
    review_candidates.add_argument("--language")
    review_candidates.add_argument("--genre")
    review_candidates.add_argument("--audience")
    review_candidates.set_defaults(handler=command_review_candidates)

    activation_plan = commands.add_parser(
        "activation-plan",
        help="show a read-only activation checklist and safe candidate recommendations",
    )
    add_registry_arguments(activation_plan)
    activation_plan.add_argument("--language")
    activation_plan.add_argument("--genre")
    activation_plan.add_argument("--audience")
    activation_plan.set_defaults(handler=command_activation_plan)

    context = commands.add_parser("context", help="retrieve separated style evidence")
    add_registry_arguments(context)
    context.add_argument("--language")
    context.add_argument("--genre")
    context.add_argument("--audience")
    context.add_argument("--channel")
    context.add_argument("--purpose")
    context.add_argument(
        "--intended-use", choices=sorted(INTENDED_USES), default="unknown"
    )
    context.add_argument("--query", default="")
    context.add_argument("--personal-limit", type=int, default=3)
    context.add_argument("--human-limit", type=int, default=2)
    context.add_argument("--negative-limit", type=int, default=2)
    context.add_argument("--preference-limit", type=int, default=8)
    context.set_defaults(handler=command_context)

    prepare = commands.add_parser(
        "prepare",
        help="build a separated fact-evidence and style-context package for one writing task",
    )
    add_registry_arguments(prepare)
    prepare.add_argument("--fact-packet", action="append", required=True)
    prepare.add_argument("--language")
    prepare.add_argument("--genre")
    prepare.add_argument("--audience")
    prepare.add_argument("--channel")
    prepare.add_argument("--purpose")
    prepare.add_argument(
        "--intended-use", choices=sorted(INTENDED_USES), default="unknown"
    )
    prepare.add_argument("--query", default="")
    prepare.add_argument("--fact-limit", type=int, default=12000)
    prepare.add_argument("--personal-limit", type=int, default=3)
    prepare.add_argument("--human-limit", type=int, default=2)
    prepare.add_argument("--negative-limit", type=int, default=2)
    prepare.add_argument("--preference-limit", type=int, default=8)
    prepare.set_defaults(handler=command_prepare)

    audit = commands.add_parser(
        "audit-corpus",
        help="report human-reference coverage, rights, provenance, and technique gaps",
    )
    add_registry_arguments(audit)
    audit.add_argument("--language")
    audit.add_argument("--genre")
    audit.add_argument("--audience")
    audit.add_argument("--channel")
    audit.add_argument("--purpose")
    audit.add_argument(
        "--intended-use", choices=sorted(INTENDED_USES), default="unknown"
    )
    audit.set_defaults(handler=command_audit_corpus)

    technique = commands.add_parser(
        "curate-technique-card",
        help="preview or write curator-confirmed methods for a human reference",
    )
    add_registry_arguments(technique)
    technique.add_argument("--corpus-id", required=True)
    technique.add_argument("--collection-id")
    technique.add_argument("--technique", action="append", required=True)
    technique.add_argument("--technique-basis", required=True)
    technique.add_argument("--curator-confirmed", action="store_true")
    technique.add_argument("--write", action="store_true")
    technique.set_defaults(handler=command_curate_technique_card)

    analyze = commands.add_parser("analyze", help="compare a draft with the personal profile")
    add_registry_arguments(analyze)
    analyze.add_argument("--file", required=True)
    analyze.add_argument("--language")
    analyze.add_argument("--genre")
    analyze.add_argument("--audience")
    analyze.set_defaults(handler=command_analyze)

    feedback = commands.add_parser("feedback", help="preview or write an explicit feedback event")
    feedback.add_argument("--vault", required=True)
    feedback.add_argument("--before", required=True)
    feedback.add_argument("--after", required=True)
    feedback.add_argument("--verdict", choices=("accepted", "revised", "rejected"), required=True)
    feedback.add_argument("--task-id", required=True)
    feedback.add_argument("--language", required=True)
    feedback.add_argument("--genre", required=True)
    feedback.add_argument("--audience", required=True)
    feedback.add_argument("--note", default="")
    feedback.add_argument("--preference", action="append", default=[])
    feedback.add_argument("--reviewer-confirmed", action="store_true")
    feedback.add_argument("--write", action="store_true")
    feedback.set_defaults(handler=command_feedback)

    evaluate_rollout = commands.add_parser(
        "evaluate-rollout",
        help="preview or write a reviewer-confirmed holdout rollout evaluation",
    )
    add_registry_arguments(evaluate_rollout)
    evaluate_rollout.add_argument("--baseline", required=True)
    evaluate_rollout.add_argument("--candidate", required=True)
    evaluate_rollout.add_argument("--final", required=True)
    evaluate_rollout.add_argument("--fact-packet", required=True)
    evaluate_rollout.add_argument("--review-evidence", required=True)
    evaluate_rollout.add_argument("--task-id", required=True)
    evaluate_rollout.add_argument("--language", required=True)
    evaluate_rollout.add_argument("--genre", required=True)
    evaluate_rollout.add_argument("--audience", required=True)
    evaluate_rollout.add_argument("--baseline-substantive-edits", type=int, required=True)
    evaluate_rollout.add_argument("--candidate-substantive-edits", type=int, required=True)
    evaluate_rollout.add_argument("--baseline-factual-errors", type=int, required=True)
    evaluate_rollout.add_argument("--candidate-factual-errors", type=int, required=True)
    evaluate_rollout.add_argument("--baseline-constraint-errors", type=int, required=True)
    evaluate_rollout.add_argument("--candidate-constraint-errors", type=int, required=True)
    evaluate_rollout.add_argument("--reviewer", choices=("user", "curator"), required=True)
    evaluate_rollout.add_argument("--reviewer-confirmed", action="store_true")
    evaluate_rollout.add_argument("--write", action="store_true")
    evaluate_rollout.set_defaults(handler=command_evaluate_rollout)

    candidates = commands.add_parser(
        "feedback-candidates", help="find recurring exact edit and preference signals"
    )
    candidates.add_argument("--vault", required=True)
    candidates.add_argument("--min-count", type=int, default=3)
    candidates.add_argument("--min-consistency", type=float, default=0.75)
    candidates.set_defaults(handler=command_feedback_candidates)

    promote = commands.add_parser(
        "promote-preference",
        help="preview or persist a user-confirmed durable writing preference",
    )
    promote.add_argument("--vault", required=True)
    promote.add_argument("--profile")
    promote.add_argument("--text", required=True)
    promote.add_argument("--language")
    promote.add_argument("--genre")
    promote.add_argument("--audience")
    promote.add_argument("--channel")
    promote.add_argument("--purpose")
    promote.add_argument("--basis", choices=sorted(PREFERENCE_BASES), required=True)
    promote.add_argument("--evidence", action="append", default=[])
    promote.add_argument("--supersedes")
    promote.add_argument("--user-confirmed", action="store_true")
    promote.add_argument("--write", action="store_true")
    promote.set_defaults(handler=command_promote_preference)

    promote_sample = commands.add_parser(
        "promote-sample",
        help="preview or persist a user-confirmed personal or holdout writing sample",
    )
    add_registry_arguments(promote_sample)
    promote_sample.add_argument("--path", required=True)
    promote_sample.add_argument("--role", choices=("personal", "holdout"), required=True)
    promote_sample.add_argument("--language", required=True)
    promote_sample.add_argument("--genre", required=True)
    promote_sample.add_argument("--audience", required=True)
    promote_sample.add_argument("--channel")
    promote_sample.add_argument("--purpose")
    promote_sample.add_argument("--weight", type=float, default=1.0)
    promote_sample.add_argument("--author")
    promote_sample.add_argument("--rights")
    promote_sample.add_argument("--evidence", required=True)
    promote_sample.add_argument("--confirmation-note", required=True)
    promote_sample.add_argument("--authorship-confirmed", action="store_true")
    promote_sample.add_argument("--representative-confirmed", action="store_true")
    promote_sample.add_argument("--write", action="store_true")
    promote_sample.set_defaults(handler=command_promote_sample)

    promote_negative = commands.add_parser(
        "promote-negative",
        help="preview or persist a user-confirmed rejected writing sample",
    )
    add_registry_arguments(promote_negative)
    promote_negative.add_argument("--path", required=True)
    promote_negative.add_argument("--language", required=True)
    promote_negative.add_argument("--genre", required=True)
    promote_negative.add_argument("--audience", required=True)
    promote_negative.add_argument("--channel")
    promote_negative.add_argument("--purpose")
    promote_negative.add_argument("--weight", type=float, default=1.0)
    promote_negative.add_argument("--evidence", required=True)
    promote_negative.add_argument("--reason", required=True)
    promote_negative.add_argument("--reviewer-confirmed", action="store_true")
    promote_negative.add_argument("--write", action="store_true")
    promote_negative.set_defaults(handler=command_promote_negative)

    promote_human = commands.add_parser(
        "promote-human-reference",
        help="preview or persist a curator-confirmed human writing reference",
    )
    add_registry_arguments(promote_human)
    promote_human.add_argument("--path", required=True)
    promote_human.add_argument("--author", required=True)
    promote_human.add_argument("--language", required=True)
    promote_human.add_argument("--genre", required=True)
    promote_human.add_argument("--audience", required=True)
    promote_human.add_argument("--weight", type=float, default=1.0)
    promote_human.add_argument("--rights", required=True)
    promote_human.add_argument("--license-id", required=True)
    promote_human.add_argument("--allowed-use", action="append", required=True)
    promote_human.add_argument(
        "--origin-claim", choices=sorted(CONFIRMED_HUMAN_ORIGINS), required=True
    )
    promote_human.add_argument(
        "--origin-confidence", choices=("medium", "high"), required=True
    )
    promote_human.add_argument("--origin-basis", required=True)
    promote_human.add_argument("--notes", default="")
    promote_human.add_argument("--evidence", required=True)
    promote_human.add_argument("--confirmation-note", required=True)
    promote_human.add_argument("--curator-confirmed", action="store_true")
    promote_human.add_argument("--write", action="store_true")
    promote_human.set_defaults(handler=command_promote_human_reference)

    catalog = commands.add_parser("catalog", help="discover possible Markdown style samples")
    catalog.add_argument("--vault", required=True)
    catalog.add_argument("--personal-author", action="append", default=[])
    catalog.add_argument("--external-root", action="append", default=[])
    catalog.add_argument("--max-documents", type=int, default=500)
    catalog.set_defaults(handler=command_catalog)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json_dump({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
