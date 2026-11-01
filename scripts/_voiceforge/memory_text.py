"""保留原有来源正文与风格统计，供历史评估重算使用。"""

from __future__ import annotations

import difflib
import html
import re
import statistics
import unicodedata
from pathlib import Path
from typing import Any


# 原脚本把统计与持久化混在一起；此处完整保留统计算法，避免改变历史评估。

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


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


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
    """返回可见正文，并排除代码和展示用标记。"""
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


def document_edit_ratio(source: str, target: str) -> float:
    source_text = clean_markdown(source)
    target_text = clean_markdown(target)
    if not source_text and not target_text:
        return 0.0
    similarity = difflib.SequenceMatcher(
        None, source_text, target_text, autojunk=False
    ).ratio()
    return round(1.0 - similarity, 4)


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
