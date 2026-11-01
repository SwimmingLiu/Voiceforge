"""从已校验证据计算画像、成熟度和任务上下文。"""

from __future__ import annotations

import argparse
import difflib
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import (
    ALLOWED_USES,
    SCOPE_FIELDS,
    active_preference_records,
    corpus_coverage,
    enrich_human_techniques,
    entry_text,
    feedback_events,
    human_reference_allows,
    load_validated,
    origin_suggestion,
    personal_author_state,
    read_preference_records,
    read_registry,
    read_technique_records,
    registry_path,
    resolve_document,
    rollout_evaluation_events,
    user_confirmed_feedback_events,
    validate_entries,
)
from .memory_text import (
    STYLE_DELTA_THRESHOLDS,
    blockquote_ratio,
    clean_markdown,
    document_features,
    normalize,
    note_title,
    paragraphs,
    parse_frontmatter,
    robust_deviations,
    tokenize,
    weighted_median,
)


# 原脚本混合存储与检索规则；此处只计算报告，持久化操作由 evidence 拥有。

# 参考风险模式只用于第三方摘录排序，不属于草稿的通用禁词。


MIN_HUMAN_REFERENCE_DOCUMENTS = 6


MIN_HUMAN_REFERENCE_GENRES = 3


HUMAN_COLLECTION_DIVERSITY_PENALTY = 2.0


HUMAN_AUTHOR_DIVERSITY_PENALTY = 0.5


HUMAN_TECHNIQUE_DIVERSITY_PENALTY = 1.5


HUMAN_ORIGIN_CONFIDENCE_PENALTY = {
    "high": 0.0,
    "medium": 0.75,
}


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


FACT_PACKET_TYPES = {"source", "journal", "concept", "project", "area", "reference"}


@dataclass(frozen=True)
class DraftQuery:
    """草稿范围只描述任务，不授予第三方研究材料的访问权限。"""

    language: str | None = None
    genre: str | None = None
    audience: str | None = None
    channel: str | None = None
    purpose: str | None = None
    intended_use: str = "unknown"
    query: str = ""
    personal_limit: int = 3
    negative_limit: int = 2
    preference_limit: int = 8


@dataclass(frozen=True)
class ResearchQuery:
    """维护研究必须显式请求，沿用草稿范围中的用途许可。"""

    draft: DraftQuery
    human_limit: int = 2



