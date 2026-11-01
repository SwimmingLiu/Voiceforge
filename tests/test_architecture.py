from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PACKAGE = SCRIPTS / "_voiceforge"


class ArchitectureTests(unittest.TestCase):
    def test_internal_imports_follow_ownership_direction(self) -> None:
        allowed = {
            "__init__": set(),
            "memory_text": set(),
            "evidence": {"memory_text"},
            "memory": {"evidence", "memory_text"},
            "memory_cli": {"memory", "evidence", "memory_text"},
            "lint": set(),
            "lint_cli": {"lint"},
        }
        self.assertTrue(PACKAGE.is_dir(), "The executable scripts require the internal package.")
        for path in PACKAGE.glob("*.py"):
            with self.subTest(module=path.stem):
                self.assertIn(path.stem, allowed)
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                dependencies: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse(any(alias.name == "*" for alias in node.names), "Wildcard imports hide ownership.")
                        if node.level:
                            if node.module:
                                dependencies.add(node.module.split(".")[0])
                            else:
                                dependencies.update(alias.name.split(".")[0] for alias in node.names)
                        elif node.module and node.module.startswith("_voiceforge."):
                            dependencies.add(node.module.split(".")[1])
                        elif node.module == "_voiceforge":
                            dependencies.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.Import):
                        dependencies.update(
                            alias.name.split(".")[1]
                            for alias in node.names
                            if alias.name.startswith("_voiceforge.")
                        )
                self.assertLessEqual(dependencies, allowed[path.stem])

    def test_executable_adapters_only_enter_their_cli(self) -> None:
        for name, cli in (("voice_memory.py", "memory_cli"), ("tone_lint.py", "lint_cli")):
            with self.subTest(script=name):
                tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
                imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
                self.assertEqual([(node.module, [alias.name for alias in node.names]) for node in imports], [(f"_voiceforge.{cli}", ["main"])])
                self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in ast.walk(tree)))

    def test_workspace_file_writes_belong_to_evidence(self) -> None:
        file_mutators = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "touch", "rename"}
        violations: list[str] = []
        for path in SCRIPTS.rglob("*.py"):
            if path == PACKAGE / "evidence.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr in file_mutators:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.func.attr}")
                if (isinstance(node.func, ast.Name) and node.func.id == "open") or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "open"
                ):
                    modes = [keyword.value for keyword in node.keywords if keyword.arg == "mode"]
                    if isinstance(node.func, ast.Name) and len(node.args) > 1:
                        modes.append(node.args[1])
                    elif isinstance(node.func, ast.Attribute) and node.args:
                        modes.append(node.args[0])
                    if any(isinstance(mode, ast.Constant) and isinstance(mode.value, str) and set(mode.value) & set("wax+") for mode in modes):
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: writable open")
        self.assertEqual(violations, [], "Workspace writes outside their owner: " + ", ".join(violations))

    def test_copied_scripts_run_from_an_unrelated_directory_without_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            copied = temporary / "bundle" / "scripts"
            shutil.copytree(SCRIPTS, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            caller = temporary / "caller"
            caller.mkdir()
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            lint = subprocess.run(
                [sys.executable, str(copied / "tone_lint.py"), "--format", "json", "-"],
                input="Read the file.\n",
                cwd=caller,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            self.assertEqual(json.loads(lint.stdout)["files"][0]["diagnostics"], [])
            workspace = temporary / "style"
            for command in ("init", "validate"):
                result = subprocess.run(
                    [sys.executable, str(copied / "voice_memory.py"), command, "--workspace", str(workspace)],
                    cwd=caller,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                if command == "validate":
                    self.assertTrue(report["healthy"])


if __name__ == "__main__":
    unittest.main()
