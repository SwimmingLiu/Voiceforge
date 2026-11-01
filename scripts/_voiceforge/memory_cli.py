"""解析风格工作区命令，并统一输出报告和退出码。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .evidence import (
    CONFIRMED_HUMAN_ORIGINS,
    INTENDED_USES,
    PREFERENCE_BASES,
    command_curate_technique_card,
    command_evaluate_rollout,
    command_feedback,
    command_init,
    command_promote_human_reference,
    command_promote_negative,
    command_promote_preference,
    command_promote_sample,
    load_validated,
)
from .memory import (
    DraftQuery,
    ResearchQuery,
    command_activation_plan,
    command_analyze,
    command_audit_corpus,
    command_catalog,
    command_feedback_candidates,
    command_profile,
    command_review_candidates,
    command_validate,
    draft_context,
    prepare,
    research_context,
)


# 原入口同时处理算法和文件写入；此层只适配参数、序列化结果和设置退出码。

def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def add_workspace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        "--vault",
        dest="vault",
        required=True,
        help="独立风格工作区路径；--vault 是兼容旧版本的别名",
    )


def add_registry_arguments(parser: argparse.ArgumentParser) -> None:
    add_workspace_argument(parser)
    parser.add_argument("--registry", help="语料索引路径，默认使用工作区内置路径")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser("init", help="初始化独立风格工作区")
    add_workspace_argument(initialize)
    initialize.set_defaults(handler=command_init)

    validate = commands.add_parser("validate", help="校验语料索引和风格工作区")
    add_registry_arguments(validate)
    validate.set_defaults(handler=command_validate)

    profile = commands.add_parser("profile", help="统计已确认的个人写作样本")
    add_registry_arguments(profile)
    profile.add_argument("--language")
    profile.add_argument("--genre")
    profile.add_argument("--audience")
    profile.set_defaults(handler=command_profile)

    review_candidates = commands.add_parser(
        "review-candidates",
        help="汇总未确认的个人样本，只供人工审核，不返回样本文本",
    )
    add_registry_arguments(review_candidates)
    review_candidates.add_argument("--language")
    review_candidates.add_argument("--genre")
    review_candidates.add_argument("--audience")
    review_candidates.set_defaults(handler=command_review_candidates)

    activation_plan = commands.add_parser(
        "activation-plan",
        help="显示只读的启用检查表和安全的候选样本建议",
    )
    add_registry_arguments(activation_plan)
    activation_plan.add_argument("--language")
    activation_plan.add_argument("--genre")
    activation_plan.add_argument("--audience")
    activation_plan.set_defaults(handler=command_activation_plan)

    context = commands.add_parser("context", help="按证据类型检索风格上下文")
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
    context.add_argument("--research", action="store_true", help="显式检索维护研究用的人类参考")
    context.set_defaults(handler=command_context)

    prepare = commands.add_parser(
        "prepare",
        help="为单次写作任务分别构建事实证据和风格上下文",
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
        help="报告人类写作参考的覆盖范围、权利、来源和方法缺口",
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
        help="预览或写入由维护者确认的人类写作方法",
    )
    add_registry_arguments(technique)
    technique.add_argument("--corpus-id", required=True)
    technique.add_argument("--collection-id")
    technique.add_argument("--technique", action="append", required=True)
    technique.add_argument("--technique-basis", required=True)
    technique.add_argument("--curator-confirmed", action="store_true")
    technique.add_argument("--write", action="store_true")
    technique.set_defaults(handler=command_curate_technique_card)

    analyze = commands.add_parser("analyze", help="比较草稿与个人风格配置")
    add_registry_arguments(analyze)
    analyze.add_argument("--file", required=True)
    analyze.add_argument("--language")
    analyze.add_argument("--genre")
    analyze.add_argument("--audience")
    analyze.set_defaults(handler=command_analyze)

    feedback = commands.add_parser("feedback", help="预览或写入明确的用户反馈")
    add_workspace_argument(feedback)
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
        help="预览或写入经审核者确认的留出样本评估",
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
        "feedback-candidates", help="查找重复出现的明确修改和偏好信号"
    )
    add_workspace_argument(candidates)
    candidates.add_argument("--min-count", type=int, default=3)
    candidates.add_argument("--min-consistency", type=float, default=0.75)
    candidates.set_defaults(handler=command_feedback_candidates)

    promote = commands.add_parser(
        "promote-preference",
        help="预览或保存用户确认的长期写作偏好",
    )
    add_workspace_argument(promote)
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
        help="预览或保存用户确认的个人样本或留出样本",
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
        help="预览或保存用户明确拒绝的写作样本",
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
        help="预览或保存维护者确认的人类写作参考",
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

    catalog = commands.add_parser("catalog", help="发现可能的 Markdown 风格样本")
    add_workspace_argument(catalog)
    catalog.add_argument("--personal-author", action="append", default=[])
    catalog.add_argument("--external-root", action="append", default=[])
    catalog.add_argument("--max-documents", type=int, default=500)
    catalog.set_defaults(handler=command_catalog)
    return root


def draft_query(args: argparse.Namespace) -> DraftQuery:
    """兼容用途字段只回显任务范围，不把旧 human-limit 参数当作研究授权。"""
    return DraftQuery(
        language=args.language,
        genre=args.genre,
        audience=args.audience,
        channel=args.channel,
        purpose=args.purpose,
        intended_use=args.intended_use,
        query=args.query,
        personal_limit=args.personal_limit,
        negative_limit=args.negative_limit,
        preference_limit=args.preference_limit,
    )


def command_context(args: argparse.Namespace) -> dict[str, Any]:
    root, entries = load_validated(args)
    query = draft_query(args)
    if args.research:
        return research_context(root, entries, ResearchQuery(query, args.human_limit))
    return draft_context(root, entries, query)


def command_prepare(args: argparse.Namespace) -> dict[str, Any]:
    root, entries = load_validated(args)
    return prepare(root, entries, draft_query(args), args.fact_packet, args.fact_limit)


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.handler(args)
        print(result if isinstance(result, str) else json_dump(result))
        return 1 if args.command == "validate" and not result["healthy"] else 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json_dump({"error": str(error)}), file=sys.stderr)
        return 2
