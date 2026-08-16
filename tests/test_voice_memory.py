from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "voice_memory.py"


class VoiceMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        (self.vault / "05-areas/writing-style").mkdir(parents=True)
        (self.vault / "06-output/published").mkdir(parents=True)
        (self.vault / "06-output/drafts").mkdir(parents=True)
        (self.vault / "02-sources").mkdir(parents=True)
        confirmation_path = "02-sources/user-confirmation.md"
        (self.vault / confirmation_path).write_text(
            "---\ntype: source\nstatus: verified\n---\n\n"
            "The user confirmed authorship and current representativeness.\n",
            encoding="utf-8",
        )

        personal_text = (
            "## 设计背景\n\n"
            "我先说明这个组件处理什么问题。系统读取输入数据，然后按照字段完成校验。"
            "如果校验失败，接口会返回具体字段和原因。\n\n"
            "## 实现方式\n\n"
            "这里保留两个步骤。第一步检查配置，第二步运行任务并记录结果。"
            "这样可以直接定位失败位置。\n\n"
        ) * 12
        entries = []
        for index in range(3):
            relative = f"06-output/published/personal-{index}.md"
            (self.vault / relative).write_text(personal_text + f"\n样本编号 {index}。\n", encoding="utf-8")
            entries.append(
                {
                    "id": f"personal-{index}",
                    "path": relative,
                    "role": "personal",
                    "status": "confirmed",
                    "authorship": "user",
                    "approval": "user-confirmed",
                    "origin_claim": "user-authored",
                    "origin_confidence": "high",
                    "confirmation_evidence": confirmation_path,
                    "language": "zh",
                    "genre": "technical-article",
                    "audience": "public",
                    "weight": 1.0,
                }
            )

        candidate_path = "06-output/drafts/candidate.md"
        (self.vault / candidate_path).write_text("这是一份尚未确认的个人草稿。", encoding="utf-8")
        entries.append(
            {
                "id": "personal-candidate",
                "path": candidate_path,
                "role": "personal",
                "status": "candidate",
                "authorship": "mixed",
                "approval": "unreviewed",
                "language": "zh",
                "genre": "technical-article",
                "audience": "public",
                "weight": 1.0,
            }
        )

        human_path = "02-sources/human.md"
        (self.vault / human_path).write_text(
            "---\ntype: source\nsource_url: https://example.com/human\n---\n\n"
            "# Human source\n\n## Preserved Content\n\n"
            "---\ntitle: Human article\nauthor: Example\n---\n\n"
            "A compact technical article introduces each term before using it.\n\n"
            "## Provenance\n\n- Author: Example\n",
            encoding="utf-8",
        )
        entries.append(
            {
                "id": "human-1",
                "path": human_path,
                "role": "human-reference",
                "status": "confirmed",
                "authorship": "third-party",
                "approval": "curator-confirmed",
                "origin_claim": "attributed-human",
                "origin_confidence": "medium",
                "origin_basis": "named author and public article provenance",
                "language": "en",
                "genre": "technical-article",
                "audience": "technical-practitioner",
                "weight": 1.0,
                "author": "Example",
                "rights": "public-reference",
                "license_id": "CC-BY-4.0",
                "allowed_uses": ["private", "noncommercial", "commercial"],
            }
        )

        holdout_path = "06-output/published/holdout.md"
        (self.vault / holdout_path).write_text(personal_text, encoding="utf-8")
        entries.append(
            {
                "id": "holdout-1",
                "path": holdout_path,
                "role": "holdout",
                "status": "confirmed",
                "authorship": "user",
                "approval": "user-confirmed",
                "origin_claim": "user-authored",
                "origin_confidence": "high",
                "confirmation_evidence": confirmation_path,
                "language": "zh",
                "genre": "technical-article",
                "audience": "public",
                "weight": 1.0,
            }
        )
        registry = "# Corpus Registry\n\n```jsonl\n" + "\n".join(
            json.dumps(item, ensure_ascii=False) for item in entries
        ) + "\n```\n"
        (self.vault / "05-areas/writing-style/Corpus Registry.md").write_text(
            registry, encoding="utf-8"
        )
        (self.vault / "05-areas/writing-style/Voice Profile.md").write_text(
            "---\ntype: area\nstatus: draft\ncreated: 2026-08-15\nupdated: 2026-08-15\n---\n\n"
            "# Voice Profile\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def rollout_evidence(self, stem: str = "rollout") -> dict[str, str]:
        final = self.vault / "06-output/published/holdout.md"
        final_text = final.read_text(encoding="utf-8")
        paths = {
            "baseline": f"06-output/drafts/{stem}-baseline.md",
            "candidate": f"06-output/drafts/{stem}-candidate.md",
            "fact_packet": f"02-sources/{stem}-fact-packet.md",
            "review_evidence": f"02-sources/{stem}-review.md",
            "final": "06-output/published/holdout.md",
        }
        (self.vault / paths["baseline"]).write_text(
            "这是一个空泛的初稿，没有按照最终文章的结构解释配置、校验和任务执行。\n",
            encoding="utf-8",
        )
        (self.vault / paths["candidate"]).write_text(
            final_text.replace("这里保留两个步骤", "这里保留两项步骤", 1),
            encoding="utf-8",
        )
        (self.vault / paths["fact_packet"]).write_text(
            "---\ntype: source\nstatus: verified\n---\n\n"
            "本次任务要求解释配置校验、任务执行和失败定位。\n",
            encoding="utf-8",
        )
        (self.vault / paths["review_evidence"]).write_text(
            "---\ntype: journal\nstatus: verified\n---\n\n"
            "用户核对了最终稿、错误计数和实质修改次数。\n",
            encoding="utf-8",
        )
        return paths

    def rollout_command(
        self,
        paths: dict[str, str],
        task_id: str = "holdout-rollout",
        candidate_factual_errors: int = 0,
        reviewer: str = "user",
    ) -> list[str]:
        return [
            "evaluate-rollout",
            "--vault",
            str(self.vault),
            "--baseline",
            paths["baseline"],
            "--candidate",
            paths["candidate"],
            "--final",
            paths["final"],
            "--fact-packet",
            paths["fact_packet"],
            "--review-evidence",
            paths["review_evidence"],
            "--task-id",
            task_id,
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--baseline-substantive-edits",
            "6",
            "--candidate-substantive-edits",
            "1",
            "--baseline-factual-errors",
            "2",
            "--candidate-factual-errors",
            str(candidate_factual_errors),
            "--baseline-constraint-errors",
            "1",
            "--candidate-constraint-errors",
            "0",
            "--reviewer",
            reviewer,
        ]

    def add_ready_human_library(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        additions = []
        genres = (
            "technical-documentation",
            "social-post",
            "technical-article",
            "technical-documentation",
            "social-post",
        )
        for index, genre in enumerate(genres, start=2):
            relative = f"02-sources/human-{index}.md"
            (self.vault / relative).write_text(
                "---\ntype: source\n"
                f"source_url: https://example.com/human-{index}\n---\n\n"
                f"# Human source {index}\n\n## Preserved Content\n\n"
                "A named human author explains one concrete point with a short example.\n",
                encoding="utf-8",
            )
            additions.append(
                {
                    "id": f"human-{index}",
                    "path": relative,
                    "role": "human-reference",
                    "status": "confirmed",
                    "authorship": "third-party",
                    "approval": "curator-confirmed",
                    "origin_claim": "attributed-human",
                    "origin_confidence": "medium",
                    "origin_basis": "named author and public article provenance",
                    "language": "en",
                    "genre": genre,
                    "audience": "technical-practitioner",
                    "weight": 1.0,
                    "author": f"Example {index}",
                    "rights": "public-reference",
                    "license_id": "CC-BY-4.0",
                    "allowed_uses": ["private", "noncommercial", "commercial"],
                }
            )
        registry = registry_path.read_text(encoding="utf-8")
        serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in additions)
        registry_path.write_text(
            registry.replace("\n```\n", f"\n{serialized}\n```\n", 1),
            encoding="utf-8",
        )

    def test_validate_and_profile(self) -> None:
        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        validation = json.loads(validate.stdout)
        self.assertTrue(validation["healthy"])
        self.assertGreaterEqual(len(validation["coverage"]), 1)
        self.assertTrue(validation["readiness"]["personal"]["profile_ready"])
        self.assertTrue(validation["readiness"]["holdout"]["available"])
        self.assertFalse(validation["readiness"]["feedback"]["observed"])
        self.assertFalse(validation["readiness"]["rollout_evaluation"]["observed"])
        self.assertEqual(validation["readiness"]["activation"]["mode"], "shadow")
        self.assertFalse(validation["readiness"]["activation"]["ready"])
        self.assertFalse(validation["readiness"]["human_reference"]["library_ready"])
        self.assertEqual(
            validation["readiness"]["human_reference"]["allowed_use_coverage"],
            {"commercial": 1, "noncommercial": 1, "private": 1},
        )

        profile = self.run_cli(
            "profile",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(profile.returncode, 0, profile.stderr)
        payload = json.loads(profile.stdout)
        self.assertEqual(payload["documents"], 3)
        self.assertFalse(payload["provisional"])
        self.assertGreater(payload["characters"], 2000)

    def test_profile_uses_language_compatible_samples_and_reports_weak_scope(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        lines = registry_path.read_text(encoding="utf-8").splitlines()
        rewritten = []
        for line in lines:
            if line.startswith("{"):
                entry = json.loads(line)
                if entry.get("id") == "personal-1":
                    entry["genre"] = "technical-documentation"
                elif entry.get("id") == "personal-2":
                    entry["genre"] = "social-post"
                line = json.dumps(entry, ensure_ascii=False)
            rewritten.append(line)
        registry_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

        profile = self.run_cli(
            "profile",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(profile.returncode, 0, profile.stderr)
        payload = json.loads(profile.stdout)
        self.assertEqual(payload["documents"], 3)
        self.assertEqual(payload["exact_documents"], 1)
        self.assertFalse(payload["provisional"])
        self.assertTrue(payload["scope_provisional"])
        self.assertEqual(payload["basis"], "language-compatible-fallback")

    def test_context_separates_roles_and_excludes_unconfirmed(self) -> None:
        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--genre",
            "technical-article",
            "--query",
            "technical component",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        personal_ids = {item["id"] for item in payload["personal"]}
        self.assertNotIn("personal-candidate", personal_ids)
        self.assertNotIn("holdout-1", personal_ids)
        self.assertEqual({item["id"] for item in payload["human_reference"]}, {"human-1"})
        self.assertNotIn("title:", payload["human_reference"][0]["excerpt"])
        self.assertEqual(payload["human_reference"][0]["rights"], "public-reference")
        self.assertEqual(payload["human_reference"][0]["author"], "Example")
        self.assertEqual(payload["human_reference"][0]["license_id"], "CC-BY-4.0")
        self.assertEqual(
            payload["human_reference"][0]["allowed_uses"],
            ["private", "noncommercial", "commercial"],
        )

        candidate_override = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--include-candidates",
        )
        self.assertNotEqual(candidate_override.returncode, 0)
        self.assertIn("unrecognized arguments", candidate_override.stderr)

    def test_prepare_keeps_fact_evidence_and_style_context_separate(self) -> None:
        fact_path = "02-sources/task-facts.md"
        (self.vault / fact_path).write_text(
            "---\n"
            "type: source\n"
            "status: verified\n"
            "sensitivity: internal\n"
            "title: Task facts\n"
            "source_url: https://example.com/task-facts\n"
            "---\n\n"
            "本次任务需要解释组件如何读取配置、校验字段，并在失败时返回原因。\n\n"
            "事实包没有说明性能指标，因此成稿不能补写吞吐量或延迟数字。\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "prepare",
            "--vault",
            str(self.vault),
            "--fact-packet",
            fact_path,
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--intended-use",
            "private",
            "--query",
            "解释配置校验和失败原因",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["fact_evidence"][0]["path"], fact_path)
        self.assertIn("不能补写吞吐量", payload["fact_evidence"][0]["excerpt"])
        self.assertEqual(payload["style_context"]["personal"][0]["id"], "personal-0")
        self.assertNotIn("personal-candidate", {
            item["id"] for item in payload["style_context"]["personal"]
        })
        self.assertTrue(any("事实、数字" in item for item in payload["generation_contract"]))
        self.assertFalse(payload["fact_evidence"][0]["truncated"])

    def test_prepare_rejects_secret_fact_packet(self) -> None:
        secret_path = "02-sources/secret-facts.md"
        (self.vault / secret_path).write_text(
            "---\ntype: source\nstatus: verified\nsensitivity: secret\n---\n\n"
            "不可输出的事实。\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "prepare",
            "--vault",
            str(self.vault),
            "--fact-packet",
            secret_path,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret fact packets", result.stderr)

    def test_audit_corpus_reports_scope_and_quality_gaps(self) -> None:
        result = self.run_cli(
            "audit-corpus",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--intended-use",
            "commercial",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["summary"]["confirmed_human_references"], 1)
        self.assertEqual(payload["summary"]["candidate_human_references"], 0)
        self.assertEqual(payload["scope_coverage"]["exact"], 0)
        self.assertEqual(payload["scope_coverage"]["partial"], 0)
        self.assertEqual(payload["quality"]["candidate_ids"], [])
        self.assertEqual(payload["quality"]["missing_technique_card_ids"], ["human-1"])
        self.assertTrue(any("exact human-reference" in item for item in payload["recommendations"]))

    def test_context_marks_cross_scope_human_reference_as_fallback(self) -> None:
        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--query",
            "解释组件的工作机制",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual([item["id"] for item in payload["human_reference"]], ["human-1"])
        selected = payload["human_reference"][0]
        self.assertEqual(selected["match_quality"], "fallback")
        self.assertEqual(set(selected["fallback_fields"]), {"language", "audience"})
        self.assertEqual(payload["retrieval"]["human_reference"]["fallback"], 1)

    def test_context_prefers_high_confidence_human_origin_with_equal_scope(self) -> None:
        high_path = "02-sources/human-high.md"
        (self.vault / high_path).write_text(
            "---\ntype: source\nsource_url: https://example.com/human-high\n---\n\n"
            "# High confidence source\n\n## Preserved Content\n\n"
            "A human-maintained technical article explains the mechanism before the example.\n",
            encoding="utf-8",
        )
        high = {
            "id": "human-high",
            "path": high_path,
            "role": "human-reference",
            "status": "confirmed",
            "authorship": "third-party",
            "approval": "curator-confirmed",
            "origin_claim": "pre-generative-ai",
            "origin_confidence": "high",
            "origin_basis": "fixed version and named human provenance",
            "language": "en",
            "genre": "technical-article",
            "audience": "technical-practitioner",
            "weight": 1.0,
            "author": "High Confidence Author",
            "rights": "CC BY 4.0",
            "license_id": "CC-BY-4.0",
            "allowed_uses": ["private", "noncommercial", "commercial"],
        }
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        registry = registry_path.read_text(encoding="utf-8")
        registry_path.write_text(
            registry.replace(
                "\n```\n",
                "\n" + json.dumps(high, ensure_ascii=False) + "\n```\n",
                1,
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--human-limit",
            "2",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [item["id"] for item in payload["human_reference"]],
            ["human-high", "human-1"],
        )
        self.assertEqual(payload["human_reference"][0]["origin_confidence"], "high")
        self.assertEqual(payload["human_reference"][1]["origin_confidence"], "medium")

    def test_context_does_not_pad_an_exact_match_with_fallback_sources(self) -> None:
        fallback_path = "02-sources/fallback-human.md"
        (self.vault / fallback_path).write_text(
            "---\ntype: source\nsource_url: https://example.com/fallback\n---\n\n"
            "# Fallback source\n\n## Preserved Content\n\n"
            "这篇文章讨论社交活动，与英文技术说明的任务范围不同。\n",
            encoding="utf-8",
        )
        fallback = {
            "id": "human-fallback",
            "path": fallback_path,
            "role": "human-reference",
            "status": "confirmed",
            "authorship": "third-party",
            "approval": "curator-confirmed",
            "origin_claim": "attributed-human",
            "origin_confidence": "medium",
            "origin_basis": "named author and public article provenance",
            "language": "zh",
            "genre": "social-post",
            "audience": "general",
            "weight": 2.0,
            "author": "Fallback Author",
            "rights": "CC BY 4.0",
            "license_id": "CC-BY-4.0",
            "allowed_uses": ["private", "noncommercial", "commercial"],
        }
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        registry = registry_path.read_text(encoding="utf-8")
        registry_path.write_text(
            registry.replace(
                "\n```\n",
                "\n" + json.dumps(fallback, ensure_ascii=False) + "\n```\n",
                1,
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--intended-use",
            "commercial",
            "--human-limit",
            "2",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [item["id"] for item in json.loads(result.stdout)["human_reference"]],
            ["human-1"],
        )

    def test_context_excerpt_prefers_coherent_relevant_paragraphs(self) -> None:
        human_path = self.vault / "02-sources/human.md"
        human_path.write_text(
            "---\ntype: source\nsource_url: https://example.com/human\n---\n\n"
            "# Human source\n\n## Preserved Content\n\n"
            "This long opening discusses unrelated market history and organizational changes "
            "without mentioning the requested operating-system concept.\n\n"
            "File permissions protect data by assigning read, write, and execute access.\n\n"
            "The next paragraph gives a concrete permission example and explains its risk.\n\n"
            "A closing paragraph changes the subject to unrelated release planning.\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--intended-use",
            "commercial",
            "--query",
            "explain file permissions with an example and risk",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        excerpt = json.loads(result.stdout)["human_reference"][0]["excerpt"]
        self.assertIn("File permissions protect data", excerpt)
        self.assertIn("concrete permission example", excerpt)
        self.assertNotIn("unrelated market history", excerpt)

    def test_human_reference_excerpt_filters_accidental_promotional_style(self) -> None:
        human_path = self.vault / "02-sources/human.md"
        human_path.write_text(
            "---\ntype: source\nsource_url: https://example.com/human\n---\n\n"
            "# Human source\n\n## Preserved Content\n\n"
            "这个方案吊打同类产品，6 到飞起，一图胜千言。\n\n"
            "这篇文章先说明架构设计，再比较实现成本、适用边界和失败处理。\n\n"
            "下一段继续解释架构取舍，并把观察到的结果与推测原因分开。\n",
            encoding="utf-8",
        )
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        lines = registry_path.read_text(encoding="utf-8").splitlines()
        rewritten = []
        for line in lines:
            if line.startswith("{"):
                entry = json.loads(line)
                if entry.get("id") == "human-1":
                    entry["language"] = "zh"
                    entry["audience"] = "public"
                line = json.dumps(entry, ensure_ascii=False)
            rewritten.append(line)
        registry_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--intended-use",
            "commercial",
            "--query",
            "架构设计 成本 边界 结果 推测",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(result.stdout)["human_reference"][0]
        self.assertNotIn("吊打", item["excerpt"])
        self.assertEqual(item["excerpt_risk"], 0.0)
        self.assertEqual(item["excerpt_risk_flags"], [])
        self.assertIn("analysis-only", item["copy_policy"])

    def test_context_excerpt_prefers_requested_language_in_mixed_source(self) -> None:
        human_path = self.vault / "02-sources/human.md"
        human_path.write_text(
            "---\ntype: source\nsource_url: https://example.com/human\n---\n\n"
            "# Human source\n\n## Preserved Content\n\n"
            "Regional standards vary between writing systems and publishing contexts.\n\n"
            "地区差异不只是繁体与简体的差异，还包括具体地区采用的排版规则。\n\n"
            "地區差異不只是繁體與簡體的差異，還包括具體地區採用的排版規則。\n\n"
            "The following example describes an unrelated English implementation detail.\n\n"
            "下一段继续用中文说明规则的适用范围，并把例外放在对应规则附近。\n",
            encoding="utf-8",
        )
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        lines = registry_path.read_text(encoding="utf-8").splitlines()
        rewritten = []
        for line in lines:
            if line.startswith("{"):
                entry = json.loads(line)
                if entry.get("id") == "human-1":
                    entry["language"] = "mixed"
                line = json.dumps(entry, ensure_ascii=False)
            rewritten.append(line)
        registry_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--query",
            "地区差异 规则 例外",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        excerpt = json.loads(result.stdout)["human_reference"][0]["excerpt"]
        self.assertIn("地区差异", excerpt)
        self.assertIn("适用范围", excerpt)
        self.assertNotIn("地區差異", excerpt)
        self.assertNotIn("Regional standards", excerpt)
        self.assertNotIn("English implementation", excerpt)

    def test_context_excludes_human_reference_for_incompatible_use(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        lines = registry_path.read_text(encoding="utf-8").splitlines()
        rewritten = []
        for line in lines:
            if line.startswith("{"):
                entry = json.loads(line)
                if entry.get("id") == "human-1":
                    entry["license_id"] = "CC-BY-NC-4.0"
                    entry["allowed_uses"] = ["private", "noncommercial"]
                line = json.dumps(entry, ensure_ascii=False)
            rewritten.append(line)
        registry_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

        commercial = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--intended-use",
            "commercial",
        )
        self.assertEqual(commercial.returncode, 0, commercial.stderr)
        commercial_payload = json.loads(commercial.stdout)
        self.assertEqual(commercial_payload["human_reference"], [])
        self.assertEqual(
            commercial_payload["retrieval"]["human_reference"]["rights_excluded_ids"],
            ["human-1"],
        )

        unknown = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--intended-use",
            "unknown",
        )
        self.assertEqual(unknown.returncode, 0, unknown.stderr)
        self.assertEqual(json.loads(unknown.stdout)["human_reference"], [])

        noncommercial = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--intended-use",
            "noncommercial",
        )
        self.assertEqual(noncommercial.returncode, 0, noncommercial.stderr)
        self.assertEqual(
            [item["id"] for item in json.loads(noncommercial.stdout)["human_reference"]],
            ["human-1"],
        )

    def test_human_technique_tags_drive_retrieval_without_becoming_rules(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        lines = registry_path.read_text(encoding="utf-8").splitlines()
        technique_path = self.vault / "05-areas/writing-style/Human Technique Index.md"
        technique_record = {
            "kind": "human-technique",
            "id": "technique-human-1",
            "corpus_id": "human-1",
            "status": "confirmed",
            "approval": "curator-confirmed",
            "techniques": ["compare alternatives and explain tradeoffs"],
            "created": "2026-08-15",
        }
        technique_path.write_text(
            "# Human Technique Index\n\n```jsonl\n"
            + json.dumps(technique_record, ensure_ascii=False)
            + "\n```\n",
            encoding="utf-8",
        )
        invalid = self.run_cli("validate", "--vault", str(self.vault))
        self.assertNotEqual(invalid.returncode, 0)
        self.assertTrue(
            any(
                "technique_basis" in issue
                for issue in json.loads(invalid.stdout)["issues"]
            )
        )

        competing_path = "02-sources/human-competing.md"
        (self.vault / competing_path).write_text(
            "---\ntype: source\nsource_url: https://example.com/competing\n---\n\n"
            "# Competing source\n\n## Preserved Content\n\n"
            "This document describes routine deployment scheduling and release dates.\n",
            encoding="utf-8",
        )
        technique_record["technique_basis"] = (
            "curator inference from the preserved source; retrieval cue only"
        )
        technique_record["collection_id"] = "example-human-article"
        technique_path.write_text(
            "# Human Technique Index\n\n```jsonl\n"
            + json.dumps(technique_record, ensure_ascii=False)
            + "\n```\n",
            encoding="utf-8",
        )
        competitor = {
            "id": "human-competing",
            "path": competing_path,
            "role": "human-reference",
            "status": "confirmed",
            "authorship": "third-party",
            "approval": "curator-confirmed",
            "origin_claim": "attributed-human",
            "origin_confidence": "medium",
            "origin_basis": "named author and public article provenance",
            "language": "en",
            "genre": "technical-article",
            "audience": "technical-practitioner",
            "weight": 2.0,
            "author": "Another Example",
            "rights": "public-reference",
            "license_id": "CC-BY-4.0",
            "allowed_uses": ["private", "noncommercial", "commercial"],
        }
        closing = lines.index("```")
        lines.insert(closing, json.dumps(competitor, ensure_ascii=False))
        registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--intended-use",
            "commercial",
            "--query",
            "compare alternatives and explain tradeoffs",
            "--human-limit",
            "1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        selected = payload["human_reference"][0]
        self.assertEqual(selected["id"], "human-1")
        self.assertEqual(selected["technique_status"], "curator-inference")
        self.assertEqual(selected["technique_card_id"], "technique-human-1")
        self.assertEqual(
            selected["techniques"], ["compare alternatives and explain tradeoffs"]
        )
        self.assertIn(
            "Treat technique tags as curator retrieval cues, not rules or source claims.",
            payload["boundaries"],
        )

    def test_human_retrieval_diversifies_source_collections(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        entries = []
        technique_records = []
        specifications = (
            ("architecture-a", "architecture-book", "Author A", 2.0),
            ("architecture-b", "architecture-book", "Author A", 1.9),
            ("operations-a", "operations-book", "Author B", 0.5),
        )
        for entry_id, collection_id, author, weight in specifications:
            relative = f"02-sources/{entry_id}.md"
            (self.vault / relative).write_text(
                "---\ntype: source\n"
                f"source_url: https://example.com/{entry_id}\n---\n\n"
                "# Architecture source\n\n## Preserved Content\n\n"
                "Recovery decisions compare deployment alternatives and explain tradeoffs.\n",
                encoding="utf-8",
            )
            entries.append(
                {
                    "id": entry_id,
                    "path": relative,
                    "role": "human-reference",
                    "status": "confirmed",
                    "authorship": "third-party",
                    "approval": "curator-confirmed",
                    "origin_claim": "pre-generative-ai",
                    "origin_confidence": "high",
                    "origin_basis": "fixed pre-2022 source with named author",
                    "language": "en",
                    "genre": "architecture-case-study",
                    "audience": "technical-practitioner",
                    "weight": weight,
                    "author": author,
                    "rights": "CC BY 4.0",
                    "license_id": "CC-BY-4.0",
                    "allowed_uses": ["private", "noncommercial", "commercial"],
                }
            )
            technique_records.append(
                {
                    "kind": "human-technique",
                    "id": f"technique-{entry_id}",
                    "corpus_id": entry_id,
                    "status": "confirmed",
                    "approval": "curator-confirmed",
                    "collection_id": collection_id,
                    "techniques": ["compare alternatives and explain tradeoffs"],
                    "technique_basis": (
                        "curator inference from the preserved source; retrieval cue only"
                    ),
                    "created": "2026-08-15",
                }
            )
        registry = registry_path.read_text(encoding="utf-8")
        serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in entries)
        registry_path.write_text(
            registry.replace("\n```\n", f"\n{serialized}\n```\n", 1),
            encoding="utf-8",
        )
        technique_path = self.vault / "05-areas/writing-style/Human Technique Index.md"
        technique_path.write_text(
            "# Human Technique Index\n\n```jsonl\n"
            + "\n".join(
                json.dumps(item, ensure_ascii=False) for item in technique_records
            )
            + "\n```\n",
            encoding="utf-8",
        )

        result = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "en",
            "--genre",
            "architecture-case-study",
            "--audience",
            "technical-practitioner",
            "--intended-use",
            "commercial",
            "--query",
            "recovery deployment alternatives tradeoffs",
            "--human-limit",
            "2",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [item["id"] for item in payload["human_reference"]],
            ["architecture-a", "operations-a"],
        )
        self.assertEqual(
            payload["retrieval"]["human_reference"]["distinct_collections"], 2
        )
        self.assertGreater(
            payload["retrieval"]["human_reference"]["diversity_penalty"], 0
        )

    def test_curate_technique_card_requires_confirmation_and_is_idempotent(self) -> None:
        base_command = (
            "curate-technique-card",
            "--vault",
            str(self.vault),
            "--corpus-id",
            "human-1",
            "--collection-id",
            "example-human-article",
            "--technique",
            "先定义术语再使用",
            "--technique",
            "把例外放在对应规则附近",
            "--technique-basis",
            "curator inference from the preserved source; retrieval cue only",
        )
        preview = self.run_cli(*base_command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_payload = json.loads(preview.stdout)
        self.assertTrue(preview_payload["preview"])
        self.assertTrue(preview_payload["requires_curator_confirmation"])
        self.assertFalse(
            (self.vault / "05-areas/writing-style/Human Technique Index.md").exists()
        )

        unconfirmed = self.run_cli(*base_command, "--write")
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertIn("curator-confirmed", unconfirmed.stderr)

        written = self.run_cli(
            *base_command,
            "--curator-confirmed",
            "--write",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        written_payload = json.loads(written.stdout)
        self.assertTrue(written_payload["created"])
        self.assertTrue(
            (self.vault / "05-areas/writing-style/Human Technique Index.md").is_file()
        )

        repeated = self.run_cli(
            *base_command,
            "--curator-confirmed",
            "--write",
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertFalse(json.loads(repeated.stdout)["created"])

        candidate = list(base_command)
        candidate[candidate.index("human-1")] = "personal-candidate"
        rejected = self.run_cli(*candidate)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("confirmed human-reference", rejected.stderr)

    def test_promote_human_reference_requires_provenance_and_is_idempotent(self) -> None:
        source_path = "02-sources/new-human-reference.md"
        (self.vault / source_path).write_text(
            "---\ntype: source\nsource_url: https://example.com/new-human\n---\n\n"
            "# New human reference\n\n## Preserved Content\n\n"
            "A named author explains a concrete architecture decision and its tradeoffs.\n",
            encoding="utf-8",
        )
        base_command = (
            "promote-human-reference",
            "--vault",
            str(self.vault),
            "--path",
            source_path,
            "--author",
            "Example Author",
            "--language",
            "en",
            "--genre",
            "architecture-case-study",
            "--audience",
            "technical-practitioner",
            "--rights",
            "CC BY 4.0",
            "--license-id",
            "CC-BY-4.0",
            "--allowed-use",
            "private",
            "--allowed-use",
            "noncommercial",
            "--allowed-use",
            "commercial",
            "--origin-claim",
            "pre-generative-ai",
            "--origin-confidence",
            "high",
            "--origin-basis",
            "fixed pre-2022 source with named author and explicit license",
            "--notes",
            "Technique reference only; recheck architecture facts before reuse.",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--confirmation-note",
            "Curator reviewed the fixed source, author evidence, license, and technique scope.",
        )
        preview = self.run_cli(*base_command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_payload = json.loads(preview.stdout)
        self.assertTrue(preview_payload["preview"])
        self.assertTrue(preview_payload["requires_curator_confirmation"])
        self.assertFalse(
            any(
                json.loads(line).get("path") == source_path
                for line in (
                    self.vault
                    / "05-areas/writing-style/Corpus Registry.md"
                ).read_text(encoding="utf-8").splitlines()
                if line.startswith("{")
            )
        )

        unconfirmed = self.run_cli(*base_command, "--write")
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertIn("curator-confirmed", unconfirmed.stderr)

        written = self.run_cli(
            *base_command,
            "--curator-confirmed",
            "--write",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        self.assertEqual(payload["action"], "created")
        human_id = payload["record"]["id"]
        confirmation = self.vault / payload["confirmation"]
        self.assertTrue(confirmation.is_file())
        self.assertIn("provenance", confirmation.read_text(encoding="utf-8"))

        repeated = self.run_cli(
            *base_command,
            "--curator-confirmed",
            "--write",
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["action"], "unchanged")
        registry_text = (
            self.vault / "05-areas/writing-style/Corpus Registry.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(registry_text.count(human_id), 1)

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertEqual(json.loads(validate.stdout)["roles"]["human-reference"], 2)

    def test_promote_human_reference_rejects_local_source_url(self) -> None:
        source_path = "02-sources/local-human-reference.md"
        (self.vault / source_path).write_text(
            "---\ntype: source\nsource_url: file:///private/reference.md\n---\n\n"
            "# Local reference\n\n## Preserved Content\n\n"
            "A named author explains a concrete writing technique.\n",
            encoding="utf-8",
        )
        command = (
            "promote-human-reference",
            "--vault",
            str(self.vault),
            "--path",
            source_path,
            "--author",
            "Example Author",
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--rights",
            "private reference only",
            "--license-id",
            "private-reference-no-reuse",
            "--allowed-use",
            "private",
            "--origin-claim",
            "attributed-human",
            "--origin-confidence",
            "medium",
            "--origin-basis",
            "local file with an unverified author",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--confirmation-note",
            "Curator reviewed the local file.",
        )
        result = self.run_cli(*command)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("http(s)", result.stderr)

    def test_promote_human_reference_rejects_secret_source(self) -> None:
        source_path = "02-sources/secret-human-reference.md"
        (self.vault / source_path).write_text(
            "---\ntype: source\nsensitivity: secret\n"
            "source_url: https://example.com/secret-human\n---\n\n"
            "# Secret reference\n\n## Preserved Content\n\n"
            "This source must never enter writing-style retrieval.\n",
            encoding="utf-8",
        )
        command = (
            "promote-human-reference",
            "--vault",
            str(self.vault),
            "--path",
            source_path,
            "--author",
            "Example Author",
            "--language",
            "en",
            "--genre",
            "technical-article",
            "--audience",
            "technical-practitioner",
            "--rights",
            "private reference only",
            "--license-id",
            "private-reference-no-reuse",
            "--allowed-use",
            "private",
            "--origin-claim",
            "attributed-human",
            "--origin-confidence",
            "high",
            "--origin-basis",
            "secret source should be rejected before provenance review",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--confirmation-note",
            "Curator review must not override the secret boundary.",
        )
        result = self.run_cli(*command)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret sources", result.stderr)

    def test_validate_rejects_secret_registered_style_entry(self) -> None:
        source_path = "02-sources/secret-registered-style.md"
        (self.vault / source_path).write_text(
            "---\ntype: source\nsensitivity: secret\n"
            "source_url: https://example.com/secret-registered\n---\n\n"
            "# Secret registered style\n\nThis must not be retrieved.\n",
            encoding="utf-8",
        )
        entry = {
            "id": "secret-style-entry",
            "path": source_path,
            "role": "personal",
            "status": "candidate",
            "authorship": "mixed",
            "approval": "unreviewed",
            "origin_claim": "unknown",
            "origin_confidence": "low",
            "language": "zh",
            "genre": "technical-article",
            "audience": "public",
            "weight": 1.0,
        }
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        registry = registry_path.read_text(encoding="utf-8")
        registry_path.write_text(
            registry.replace(
                "\n```\n",
                "\n" + json.dumps(entry, ensure_ascii=False) + "\n```\n",
                1,
            ),
            encoding="utf-8",
        )
        result = self.run_cli("validate", "--vault", str(self.vault))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret documents cannot be registered", result.stdout)

    def test_catalog_preserves_registered_status_and_scans_external_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir)
            exact = external / "exact.md"
            exact.write_text(
                "---\nauthor: [\"SwimmingLiu\"]\npublished: 2021-01-01\n---\n\n"
                "# Exact sample\n\n这是一篇用于测试作者识别的完整文章，包含足够的自然语言内容。\n",
                encoding="utf-8",
            )
            mixed = external / "mixed.md"
            mixed.write_text(
                "---\nauthor: SwimmingLiu and Example\npublished: 2021-01-01\n---\n\n"
                "# Mixed sample\n\n这是一篇由多人共同整理的文章，不能直接认定为个人文风。\n",
                encoding="utf-8",
            )
            quoted = external / "quoted.md"
            quoted.write_text(
                "---\nauthor: [\"SwimmingLiu\"]\npublished: 2021-01-01\n---\n\n"
                "# Quoted sample\n\n"
                "> 这是一段很长的外部原文引用，用来测试引用占比足够高时不会被当成个人文风。\n"
                "> 外部原文继续展开，并且明显超过作者自己补充的少量说明。\n\n"
                "个人补充。\n",
                encoding="utf-8",
            )

            result = self.run_cli(
                "catalog",
                "--vault",
                str(self.vault),
                "--personal-author",
                "SwimmingLiu",
                "--external-root",
                str(external),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        by_path = {item["path"]: item for item in payload["candidates"]}
        self.assertEqual(by_path["02-sources/human.md"]["registered_id"], "human-1")
        self.assertEqual(by_path["02-sources/human.md"]["suggested_status"], "confirmed")
        self.assertEqual(by_path[str(exact.resolve())]["suggested_role"], "personal")
        self.assertEqual(by_path[str(exact.resolve())]["origin_claim"], "user-authored")
        self.assertEqual(by_path[str(mixed.resolve())]["suggested_role"], "unclassified")
        self.assertEqual(by_path[str(mixed.resolve())]["origin_claim"], "mixed")
        self.assertEqual(by_path[str(quoted.resolve())]["suggested_role"], "unclassified")
        self.assertEqual(by_path[str(quoted.resolve())]["origin_claim"], "mixed")
        self.assertGreaterEqual(by_path[str(quoted.resolve())]["blockquote_ratio"], 0.4)

    def test_review_candidates_is_metadata_only_and_never_changes_retrieval(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        original_registry = registry_path.read_text(encoding="utf-8")
        result = self.run_cli(
            "review-candidates",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["generation_eligible"])
        self.assertTrue(payload["review_gates"]["authorship_confirmation"])
        self.assertTrue(payload["review_gates"]["representativeness_confirmation"])
        self.assertEqual([item["id"] for item in payload["documents_detail"]], ["personal-candidate"])
        self.assertFalse(payload["recommendations"]["training_ready"])
        self.assertFalse(payload["recommendations"]["holdout_available"])
        self.assertEqual(payload["recommendations"]["training"], [])
        self.assertNotIn("尚未确认的个人草稿", result.stdout)
        self.assertEqual(registry_path.read_text(encoding="utf-8"), original_registry)

        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        personal_ids = {item["id"] for item in json.loads(context.stdout)["personal"]}
        self.assertIn("personal-0", personal_ids)
        self.assertNotIn("personal-candidate", personal_ids)

    def test_activation_plan_is_read_only_and_reports_remaining_gates(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        original_registry = registry_path.read_text(encoding="utf-8")
        result = self.run_cli(
            "activation-plan",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["activation"]["mode"], "shadow")
        self.assertFalse(payload["candidate_review"]["generation_eligible"])
        actions = {item["id"]: item for item in payload["next_actions"]}
        self.assertEqual(actions["personal-profile"]["status"], "complete")
        self.assertEqual(actions["personal-holdout"]["status"], "complete")
        self.assertEqual(actions["human-library"]["status"], "pending")
        self.assertEqual(actions["confirmed-feedback"]["status"], "pending")
        self.assertEqual(actions["rollout-evaluation"]["status"], "pending")
        self.assertNotIn("尚未确认的个人草稿", result.stdout)
        self.assertEqual(registry_path.read_text(encoding="utf-8"), original_registry)

    def test_candidate_recommendations_reserve_holdout_without_exposing_text(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        original_registry = registry_path.read_text(encoding="utf-8")
        entries = []
        for index, genre in enumerate(
            ("technical-article", "technical-documentation", "technical-project-note", "technical-tutorial")
        ):
            relative = f"06-output/drafts/review-candidate-{index}.md"
            text = (f"## 样本 {index}\n\n这是一篇由用户完成的候选文章，包含具体的技术说明。" * 100)
            (self.vault / relative).write_text(text, encoding="utf-8")
            entries.append(
                {
                    "id": f"review-candidate-{index}",
                    "path": relative,
                    "role": "personal",
                    "status": "candidate",
                    "authorship": "user",
                    "approval": "unreviewed",
                    "origin_claim": "user-authored",
                    "origin_confidence": "medium",
                    "language": "zh",
                    "genre": genre,
                    "audience": "public",
                    "weight": 1.0,
                }
            )
        json_block = "\n".join(json.dumps(item, ensure_ascii=False) for item in entries)
        registry_path.write_text(
            original_registry.replace("```\n", json_block + "\n```\n", 1), encoding="utf-8"
        )
        result = self.run_cli(
            "review-candidates",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        recommendations = payload["recommendations"]
        self.assertTrue(recommendations["training_ready"])
        self.assertTrue(recommendations["holdout_available"])
        self.assertEqual(len(recommendations["training"]), 3)
        self.assertIsNotNone(recommendations["holdout"])
        self.assertTrue(
            all(not item["generation_eligible"] for item in recommendations["training"])
        )
        self.assertNotIn("这是一篇由用户完成的候选文章", result.stdout)

    def test_user_confirmed_preference_is_persisted_and_retrieved(self) -> None:
        profile_path = self.vault / "05-areas/writing-style/Voice Profile.md"
        original = profile_path.read_text(encoding="utf-8")
        base_command = (
            "promote-preference",
            "--vault",
            str(self.vault),
            "--text",
            "先说明机制，再给出例子。",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--basis",
            "explicit-user-statement",
        )

        preview = self.run_cli(*base_command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertTrue(json.loads(preview.stdout)["requires_user_confirmation"])
        self.assertEqual(profile_path.read_text(encoding="utf-8"), original)

        unconfirmed = self.run_cli(*base_command, "--write")
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertEqual(profile_path.read_text(encoding="utf-8"), original)

        written = self.run_cli(*base_command, "--user-confirmed", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        self.assertTrue(payload["created"])
        preference_id = payload["record"]["id"]

        repeated = self.run_cli(*base_command, "--user-confirmed", "--write")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertFalse(json.loads(repeated.stdout)["created"])
        self.assertEqual(profile_path.read_text(encoding="utf-8").count(preference_id), 1)

        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        preferences = json.loads(context.stdout)["confirmed_preferences"]
        self.assertEqual([item["id"] for item in preferences], [preference_id])
        self.assertEqual(preferences[0]["match_quality"], "exact")

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertEqual(json.loads(validate.stdout)["confirmed_preferences"], 1)

    def test_promote_sample_requires_confirmation_and_is_idempotent(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        original_registry = registry_path.read_text(encoding="utf-8")
        base_command = (
            "promote-sample",
            "--vault",
            str(self.vault),
            "--path",
            "06-output/drafts/candidate.md",
            "--role",
            "personal",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--channel",
            "blog",
            "--purpose",
            "explain",
            "--weight",
            "1.5",
            "--author",
            "SwimmingLiu",
            "--rights",
            "owned",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--confirmation-note",
            "用户确认这篇文章由本人完成，并且仍然代表当前写作方式。",
        )

        preview = self.run_cli(*base_command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_payload = json.loads(preview.stdout)
        self.assertTrue(preview_payload["preview"])
        self.assertTrue(preview_payload["requires_authorship_confirmation"])
        self.assertTrue(preview_payload["requires_representativeness_confirmation"])
        self.assertEqual(preview_payload["action"], "updated")
        self.assertEqual(preview_payload["record"]["id"], "personal-candidate")
        self.assertEqual(registry_path.read_text(encoding="utf-8"), original_registry)
        self.assertFalse((self.vault / "08-journal/writing-sample-confirmations").exists())

        for flags in (
            ("--write",),
            ("--authorship-confirmed", "--write"),
            ("--representative-confirmed", "--write"),
        ):
            unconfirmed = self.run_cli(*base_command, *flags)
            self.assertNotEqual(unconfirmed.returncode, 0)
            self.assertIn("requires both", unconfirmed.stderr)
            self.assertEqual(registry_path.read_text(encoding="utf-8"), original_registry)

        written = self.run_cli(
            *base_command,
            "--authorship-confirmed",
            "--representative-confirmed",
            "--write",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        self.assertEqual(payload["action"], "updated")
        self.assertEqual(payload["record"]["status"], "confirmed")
        self.assertEqual(payload["record"]["authorship"], "user")
        self.assertEqual(payload["record"]["approval"], "user-confirmed")
        self.assertEqual(
            payload["record"]["confirmation_evidence"],
            "02-sources/user-confirmation.md",
        )

        registry_after_write = registry_path.read_text(encoding="utf-8")
        self.assertEqual(registry_after_write.count('"id": "personal-candidate"'), 1)
        confirmation_path = self.vault / payload["confirmation"]
        self.assertTrue(confirmation_path.is_file())
        confirmation = confirmation_path.read_text(encoding="utf-8")
        self.assertIn("type: journal", confirmation)
        self.assertIn("user-confirmation", confirmation)
        self.assertIn("both authorship and current representativeness", confirmation)

        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--personal-limit",
            "10",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        self.assertIn(
            "personal-candidate",
            {item["id"] for item in json.loads(context.stdout)["personal"]},
        )

        repeated = self.run_cli(
            *base_command,
            "--authorship-confirmed",
            "--representative-confirmed",
            "--write",
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["action"], "unchanged")
        self.assertEqual(registry_path.read_text(encoding="utf-8"), registry_after_write)
        index = (
            self.vault
            / "08-journal/writing-sample-confirmations/Sample Confirmations Index.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(index.count(confirmation_path.stem), 1)

    def test_promoted_holdout_is_never_returned_as_drafting_context(self) -> None:
        relative = "06-output/published/new-holdout.md"
        (self.vault / relative).write_text(
            "这是一篇独立完成的最终文章，只用于评估个人写作风格。",
            encoding="utf-8",
        )
        written = self.run_cli(
            "promote-sample",
            "--vault",
            str(self.vault),
            "--path",
            relative,
            "--role",
            "holdout",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--confirmation-note",
            "用户确认本人作者身份，并要求把这篇文章保留为盲测样本。",
            "--authorship-confirmed",
            "--representative-confirmed",
            "--write",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        holdout_id = json.loads(written.stdout)["record"]["id"]

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        profile = self.run_cli(
            "profile",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(profile.returncode, 0, profile.stderr)
        self.assertEqual(json.loads(profile.stdout)["documents"], 3)
        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--personal-limit",
            "20",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        self.assertNotIn(
            holdout_id,
            {item["id"] for item in json.loads(context.stdout)["personal"]},
        )

    def test_promote_negative_requires_confirmation_and_is_retrieved_as_contrast(self) -> None:
        relative = "06-output/drafts/rejected-style.md"
        (self.vault / relative).write_text(
            "这是一段用户明确拒绝的空泛表达，不应当作为正向个人声音样本。",
            encoding="utf-8",
        )
        base_command = (
            "promote-negative",
            "--vault",
            str(self.vault),
            "--path",
            relative,
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--evidence",
            "02-sources/user-confirmation.md",
            "--reason",
            "用户确认这段表达空泛，不应继续生成类似句子。",
        )

        preview = self.run_cli(*base_command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_payload = json.loads(preview.stdout)
        self.assertTrue(preview_payload["preview"])
        self.assertTrue(preview_payload["requires_reviewer_confirmation"])
        self.assertEqual(preview_payload["record"]["status"], "rejected")
        self.assertFalse((self.vault / "08-journal/writing-negative-confirmations").exists())

        unconfirmed = self.run_cli(*base_command, "--write")
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertIn("reviewer-confirmed", unconfirmed.stderr)

        written = self.run_cli(*base_command, "--reviewer-confirmed", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        negative_id = payload["record"]["id"]
        self.assertEqual(payload["record"]["role"], "negative")
        self.assertEqual(payload["record"]["approval"], "user-confirmed")
        self.assertTrue((self.vault / payload["confirmation"]).is_file())

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--negative-limit",
            "10",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        self.assertIn(
            negative_id,
            {item["id"] for item in json.loads(context.stdout)["negative"]},
        )

        repeated = self.run_cli(*base_command, "--reviewer-confirmed", "--write")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["action"], "unchanged")

    def test_feedback_requires_explicit_write_and_aggregates_three_events(self) -> None:
        before = self.vault / "06-output/drafts/before.md"
        after = self.vault / "06-output/published/after.md"
        before.write_text(
            "这个系统非常强大，它不仅能够全面赋能团队，而且能够在不断演变的技术格局中"
            "发挥至关重要的作用，从而确保每一位成员都可以更加高效地完成自己的工作。",
            encoding="utf-8",
        )
        after.write_text("系统支持批量处理。团队可以减少重复操作。", encoding="utf-8")

        preview = self.run_cli(
            "feedback",
            "--vault",
            str(self.vault),
            "--before",
            str(before.relative_to(self.vault)),
            "--after",
            str(after.relative_to(self.vault)),
            "--verdict",
            "revised",
            "--task-id",
            "preview",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("## Change pairs", preview.stdout)
        self.assertFalse((self.vault / "08-journal/writing-feedback").exists())

        unconfirmed = self.run_cli(
            "feedback",
            "--vault",
            str(self.vault),
            "--before",
            str(before.relative_to(self.vault)),
            "--after",
            str(after.relative_to(self.vault)),
            "--verdict",
            "revised",
            "--task-id",
            "unconfirmed",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--write",
        )
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertFalse((self.vault / "08-journal/writing-feedback").exists())

        for index in range(3):
            written = self.run_cli(
                "feedback",
                "--vault",
                str(self.vault),
                "--before",
                str(before.relative_to(self.vault)),
                "--after",
                str(after.relative_to(self.vault)),
                "--verdict",
                "revised",
                "--task-id",
                f"task-{index}",
                "--language",
                "zh",
                "--genre",
                "technical-article",
                "--audience",
                "public",
                "--preference",
                "用具体功能替代空泛价值判断",
                "--reviewer-confirmed",
                "--write",
            )
            self.assertEqual(written.returncode, 0, written.stderr)

        candidates = self.run_cli(
            "feedback-candidates", "--vault", str(self.vault), "--min-count", "3"
        )
        self.assertEqual(candidates.returncode, 0, candidates.stderr)
        payload = json.loads(candidates.stdout)
        self.assertEqual(len(payload["edit_pairs"]), 1)
        self.assertEqual(payload["edit_pairs"][0]["events"], 3)
        self.assertEqual(len(payload["edit_pairs"][0]["evidence"]), 3)
        self.assertEqual(len(payload["preferences"]), 1)
        self.assertEqual(payload["preferences"][0]["events"], 3)
        self.assertEqual(len(payload["preferences"][0]["evidence"]), 3)
        self.assertGreaterEqual(len(payload["style_signals"]), 1)
        self.assertEqual(
            payload["style_signals"][0]["scope"],
            {
                "language": "zh",
                "genre": "technical-article",
                "audience": "public",
            },
        )
        self.assertEqual(len(payload["style_signals"][0]["evidence"]), 3)

        unconfirmed_path = "08-journal/writing-feedback/unconfirmed-manual.md"
        (self.vault / unconfirmed_path).write_text(
            "---\ntype: journal\nstatus: verified\nreviewer: user\n"
            "reviewer_confirmed: false\n---\n\nUnconfirmed edit.\n",
            encoding="utf-8",
        )
        untrusted_promotion = [
            "promote-preference",
            "--vault",
            str(self.vault),
            "--text",
            "这条偏好包含未确认的反馈。",
            "--basis",
            "repeated-feedback",
            "--evidence",
            payload["preferences"][0]["evidence"][0],
            "--evidence",
            payload["preferences"][0]["evidence"][1],
            "--evidence",
            unconfirmed_path,
        ]
        rejected = self.run_cli(*untrusted_promotion)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("verified user-confirmed", rejected.stderr)

        promote_args = [
            "promote-preference",
            "--vault",
            str(self.vault),
            "--text",
            "用具体功能替代空泛价值判断",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--basis",
            "repeated-feedback",
        ]
        for evidence in payload["preferences"][0]["evidence"]:
            promote_args.extend(("--evidence", evidence))
        promoted = self.run_cli(*promote_args, "--user-confirmed", "--write")
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        self.assertTrue(json.loads(promoted.stdout)["created"])

        context = self.run_cli(
            "context",
            "--vault",
            str(self.vault),
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertEqual(context.returncode, 0, context.stderr)
        self.assertEqual(
            json.loads(context.stdout)["confirmed_preferences"][0]["text"],
            "用具体功能替代空泛价值判断",
        )

    def test_feedback_rejects_secret_documents_before_persisting_diff(self) -> None:
        before = self.vault / "06-output/drafts/secret-before.md"
        after = self.vault / "06-output/published/secret-after.md"
        before.write_text(
            "---\ntype: draft\nsensitivity: secret\n---\n\n"
            "这段内容不能进入反馈日志。\n",
            encoding="utf-8",
        )
        after.write_text("公开稿。\n", encoding="utf-8")
        result = self.run_cli(
            "feedback",
            "--vault",
            str(self.vault),
            "--before",
            str(before.relative_to(self.vault)),
            "--after",
            str(after.relative_to(self.vault)),
            "--verdict",
            "revised",
            "--task-id",
            "secret-feedback",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret documents", result.stderr)
        self.assertFalse((self.vault / "08-journal/writing-feedback").exists())

    def test_rollout_preview_requires_confirmation_and_is_idempotent(self) -> None:
        paths = self.rollout_evidence()
        command = self.rollout_command(paths)
        directory = self.vault / "08-journal/writing-rollout-evaluations"

        preview = self.run_cli(*command)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_payload = json.loads(preview.stdout)
        self.assertTrue(preview_payload["preview"])
        self.assertTrue(preview_payload["requires_reviewer_confirmation"])
        self.assertTrue(preview_payload["record"]["passed"])
        self.assertFalse(preview_payload["record"]["qualifies_for_activation"])
        self.assertFalse(directory.exists())

        unconfirmed = self.run_cli(*command, "--write")
        self.assertNotEqual(unconfirmed.returncode, 0)
        self.assertIn("reviewer-confirmed", unconfirmed.stderr)
        self.assertFalse(directory.exists())

        written = self.run_cli(*command, "--reviewer-confirmed", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        self.assertTrue(payload["created"])
        self.assertTrue(payload["record"]["passed"])
        self.assertTrue(payload["record"]["qualifies_for_activation"])
        evaluation_path = self.vault / payload["path"]
        self.assertTrue(evaluation_path.is_file())
        self.assertIn("status: verified", evaluation_path.read_text(encoding="utf-8"))

        repeated = self.run_cli(*command, "--reviewer-confirmed", "--write")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertFalse(json.loads(repeated.stdout)["created"])
        index = (directory / "Rollout Evaluations Index.md").read_text(encoding="utf-8")
        self.assertEqual(index.count(evaluation_path.stem), 1)

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        readiness = json.loads(validate.stdout)["readiness"]
        self.assertEqual(readiness["rollout_evaluation"]["records"], 1)
        self.assertEqual(readiness["rollout_evaluation"]["qualifying"], 1)
        self.assertEqual(readiness["activation"]["mode"], "shadow")
        self.assertFalse(readiness["human_reference"]["library_ready"])
        self.assertFalse(readiness["feedback"]["observed"])

    def test_rollout_final_must_be_a_confirmed_holdout(self) -> None:
        paths = self.rollout_evidence("not-holdout")
        paths["final"] = "06-output/published/personal-0.md"
        result = self.run_cli(*self.rollout_command(paths, task_id="not-holdout"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("confirmed holdout", result.stderr)
        self.assertFalse(
            (self.vault / "08-journal/writing-rollout-evaluations").exists()
        )

    def test_failed_rollout_is_recorded_but_never_qualifies(self) -> None:
        paths = self.rollout_evidence("failed")
        command = self.rollout_command(
            paths,
            task_id="failed-rollout",
            candidate_factual_errors=1,
        )
        written = self.run_cli(*command, "--reviewer-confirmed", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        record = json.loads(written.stdout)["record"]
        self.assertFalse(record["passed"])
        self.assertFalse(record["qualifies_for_activation"])

        curator_paths = self.rollout_evidence("curator")
        curator = self.run_cli(
            *self.rollout_command(
                curator_paths,
                task_id="curator-rollout",
                reviewer="curator",
            ),
            "--reviewer-confirmed",
            "--write",
        )
        self.assertEqual(curator.returncode, 0, curator.stderr)
        curator_record = json.loads(curator.stdout)["record"]
        self.assertTrue(curator_record["passed"])
        self.assertFalse(curator_record["qualifies_for_activation"])

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        evaluation = json.loads(validate.stdout)["readiness"]["rollout_evaluation"]
        self.assertEqual(evaluation["records"], 2)
        self.assertEqual(evaluation["qualifying"], 0)

    def test_validate_rejects_tampered_rollout_metrics(self) -> None:
        paths = self.rollout_evidence("tampered")
        command = self.rollout_command(paths, task_id="tampered-rollout")
        written = self.run_cli(*command, "--reviewer-confirmed", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        payload = json.loads(written.stdout)
        evaluation_path = self.vault / payload["path"]
        ratio = payload["record"]["candidate_edit_ratio"]
        text = evaluation_path.read_text(encoding="utf-8")
        text = text.replace(
            f'"candidate_edit_ratio": {ratio}',
            '"candidate_edit_ratio": 0.9999',
            1,
        )
        evaluation_path.write_text(text, encoding="utf-8")

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertNotEqual(validate.returncode, 0)
        issues = json.loads(validate.stdout)["issues"]
        self.assertTrue(any("candidate_edit_ratio" in issue for issue in issues))

    def test_activation_requires_every_evidence_gate(self) -> None:
        self.add_ready_human_library()
        paths = self.rollout_evidence("activation")

        before_feedback = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(before_feedback.returncode, 0, before_feedback.stderr)
        before_readiness = json.loads(before_feedback.stdout)["readiness"]
        self.assertTrue(before_readiness["human_reference"]["library_ready"])
        self.assertFalse(before_readiness["feedback"]["observed"])
        self.assertFalse(before_readiness["rollout_evaluation"]["observed"])
        self.assertEqual(before_readiness["activation"]["mode"], "shadow")

        feedback = self.run_cli(
            "feedback",
            "--vault",
            str(self.vault),
            "--before",
            paths["baseline"],
            "--after",
            paths["candidate"],
            "--verdict",
            "revised",
            "--task-id",
            "activation-feedback",
            "--language",
            "zh",
            "--genre",
            "technical-article",
            "--audience",
            "public",
            "--reviewer-confirmed",
            "--write",
        )
        self.assertEqual(feedback.returncode, 0, feedback.stderr)

        before_evaluation = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(before_evaluation.returncode, 0, before_evaluation.stderr)
        readiness = json.loads(before_evaluation.stdout)["readiness"]
        self.assertTrue(readiness["feedback"]["observed"])
        self.assertEqual(readiness["activation"]["mode"], "shadow")

        evaluation = self.run_cli(
            *self.rollout_command(paths, task_id="activation-rollout"),
            "--reviewer-confirmed",
            "--write",
        )
        self.assertEqual(evaluation.returncode, 0, evaluation.stderr)

        activated = self.run_cli("validate", "--vault", str(self.vault))
        self.assertEqual(activated.returncode, 0, activated.stderr)
        activated_readiness = json.loads(activated.stdout)["readiness"]
        self.assertTrue(activated_readiness["activation"]["ready"])
        self.assertEqual(activated_readiness["activation"]["mode"], "active")

    def test_validate_rejects_unproven_confirmed_human_reference(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        registry = registry_path.read_text(encoding="utf-8")
        registry = registry.replace('"origin_confidence": "medium"', '"origin_confidence": "low"')
        registry_path.write_text(registry, encoding="utf-8")

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertNotEqual(validate.returncode, 0)
        issues = json.loads(validate.stdout)["issues"]
        self.assertTrue(any("confirmed human-reference" in issue for issue in issues))

    def test_validate_rejects_noncommercial_license_marked_commercial(self) -> None:
        registry_path = self.vault / "05-areas/writing-style/Corpus Registry.md"
        registry = registry_path.read_text(encoding="utf-8")
        registry = registry.replace('"license_id": "CC-BY-4.0"', '"license_id": "CC-BY-NC-4.0"')
        registry_path.write_text(registry, encoding="utf-8")

        validate = self.run_cli("validate", "--vault", str(self.vault))
        self.assertNotEqual(validate.returncode, 0)
        issues = json.loads(validate.stdout)["issues"]
        self.assertTrue(any("noncommercial license" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
