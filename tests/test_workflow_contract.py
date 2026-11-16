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
    def _markdown_section(markdown: str, title: str, end_title: str) -> str:
        lines = markdown.splitlines()
        target_heading = f"## {title}"
        end_heading = f"## {end_title}"
        try:
            target_index = lines.index(target_heading)
        except ValueError:
            raise AssertionError(f"Markdown section not found: {title}")
        try:
            end_index = lines.index(end_heading, target_index + 1)
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
            "selector": "newest_verified_immutable_release",
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
                    "verified_release_version",
                )
            elif scenario["kind"] == "in-flight-task":
                self.assertIn(scenario["existing_pin"], HISTORICAL_POLICY_REVISIONS)
                self.assertEqual(
                    scenario["expected"],
                    "existing_pin",
                )
            else:
                self.fail(f"Unknown policy scenario: {scenario['kind']}")

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

class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.safe_load(
            (ROOT / ".github/workflows/skill-release.yml").read_text()
        )

    def test_only_owner_manual_main_dispatch_can_enter_preflight(self) -> None:
        triggers = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        self.assertTrue(triggers["workflow_dispatch"]["inputs"]["source_revision"]["required"])
        guard = self.workflow["jobs"]["preflight"]["if"]
        for predicate in (
            "github.repository == 'danielbyon/development-process'",
            "github.actor == 'danielbyon'",
            "github.triggering_actor == 'danielbyon'",
            "github.ref == 'refs/heads/main'",
        ):
            self.assertIn(predicate, guard)
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])

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

    def test_workflow_write_requires_explicit_owner_variable(self) -> None:
        jobs = self.workflow["jobs"]
        for job_name, operation in (("preflight", "preflight"), ("publication", "publish")):
            step = next(s for s in jobs[job_name]["steps"]
                        if f"skill_release.py {operation}" in s.get("run", ""))
            self.assertEqual(step["env"]["RELEASE_WORKFLOW_WRITE_AUTHORIZED"],
                             "${{ vars.RELEASE_WORKFLOW_WRITE_AUTHORIZED }}")
        publication = next(s for s in jobs["publication"]["steps"]
                           if "skill_release.py publish" in s.get("run", ""))
        self.assertEqual(publication["env"]["RELEASE_WORKFLOW_WRITE_TOKEN"],
                         "${{ secrets.RELEASE_WORKFLOW_WRITE_TOKEN }}")
        triggers = self.workflow.get("on", self.workflow.get(True))
        reference = triggers["workflow_dispatch"]["inputs"]["evidence_reference"]
        self.assertFalse(reference["required"])
        preflight = next(s for s in jobs["preflight"]["steps"]
                         if "skill_release.py preflight" in s.get("run", ""))
        self.assertEqual(preflight["env"]["RELEASE_EVIDENCE_REFERENCE"],
                         "${{ inputs.evidence_reference }}")

    def test_attempt_bound_artifacts_and_original_run_lookup(self) -> None:
        for job in self.workflow["jobs"].values():
            for step in job["steps"]:
                if "artifact@" in step.get("uses", ""):
                    self.assertIn("github.run_attempt", step["with"]["name"])
        preflight = next(s for s in self.workflow["jobs"]["preflight"]["steps"] if "preflight" in s.get("run", ""))
        self.assertEqual(preflight["env"]["RELEASE_RUN_ID"], "${{ github.run_id }}")
        self.assertIn('--run-attempt "$RELEASE_RUN_ATTEMPT"', preflight["run"])
        self.assertNotIn("date ", preflight["run"])

    def test_optional_tag_hardening_allows_creation(self) -> None:
        ruleset = json.loads((ROOT / ".github/rulesets/calver-tags.json").read_text())
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["bypass_actors"], [])
        self.assertEqual({r["type"] for r in ruleset["rules"]}, {"update", "deletion"})
        self.assertEqual(len(ruleset["conditions"]["ref_name"]["include"]), 2)


if __name__ == "__main__":
    unittest.main()
