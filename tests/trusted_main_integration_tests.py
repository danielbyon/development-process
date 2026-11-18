"""Exercise release qualification with a real Git history and provider boundary."""

from __future__ import annotations

import os
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
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
        self.attempt = 1
        self.action_artifacts = []
        self.artifact_payloads = {}
        self.remote_releases = []
        self.remote_tags = []
        self.remote_assets = {}
        self.remote_events = []

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
                "run_attempt": self.attempt, "created_at": CREATED_AT,
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
            return {"artifacts": self.action_artifacts}
        if "/actions/artifacts/" in endpoint and endpoint.endswith("/zip"):
            artifact_id = endpoint.rsplit("/", 2)[1]
            return self.artifact_payloads[artifact_id]
        if endpoint.startswith(self.base + "/releases?"):
            return self.remote_releases
        if endpoint.startswith(self.base + "/git/matching-refs/tags/?"):
            return self.remote_tags
        raise AssertionError(f"Unexpected GitHub endpoint: {endpoint}")

    def save_action_artifact(self, name: str, artifact_id: int, files: dict[str, bytes]):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, payload in sorted(files.items()):
                archive.writestr(path, payload)
        payload = buffer.getvalue()
        self.action_artifacts = [{
            "name": name, "id": artifact_id, "expired": False,
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }]
        self.artifact_payloads[str(artifact_id)] = payload

    def releases(self):
        return self.remote_releases

    def tags(self):
        return self.remote_tags

    def asset(self, asset):
        return self.remote_assets[asset["name"]]

    def create_draft(self, context, body):
        self.remote_events.append("create_draft")
        raise AssertionError("The retry should recover its matching draft")

    def upload(self, release_id, path):
        self.remote_events.append("upload")
        self.remote_assets[path.name] = path.read_bytes()

    def create_tag(self, tag, revision):
        self.remote_events.append("create_tag")
        self.remote_tags.append({"ref": "refs/tags/" + tag,
                                 "object": {"sha": revision, "type": "commit"}})

    def release(self, release_id):
        return self.remote_releases[0]

    def publish(self, release_id):
        self.remote_events.append("publish")
        self.remote_releases[0]["draft"] = False
        self.remote_releases[0]["immutable"] = True

    def verify_attestation(self, tag, directory):
        self.remote_events.append("verify_release_attestation")


