"""Exercise release qualification with a real Git history and provider boundary."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import github_releases
import skill_release


SOURCE_ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-11-17T09:00:00Z"


def git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=input,
        check=True, capture_output=True,
    )
    return result.stdout


class GitHubBoundary(github_releases.GitHubAPI):
    """Return provider-shaped records while deriving comparisons from real Git."""

    def __init__(self, root: Path, source: str, main: str):
        super().__init__()
        self.root = root
        self.source = source
        self.main = main

    def request(self, method, endpoint, data=None, raw=False):
        if method != "GET" or data is not None:
            raise AssertionError("The qualification test must not publish remotely")
        if endpoint == self.base:
            return {"full_name": self.repository, "default_branch": "main",
                    "owner": {"login": "danielbyon", "id": 123}}
        if endpoint == self.base + "/immutable-releases":
            return {"enabled": True}
        if endpoint == self.base + "/actions/runs/41":
            return {
                "id": 41, "event": "workflow_dispatch", "head_branch": "main",
                "head_sha": self.source,
                "actor": {"id": 123, "login": "danielbyon"},
                "triggering_actor": {"id": 123, "login": "danielbyon"},
                "run_attempt": 1, "created_at": CREATED_AT,
                "path": ".github/workflows/skill-release.yml@refs/heads/main",
            }
        if endpoint == self.base + "/git/ref/heads/main":
            return {"ref": "refs/heads/main",
                    "object": {"type": "commit", "sha": self.main}}
        if endpoint.startswith(self.base + "/compare/"):
            spec = endpoint.rsplit("/", 1)[1]
            base_sha, head_sha = spec.split("...", 1)
            try:
                merge_base = git(self.root, "merge-base", base_sha, head_sha).decode().strip()
            except subprocess.CalledProcessError:
                merge_base = None
            if base_sha == head_sha:
                status = "identical"
            elif merge_base == base_sha:
                status = "ahead"
            elif merge_base == head_sha:
                status = "behind"
            else:
                status = "diverged"
            return {
                "status": status,
                "base_commit": {"sha": base_sha},
                "head_commit": {"sha": head_sha},
                "merge_base_commit": {"sha": merge_base} if merge_base else None,
            }
        if "/actions/runs/41/artifacts?" in endpoint:
            return {"artifacts": []}
        if endpoint.startswith(self.base + "/releases?"):
            return []
        if endpoint.startswith(self.base + "/git/matching-refs/tags/?"):
            return []
        raise AssertionError(f"Unexpected GitHub endpoint: {endpoint}")


class TrustedMainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="trusted-main-release-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", "--shared", str(SOURCE_ROOT), str(self.root)],
            check=True, capture_output=True,
        )
        git(self.root, "switch", "--quiet", "--force-create", "main")
        git(self.root, "config", "user.name", "Release Test")
        git(self.root, "config", "user.email", "release-test@example.invalid")
        self.base = git(self.root, "rev-parse", "HEAD").decode().strip()

        tracked = git(SOURCE_ROOT, "ls-files", "-z").split(b"\0")
        for raw in tracked:
            if not raw:
                continue
            relative = Path(os.fsdecode(raw))
            source = SOURCE_ROOT / relative
            destination = self.root / relative
            if not source.exists() and not source.is_symlink():
                if destination.is_file() or destination.is_symlink():
                    destination.unlink()
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                if destination.exists() or destination.is_symlink():
                    destination.unlink()
                destination.symlink_to(os.readlink(source))
            else:
                if destination.is_symlink():
                    destination.unlink()
                shutil.copy2(source, destination)
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "trusted dispatch source")
        self.source = git(self.root, "rev-parse", "HEAD").decode().strip()
        tree = git(self.root, "rev-parse", self.source + "^{tree}").decode().strip()

        marker = self.root / "main-advanced-after-dispatch.txt"
        marker.write_text("main advanced after workflow dispatch\n")
        git(self.root, "add", marker.name)
        git(self.root, "commit", "--quiet", "-m", "advance main after dispatch")
        self.main = git(self.root, "rev-parse", "HEAD").decode().strip()

        self.unrelated = subprocess.run(
            ["git", "-C", str(self.root), "commit-tree", tree, "-p", self.base,
             "-m", "unrelated commit with the same tree"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        git(self.root, "update-ref", "refs/heads/equal-tree-unrelated", self.unrelated)
        git(self.root, "checkout", "--quiet", "--detach", self.source)

    def dispatch_environment(self):
        return {
            "GITHUB_REPOSITORY": skill_release.REPOSITORY,
            "GITHUB_SHA": self.source,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ID": "41",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_ACTOR": "danielbyon",
            "GITHUB_TRIGGERING_ACTOR": "danielbyon",
            "GITHUB_WORKFLOW_REF": skill_release.REPOSITORY +
                "/.github/workflows/skill-release.yml@refs/heads/main",
        }

    def test_owner_dispatch_qualifies_from_frozen_main_commit_without_receipts(self):
        api = GitHubBoundary(self.root, self.source, self.main)
        with patch.dict(os.environ, self.dispatch_environment(), clear=False):
            context = skill_release.preflight(self.root, api, 41, 1)
            artifacts = self.root.parent / "artifacts"
            context = skill_release.qualify(self.root, context, artifacts)
            skill_release.verify_bundle(self.root, artifacts, context)

        self.assertEqual(context["source_revision"], self.source)
        self.assertEqual(context["builder_revision"], self.source)
        self.assertEqual(context["release_context_schema_version"], 1)
        self.assertEqual({item["suite"] for item in context["qualification"]["suites"]},
                         set(skill_release.SUITES))
        self.assertEqual(len(context["qualified_artifacts"]), 8)
        for key in ("evidence", "evidence_snapshots", "evidence_digest",
                    "authenticated_evidence", "baseline_admission"):
            self.assertNotIn(key, context)

    def test_equal_tree_commit_outside_main_ancestry_is_rejected(self):
        self.assertEqual(
            git(self.root, "rev-parse", self.source + "^{tree}").decode().strip(),
            git(self.root, "rev-parse", self.unrelated + "^{tree}").decode().strip(),
        )
        api = GitHubBoundary(self.root, self.source, self.unrelated)
        with patch.dict(os.environ, self.dispatch_environment(), clear=False):
            with self.assertRaisesRegex(github_releases.APIError, "main history"):
                skill_release.preflight(self.root, api, 41, 1)

    def test_environment_cannot_substitute_another_dispatch_sha(self):
        api = GitHubBoundary(self.root, self.source, self.main)
        environment = self.dispatch_environment()
        environment["GITHUB_SHA"] = self.unrelated
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesRegex(skill_release.ReleaseError, "GITHUB_SHA"):
                skill_release.preflight(self.root, api, 41, 1)

    def test_removed_main_ancestry_blocks_publication_before_remote_mutation(self):
        api = GitHubBoundary(self.root, self.source, self.main)
        with patch.dict(os.environ, self.dispatch_environment(), clear=False):
            context = skill_release.preflight(self.root, api, 41, 1)
            api.main = self.unrelated
            with self.assertRaisesRegex(github_releases.APIError, "main history"):
                skill_release.publish(
                    self.root, api, context, self.root.parent / "unbuilt-artifacts",
                )


if __name__ == "__main__":
    unittest.main()
