"""独占风格工作区的持久化、确认和证据校验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Iterable

from .memory_text import (
    changed_pairs,
    document_edit_ratio,
    normalize,
    parse_frontmatter,
    slugify,
    style_delta,
)


# 原命令层分散写入注册表和确认日志；完整操作集中到此处，保留确认与审计规则。

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


SCOPE_FIELDS = ("language", "genre", "audience", "channel", "purpose")


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


def is_external_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
            "# 人类写作方法索引\n\n"
            "维护者根据已确认的人类写作参考归纳的检索线索。\n\n"
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
            r"^## (?:明确偏好|Explicit preferences)\s*$\n(.*?)(?=^## |\Z)",
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


def load_validated(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    vault = Path(args.vault).expanduser().resolve()
    entries, parse_issues = read_registry(registry_path(vault, args.registry))
    issues = validate_entries(vault, entries, parse_issues)
    if issues:
        raise ValueError("invalid corpus registry:\n- " + "\n- ".join(issues))
    return vault, entries


def command_curate_technique_card(args: argparse.Namespace) -> dict[str, Any]:
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
        return {
            "preview": True,
            "requires_curator_confirmation": not args.curator_confirmed,
            "action": action,
            "record": record,
        }
    if not args.curator_confirmed:
        raise ValueError("--write requires an explicit --curator-confirmed signal")
    if action == "unchanged":
        return {
            "created": False,
            "index": technique_index_path(vault).relative_to(vault).as_posix(),
            "record": record,
        }
    created = write_technique_record(vault, entries, record)
    _, validation_issues = read_technique_records(vault, entries)
    if validation_issues:
        raise ValueError(
            "written human technique index is invalid:\n- "
            + "\n- ".join(validation_issues)
        )
    return {
        "created": created,
        "index": technique_index_path(vault).relative_to(vault).as_posix(),
        "record": record,
    }


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
        f"# 写作反馈：{args.task_id}",
        "",
        "## 反馈信号",
        "",
        f"- 结论：`{args.verdict}`",
        f"- 修改前：`{relative_before}`",
        f"- 修改后：`{relative_after}`",
    ]
    if args.note:
        lines.append(f"- 备注：{args.note}")
    if preferences:
        lines.extend(("", "## 明确偏好", ""))
        lines.extend(f"- {item}" for item in preferences)
    lines.extend(("", "## 修改对照", "", "```jsonl"))
    lines.append(
        json.dumps(
            {"kind": "style-delta", "metrics": recorded_style_delta},
            ensure_ascii=False,
        )
    )
    lines.extend(json.dumps(item, ensure_ascii=False) for item in changes)
    lines.extend(("```", ""))
    return record_id, "\n".join(lines), changes


def command_feedback(args: argparse.Namespace) -> dict[str, Any] | str:
    vault = Path(args.vault).expanduser().resolve()
    before_path = resolve_document(vault, args.before)
    after_path = resolve_document(vault, args.after)
    record_id, markdown, changes = feedback_markdown(vault, before_path, after_path, args)
    if not args.write:
        return markdown
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
    return {
        "created": output.relative_to(vault).as_posix(),
        "record_id": record_id,
        "change_pairs": len(changes),
    }


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
    outcome = "通过" if record["passed"] else "未通过"
    qualification = "是" if record["qualifies_for_activation"] else "否"
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
            f"# 发布评估：{record['task_id']}",
            "",
            "## 结果",
            "",
            f"- 评估结果：`{outcome}`",
            f"- 是否满足激活条件：`{qualification}`",
            f"- 审核者：`{record['reviewer']}`（已明确确认）",
            f"- 基线稿编辑比例：`{record['baseline_edit_ratio']}`",
            f"- 候选稿编辑比例：`{record['candidate_edit_ratio']}`",
            f"- 编辑改善幅度：`{record['editing_improvement']}`",
            "",
            "## 证据",
            "",
            f"- 事实材料：[[{fact_link}]]",
            f"- 审核证据：[[{review_link}]]",
            f"- 已确认留出样本：[[{final_link}]]",
            "",
            "## 机器记录",
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


def command_evaluate_rollout(args: argparse.Namespace) -> dict[str, Any]:
    vault, entries = load_validated(args)
    existing_evaluations, evaluation_issues = rollout_evaluation_events(vault, entries)
    if evaluation_issues:
        raise ValueError(
            "invalid rollout evaluation history:\n- " + "\n- ".join(evaluation_issues)
        )
    record = build_rollout_evaluation(vault, entries, args)
    if not args.write:
        return {
            "preview": True,
            "requires_reviewer_confirmation": not args.reviewer_confirmed,
            "existing_evaluations": len(existing_evaluations),
            "record": record,
        }
    if not args.reviewer_confirmed:
        raise ValueError("--write requires an explicit --reviewer-confirmed signal")
    output, created = write_rollout_evaluation(vault, record)
    _, validation_issues = rollout_evaluation_events(vault, entries)
    if validation_issues:
        raise ValueError(
            "written rollout evaluation is invalid:\n- " + "\n- ".join(validation_issues)
        )
    return {
        "created": created,
        "path": output.relative_to(vault).as_posix(),
        "record": record,
    }


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
            f"# 写作样本确认：{record['id']}",
            "",
            f"- 样本：[[{sample_link}]]",
            f"- 证据：[[{evidence_link}]]",
            f"- 确认说明：{confirmation_note.strip()}",
            "- 用户已确认作者身份和样本当前代表性。",
            "",
            "## 索引记录",
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
            f"# 负面写作样本确认：{record['id']}",
            "",
            f"- 样本：[[{sample_link}]]",
            f"- 证据：[[{evidence_link}]]",
            f"- 拒绝原因：{reason.strip()}",
            "- 用户已确认该样本属于负面风格证据，不得影响正向个人风格检索。",
            "",
            "## 索引记录",
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
            f"# 人类写作参考确认：{record['id']}",
            "",
            f"- 来源：[[{source_link}]]",
            f"- 审核证据：[[{evidence_link}]]",
            f"- 确认说明：{confirmation_note.strip()}",
            "- 维护者已确认来源、权利、人类作者依据、适用范围和写作方法适用性。",
            "",
            "## 索引记录",
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


def command_promote_human_reference(args: argparse.Namespace) -> dict[str, Any]:
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
        return preview
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
    return {
        "action": action,
        "registry": registry.relative_to(vault).as_posix(),
        "confirmation": confirmation_path.relative_to(vault).as_posix(),
        "record": record,
    }


def command_promote_sample(args: argparse.Namespace) -> dict[str, Any]:
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
        return preview
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
    return {
        "action": action,
        "registry": registry.relative_to(vault).as_posix(),
        "confirmation": confirmation_path.relative_to(vault).as_posix(),
        "record": record,
    }


def command_promote_negative(args: argparse.Namespace) -> dict[str, Any]:
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
        return preview
    if not args.reviewer_confirmed:
        raise ValueError("--write requires an explicit --reviewer-confirmed signal")
    if existing and existing.get("status") == "rejected" and existing != record:
        raise ValueError("confirmed negative metadata differs; preserve history and review manually")
    registry = registry_path(vault, args.registry)
    if action != "unchanged":
        write_registry(registry, proposed)
    confirmation_path = write_negative_confirmation(vault, record, args.reason)
    return {
        "action": action,
        "registry": registry.relative_to(vault).as_posix(),
        "confirmation": confirmation_path.relative_to(vault).as_posix(),
        "record": record,
    }


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


def command_promote_preference(args: argparse.Namespace) -> dict[str, Any]:
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
        return {
            "preview": True,
            "requires_user_confirmation": not args.user_confirmed,
            "profile": profile.relative_to(vault).as_posix(),
            "record": record,
        }
    if not args.user_confirmed:
        raise ValueError("--write requires an explicit --user-confirmed signal")
    created = append_preference_record(vault, profile, record)
    return {
        "created": created,
        "profile": profile.relative_to(vault).as_posix(),
        "record": record,
    }


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
            "作者元数据与提供的个人身份一致，但仍需用户确认",
        )
    if personal_state == "mixed":
        return (
            "mixed",
            "low",
            "个人身份与其他作者或维护者同时出现，需要审核贡献边界",
        )
    year_match = re.match(r"(\d{4})", published)
    if year_match and int(year_match.group(1)) <= 2022:
        return (
            "pre-generative-ai",
            "high",
            "发布日期早于生成式 AI 写作工具广泛使用的时期",
        )
    if author not in {"", "unknown"} and source_url not in {"", "unknown"}:
        return (
            "attributed-human",
            "low",
            "存在具名作者和公开来源，但仅凭元数据无法确认近期文本的作者身份",
        )
    return ("unknown", "low", "作者身份或发布来源信息不完整")


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.vault).expanduser().resolve()
    directories = (
        DEFAULT_REGISTRY.parent,
        Path("02-sources"),
        Path("06-output/drafts"),
        Path("06-output/published"),
        FEEDBACK_DIR,
        SAMPLE_CONFIRMATION_DIR,
        NEGATIVE_CONFIRMATION_DIR,
        HUMAN_REFERENCE_CONFIRMATION_DIR,
        ROLLOUT_EVALUATION_DIR,
    )
    for relative in directories:
        (workspace / relative).mkdir(parents=True, exist_ok=True)

    templates = {
        DEFAULT_REGISTRY: "# 语料索引\n\n```jsonl\n\n```\n",
        DEFAULT_VOICE_PROFILE: "# 个人风格配置\n\n```jsonl\n\n```\n",
        DEFAULT_TECHNIQUE_INDEX: "# 人类写作方法索引\n\n```jsonl\n\n```\n",
    }
    created: list[str] = []
    existing: list[str] = []
    for relative, content in templates.items():
        target = workspace / relative
        if target.exists():
            existing.append(relative.as_posix())
            continue
        target.write_text(content, encoding="utf-8")
        created.append(relative.as_posix())

    return {
        "workspace": str(workspace),
        "created": created,
        "existing": existing,
        "message": "风格工作区已就绪。普通写作不需要配置此工作区。",
    }
