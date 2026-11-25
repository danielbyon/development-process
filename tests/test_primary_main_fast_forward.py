"""Exercise the post-merge fast-forward contract with disposable Git repositories."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAFE_MERGE = [
    "merge",
    "--ff-only",
    "--no-overwrite-ignore",
    "--no-autostash",
    "origin/main",
]


class PrimaryMainFastForwardTests(unittest.TestCase):
    """Check the documented command and its protections in temporary repositories."""

    def test_protected_command_is_required_in_normative_directives(self) -> None:
        command = "git merge --ff-only --no-overwrite-ignore --no-autostash origin/main"
        process = (ROOT / "docs" / "PROCESS.md").read_text()
        review = (ROOT / "skills" / "development-review" / "SKILL.md").read_text()
        executor = (ROOT / "skills" / "delegation-executor" / "SKILL.md").read_text()

        process_directives = [line.lower() for line in process.splitlines() if command in line]
        self.assertEqual(len(process_directives), 1)
        self.assertIn("run `" + command + "`", process_directives[0])
        self.assertIn("strict ancestor", process_directives[0])
        self.assertIn("from the verified primary root", process_directives[0])

        review_directives = [line.lower() for line in review.splitlines() if command in line]
        self.assertEqual(len(review_directives), 2)
        codex_directive = next(line for line in review_directives if "prompt must include" in line)
        self.assertIn("eligible fast-forward", codex_directive)
        self.assertIn("no additional approval", codex_directive)
        chatgpt_directive = next(line for line in review_directives if "chatgpt-implemented task" in line)
        self.assertIn("run `" + command + "`", chatgpt_directive)
        self.assertIn("without another approval", chatgpt_directive)

        executor_directives = [line.lower() for line in executor.splitlines() if command in line]
        self.assertEqual(len(executor_directives), 1)
        self.assertIn("when §11's checks allow a fast-forward, run `" + command + "`", executor_directives[0])
        self.assertIn("without a second owner approval", executor_directives[0])

    def test_process_documents_the_full_primary_sync_safety_contract(self) -> None:
        process = (ROOT / "docs" / "PROCESS.md").read_text().lower()
        required_fragments = (
            "primary checkout root and repository identity",
            "configured `origin` points to the intended repository",
            "current branch to be `main`",
            "index and tracked/untracked working tree to be clean",
            "successful fetch using the configured credentials",
            "merge-base --is-ancestor head origin/main",
            "immediately before the merge",
            "incoming paths against ignored files",
            "verified no-op",
            "do not run the merge",
            "strict ancestor",
            "git merge --ff-only --no-overwrite-ignore --no-autostash origin/main",
            "no additional approval",
            "merged — cleanup pending",
            "not applicable",
            "keep the issue open until the required synchronization is verified",
        )

        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment.lower(), process)

    def test_review_closeout_waits_for_verified_primary_sync(self) -> None:
        review = (ROOT / "skills" / "development-review" / "SKILL.md").read_text().lower()
        closeout_section = review.split("## close out an authorized change", 1)[1].split("\n## ", 1)[0]
        closeout_step = next(line for line in closeout_section.splitlines() if line.startswith("3."))
        required_fragments = (
            "required checks pass",
            "accepted scope is complete",
            "completed as a fast-forward and passed verification",
            "verified as an already-current no-op",
            "verified remote-only implementation makes task-worktree cleanup inapplicable",
            "primary-main synchronization is inapplicable only when task-bound evidence verifies that the remote-only task has no primary checkout",
            "if applicable primary-main synchronization is blocked or unverified, keep the issue open and block discovery",
            "deferred obligations",
            "formally transferred",
        )

        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, closeout_step)

    def test_review_scenario_closeout_states_match_sync_outcomes(self) -> None:
        scenarios = (ROOT / "skills" / "development-review" / "tests" / "scenarios.md").read_text()
        expected_outcomes = (
            ("CLEANUP-PRIMARY-FAST-FORWARD", "Keep Issue #96 open until Codex completes and verifies synchronization"),
            ("CLEANUP-PRIMARY-CHATGPT", "Keep Issue #99 open until the operation and verification succeed"),
            ("CLEANUP-PRIMARY-IDENTITY-UNKNOWN", "Keep Issue #100 open"),
            ("CLEANUP-PRIMARY-BLOCKED", "Keep Issue #102 open"),
            ("CLEANUP-PRIMARY-REMOTE-ONLY", "Issue #101 may remain closed because the verified remote-only exception makes synchronization inapplicable"),
        )

        for scenario, expected_outcome_fragment in expected_outcomes:
            with self.subTest(scenario=scenario):
                start = scenarios.index(f"## {scenario}:")
                end = scenarios.find("\n## ", start + 1)
                scenario_text = scenarios[start:end if end >= 0 else None]
                expected_outcome = scenario_text.split("Expected outcome:", 1)[1].split("\n\n**Evaluation record:**", 1)[0]
                self.assertIn(expected_outcome_fragment, expected_outcome)

    def test_scenario_evaluation_anchors_are_standalone_lines(self) -> None:
        evaluations = (ROOT / "tests" / "primary_main_fast_forward_evaluations.md").read_text()
        anchor_lines = [line for line in evaluations.splitlines() if "<a id=" in line]

        self.assertTrue(anchor_lines)
        for line in anchor_lines:
            with self.subTest(anchor=line):
                self.assertRegex(line, r'^<a id="[^"]+"></a>$')

    def test_skills_defer_safety_details_and_retain_actor_requirements(self) -> None:
        review = (ROOT / "skills" / "development-review" / "SKILL.md").read_text().lower()
        executor = (ROOT / "skills" / "delegation-executor" / "SKILL.md").read_text().lower()
        command = "git merge --ff-only --no-overwrite-ignore --no-autostash origin/main"

        self.assertIn("§11", review)
        self.assertIn(command, review)
        self.assertIn("no additional approval", review)
        self.assertIn("chatgpt-implemented task", review)
        self.assertIn("§11", executor)
        self.assertIn(command, executor)
        self.assertIn("without a second owner approval", executor)
        self.assertIn("do not interpret the prohibition on force-updating `main`", executor)
        for skill_name, content in (("development-review", review), ("delegation-executor", executor)):
            with self.subTest(skill=skill_name):
                self.assertNotIn("incoming paths against ignored files", content)
                self.assertNotIn("equal shas", content)

    def test_scenarios_cover_required_primary_sync_outcomes(self) -> None:
        scenarios = ROOT / "skills" / "delegation-executor" / "tests" / "scenarios.md"
        content = scenarios.read_text()
        required_cases = (
            "POSTMERGE-PRIMARY-FAST-FORWARD",
            "POSTMERGE-PRIMARY-ALREADY-CURRENT",
            "POSTMERGE-PRIMARY-DIRTY",
            "POSTMERGE-PRIMARY-DIVERGED",
            "POSTMERGE-PRIMARY-WRONG-BRANCH",
            "POSTMERGE-PRIMARY-DETACHED",
            "POSTMERGE-PRIMARY-ORIGIN-MISMATCH",
            "POSTMERGE-PRIMARY-FETCH-FAILURE",
            "POSTMERGE-PRIMARY-IGNORED-CONFLICT",
            "POSTMERGE-PRIMARY-IGNORED-NONCONFLICT",
            "POSTMERGE-PRIMARY-UNAVAILABLE",
            "POSTMERGE-PRIMARY-REMOTE-ONLY",
            "POSTMERGE-PRIMARY-AMBIGUOUS",
        )

        evaluations = (ROOT / "tests" / "primary_main_fast_forward_evaluations.md").read_text()
        for scenario in required_cases:
            anchor = scenario.lower()
            with self.subTest(scenario=scenario):
                self.assertIn(f"## {scenario}", content)
                self.assertIn(f'<a id="{anchor}"></a>', evaluations)
                start = evaluations.index(f'<a id="{anchor}"></a>')
                next_anchor = evaluations.find('<a id="', start + 1)
                case_record = evaluations[start:next_anchor if next_anchor >= 0 else None]
                self.assertRegex(case_record, r"(?im)^\*\*Current evaluation status:\*\* PASS\b")

    def test_review_scenarios_preserve_ownership_and_applicability(self) -> None:
        scenarios = ROOT / "skills" / "development-review" / "tests" / "scenarios.md"
        content = scenarios.read_text()
        evaluations = (ROOT / "tests" / "primary_main_fast_forward_evaluations.md").read_text()
        required_cases = (
            "CLEANUP-PRIMARY-FAST-FORWARD",
            "CLEANUP-PRIMARY-BLOCKED",
            "CLEANUP-PRIMARY-CHATGPT",
            "CLEANUP-PRIMARY-REMOTE-ONLY",
            "CLEANUP-PRIMARY-IDENTITY-UNKNOWN",
        )

        for scenario in required_cases:
            anchor = scenario.lower()
            with self.subTest(scenario=scenario):
                self.assertIn(f"## {scenario}", content)
                self.assertIn(f'<a id="{anchor}"></a>', evaluations)
                start = evaluations.index(f'<a id="{anchor}"></a>')
                next_anchor = evaluations.find('<a id="', start + 1)
                case_record = evaluations[start:next_anchor if next_anchor >= 0 else None]
                self.assertRegex(case_record, r"(?im)^\*\*Current evaluation status:\*\* PASS\b")

    def test_clean_behind_primary_advances_to_fetched_origin_main(self) -> None:
        with tempfile.TemporaryDirectory(prefix="primary-fast-forward-") as directory:
            primary, writer = self._repositories(Path(directory))
            (writer / "release.txt").write_text("release 2\n")
            self._git(writer, "add", "release.txt")
            self._commit(writer, "Advance origin/main")
            self._git(writer, "push", "origin", "main")

            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            self._fetch_and_check_ancestry(primary)
            fetched = self._git(primary, "rev-parse", "origin/main").stdout.strip()
            self.assertNotEqual(before, fetched)

            result = self._git(primary, *SAFE_MERGE)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), fetched)
            self.assertEqual(self._git(primary, "branch", "--show-current").stdout.strip(), "main")
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")

    def test_policy_noop_requires_equal_shas_and_skips_merge(self) -> None:
        process = (ROOT / "docs" / "PROCESS.md").read_text().lower()
        equal_sha_rule = next(line for line in process.splitlines() if "if the shas match" in line)

        self.assertIn("verified no-op", equal_sha_rule)
        self.assertIn("do not run the merge", equal_sha_rule)

    def test_git_allows_fast_forward_merge_when_already_current(self) -> None:
        """Document Git behavior separately from the policy's no-merge no-op."""
        with tempfile.TemporaryDirectory(prefix="git-equal-shas-") as directory:
            primary, _ = self._repositories(Path(directory))
            self._fetch_and_check_ancestry(primary)
            local = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            fetched = self._git(primary, "rev-parse", "origin/main").stdout.strip()
            self.assertEqual(local, fetched)

            result = self._git(primary, *SAFE_MERGE)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), local)
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")

    def test_conflicting_ignored_file_blocks_merge_and_preserves_local_data(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ignored-conflict-") as directory:
            primary, writer = self._repositories(Path(directory))
            ignored_file = primary / "owner-data.db"
            ignored_file.write_text("local sole copy\n")
            (writer / "owner-data.db").write_text("upstream file\n")
            self._git(writer, "add", "-f", "owner-data.db")
            self._commit(writer, "Add a path ignored in the primary checkout")
            self._git(writer, "push", "origin", "main")

            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(self._git(primary, "check-ignore", "owner-data.db").returncode, 0)
            self._fetch_and_check_ancestry(primary)
            fetched = self._git(primary, "rev-parse", "origin/main").stdout.strip()

            result = self._git(primary, *SAFE_MERGE, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), before)
            self.assertNotEqual(before, fetched)
            self.assertEqual(ignored_file.read_text(), "local sole copy\n")
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")

    def test_nonconflicting_ignored_file_survives_fast_forward(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ignored-safe-") as directory:
            primary, writer = self._repositories(Path(directory))
            ignored_file = primary / "cache" / "local-index.bin"
            ignored_file.parent.mkdir()
            ignored_file.write_bytes(b"local cache")
            (writer / "release.txt").write_text("release 2\n")
            self._git(writer, "add", "release.txt")
            self._commit(writer, "Advance without touching ignored data")
            self._git(writer, "push", "origin", "main")

            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            self._fetch_and_check_ancestry(primary)
            fetched = self._git(primary, "rev-parse", "origin/main").stdout.strip()
            self.assertNotEqual(before, fetched)

            result = self._git(primary, *SAFE_MERGE)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), fetched)
            self.assertEqual(self._git(primary, "branch", "--show-current").stdout.strip(), "main")
            self.assertEqual(ignored_file.read_bytes(), b"local cache")
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")

    def test_no_autostash_leaves_a_dirty_checkout_untouched(self) -> None:
        with tempfile.TemporaryDirectory(prefix="no-autostash-") as directory:
            primary, writer = self._repositories(Path(directory))
            self._git(primary, "config", "merge.autoStash", "true")
            (writer / "README.md").write_text("upstream edit\n")
            self._git(writer, "add", "README.md")
            self._commit(writer, "Advance origin/main")
            self._git(writer, "push", "origin", "main")
            (primary / "README.md").write_text("local edit\n")
            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            self._fetch_and_check_ancestry(primary)

            result = self._git(primary, *SAFE_MERGE, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), before)
            self.assertEqual((primary / "README.md").read_text(), "local edit\n")
            self.assertEqual(self._git(primary, "stash", "list").stdout, "")

    def test_diverged_history_fails_ancestry_gate_without_moving_main(self) -> None:
        with tempfile.TemporaryDirectory(prefix="diverged-main-") as directory:
            primary, writer = self._repositories(Path(directory))
            (primary / "local.txt").write_text("local commit\n")
            self._git(primary, "add", "local.txt")
            self._commit(primary, "Advance local main")
            (writer / "remote.txt").write_text("remote commit\n")
            self._git(writer, "add", "remote.txt")
            self._commit(writer, "Advance origin/main")
            self._git(writer, "push", "origin", "main")

            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            self._fetch_and_check_ancestry(primary, expect_ancestor=False)
            fetched = self._git(primary, "rev-parse", "origin/main").stdout.strip()

            self.assertNotEqual(before, fetched)
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), before)

    def test_unavailable_origin_fetch_preserves_local_head_and_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="origin-unavailable-") as directory:
            primary, _ = self._repositories(Path(directory))
            before = self._git(primary, "rev-parse", "HEAD").stdout.strip()
            stale_remote = self._git(primary, "rev-parse", "origin/main").stdout.strip()
            missing_origin = Path(directory) / "missing-origin.git"
            self._git(primary, "remote", "set-url", "origin", str(missing_origin))

            fetch = self._git(primary, "fetch", "origin", check=False)

            self.assertNotEqual(fetch.returncode, 0)
            self.assertEqual(self._git(primary, "rev-parse", "HEAD").stdout.strip(), before)
            self.assertEqual(self._git(primary, "rev-parse", "origin/main").stdout.strip(), stale_remote)
            self.assertEqual(self._git(primary, "status", "--porcelain").stdout, "")

    def _repositories(self, root: Path) -> tuple[Path, Path]:
        """Create a bare origin, its clean primary checkout, and a remote writer."""
        origin = root / "origin.git"
        primary = root / "primary"
        writer = root / "writer"
        self._git(root, "init", "--bare", "--initial-branch=main", str(origin))
        self._git(root, "init", "--initial-branch=main", str(primary))
        self._configure_identity(primary)
        (primary / ".gitignore").write_text("owner-data.db\ncache/\n")
        (primary / "README.md").write_text("release 1\n")
        self._git(primary, "add", ".gitignore", "README.md")
        self._commit(primary, "Initial commit")
        self._git(primary, "remote", "add", "origin", str(origin))
        self._git(primary, "push", "-u", "origin", "main")
        self._git(root, "clone", str(origin), str(writer))
        self._configure_identity(writer)
        return primary, writer

    def _fetch_and_check_ancestry(self, primary: Path, *, expect_ancestor: bool = True) -> None:
        """Refresh origin/main and check whether the local tip can fast-forward."""
        self._git(primary, "fetch", "origin")
        result = self._git(primary, "merge-base", "--is-ancestor", "HEAD", "origin/main", check=False)
        self.assertEqual(result.returncode == 0, expect_ancestor)

    def _commit(self, repository: Path, message: str) -> None:
        self._git(repository, "commit", "--quiet", "-m", message)

    def _configure_identity(self, repository: Path) -> None:
        self._git(repository, "config", "user.name", "Primary Sync Fixture")
        self._git(repository, "config", "user.email", "primary-sync-fixture@example.invalid")

    def _git(self, cwd: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
