# ADR-0001: Immutable Skill release authority

## Status

Accepted design for Issue #28. Real publication and live activation remain separate owner actions.

## Context

Per-release promotion PRs couple distribution metadata to implementation history. New-task selection needs an inspectable release authority while existing tasks retain stable policy and Skill identities. Historical source may differ from current trusted tooling and may have incomplete review evidence.

## Decision

Use one owner-triggered qualification/build/publication workflow. Trusted main tooling reads explicitly selected source as data, verifies bounded historical evidence, builds deterministic release-specific policy links, and publishes eight verified assets from a complete draft. Keep source, policy and builder identities distinct. Native immutable-release attestation binds publication. A dedicated job signs the exact verified manifest with GitHub artifact attestation, binding durable qualification evidence to the trusted main workflow and builder. Publication cryptographically verifies this proof before mutation; temporary Actions artifact retention is not the release authority. Ordinary qualification remains read-only. Only the attestation job receives OIDC token write and Attestations write; publication receives Attestations read. The owner approved this scoped design on 2026-11-16.

Draft-first publication establishes ownership before source-tag creation and allows complete asset verification. Tag-first adds an orphan-tag window without a documented universal permission exemption. Ordinary publication uses Contents write. Conditional Workflows write requires necessity and separate owner authorization. Administration-read verification access remains pending owner provisioning and verification. Optional tag update/deletion protection reduces the prepublication mutation window.

Release discovery verifies numeric CalVer candidates and fails closed on unverifiable newest eligible releases. Existing task pins remain unchanged. Compatibility is explicit. Publication never activates Skills or changes MCP state.

## Consequences

Incomplete historical evidence blocks publication instead of becoming fabricated approval. Candidate baseline admission is bounded and cannot establish trust backwards. The controller must reconcile interrupted remote mutations and preserve unknown state. Published corrections require a new version.

GitHub mutable presentation metadata requires repeated resolver checks. Repository administrators can change protections; prepublication checks do not eliminate that authority. Reproducibility is qualified within a recorded toolchain. Live environment qualification and installation remain separate work.
