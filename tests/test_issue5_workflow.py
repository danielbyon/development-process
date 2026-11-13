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

    def test_skill_sections_satisfy_issue20_workflow_contracts(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "issue5_workflow.json").read_text()
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

    def test_policy_sections_preserve_issue20_distribution_obligations(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "issue5_workflow.json").read_text()
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

if __name__ == "__main__":
    unittest.main()
