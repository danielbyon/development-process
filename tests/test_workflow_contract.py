from __future__ import annotations

import json
import os
import subprocess
import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path

import yaml

from test_skill_distribution import (
    HISTORICAL_POLICY_REVISIONS,
    ROOT,
)


class WorkflowContractTests(unittest.TestCase):
    @staticmethod
    def _markdown_section(markdown: str, title: str, end_title: str | None) -> str:
        lines = markdown.splitlines()
        target_heading = f"## {title}"
        try:
            target_index = lines.index(target_heading)
        except ValueError:
            raise AssertionError(f"Markdown section not found: {title}")
        if end_title is None:
            return "\n".join(lines[target_index + 1:]).casefold()
        try:
            end_index = lines.index(f"## {end_title}", target_index + 1)
        except ValueError:
            raise AssertionError(f"Markdown section boundary not found: {end_title}")
        return "\n".join(lines[target_index + 1:end_index]).casefold()

    def test_ci_packages_from_the_exact_pr_source_commit(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        )
        steps = workflow["jobs"]["committed-pr-diff"]["steps"]
        source_checkout = next(
            step
            for step in steps
            if step.get("name") == "Check out the exact PR source for package provenance"
        )
        package_source = source_checkout["with"]
        self.assertEqual(
            package_source["ref"],
            "${{ github.event.pull_request.head.sha }}",
        )
        package_step = next(
            step
            for step in steps
            if step.get("name") == "Build and verify packages against the PR source commit"
        )
        self.assertIn(
            f'source_root="$GITHUB_WORKSPACE/{package_source["path"]}"',
            package_step["run"],
        )
        self.assertEqual(package_step["env"]["EXPECTED_SOURCE_SHA"], package_source["ref"])
        self.assertEqual(package_step["env"]["EXPECTED_BUILDER_SHA"], "${{ github.sha }}")
        command = package_step["run"]
        self.assertIn('log --first-parent -1 --format=%H "$EXPECTED_SOURCE_SHA" -- docs/PROCESS.md', command)
        self.assertIn('fetch --no-tags "$GITHUB_WORKSPACE" "$EXPECTED_BUILDER_SHA"', command)
        self.assertIn('package_dir="$candidate_root/packages"', command)
        self.assertNotIn('mkdir "$package_dir"', command)
        for operation in ("release-package", "release-verify"):
            self.assertIn(f"python3 scripts/skill_distribution.py {operation}", command)
        self.assertEqual(command.count('--context "$CANDIDATE_CONTEXT"'), 2)
        self.assertNotIn("git push", command)
        self.assertNotIn("gh release", command)
        subprocess.run(["bash", "-n"], input=command, text=True, check=True)

    def test_trusted_main_git_integration_runs_in_pull_request_ci(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        steps = workflow["jobs"]["committed-pr-diff"]["steps"]
        integration = next(
            (step for step in steps if step.get("name") == "Run trusted-main release integration tests"),
            None,
        )
        self.assertIsNotNone(integration)
        self.assertEqual(integration["env"], {"PYTHONSAFEPATH": "1"})
        self.assertEqual(
            integration["run"],
            "python3 -m unittest discover -s tests -p trusted_main_integration_tests.py -v",
        )

    def test_ci_candidate_context_is_unpublished_and_binds_distinct_revisions(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        step = next(s for s in workflow["jobs"]["committed-pr-diff"]["steps"]
                    if s.get("name") == "Build and verify packages against the PR source commit")
        generator = step["run"].split("python3 - <<'CONTEXT'\n", 1)[1].split("\nCONTEXT", 1)[0]
        with tempfile.TemporaryDirectory(prefix="candidate-context-") as temporary:
            context_path = Path(temporary) / "context.json"
            environment = {
                "CANDIDATE_CONTEXT": str(context_path),
                "EXPECTED_SOURCE_SHA": "a" * 40,
                "POLICY_REVISION": "b" * 40,
                "EXPECTED_BUILDER_SHA": "c" * 40,
            }
            with patch.dict(os.environ, environment):
                exec(compile(generator, "<CI candidate context>", "exec"), {})
            self.assertEqual(json.loads(context_path.read_text()), {
                "release_version": "2000.01.01",
                "source_revision": "a" * 40,
                "policy_revision": "b" * 40,
                "builder_revision": "c" * 40,
                "qualification_only": True,
            })

    def test_ci_retains_required_check_and_mandatory_suites(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        job = workflow["jobs"]["committed-pr-diff"]
        self.assertEqual(job["name"], "Validate committed PR integration diff")
        for suite in (
            "test_workflow_contract.py", "test_skill_distribution.py",
            "test_distribution_smoke.py", "test_primary_main_fast_forward.py",
            "test_skill_releases.py", "test_github_releases.py",
        ):
            step = next(s for s in job["steps"] if suite in s.get("run", ""))
            self.assertNotIn("if", step)
            self.assertNotIn("continue-on-error", step)

    def test_shipped_skills_satisfy_workflow_contract_fixture(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )
        self.assertEqual(fixture["new_task_resolution"], {
            "selector": "newest_qualified_immutable_release",
            "recorded_pin": "release_version",
            "failure": "fail_closed",
            "continuation": "preserve_existing_pin",
        })
        manifest = json.loads((ROOT / "skills" / "distribution.json").read_text())
        self.assertEqual(manifest["schema_version"], 2)
        for phase in fixture["phases"]:
            skill = (
                ROOT / "skills" / phase["skill"] / "SKILL.md"
            ).read_text().casefold()
            for required_contract in phase["contract"]:
                self.assertIn(required_contract.casefold(), skill)

        in_flight_pins = {
            scenario["existing_pin"]
            for scenario in fixture["policy_scenarios"]
            if scenario["kind"] == "in-flight-task"
        }
        self.assertEqual(in_flight_pins, set(HISTORICAL_POLICY_REVISIONS))

        for scenario in fixture["policy_scenarios"]:
            if scenario["kind"] == "new-task":
                self.assertEqual(
                    scenario["expected"],
                    "qualified_release_version",
                )
            elif scenario["kind"] == "in-flight-task":
                self.assertIn(scenario["existing_pin"], HISTORICAL_POLICY_REVISIONS)
                self.assertEqual(
                    scenario["expected"],
                    "existing_pin",
                )
            else:
                self.fail(f"Unknown policy scenario: {scenario['kind']}")

    def test_development_review_activation_metadata_covers_closeout_triggers(self) -> None:
        skill_path = ROOT / "skills" / "development-review" / "SKILL.md"
        skill_markdown = skill_path.read_text()
        _, separator, frontmatter_and_body = skill_markdown.partition("---")
        self.assertEqual(separator, "---")
        frontmatter, separator, _ = frontmatter_and_body.partition("---")
        self.assertEqual(separator, "---")
        skill_description = yaml.safe_load(frontmatter)["description"].casefold()

        for trigger in (
            "`implemented`",
            "`review feedback`",
            "merge readiness",
            "`merge`",
            "`close this out`",
            "reports cleanup complete",
            "post-closeout issue discovery",
        ):
            with self.subTest(trigger=trigger):
                self.assertIn(trigger, skill_description)

        skill_intro = next(
            line
            for line in skill_markdown.splitlines()
            if line.startswith("Use this Skill ")
        ).casefold()
        for trigger in (
            "`implemented`",
            "`review feedback`",
            "readiness, `merge`",
            "`close this out`",
            "reports cleanup complete",
            "requests post-closeout issue discovery",
        ):
            with self.subTest(intro_trigger=trigger):
                self.assertIn(trigger, skill_intro)

        agent_metadata = yaml.safe_load(
            (
                ROOT
                / "skills"
                / "development-review"
                / "agents"
                / "openai.yaml"
            ).read_text()
        )
        agent_description = agent_metadata["interface"]["short_description"].casefold()
        self.assertIn("cleanup", agent_description)
        self.assertIn("post-closeout issue discovery", agent_description)

    def test_skill_sections_satisfy_workflow_contracts(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )
        for contract in fixture["workflow_contracts"]:
            skill = (
                ROOT / "skills" / contract["skill"] / "SKILL.md"
            ).read_text()
            section = self._markdown_section(
                skill,
                contract["heading"],
                contract["end_heading"],
            )
            with self.subTest(skill=contract["skill"], heading=contract["heading"]):
                for required in contract["required"]:
                    self.assertIn(required.casefold(), section)
                for forbidden in contract["forbidden"]:
                    self.assertNotIn(forbidden.casefold(), section)

    def test_post_closeout_contract_explicitly_forbids_hosted_compatibility_gates(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )
        expected_forbidden = {
            "compatible Skill identity",
            "hosted installation",
            "payload compatibility",
            "session revision",
            "session compatibility",
        }
        contracts = [
            contract
            for contract in fixture["workflow_contracts"]
            if contract["skill"] == "development-review"
            and contract["heading"] == "Post-closeout issue discovery"
        ]
        contracts += [
            contract
            for contract in fixture["policy_contracts"]
            if contract["heading"] in {
                "11. Merge/closeout/cleanup",
                "12. Distribution/pinning",
            }
        ]
        self.assertEqual(len(contracts), 3)
        for contract in contracts:
            with self.subTest(heading=contract["heading"]):
                if contract["heading"] == "12. Distribution/pinning":
                    expected = {
                        "compatible Skill identity",
                        "hosted compatibility check",
                        "hosted installation is required",
                        "verify hosted installation before discovery",
                        "session compatibility check",
                        "verify session revision before discovery",
                        "payload compatibility check",
                    }
                else:
                    expected = expected_forbidden
                self.assertTrue(expected.issubset(set(contract["forbidden"])))

    def test_mcp_root_registry_workflow_contract(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )
        for contract in fixture["mcp_registry_contracts"]:
            section = self._markdown_section(
                (ROOT / contract["path"]).read_text(),
                contract["heading"],
                contract["end_heading"],
            )
            for required in contract["required"]:
                with self.subTest(path=contract["path"], heading=contract["heading"], required=required):
                    self.assertIn(required.casefold(), section)

    def test_policy_sections_preserve_workflow_and_distribution_obligations(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )
        policy = (ROOT / "docs" / "PROCESS.md").read_text()
        for contract in fixture["policy_contracts"]:
            section = self._markdown_section(
                policy,
                contract["heading"],
                contract["end_heading"],
            )
            with self.subTest(heading=contract["heading"]):
                for required in contract["required"]:
                    self.assertIn(required.casefold(), section)
                for forbidden in contract["forbidden"]:
                    self.assertNotIn(forbidden.casefold(), section)

    def test_cleanup_scenarios_cover_disposable_cache_boundaries(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "workflow_contract.json").read_text()
        )

        for contract in fixture["scenario_contracts"]:
            scenarios = (ROOT / contract["path"]).read_text().casefold()
            for required in contract["required"]:
                with self.subTest(path=contract["path"], required=required):
                    self.assertIn(required.casefold(), scenarios)

            expected_scenarios = {
                required.casefold()
                for required in contract["required"]
                if required.startswith("DISPOSABLE-TOOL-CACHE-")
            }
            run_id_pattern = (
                r"independent evaluator `"
                r"[0-9a-f]{8}-[0-9a-f]{4}-"
                r"[0-9a-f]{4}-[0-9a-f]{4}-"
                r"[0-9a-f]{12}`"
            )
            scenario_sections = []
            for section in scenarios.split("\n## "):
                heading, _, body = section.partition("\n")
                if heading.startswith("disposable-tool-cache-"):
                    scenario_sections.append((heading, body))

            self.assertCountEqual(
                expected_scenarios,
                [heading for heading, _ in scenario_sections],
            )
            eligibility_section = next(
                section
                for heading, section in scenario_sections
                if heading == "disposable-tool-cache-eligibility"
            )
            for required in contract["eligibility_required"]:
                with self.subTest(path=contract["path"], eligibility=required):
                    self.assertIn(required.casefold(), eligibility_section)

            for heading, section in scenario_sections:
                with self.subTest(
                    path=contract["path"],
                    scenario=heading,
                ):
                    run_record_marker = "**run record:** pass"
                    self.assertIn(run_record_marker, section)
                    current_record = section.split(run_record_marker, maxsplit=1)[1]
                    self.assertIn("- observed result:", current_record)
                    self.assertIn("- evidence:", current_record)
                    self.assertRegex(current_record, run_id_pattern)


class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.safe_load(
            (ROOT / ".github/workflows/skill-release.yml").read_text()
        )

    def test_only_owner_manual_main_dispatch_can_enter_preflight(self) -> None:
        triggers = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        self.assertEqual(set(triggers["workflow_dispatch"]["inputs"]),
                         {"supersedes", "correction_reason"})
        guard = self.workflow["jobs"]["preflight"]["if"]
        for predicate in (
            "github.repository == 'danielbyon/development-process'",
            "github.actor == 'danielbyon'",
            "github.triggering_actor == 'danielbyon'",
            "github.ref == 'refs/heads/main'",
        ):
            self.assertIn(predicate, guard)
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])

    def test_release_source_and_builder_are_the_dispatch_sha(self) -> None:
        triggers = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(set(triggers["workflow_dispatch"].get("inputs", {})),
                         {"supersedes", "correction_reason"})
        for job in self.workflow["jobs"].values():
            checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
            self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
        preflight = next(s for s in self.workflow["jobs"]["preflight"]["steps"]
                         if "skill_release.py preflight" in s.get("run", ""))
        self.assertNotIn("--source-revision", preflight["run"])
        self.assertNotIn("--builder-revision", preflight["run"])
        self.assertNotIn("SOURCE_REVISION", preflight.get("env", {}))
        self.assertNotIn("BUILDER_REVISION", preflight.get("env", {}))
        self.assertNotIn("RELEASE_EVIDENCE_REFERENCE", preflight.get("env", {}))
        encoded = json.dumps(self.workflow)
        self.assertNotIn("RELEASE_WORKFLOW_WRITE_AUTHORIZED", encoded)
        self.assertNotIn("RELEASE_WORKFLOW_WRITE_TOKEN", encoded)

    def test_credentials_are_isolated_from_qualification(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        jobs = self.workflow["jobs"]
        self.assertEqual(jobs["publication"]["permissions"], {"contents": "write", "actions": "read", "attestations": "read"})
        self.assertEqual(jobs["preflight"]["permissions"], {"contents": "read", "actions": "read"})
        self.assertEqual(jobs["publication"]["needs"], ["preflight", "qualification", "attestation"])
        self.assertNotIn("secrets.", json.dumps(jobs["qualification"]))
        self.assertNotIn("write", json.dumps(jobs["qualification"]))
        for job in jobs.values():
            checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
            self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
            self.assertFalse(checkout["with"]["persist-credentials"])
        steps = jobs["publication"]["steps"]
        rebuild = next(i for i, s in enumerate(steps) if "verify-bundle" in s.get("run", ""))
        publish = next(i for i, s in enumerate(steps) if "skill_release.py publish" in s.get("run", ""))
        self.assertLess(rebuild, publish)
        self.assertNotIn("env", steps[rebuild])
        self.assertIn("RELEASE_ADMIN_READ_TOKEN", steps[publish]["env"])

    def test_attestation_is_isolated_and_signs_only_verified_manifest(self) -> None:
        job = self.workflow["jobs"]["attestation"]
        self.assertEqual(job["needs"], ["preflight", "qualification"])
        self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write", "attestations": "write"})
        self.assertNotIn("secrets.", json.dumps(job))
        steps = job["steps"]
        verify = next(i for i, step in enumerate(steps) if "verify-bundle" in step.get("run", ""))
        sign = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/attest@"))
        self.assertLess(verify, sign)
        self.assertIn("--for-attestation", steps[verify]["run"])
        self.assertEqual(steps[sign]["uses"], "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6")
        self.assertEqual(steps[sign]["with"], {"subject-path": "${{ runner.temp }}/release-bundle/release-manifest.json", "push-to-registry": False, "create-storage-record": False})
        self.assertNotIn("continue-on-error", json.dumps(job))

    def test_immutable_release_read_uses_admin_credential_without_workflow_write(self) -> None:
        jobs = self.workflow["jobs"]
        for job_name, operation in (("preflight", "preflight"), ("publication", "publish")):
            step = next(s for s in jobs[job_name]["steps"]
                        if f"skill_release.py {operation}" in s.get("run", ""))
            self.assertEqual(step["env"]["RELEASE_ADMIN_READ_TOKEN"],
                             "${{ secrets.RELEASE_ADMIN_READ_TOKEN }}")
        encoded = json.dumps(self.workflow)
        self.assertNotIn("RELEASE_WORKFLOW_WRITE_AUTHORIZED", encoded)
        self.assertNotIn("RELEASE_WORKFLOW_WRITE_TOKEN", encoded)
        self.assertNotIn("evidence_reference", encoded)

    def test_attempt_bound_artifacts_and_original_run_lookup(self) -> None:
        for job in self.workflow["jobs"].values():
            for step in job["steps"]:
                if "artifact@" in step.get("uses", ""):
                    self.assertIn("github.run_attempt", step["with"]["name"])
        preflight = next(s for s in self.workflow["jobs"]["preflight"]["steps"] if "preflight" in s.get("run", ""))
        self.assertIn('--run-id "$GITHUB_RUN_ID"', preflight["run"])
        self.assertIn('--run-attempt "$GITHUB_RUN_ATTEMPT"', preflight["run"])
        self.assertNotIn("date ", preflight["run"])

    def test_review_and_merge_authorization_remain_premerge_requirements(self) -> None:
        process = (ROOT / "docs/PROCESS.md").read_text()
        review_and_ci = process.split("## 6. Independent review", 1)[1].split("## 9.", 1)[0]
        self.assertIn("independent review", review_and_ci.lower())
        self.assertIn("chatgpt inspection", review_and_ci.lower())
        self.assertIn("required ci", review_and_ci.lower())
        self.assertIn("owner explicitly authorizes merging", review_and_ci.lower())

    def test_release_docs_use_trusted_main_without_receipt_or_baseline_gates(self) -> None:
        guide = (ROOT / "docs/skill-releases.md").read_text().casefold()
        policy = (ROOT / "docs/PROCESS.md").read_text().casefold()
        decisions = (ROOT / "docs/DECISIONS.md").read_text().casefold()
        adr = (ROOT / "docs/adr/0001-immutable-skill-releases.md").read_text().casefold()
        for required in (
            "github.sha", "source and builder", "authenticated `main` ref", "ancestor",
            "policy revision", "all six required test suites",
            "eight assets", "immutable-release capability endpoint",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)
        self.assertIn("does not reconstruct pr review receipts", policy)
        self.assertIn("no baseline-admission step", policy)
        self.assertIn("release evidence chronology and prospective baseline — superseded", decisions)
        self.assertIn("current owner decision (2026-11-17)", decisions)
        self.assertIn("superseded by the owner-approved issue #32 decision", adr)
        for obsolete in ("capture-execution", "prepare-index", "admit-baseline"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, guide)

    def test_optional_tag_hardening_allows_creation(self) -> None:
        ruleset = json.loads((ROOT / ".github/rulesets/calver-tags.json").read_text())
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["bypass_actors"], [])
        self.assertEqual({r["type"] for r in ruleset["rules"]}, {"update", "deletion"})
        self.assertEqual(len(ruleset["conditions"]["ref_name"]["include"]), 2)


if __name__ == "__main__":
    unittest.main()
