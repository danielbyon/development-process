from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from test_skill_distribution import (
    HISTORICAL_POLICY_REVISIONS,
    POLICY_REVISION,
    ROOT,
)


class Issue5WorkflowSmokeTests(unittest.TestCase):
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

    def test_shipped_skills_satisfy_workflow_contract_fixture(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "issue5_workflow.json").read_text()
        )
        self.assertEqual(
            fixture["approved_policy_revision"],
            POLICY_REVISION,
        )
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
                    "approved_policy_revision",
                )
            elif scenario["kind"] == "in-flight-task":
                self.assertIn(scenario["existing_pin"], HISTORICAL_POLICY_REVISIONS)
                self.assertEqual(
                    scenario["expected"],
                    "existing_pin",
                )
            else:
                self.fail(f"Unknown policy scenario: {scenario['kind']}")


if __name__ == "__main__":
    unittest.main()
