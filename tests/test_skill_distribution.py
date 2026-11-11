from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import scripts.skill_distribution as distribution_module
from scripts.skill_distribution import (
    DistributionError,
    build_packages,
    install_archive,
    resolve_task_policy,
    initialize_staging_root,
    validate_distribution,
    verify_packages,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_REVISION = "aa8dc7784641dd5416befdebc246ed081bfd7ade"
HISTORICAL_POLICY_REVISION = "93a86127a3721d6044f4a8e993a764731fbda4e5"
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

    shutil.copytree(ROOT / "skills", checkout / "skills", dirs_exist_ok=True)
    shutil.copytree(
        ROOT / "scripts" / "vendor",
        checkout / "scripts" / "vendor",
        dirs_exist_ok=True,
    )
    git(checkout, "add", "skills", "scripts/vendor")
    git(checkout, "-c", "user.name=Issue 5 Test", "-c",
        "user.email=issue5-test@example.invalid", "commit", "--quiet",
        "-m", "Test fixture source")
    return checkout, git(checkout, "rev-parse", "HEAD")


class SkillDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="issue5-distribution-")
        self.addCleanup(self.temporary.cleanup)
        self.temp_root = Path(self.temporary.name)
        self.source_root, self.source_revision = source_checkout(self.temp_root)
        self.artifacts = self.temp_root / "packages"

    def test_manifest_validates_three_standalone_skills(self) -> None:
        self.assertEqual(
            set(validate_distribution(self.source_root)),
            set(SKILL_NAMES),
        )

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
        self.assertEqual(
            resolve_task_policy(
                self.source_root, HISTORICAL_POLICY_REVISION
            ),
            HISTORICAL_POLICY_REVISION,
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
        project_root = self.temp_root / "project"
        project_root.mkdir()
        initialize_staging_root(self.source_root, project_root)
        with self.assertRaises(DistributionError):
            install_archive(
                self.source_root,
                archive,
                project_root,
                expected_policy_revision=HISTORICAL_POLICY_REVISION,
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
        git(self.source_root, "-c", "user.name=Issue 5 Test", "-c",
            "user.email=issue5-test@example.invalid", "commit", "--quiet",
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
        project_root = self.temp_root / "project"
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
        marker["policy_revision"] = HISTORICAL_POLICY_REVISION
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
            HISTORICAL_POLICY_REVISION,
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


if __name__ == "__main__":
    unittest.main()
