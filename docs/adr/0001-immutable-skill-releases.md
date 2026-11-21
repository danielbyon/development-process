# ADR-0001: Immutable Skill release authority

## Status

Accepted for immutable packaging and publication under Issue #28. The release trust boundary in the original decision was superseded by the owner-approved Issue #32 decision on 2026-11-17. Real publication and live activation remain separate owner actions.

## Context

New tasks need an inspectable immutable release while existing tasks retain stable policy and Skill identities. The sole maintainer treats a commit merged into authenticated `main` as trusted for release. Reconstructing local reviewer executions and prior PR evidence at release time does not strengthen that boundary.

## Decision

The owner dispatches the release workflow on `main`. The workflow uses the authenticated run's exact `github.sha` as both source and builder, then confirms that commit remains in authenticated `main` history at preflight and before publication. It derives the policy revision separately and checks its committed bytes against the source. The release controller does not require PR receipts or a promotion PR. Independent review, ChatGPT inspection, required CI and owner merge authorization remain pre-merge requirements.

Run all six release qualification suites, build the package twice, and compare the outputs. Publish eight verified assets from an owned draft. A dedicated job signs the verified release manifest with GitHub artifact attestation. Publication verifies the signature and manifest before mutation. Only the attestation job receives OIDC token write and Attestations write; publication receives Attestations read. The workflow uses Contents write for publication. `RELEASE_ADMIN_READ_TOKEN` is used only to check the immutable-release capability endpoint. No Workflows-write escalation is used.

Draft-first publication establishes ownership before source-tag creation and allows complete asset verification. Tag-first adds an orphan-tag window without a documented universal permission exemption. Ordinary publication uses Contents write. The earlier conditional Workflows-write escalation, which required necessity and separate owner authorization, is superseded by Issue #32 and is not active behavior. Administration-read verification access remains pending owner provisioning and verification. Optional tag update/deletion protection reduces the prepublication mutation window.

Release discovery verifies numeric CalVer candidates and fails closed on an unverifiable newest eligible release. Historical signed releases remain verifiable with their frozen evidence. Existing task pins and installed-payload compatibility checks remain unchanged. Publication never activates Skills or changes MCP state.

## Consequences

Merged code can be released without reconstructing its review history. Historical evidence formats remain available only for verifying signed releases that already contain them. The controller still reconciles interrupted remote mutations and preserves unknown state. Published corrections require a new version.

GitHub mutable presentation metadata requires repeated resolver checks. Repository administrators can change protections; prepublication checks do not eliminate that authority. Reproducibility is qualified within a recorded toolchain. Live environment qualification and installation remain separate work.

## Amendment for Issue #42 (2026-11-20)

A successful owner-triggered release workflow on merged `main`, followed by immutable publication, is sufficient release qualification. The workflow retains its six suites, deterministic packaging, provenance, signed attestation and publication checks. Ordinary new-task resolution matches the published manifest, tag, sidecars and successful workflow identity. It does not run `verify-release`, reconstruct attestations or require hosted installation and session-revision evidence. The explicit full audit remains available. Existing SHA and CalVer pins retain their recorded identities. The user installs and updates Skills manually; release publication does not install or activate them.
