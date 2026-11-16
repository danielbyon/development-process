from __future__ import annotations

import copy
import io
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import scripts.skill_distribution as distribution_module
from scripts.skill_distribution import (
    DistributionError,
    build_packages,
    install_archive,
    resolve_task_policy,
    initialize_staging_root,
    main,
    validate_distribution,
    verify_packages,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_REVISION = "e2afa055d1126763c69f0e0392d25b86bab98014"
HISTORICAL_POLICY_REVISION = "93a86127a3721d6044f4a8e993a764731fbda4e5"
HISTORICAL_POLICY_REVISIONS = (
    "aa8dc7784641dd5416befdebc246ed081bfd7ade",
    HISTORICAL_POLICY_REVISION,
    "142422527de28b8e20dea1158d2f54d020dcdcd5",
    "9da7c0b9113da4c0aab172860bdc5d5c77cccf0d",
    "6fea1f50e0745c189685849f560f10a946e04091",
)
SKILL_NAMES = (
    "development-orchestrator",
    "development-review",
    "delegation-executor",
)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def source_checkout(parent: Path) -> tuple[Path, str]:
    """Create a disposable committed source tree based on the approved policy."""
    checkout = parent / "source"
    git(ROOT, "clone", "--quiet", "--shared", str(ROOT), str(checkout))
    git(checkout, "checkout", "--quiet", "--detach", POLICY_REVISION)

    # Keep legacy sources independent of the current release templates.
    git(checkout, "checkout", "e47c8882e590c3ec41d2d46f461d18ed73132534", "--", "skills")
    shutil.copytree(
        ROOT / "scripts" / "vendor",
        checkout / "scripts" / "vendor",
        dirs_exist_ok=True,
    )
    git(checkout, "add", "skills", "scripts/vendor")
    git(checkout, "-c", "user.name=Skill Distribution Test", "-c",
        "user.email=skill-distribution-test@example.invalid", "commit", "--quiet",
        "--allow-empty",
        "-m", "Test fixture source")
    return checkout, git(checkout, "rev-parse", "HEAD")


class SkillDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="skill-distribution-")
        self.addCleanup(self.temporary.cleanup)
        self.temp_root = Path(self.temporary.name)
        self.source_root, self.source_revision = source_checkout(self.temp_root)
        self.artifacts = self.temp_root / "packages"

    def test_manifest_validates_three_standalone_skills(self) -> None:
        self.assertEqual(
            set(validate_distribution(self.source_root)),
            set(SKILL_NAMES),
        )

    def test_manifest_rejects_invalid_distribution_shapes(self) -> None:
        manifest_path = self.source_root / "skills" / "distribution.json"
        original = json.loads(manifest_path.read_text())
        cases = [
            ("unsupported schema", lambda value: value.update(schema_version=2)),
            ("skills must be a list", lambda value: value.update(skills="invalid")),
            ("entry must be an object", lambda value: value["skills"].__setitem__(0, "invalid")),
            ("duplicate Skill", lambda value: value["skills"][1].update(name=value["skills"][0]["name"])),
            ("unsafe source path", lambda value: value["skills"][0].update(source_dir="../escape")),
            ("wrong source directory", lambda value: value["skills"][0].update(source_dir="skills/other")),
            ("files must be a list", lambda value: value["skills"][0].update(files="SKILL.md")),
            ("file path must be a string", lambda value: value["skills"][0]["files"].append(None)),
            ("empty file path", lambda value: value["skills"][0]["files"].append("")),
            ("absolute file path", lambda value: value["skills"][0]["files"].append("/outside")),
            ("backslash file path", lambda value: value["skills"][0]["files"].append("agents\\openai.yaml")),
            ("duplicate file", lambda value: value["skills"][0]["files"].append("SKILL.md")),
            ("required file omitted", lambda value: value["skills"][0].update(files=["SKILL.md"])),
            ("test file included", lambda value: value["skills"][0]["files"].append("tests/scenarios.md")),
            ("Skill omitted", lambda value: value["skills"].pop()),
        ]

        for label, mutate in cases:
            with self.subTest(case=label):
                manifest = copy.deepcopy(original)
                mutate(manifest)
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)

    def test_manifest_must_be_valid_json_object(self) -> None:
        manifest_path = self.source_root / "skills" / "distribution.json"
        for invalid_content in ("{", "[]"):
            with self.subTest(content=invalid_content):
                manifest_path.write_text(invalid_content)
                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)

    def test_skill_frontmatter_and_local_links_fail_closed(self) -> None:
        skill_path = self.source_root / "skills" / SKILL_NAMES[0] / "SKILL.md"
        original = skill_path.read_text()
        invalid_frontmatter = [
            "plain text without frontmatter\n",
            "---\nname: example\ndescription: missing close\n",
            "---\nname: [unterminated\n---\n",
            "---\n- a sequence\n---\n",
            "---\nname: other-skill\ndescription: valid\n---\n",
            f"---\nname: {SKILL_NAMES[0]}\ndescription: '   '\n---\n",
        ]
        for content in invalid_frontmatter:
            with self.subTest(frontmatter=content[:30]):
                skill_path.write_text(content)
                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)

        skill_path.write_bytes(b"\xff\xfe")
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

        for destination in ("../outside.md", "missing-resource.md"):
            with self.subTest(destination=destination):
                skill_path.write_text(original + f"\n[resource]({destination})\n")
                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)

        skill_path.write_text(original)

    def test_escaped_links_are_ignored_and_image_resources_are_checked(self) -> None:
        skill_path = self.source_root / "skills" / SKILL_NAMES[0] / "SKILL.md"
        original = skill_path.read_text()
        escaped_link = "\\" + "[literal](missing-resource.md)"
        skill_path.write_text(original + f"\n{escaped_link}\n")
        self.assertEqual(set(validate_distribution(self.source_root)), set(SKILL_NAMES))

        skill_path.write_text(original + "\n![image](missing-image.png)\n")
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

        even_backslashes = "\\\\" + "[link](missing-resource.md)"
        skill_path.write_text(original + f"\n{even_backslashes}\n")
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

    def test_skill_policy_link_and_included_local_resource_are_validated(self) -> None:
        skill_dir = self.source_root / "skills" / SKILL_NAMES[0]
        skill_path = skill_dir / "SKILL.md"
        original_skill = skill_path.read_text()
        policy_url = (
            "https://github.com/danielbyon/development-process/blob/"
            f"{POLICY_REVISION}/docs/PROCESS.md"
        )
        skill_path.write_text(original_skill.replace(policy_url, "https://example.com/policy"))
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

        resource = skill_dir / "reference.md"
        resource.write_text("Included local reference.\n")
        manifest_path = self.source_root / "skills" / "distribution.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["skills"][0]["files"].append("reference.md")
        manifest_path.write_text(json.dumps(manifest))
        skill_path.write_text(original_skill + "\n[reference](reference.md)\n")
        self.assertIn(SKILL_NAMES[0], validate_distribution(self.source_root))

    def test_immutable_github_links_resolve_from_local_git_objects(self) -> None:
        """Check shipped Skill links against local commits without network access."""
        immutable_link = re.compile(
            r"https://github\.com/danielbyon/development-process/blob/"
            r"([0-9a-f]{40})/([^\s?#)]+)"
        )
        checked_links = 0

        for skill_name in SKILL_NAMES:
            skill_path = self.source_root / "skills" / skill_name / "SKILL.md"
            for revision, path in immutable_link.findall(skill_path.read_text()):
                revision_type = subprocess.run(
                    ["git", "cat-file", "-t", revision],
                    cwd=self.source_root,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    revision_type.stdout.strip(),
                    "commit",
                    f"{skill_path.relative_to(self.source_root)} uses a missing or "
                    f"non-commit revision {revision}: {revision_type.stderr.strip()}",
                )
                target_type = subprocess.run(
                    ["git", "cat-file", "-t", f"{revision}:{path}"],
                    cwd=self.source_root,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    target_type.stdout.strip(),
                    "blob",
                    f"{skill_path.relative_to(self.source_root)} points to "
                    f"{revision}:{path}, whose object type is "
                    f"{target_type.stdout.strip() or 'missing'}: "
                    f"{target_type.stderr.strip()}",
                )
                checked_links += 1

        self.assertGreater(checked_links, 0, "No immutable repository links were checked")

    def test_official_validator_rejection_and_missing_copy_are_reported(self) -> None:
        skill_path = self.source_root / "skills" / SKILL_NAMES[0] / "SKILL.md"
        original_skill = skill_path.read_text()
        skill_path.write_text(original_skill + "\n[TODO: remove this placeholder]\n")
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

        skill_path.write_text(original_skill)
        validator = self.source_root / "scripts" / "vendor" / "quick_validate.py"
        original_validator = validator.read_bytes()
        validator.unlink()
        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)
        validator.write_bytes(original_validator)

    def test_invalid_skill_metadata_is_rejected(self) -> None:
        metadata_path = (
            self.source_root
            / "skills"
            / SKILL_NAMES[0]
            / "agents"
            / "openai.yaml"
        )
        original = metadata_path.read_text()
        for content in ("interface: [invalid\n", "{}\n"):
            with self.subTest(metadata=content):
                metadata_path.write_text(content)
                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)
        metadata_path.write_text(original)

    def test_missing_symlinked_and_non_file_skill_sources_are_refused(self) -> None:
        skill_dir = self.source_root / "skills" / SKILL_NAMES[0]
        metadata_path = skill_dir / "agents" / "openai.yaml"
        original = metadata_path.read_bytes()
        in_repo_target = self.source_root / "skills" / SKILL_NAMES[1] / "agents" / "openai.yaml"
        outside_target = self.temp_root / "outside-openai.yaml"
        outside_target.write_bytes(original)

        for kind in ("missing", "symlink-inside", "symlink-outside", "directory"):
            with self.subTest(kind=kind):
                if kind == "missing":
                    metadata_path.unlink()
                elif kind == "symlink-inside":
                    metadata_path.unlink()
                    metadata_path.symlink_to(in_repo_target)
                elif kind == "symlink-outside":
                    metadata_path.unlink()
                    metadata_path.symlink_to(outside_target)
                else:
                    metadata_path.unlink()
                    metadata_path.mkdir()

                with self.assertRaises(DistributionError):
                    validate_distribution(self.source_root)

                if metadata_path.is_symlink() or metadata_path.is_file():
                    metadata_path.unlink()
                elif metadata_path.is_dir():
                    metadata_path.rmdir()
                metadata_path.write_bytes(original)

    def test_skill_source_directory_symlink_is_refused(self) -> None:
        skill_dir = self.source_root / "skills" / SKILL_NAMES[0]
        backup = self.temp_root / "original-skill"
        other_skill = self.source_root / "skills" / SKILL_NAMES[1]
        skill_dir.rename(backup)
        skill_dir.symlink_to(other_skill, target_is_directory=True)

        with self.assertRaises(DistributionError):
            validate_distribution(self.source_root)

        skill_dir.unlink()
        backup.rename(skill_dir)

    def test_archives_are_deterministic_separate_and_provenanced(self) -> None:
        first = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )
        second_dir = self.temp_root / "repeated-packages"
        second = build_packages(
            self.source_root, second_dir, self.source_revision
        )

        self.assertEqual({path.stem for path in first}, set(SKILL_NAMES))
        for left in first:
            right = second_dir / left.name
            self.assertEqual(left.read_bytes(), right.read_bytes())
            provenance_path = left.with_suffix(".provenance.json")
            provenance = json.loads(provenance_path.read_text())
            self.assertEqual(provenance["policy_revision"], POLICY_REVISION)
            self.assertEqual(provenance["source_revision"], self.source_revision)
            self.assertEqual(
                provenance["archive_sha256"],
                hashlib.sha256(left.read_bytes()).hexdigest(),
            )
            with zipfile.ZipFile(left) as archive:
                members = archive.namelist()
                self.assertNotIn(provenance_path.name, members)
                self.assertTrue(members)
                self.assertTrue(
                    all(member.startswith(f"{left.stem}/") for member in members)
                )
                self.assertNotIn("tests/scenarios.md", "\n".join(members))

        verified = verify_packages(
            self.source_root, self.artifacts, self.source_revision
        )
        self.assertEqual(len(verified), len(SKILL_NAMES))

    def test_missing_or_unavailable_policy_revision_fails_closed(self) -> None:
        self.assertEqual(
            resolve_task_policy(self.source_root),
            POLICY_REVISION,
        )
        for historical_revision in HISTORICAL_POLICY_REVISIONS:
            with self.subTest(policy_revision=historical_revision):
                self.assertEqual(
                    resolve_task_policy(self.source_root, historical_revision),
                    historical_revision,
                )

        manifest_path = self.source_root / "skills" / "distribution.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["policy_revision"] = "f" * 40
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(DistributionError):
            resolve_task_policy(self.source_root)

    def test_inflight_policy_pin_mismatch_is_not_silently_advanced(self) -> None:
        with self.assertRaises(DistributionError):
            resolve_task_policy(
                self.source_root,
                "f" * 40,
            )

    def test_blank_inflight_policy_pin_fails_closed(self) -> None:
        with self.assertRaises(DistributionError):
            resolve_task_policy(self.source_root, "")

    def test_policy_command_preserves_a_supplied_historical_pin(self) -> None:
        for historical_revision in HISTORICAL_POLICY_REVISIONS:
            with self.subTest(policy_revision=historical_revision):
                output = io.StringIO()
                with redirect_stdout(output):
                    result = main(
                        [
                            "policy",
                            "--root",
                            str(self.source_root),
                            "--task-policy-revision",
                            historical_revision,
                        ]
                    )
                self.assertEqual(result, 0)
                self.assertEqual(output.getvalue().strip(), historical_revision)

    def test_cli_reports_distribution_errors_without_traceback(self) -> None:
        manifest_path = self.source_root / "skills" / "distribution.json"
        manifest_path.write_text("not JSON")
        error_output = io.StringIO()
        with redirect_stderr(error_output):
            result = main(["validate", "--root", str(self.source_root)])
        self.assertEqual(result, 1)
        self.assertIn("ERROR:", error_output.getvalue())

    def test_stage_first_install_is_idempotent_and_preserves_other_skills(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        project_root = self.temp_root / "project"
        project_root.mkdir()
        initialize_staging_root(self.source_root, project_root)
        unrelated = project_root / ".agents" / "skills" / "unrelated-skill"
        unrelated.mkdir(parents=True)
        sentinel = unrelated / "SKILL.md"
        sentinel.write_text("owner content\n")
        original_sentinel = hashlib.sha256(sentinel.read_bytes()).hexdigest()

        first = install_archive(
            self.source_root,
            archive,
            project_root,
            expected_policy_revision=POLICY_REVISION,
        )
        installed_skill = (
            project_root / ".agents" / "skills" / archive.stem / "SKILL.md"
        )
        self.assertEqual(first["status"], "installed")
        self.assertTrue(installed_skill.is_file())

        second = install_archive(
            self.source_root,
            archive,
            project_root,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(
            hashlib.sha256(sentinel.read_bytes()).hexdigest(),
            original_sentinel,
        )
        self.assertEqual(sentinel.read_text(), "owner content\n")

    def test_stage_refuses_policy_mismatch_without_mutating_target(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        for historical_revision in HISTORICAL_POLICY_REVISIONS:
            with self.subTest(policy_revision=historical_revision):
                project_root = self.temp_root / f"project-{historical_revision[:7]}"
                project_root.mkdir()
                initialize_staging_root(self.source_root, project_root)
                with self.assertRaises(DistributionError):
                    install_archive(
                        self.source_root,
                        archive,
                        project_root,
                        expected_policy_revision=historical_revision,
                    )
                self.assertFalse((project_root / ".agents").exists())

    def test_staging_requires_an_explicitly_initialized_root(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "uninitialized-staging"
        staging_root.mkdir()

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                staging_root,
                expected_policy_revision=POLICY_REVISION,
            )
        self.assertFalse((staging_root / ".agents").exists())

    def test_staging_initialization_refuses_a_nonempty_root(self) -> None:
        staging_root = self.temp_root / "nonempty-staging"
        staging_root.mkdir()
        existing_file = staging_root / "README.md"
        existing_file.write_text("keep this file\n")

        with self.assertRaises(DistributionError):
            initialize_staging_root(self.source_root, staging_root)

        self.assertEqual(existing_file.read_text(), "keep this file\n")
        self.assertFalse((staging_root / ".codex-skill-staging.json").exists())

    def test_staging_root_must_not_overlap_source_repository(self) -> None:
        for staging_root in (self.source_root, self.temp_root):
            with self.subTest(root=staging_root.name):
                with self.assertRaises(DistributionError):
                    initialize_staging_root(self.source_root, staging_root)

    def test_staging_layout_refuses_non_directory_agents_paths(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        for kind in ("agents-file", "skills-file"):
            with self.subTest(kind=kind):
                staging_root = self.temp_root / kind
                staging_root.mkdir()
                initialize_staging_root(self.source_root, staging_root)
                agents = staging_root / ".agents"
                if kind == "agents-file":
                    agents.write_text("not a directory\n")
                else:
                    agents.mkdir()
                    (agents / "skills").write_text("not a directory\n")

                with self.assertRaises(DistributionError):
                    install_archive(
                        self.source_root,
                        archive,
                        staging_root,
                        expected_policy_revision=POLICY_REVISION,
                    )

    def test_skill_target_symlink_is_never_followed(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "staging"
        staging_root.mkdir()
        initialize_staging_root(self.source_root, staging_root)
        outside = self.temp_root / "outside-skill"
        outside.mkdir()
        skills_dir = staging_root / ".agents" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / archive.stem).symlink_to(outside, target_is_directory=True)

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                staging_root,
                expected_policy_revision=POLICY_REVISION,
            )

        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_staging_marker_is_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "staging"
        staging_root.mkdir()
        initialize_staging_root(self.source_root, staging_root)
        (staging_root / ".codex-skill-staging.json").write_text("{}\n")

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                staging_root,
                expected_policy_revision=POLICY_REVISION,
            )

        self.assertFalse((staging_root / ".agents").exists())

    def test_personal_skill_path_is_refused_without_writing_into_it(self) -> None:
        staging_home = self.temp_root / "simulated-home"
        personal_skills = staging_home / ".agents" / "skills"
        personal_skills.mkdir(parents=True)

        with patch.object(Path, "home", return_value=staging_home):
            with self.assertRaises(DistributionError):
                initialize_staging_root(self.source_root, personal_skills)

        self.assertEqual(list(personal_skills.iterdir()), [])

    def test_upgrade_requires_explicit_flag_and_keeps_unrelated_skills(self) -> None:
        archive_v1 = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        project_root = self.temp_root / "project"
        project_root.mkdir()
        initialize_staging_root(self.source_root, project_root)
        unrelated = project_root / ".agents" / "skills" / "unrelated-skill"
        unrelated.mkdir(parents=True)
        sentinel = unrelated / "SKILL.md"
        sentinel.write_text("keep me\n")
        install_archive(
            self.source_root,
            archive_v1,
            project_root,
            expected_policy_revision=POLICY_REVISION,
        )

        skill_path = (
            self.source_root / "skills" / archive_v1.stem / "SKILL.md"
        )
        with skill_path.open("a") as skill:
            skill.write("\nUpgrade fixture marker.\n")
        git(self.source_root, "add", str(skill_path.relative_to(self.source_root)))
        git(self.source_root, "-c", "user.name=Skill Distribution Test", "-c",
            "user.email=skill-distribution-test@example.invalid", "commit", "--quiet",
            "-m", "Test fixture upgrade")
        source_revision_v2 = git(self.source_root, "rev-parse", "HEAD")
        archive_v2 = build_packages(
            self.source_root,
            self.temp_root / "packages-v2",
            source_revision_v2,
        )[0]

        installed_skill = (
            project_root / ".agents" / "skills" / archive_v1.stem / "SKILL.md"
        )
        installed_original = installed_skill.read_text()
        installed_skill.write_text(installed_original + "\nLocal edit.\n")
        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive_v2,
                project_root,
                expected_policy_revision=POLICY_REVISION,
                upgrade=True,
            )
        self.assertIn("Local edit.", installed_skill.read_text())
        installed_skill.write_text(installed_original)

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive_v2,
                project_root,
                expected_policy_revision=POLICY_REVISION,
            )
        upgraded = install_archive(
            self.source_root,
            archive_v2,
            project_root,
            expected_policy_revision=POLICY_REVISION,
            upgrade=True,
        )
        self.assertEqual(upgraded["status"], "upgraded")
        installed_skill = (
            project_root / ".agents" / "skills" / archive_v2.stem / "SKILL.md"
        )
        self.assertIn("Upgrade fixture marker.", installed_skill.read_text())
        self.assertEqual(sentinel.read_text(), "keep me\n")

    def test_failed_upgrade_restores_the_previous_skill(self) -> None:
        archive_v1 = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "staging"
        staging_root.mkdir()
        initialize_staging_root(self.source_root, staging_root)
        install_archive(
            self.source_root,
            archive_v1,
            staging_root,
            expected_policy_revision=POLICY_REVISION,
        )
        skill_path = self.source_root / "skills" / archive_v1.stem / "SKILL.md"
        with skill_path.open("a") as skill:
            skill.write("\nSecond committed source version.\n")
        git(self.source_root, "add", str(skill_path.relative_to(self.source_root)))
        git(self.source_root, "-c", "user.name=Skill Distribution Test", "-c",
            "user.email=skill-distribution-test@example.invalid", "commit", "--quiet",
            "-m", "Test rollback source")
        archive_v2 = build_packages(
            self.source_root,
            self.temp_root / "packages-v2",
            git(self.source_root, "rev-parse", "HEAD"),
        )[0]

        target = staging_root / ".agents" / "skills" / archive_v1.stem
        installed_skill = target / "SKILL.md"
        original_content = installed_skill.read_text()
        original_replace = distribution_module.os.replace
        replace_calls = 0

        def fail_second_replace(source: str | Path, destination: str | Path) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("simulated atomic promotion failure")
            original_replace(source, destination)

        with patch.object(
            distribution_module.os,
            "replace",
            side_effect=fail_second_replace,
        ):
            with self.assertRaises(DistributionError):
                install_archive(
                    self.source_root,
                    archive_v2,
                    staging_root,
                    expected_policy_revision=POLICY_REVISION,
                    upgrade=True,
                )

        self.assertEqual(replace_calls, 3)
        self.assertEqual(installed_skill.read_text(), original_content)

    def test_unknown_existing_skill_is_never_overwritten(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        project_root = self.temp_root / "project"
        project_root.mkdir()
        initialize_staging_root(self.source_root, project_root)
        target = project_root / ".agents" / "skills" / archive.stem
        target.mkdir(parents=True)
        sentinel = target / "SKILL.md"
        sentinel.write_text("unmanaged content\n")

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                project_root,
                expected_policy_revision=POLICY_REVISION,
                upgrade=True,
            )
        self.assertEqual(sentinel.read_text(), "unmanaged content\n")

    def test_policy_migration_is_refused_even_when_upgrade_requested(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        for historical_revision in HISTORICAL_POLICY_REVISIONS:
            with self.subTest(policy_revision=historical_revision):
                project_root = self.temp_root / f"project-{historical_revision[:7]}"
                project_root.mkdir()
                initialize_staging_root(self.source_root, project_root)
                install_archive(
                    self.source_root,
                    archive,
                    project_root,
                    expected_policy_revision=POLICY_REVISION,
                )
                target = project_root / ".agents" / "skills" / archive.stem
                marker_path = target / ".skill-distribution.json"
                marker = json.loads(marker_path.read_text())
                marker["policy_revision"] = historical_revision
                marker_path.write_text(json.dumps(marker))

                with self.assertRaises(DistributionError):
                    install_archive(
                        self.source_root,
                        archive,
                        project_root,
                        expected_policy_revision=POLICY_REVISION,
                        upgrade=True,
                    )
                self.assertEqual(
                    json.loads(marker_path.read_text())["policy_revision"],
                    historical_revision,
                )

    def test_archive_payload_corruption_and_extra_members_are_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        with zipfile.ZipFile(archive, "a") as package:
            package.writestr("../escape.txt", "must not extract")
        provenance_path = archive.with_suffix(".provenance.json")
        provenance = json.loads(provenance_path.read_text())
        provenance["archive_sha256"] = hashlib.sha256(
            archive.read_bytes()
        ).hexdigest()
        provenance_path.write_text(json.dumps(provenance))

        with self.assertRaises(DistributionError):
            verify_packages(
                self.source_root,
                self.artifacts,
                self.source_revision,
            )

    def test_archive_duplicate_member_is_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        with zipfile.ZipFile(archive, "a") as package:
            package.writestr(f"{archive.stem}/SKILL.md", b"duplicate member\n")
        sidecar_path = archive.with_suffix(".provenance.json")
        sidecar = json.loads(sidecar_path.read_text())
        sidecar["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        sidecar_path.write_text(json.dumps(sidecar))

        with self.assertRaises(DistributionError):
            verify_packages(self.source_root, self.artifacts, self.source_revision)

    def test_missing_and_symlinked_provenance_sidecars_are_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        sidecar_path = archive.with_suffix(".provenance.json")
        original = sidecar_path.read_bytes()

        sidecar_path.unlink()
        with self.assertRaises(DistributionError):
            verify_packages(self.source_root, self.artifacts, self.source_revision)

        external_sidecar = self.temp_root / "external-provenance.json"
        external_sidecar.write_bytes(original)
        sidecar_path.symlink_to(external_sidecar)
        with self.assertRaises(DistributionError):
            verify_packages(self.source_root, self.artifacts, self.source_revision)

        sidecar_path.unlink()
        sidecar_path.write_bytes(original)

    def test_archive_symlink_member_is_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        with zipfile.ZipFile(archive) as original:
            members = {
                info.filename: original.read(info.filename)
                for info in original.infolist()
            }
        with zipfile.ZipFile(archive, "w") as rewritten:
            for name, payload in members.items():
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (
                    stat.S_IFLNK | 0o777 if name.endswith("SKILL.md")
                    else stat.S_IFREG | 0o644
                ) << 16
                rewritten.writestr(info, b"../escape" if name.endswith("SKILL.md") else payload)
        sidecar_path = archive.with_suffix(".provenance.json")
        sidecar = json.loads(sidecar_path.read_text())
        sidecar["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        sidecar_path.write_text(json.dumps(sidecar))

        with self.assertRaises(DistributionError):
            verify_packages(self.source_root, self.artifacts, self.source_revision)

    def test_provenance_sidecar_metadata_is_verified(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        sidecar_path = archive.with_suffix(".provenance.json")
        original = json.loads(sidecar_path.read_text())
        mutations = [
            ("schema", lambda value: value.update(schema_version=2)),
            ("Skill identity", lambda value: value.update(skill_name="other")),
            *[
                (
                    f"historical policy pin {revision}",
                    lambda value, revision=revision: value.update(
                        policy_revision=revision
                    ),
                )
                for revision in HISTORICAL_POLICY_REVISIONS
            ],
            ("source revision", lambda value: value.update(source_revision="invalid")),
            ("source paths", lambda value: value.update(source_files={})),
            ("payload hash set", lambda value: value.update(payload_sha256={})),
            ("archive digest", lambda value: value.update(archive_sha256="0" * 64)),
            ("hash scope", lambda value: value.update(hash_scope="recursive")),
        ]
        for label, mutate in mutations:
            with self.subTest(field=label):
                provenance = copy.deepcopy(original)
                mutate(provenance)
                sidecar_path.write_text(json.dumps(provenance))
                with self.assertRaises(DistributionError):
                    verify_packages(
                        self.source_root,
                        self.artifacts,
                        self.source_revision,
                    )

        sidecar_path.write_text(json.dumps(original))

    def test_staging_rechecks_payload_after_archive_verification(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "staging"
        staging_root.mkdir()
        initialize_staging_root(self.source_root, staging_root)
        verify_archive = distribution_module._verify_archive

        def verify_then_replace_payload(
            root: Path,
            archive_path: Path,
            expected_source_revision: str | None = None,
        ) -> dict[str, object]:
            provenance = verify_archive(
                root, archive_path, expected_source_revision
            )
            with zipfile.ZipFile(archive_path, "r") as package:
                payloads = {
                    info.filename: package.read(info)
                    for info in package.infolist()
                }
            payloads[f"{archive.stem}/SKILL.md"] = b"unverified replacement\n"
            with zipfile.ZipFile(archive_path, "w") as package:
                for member, payload in sorted(payloads.items()):
                    info = zipfile.ZipInfo(
                        member, date_time=(1980, 1, 1, 0, 0, 0)
                    )
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    package.writestr(info, payload)
            return provenance

        with patch.object(
            distribution_module,
            "_verify_archive",
            side_effect=verify_then_replace_payload,
        ):
            with self.assertRaises(DistributionError):
                install_archive(
                    self.source_root,
                    archive,
                    staging_root,
                    expected_policy_revision=POLICY_REVISION,
                )

        target = (
            staging_root
            / ".agents"
            / "skills"
            / archive.stem
        )
        self.assertFalse(target.exists())

    def test_staging_directory_symlink_is_refused(self) -> None:
        archive = build_packages(
            self.source_root, self.artifacts, self.source_revision
        )[0]
        staging_root = self.temp_root / "staging"
        staging_root.mkdir()
        initialize_staging_root(self.source_root, staging_root)
        outside = self.temp_root / "outside"
        outside.mkdir()
        (staging_root / ".agents").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                staging_root,
                expected_policy_revision=POLICY_REVISION,
            )
        self.assertFalse((outside / "skills").exists())

    def test_package_source_revision_must_match_committed_payload(self) -> None:
        build_packages(self.source_root, self.artifacts, self.source_revision)
        with self.assertRaises(DistributionError):
            verify_packages(
                self.source_root,
                self.artifacts,
                HISTORICAL_POLICY_REVISION,
            )

    def test_package_refuses_uncommitted_skill_changes(self) -> None:
        skill_path = self.source_root / "skills" / SKILL_NAMES[0] / "SKILL.md"
        with skill_path.open("a") as skill:
            skill.write("\nUncommitted source change.\n")
        with self.assertRaises(DistributionError):
            build_packages(
                self.source_root,
                self.artifacts,
                self.source_revision,
            )

    def test_package_refuses_manifest_changes_after_declared_source_commit(self) -> None:
        manifest_path = self.source_root / "skills" / "distribution.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["skills"][0]["files"].reverse()
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaises(DistributionError):
            build_packages(
                self.source_root,
                self.artifacts,
                self.source_revision,
            )

    def test_atomic_package_write_removes_temporary_file_on_failure(self) -> None:
        with patch.object(
            distribution_module.os,
            "replace",
            side_effect=OSError("simulated atomic replace failure"),
        ):
            with self.assertRaises(OSError):
                distribution_module._atomic_write(
                    self.artifacts / "package.zip",
                    b"package content",
                )

        self.assertFalse((self.artifacts / "package.zip").exists())
        self.assertEqual(list(self.artifacts.glob("*.tmp")), [])


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release-packages-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, revision = source_checkout(self.base)
        manifest_path = self.root / "skills/distribution.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.update(schema_version=2, policy_reference="{{release_tag}}", transform_version=1)
        manifest.pop("policy_revision")
        manifest_path.write_text(json.dumps(manifest))
        for name in SKILL_NAMES:
            path = self.root / "skills" / name / "SKILL.md"
            text = path.read_text()
            text = text.replace(f"/blob/{POLICY_REVISION}/docs/PROCESS.md", "/blob/{{release_tag}}/docs/PROCESS.md")
            path.write_text(text)
        git(self.root, "add", "skills")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c",
            "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Release template")
        self.context = dict(release_version="2026.11.16", source_revision=git(self.root, "rev-parse", "HEAD"),
                            policy_revision=POLICY_REVISION, builder_revision=revision, transform_version=1)

    def test_reconstructs_eight_identical_artifacts_without_working_sources(self):
        first, second = self.base / "first", self.base / "second"
        paths = distribution_module.build_release_packages(self.root, first, self.context)
        shutil.rmtree(self.root / "skills")
        distribution_module.build_release_packages(self.root, second, self.context)
        self.assertEqual(len(paths), 8)
        self.assertEqual({p.name:p.read_bytes() for p in first.iterdir()},
                         {p.name:p.read_bytes() for p in second.iterdir()})
        self.assertEqual(len(distribution_module.verify_release_packages(self.root, first, self.context)), 8)
        with zipfile.ZipFile(first / "development-review.zip") as archive:
            payload = archive.read("development-review/SKILL.md")
            self.assertIn(b"/blob/2026.11.16/docs/PROCESS.md", payload)
            self.assertNotIn(b"{{release_tag}}", payload)

    def test_rejects_tampering_and_conflicting_output(self):
        output = self.base / "packages"
        distribution_module.build_release_packages(self.root, output, self.context)
        (output / "development-review.zip").write_bytes(b"tampered")
        with self.assertRaises(DistributionError):
            distribution_module.verify_release_packages(self.root, output, self.context)
        with self.assertRaises(DistributionError):
            distribution_module.build_release_packages(self.root, output, self.context)

    def test_rejects_unknown_transform_and_invalid_version(self):
        for changes in ({"transform_version": 2}, {"release_version": "2026.02.30"}, {"release_version": "2026.11.16.1"}):
            with self.subTest(changes=changes), self.assertRaises(DistributionError):
                distribution_module.build_release_packages(self.root, self.base / "out", self.context | changes)

    def test_candidate_staging_is_idempotent_and_rejects_drift(self):
        output, staging = self.base / "packages", self.base / "staging"
        distribution_module.build_release_packages(self.root, output, self.context)
        staging.mkdir()
        initialize_staging_root(self.root, staging)
        results = distribution_module.stage_release_packages(self.root, output, staging, self.context)
        self.assertEqual([r["status"] for r in results], ["installed"] * 3)
        results = distribution_module.stage_release_packages(self.root, output, staging, self.context)
        self.assertEqual([r["status"] for r in results], ["unchanged"] * 3)
        (staging / ".agents/skills/development-review/SKILL.md").write_text("drift")
        with self.assertRaises(DistributionError):
            distribution_module.stage_release_packages(self.root, output, staging, self.context)

    def test_cli_candidate_package_and_verify_without_tag(self):
        context_path = self.base / "context.json"
        context_path.write_text(json.dumps(self.context))
        output = self.base / "cli-packages"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["release-package", "--root", str(self.root), "--context", str(context_path), "--output-dir", str(output)]), 0)
            self.assertEqual(main(["release-verify", "--root", str(self.root), "--context", str(context_path), "--artifact-dir", str(output)]), 0)

    def test_rejects_historical_symlink_and_missing_template(self):
        path = self.root / "skills/development-review/SKILL.md"
        path.unlink()
        path.symlink_to("../development-orchestrator/SKILL.md")
        git(self.root, "add", "skills")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c", "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Invalid source")
        context = self.context | {"source_revision": git(self.root, "rev-parse", "HEAD")}
        with self.assertRaises(DistributionError):
            distribution_module.build_release_packages(self.root, self.base / "bad", context)

    def test_verification_binds_full_context(self):
        output = self.base / "packages"
        distribution_module.build_release_packages(self.root, output, self.context)
        with self.assertRaises(DistributionError):
            distribution_module.verify_release_packages(self.root, output, self.context | {"evidence": "changed"})

    def test_legacy_source_release_adapter(self):
        legacy_base = self.base / "legacy"
        legacy_base.mkdir()
        root, revision = source_checkout(legacy_base)
        context = self.context | {"source_revision": revision}
        self.assertEqual(len(distribution_module.build_release_packages(root, self.base / "legacy-release", context)), 8)

    def test_rejects_self_consistent_forged_sidecar_and_archive(self):
        output = self.base / "packages"
        distribution_module.build_release_packages(self.root, output, self.context)
        archive_path = output / "development-review.zip"
        with zipfile.ZipFile(archive_path) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()}
        payloads["development-review/SKILL.md"] += b"forged policy instructions\n"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, payload in payloads.items():
                archive.writestr(name, payload)
        sidecar_path = output / "development-review.provenance.json"
        sidecar = json.loads(sidecar_path.read_text())
        sidecar["archive_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        sidecar["payload_sha256"] = {k: hashlib.sha256(v).hexdigest() for k,v in payloads.items()}
        sidecar_path.write_text(json.dumps(sidecar))
        with self.assertRaises(DistributionError):
            distribution_module.verify_release_packages(self.root, output, self.context)

    def test_candidate_staging_rejects_source_overlap(self):
        output = self.base / "packages"
        distribution_module.build_release_packages(self.root, output, self.context)
        with self.assertRaises(DistributionError):
            distribution_module.stage_release_packages(self.root, output, self.root, self.context)

    def test_rejects_missing_template(self):
        path = self.root / "skills/development-review/SKILL.md"
        path.write_text(path.read_text().replace("{{release_tag}}", "unbound"))
        git(self.root, "add", "skills")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c", "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Invalid binding")
        with self.assertRaises(DistributionError):
            distribution_module.build_release_packages(self.root, self.base / "bad", self.context | {"source_revision": git(self.root, "rev-parse", "HEAD")})

    def test_rejects_release_token_outside_canonical_policy_url(self):
        path = self.root / "skills/development-review/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nHistorical example identifier: `{{release_tag}}`.\n")
        git(self.root, "add", "skills")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c", "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Unrelated template token")
        context = self.context | {"source_revision": git(self.root, "rev-parse", "HEAD")}
        with self.assertRaises(DistributionError):
            distribution_module.build_release_packages(self.root, self.base / "bad", context)

    def test_transformation_preserves_all_bytes_outside_policy_url(self):
        output = self.base / "packages"
        distribution_module.build_release_packages(self.root, output, self.context)
        for name in SKILL_NAMES:
            original = (self.root / "skills" / name / "SKILL.md").read_bytes()
            with zipfile.ZipFile(output / f"{name}.zip") as archive:
                actual = archive.read(f"{name}/SKILL.md")
            url = b"https://github.com/danielbyon/development-process/blob/{{release_tag}}/docs/PROCESS.md"
            self.assertEqual(actual, original.replace(url, url.replace(b"{{release_tag}}", self.context["release_version"].encode())))

    def test_rejects_release_token_in_nonpolicy_payload(self):
        path = self.root / "skills/development-review/agents/openai.yaml"
        path.write_bytes(path.read_bytes() + b"\n# {{release_tag}}\n")
        git(self.root, "add", "skills")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c", "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Unexpected metadata token")
        context = self.context | {"source_revision": git(self.root, "rev-parse", "HEAD")}
        with self.assertRaises(DistributionError):
            distribution_module.build_release_packages(self.root, self.base / "bad", context)

    def test_official_validator_receives_exact_transformed_archive_bytes(self):
        checked = {}
        real_run = subprocess.run
        validator = str(self.root.resolve() / distribution_module.VALIDATOR_PATH)

        def observe(arguments, **kwargs):
            if len(arguments) > 2 and str(arguments[1]) == validator:
                directory = Path(arguments[2])
                payload = (directory / "SKILL.md").read_bytes()
                if b"/blob/2026.11.16/docs/PROCESS.md" in payload:
                    checked[directory.name] = payload
            return real_run(arguments, **kwargs)

        output = self.base / "packages"
        with patch.object(distribution_module.subprocess, "run", side_effect=observe):
            distribution_module.build_release_packages(self.root, output, self.context)
        self.assertEqual(set(checked), set(SKILL_NAMES))
        for name in SKILL_NAMES:
            with zipfile.ZipFile(output / f"{name}.zip") as archive:
                self.assertEqual(checked[name], archive.read(f"{name}/SKILL.md"))
                self.assertEqual(set(archive.namelist()), {f"{name}/SKILL.md", f"{name}/agents/openai.yaml"})

    def test_transformed_payload_validator_failure_blocks_bundle(self):
        real_run = subprocess.run
        validator = str(self.root.resolve() / distribution_module.VALIDATOR_PATH)

        def reject_transformed(arguments, **kwargs):
            result = real_run(arguments, **kwargs)
            if len(arguments) > 2 and str(arguments[1]) == validator:
                if b"/blob/2026.11.16/docs/PROCESS.md" in (Path(arguments[2]) / "SKILL.md").read_bytes():
                    return subprocess.CompletedProcess(arguments, 1, "rejected transformed payload", "")
            return result

        output = self.base / "packages"
        with patch.object(distribution_module.subprocess, "run", side_effect=reject_transformed):
            with self.assertRaisesRegex(DistributionError, "rejected transformed payload"):
                distribution_module.build_release_packages(self.root, output, self.context)
        self.assertFalse(output.exists())

    def test_actual_templates_validate_and_package_from_committed_inputs(self):
        self.assertEqual(set(validate_distribution(ROOT)), set(SKILL_NAMES))
        manifest_path = Path("skills/distribution.json")
        (self.root / manifest_path).write_bytes((ROOT / manifest_path).read_bytes())
        for name in SKILL_NAMES:
            for relative in ("SKILL.md", "agents/openai.yaml"):
                path = Path("skills") / name / relative
                (self.root / path).write_bytes((ROOT / path).read_bytes())
        (self.root / "docs/PROCESS.md").write_bytes((ROOT / "docs/PROCESS.md").read_bytes())
        git(self.root, "add", "skills", "docs/PROCESS.md")
        git(self.root, "-c", "user.name=Skill Distribution Test", "-c",
            "user.email=skill-distribution-test@example.invalid", "commit", "-qm", "Actual release inputs")
        revision = git(self.root, "rev-parse", "HEAD")
        context = self.context | {"source_revision": revision, "policy_revision": revision}
        output = self.base / "actual-template-packages"
        self.assertEqual(len(distribution_module.build_release_packages(self.root, output, context)), 8)
        self.assertEqual(len(distribution_module.verify_release_packages(self.root, output, context)), 8)
        for name in SKILL_NAMES:
            original = (ROOT / "skills" / name / "SKILL.md").read_bytes()
            with zipfile.ZipFile(output / f"{name}.zip") as archive:
                self.assertEqual(set(archive.namelist()), {f"{name}/SKILL.md", f"{name}/agents/openai.yaml"})
                url = b"https://github.com/danielbyon/development-process/blob/{{release_tag}}/docs/PROCESS.md"
                self.assertEqual(archive.read(f"{name}/SKILL.md"),
                    original.replace(url, url.replace(b"{{release_tag}}", context["release_version"].encode())))
                self.assertEqual(archive.read(f"{name}/agents/openai.yaml"),
                    (ROOT / "skills" / name / "agents/openai.yaml").read_bytes())


if __name__ == "__main__":
    unittest.main()
