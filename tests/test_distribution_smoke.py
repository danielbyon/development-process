from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_skill_distribution import (
    POLICY_REVISION,
    ROOT,
    SKILL_NAMES,
    source_checkout,
)


def python_environment() -> dict[str, str]:
    python_paths = [str(ROOT)]
    inherited_python_path = os.environ.get("PYTHONPATH")
    if inherited_python_path:
        python_paths.append(inherited_python_path)
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(python_paths),
    }


class DistributionSmokeTests(unittest.TestCase):
    def test_cli_packages_verifies_and_stages_all_skills_in_temp_codex_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-distribution-smoke-") as directory:
            temp_root = Path(directory)
            source_root, source_revision = source_checkout(temp_root)
            package_dir = temp_root / "packages"
            staging_root = temp_root / "codex-staging"
            staging_root.mkdir()
            cli = ROOT / "scripts" / "skill_distribution.py"
            subprocess.run(
                [
                    "python3", str(cli), "init-staging",
                    "--root", str(source_root),
                    "--staging-root", str(staging_root),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env=python_environment(),
            )
            unrelated = staging_root / ".agents" / "skills" / "unrelated"
            unrelated.mkdir(parents=True)
            sentinel = unrelated / "SKILL.md"
            sentinel.write_text("keep\n")

            commands = [
                [
                    "python3", str(cli), "validate",
                    "--root", str(source_root),
                ],
                [
                    "python3", str(cli), "package",
                    "--root", str(source_root),
                    "--output-dir", str(package_dir),
                    "--source-revision", source_revision,
                ],
                [
                    "python3", str(cli), "verify",
                    "--root", str(source_root),
                    "--artifact-dir", str(package_dir),
                    "--source-revision", source_revision,
                ],
            ]
            for command in commands:
                subprocess.run(
                    command,
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=python_environment(),
                )

            for skill_name in SKILL_NAMES:
                archive = package_dir / f"{skill_name}.zip"
                staged = subprocess.run(
                    [
                        "python3", str(cli), "stage",
                        "--root", str(source_root),
                        "--archive", str(archive),
                        "--staging-root", str(staging_root),
                        "--policy-revision", POLICY_REVISION,
                    ],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=python_environment(),
                )
                self.assertIn("installed", staged.stdout)
                staged_skill = staging_root / ".agents" / "skills" / skill_name
                self.assertTrue((staged_skill / "SKILL.md").is_file())
                self.assertTrue((staged_skill / "agents" / "openai.yaml").is_file())
                self.assertEqual(sentinel.read_text(), "keep\n")

            for skill_name in SKILL_NAMES:
                archive = package_dir / f"{skill_name}.zip"
                repeat = subprocess.run(
                    [
                        "python3", str(cli), "stage",
                        "--root", str(source_root),
                        "--archive", str(archive),
                        "--staging-root", str(staging_root),
                        "--policy-revision", POLICY_REVISION,
                    ],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    env=python_environment(),
                )
                self.assertIn("unchanged", repeat.stdout)
            self.assertEqual(sentinel.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main()