class TrustedMainIntegrationTests(unittest.TestCase):
    def setUp(self):
        for pattern in skill_release.SUITES:
            sys.modules.pop(Path(pattern).stem, None)
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
        (self.root / "trusted-main-integration-source.txt").write_text(
            "fixture-only source commit\n"
        )
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

    def test_completed_qualification_retry_reuses_assets_and_current_attempt_attestation(self):
        api = GitHubBoundary(self.root, self.source, self.main)
        artifacts1 = self.root.parent / "attempt-1"
        artifacts2 = self.root.parent / "attempt-2"
        with patch.dict(os.environ, self.dispatch_environment(), clear=False):
            context1 = skill_release.preflight(self.root, api, 41, 1)
            context1 = skill_release.qualify(self.root, context1, artifacts1)
            skill_release.verify_bundle(self.root, artifacts1, context1)

        (artifacts1 / "release-context.json").write_bytes(
            skill_release.canonical(context1) + b"\n"
        )
        hashes1 = skill_release.artifact_hashes(artifacts1)
        bytes1 = {name: (artifacts1 / name).read_bytes() for name in hashes1}
        frozen1 = {key: value for key, value in context1.items()
                   if key not in ("qualified_artifacts", "validation_attempt", "current_validation")}
        api.save_action_artifact("release-bundle-1", 301, {
            **bytes1,
            "release-context.json": (artifacts1 / "release-context.json").read_bytes(),
        })
        api.attempt = 2
        environment2 = self.dispatch_environment()
        environment2["GITHUB_RUN_ATTEMPT"] = "2"
        with patch.dict(os.environ, environment2, clear=False):
            context2 = skill_release.preflight(self.root, api, 41, 2)
            self.assertNotIn("current_validation", context2)
            context2 = skill_release.qualify(self.root, context2, artifacts2)
            skill_release.verify_signing_context(self.root, context2)
            skill_release.verify_bundle(self.root, artifacts2, context2)

            hashes2 = skill_release.artifact_hashes(artifacts2)
            bytes2 = {name: (artifacts2 / name).read_bytes() for name in hashes2}
            frozen2 = {key: value for key, value in context2.items()
                       if key not in ("qualified_artifacts", "validation_attempt", "current_validation")}
            self.assertEqual(frozen2, frozen1)
            self.assertEqual(context1["qualification"]["run_attempt"], 1)
            self.assertEqual(context2["qualification"]["run_attempt"], 1)
            self.assertEqual(context2["current_validation"]["run_attempt"], 2)
            self.assertEqual(context2["current_validation"]["suites"], context2["qualification"]["suites"])
            self.assertEqual(hashes2, hashes1)
            self.assertEqual(bytes2, bytes1)
            self.assertEqual(context2["qualified_artifacts"], context1["qualified_artifacts"])

            identity = skill_release.digest(skill_release.canonical(frozen2))
            body = "Release context: " + identity
            api.remote_releases = [{
                "id": 900, "tag_name": context1["release_version"],
                "name": context1["release_version"], "body": body,
                "draft": True, "prerelease": False,
                "assets": [{"name": name, "id": index}
                           for index, name in enumerate(sorted(bytes1), 1)],
            }]
            api.remote_assets = dict(bytes1)

            real_run = subprocess.run
            attested_attempt = {"value": 1}

            def attestation_run(command, *args, **kwargs):
                if command[:3] == ["gh", "attestation", "verify"]:
                    manifest = Path(command[3]).read_bytes()
                    statement = {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [{"name": "release-manifest.json", "digest": {
                            "sha256": hashlib.sha256(manifest).hexdigest()}}],
                        "predicate": {"runDetails": {
                            "builder": {"id": "https://github.com/" + skill_release.REPOSITORY +
                                "/.github/workflows/skill-release.yml@refs/heads/main"},
                            "metadata": {"invocationId": "https://github.com/" +
                                skill_release.REPOSITORY + "/actions/runs/41/attempts/" +
                                str(attested_attempt["value"])},
                        }},
                    }
                    result = [{"verificationResult": {"statement": statement}}]
                    return subprocess.CompletedProcess(command, 0, json.dumps(result).encode(), b"")
                return real_run(command, *args, **kwargs)

            with patch.object(github_releases.subprocess, "run", side_effect=attestation_run):
                with self.assertRaisesRegex(github_releases.APIError, "invocation"):
                    api.verify_qualification_attestation(artifacts2, context2)
                attested_attempt["value"] = 2
                api.verify_qualification_attestation(artifacts2, context2)
                published = skill_release.publish(self.root, api, context2, artifacts2)

        self.assertEqual(published["draft"], False)
        self.assertEqual(published["immutable"], True)
        self.assertNotIn("create_draft", api.remote_events)
        self.assertNotIn("upload", api.remote_events)
        self.assertEqual(api.remote_events, ["create_tag", "publish", "verify_release_attestation"])

    def test_preflight_only_context_can_be_recovered_and_qualified_on_retry(self):
        api = GitHubBoundary(self.root, self.source, self.main)
        environment1 = self.dispatch_environment()
        with patch.dict(os.environ, environment1, clear=False):
            context1 = skill_release.preflight(self.root, api, 41, 1)
        api.save_action_artifact("release-context-1", 302, {
            "release-context.json": skill_release.canonical(context1) + b"\n",
        })
        api.attempt = 2
        environment2 = self.dispatch_environment()
        environment2["GITHUB_RUN_ATTEMPT"] = "2"
        with patch.dict(os.environ, environment2, clear=False):
            context2 = skill_release.preflight(self.root, api, 41, 2)
            self.assertNotIn("qualification", context2)
            self.assertNotIn("qualified_artifacts", context2)
            context2 = skill_release.qualify(self.root, context2, self.root.parent / "retry")
        self.assertEqual(context2["run_attempt"], 1)
        self.assertEqual(context2["qualification"]["run_attempt"], 2)
        self.assertEqual(context2["current_validation"]["run_attempt"], 2)

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