def select_preferences(
    records: list[dict[str, Any]], args: DraftQuery, limit: int = 8
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
        next_gates.append("确认至少 3 份个人文档，合计达到 2,000 个可用字符")
    if not human_ready:
        next_gates.append(
            f"确认至少 {MIN_HUMAN_REFERENCE_DOCUMENTS} 份人类写作参考，"
            f"覆盖 {MIN_HUMAN_REFERENCE_GENRES} 种体裁"
        )
    if not holdout_ready:
        next_gates.append("至少保留 1 份已确认的个人留出文档")
    if not feedback_observed:
        next_gates.append("记录 1 次由用户实际审核的前后修改事件")
    if not qualifying_evaluations:
        next_gates.append(
            "记录 1 次由用户确认的留出样本评估，要求没有事实错误且修改负担更低"
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
    """返回未确认个人样本的只读审核报告。

    候选材料只汇总元数据和可量化特征。此命令只帮助用户决定确认哪些样本，
    不得成为另一条成稿检索路径，也不得静默地把候选项变成个人配置样本。
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
    """只根据元数据建议审核顺序，不升级任何候选项。

    推荐逻辑有意保持保守：只有已经归类为用户创作、且来源置信度至少为中等的条目，
    才能被建议进入个人配置。混合来源或低置信度文档仍显示在 ``documents_detail`` 中，
    但不能成为训练样本或留出样本建议。结果不包含文档正文，也不会修改索引。
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
    """范围和相关性相近时，优先使用来源证据更强的人类写作参考。"""
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
    """评估第三方参考摘录夹带无关风格特征的风险。

    分数只用于本次检索，不判断同样的表达是否适合用户自己的文章，
    也不会成为草稿检查规则。
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
    args: DraftQuery,
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


def context_feedback(vault: Path, args: DraftQuery, limit: int = 3) -> list[dict[str, Any]]:
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


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
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
    return report


def command_profile(args: argparse.Namespace) -> dict[str, Any]:
    vault, entries = load_validated(args)
    return profile_for(vault, entries, args.language, args.genre, args.audience)


def command_review_candidates(args: argparse.Namespace) -> dict[str, Any]:
    vault, entries = load_validated(args)
    return candidate_profile_for(vault, entries, args.language, args.genre, args.audience)


def activation_plan_payload(
    vault: Path,
    entries: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """构建只读的启用检查表，不改变索引状态。"""
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


def command_activation_plan(args: argparse.Namespace) -> dict[str, Any]:
    vault, entries = load_validated(args)
    return activation_plan_payload(vault, entries, args)


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


def command_audit_corpus(args: argparse.Namespace) -> dict[str, Any]:
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
    return {
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


def command_analyze(args: argparse.Namespace) -> dict[str, Any]:
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
            "个人证据不足；请结合明确偏好和检索到的样本判断。"
            if profile["provisional"]
            else "通用个人基线可用，但当前任务范围内的精确证据较弱。"
            if profile["scope_provisional"]
            else "量化指标只用于诊断；明显偏差应对照实际样本判断。"
        ),
    }
    return result


def command_feedback_candidates(args: argparse.Namespace) -> dict[str, Any]:
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
    return {
        "min_count": args.min_count,
        "min_consistency": args.min_consistency,
        "edit_pairs": pairs,
        "preferences": preferences,
        "style_signals": style_signals,
    }


def command_catalog(args: argparse.Namespace) -> dict[str, Any]:
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
                reason = "已经登记，以索引中的角色和状态为准"
            elif likely_quoted_compilation:
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = "引用占比较高，无法确认正文属于个人原创"
            elif author_state == "exact" and not likely_non_prose:
                suggested_role = "personal"
                suggested_status = "candidate"
                reason = "作者元数据与提供的个人作者一致，但仍需确认"
            elif author_state == "mixed":
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = "个人身份与其他作者或维护者同时出现"
            elif (
                location == "vault"
                and path.is_relative_to(vault / "02-sources")
                and normalize(author) not in {"", "unknown"}
                and not likely_non_prose
            ):
                suggested_role = "human-reference"
                suggested_status = "candidate"
                reason = "带有作者元数据的外部来源"
            else:
                suggested_role = "unclassified"
                suggested_status = "candidate"
                reason = (
                    "来源类型不是自然语言文章样本"
                    if likely_non_prose
                    else "作者身份或适用性需要审核"
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
    return {
        "vault": str(vault),
        "documents": len(results),
        "truncated": truncated,
        "registry_issues": registry_issues,
        "candidates": results,
    }


def _context_payload(
    vault: Path, entries: list[dict[str, Any]], args: DraftQuery,
    research: ResearchQuery | None = None,
) -> dict[str, Any]:
    technique_records, technique_issues = read_technique_records(vault, entries)
    if technique_issues:
        raise ValueError(
            "invalid human technique index:\n- " + "\n- ".join(technique_issues)
        )
    # 默认草稿不得获得第三方方法；只有显式研究请求才关联方法卡片。
    if research is not None:
        entries = enrich_human_techniques(entries, technique_records)
    preferences, preference_issues = read_preference_records(vault)
    if preference_issues:
        raise ValueError("invalid voice profile preferences:\n- " + "\n- ".join(preference_issues))
    query_tokens = tokenize(args.query or "")
    personal = select_context(
        vault, entries, "personal", args.personal_limit, query_tokens, args
    )
    human_reference = (
        select_context(
            vault, entries, "human-reference", research.human_limit, query_tokens, args
        )
        if research is not None
        else []
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
    ] if research is not None else []
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
            "事实声称必须来自任务证据，不能来自风格样本。",
            "人类写作参考只用于研究写作方法，不能提供个人身份或独特措辞。",
            "方法标签是维护者检索线索，不是规则或来源声称。",
            "与声明用途不相容的人类写作参考已在检索前排除。",
            "已确认偏好只用于指导表达，不能作为任务事实。",
            "候补证据的可信度低于范围精确匹配的证据。",
            "范围和主题相关性相近时，优先使用高置信度的人类来源证据。",
            "暂定个人配置只能作为较弱证据。",
        ],
    }
    return result


def draft_context(
    root: Path, entries: list[dict[str, Any]], query: DraftQuery
) -> dict[str, Any]:
    """普通成稿只返回个人、偏好和负面证据。"""
    return _context_payload(root, entries, query)


def research_context(
    root: Path, entries: list[dict[str, Any]], query: ResearchQuery
) -> dict[str, Any]:
    """显式维护研究保留原有用途、范围和来源筛选。"""
    return _context_payload(root, entries, query.draft, query)



def prepare(
    vault: Path, entries: list[dict[str, Any]], query: DraftQuery,
    fact_packets: list[str], fact_limit: int = 12000,
) -> dict[str, Any]:
    query_tokens = tokenize(query.query or "")
    seen: set[str] = set()
    fact_evidence: list[dict[str, Any]] = []
    for raw_path in fact_packets:
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
                query.language,
                fact_limit,
            )
        )
    # 原准备流程把研究材料用于生成；此入口固定使用草稿请求，无法启用研究。
    style_context = draft_context(vault, entries, query)
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
            "第三方参考摘录和方法卡片只供显式维护研究，不进入本次成稿上下文。",
            "candidate personal、holdout 和模型未修改输出不能进入生成上下文。",
            "如果证据不足，保留不确定性并提出问题，不用风格样本补齐事实。",
        ],
        "warnings": warnings,
    }
    return result
