# Development Process

This private repository is the canonical source for the owner-approved Unified Development Process v1.0 and its focused future Skills. The complete policy is in [docs/PROCESS.md](docs/PROCESS.md); this README describes where the records live and how the repository is used.

## Source of truth

- [Unified Development Process v1.0](docs/PROCESS.md) is the normative policy.
- [Issue #1](https://github.com/danielbyon/development-process/issues/1) records the approved initial scope and contract.
- [docs/DECISIONS.md](docs/DECISIONS.md) preserves the approved rationale, alternatives, constraints, and known limitations.
- [docs/BOOTSTRAP.md](docs/BOOTSTRAP.md) records the initial Git baseline, task identity, and validation and review evidence.
- [AGENTS.md](AGENTS.md) points project work to the canonical policy.
- [.github/workflows/ci.yml](.github/workflows/ci.yml) checks the committed PR integration diff.

The issue is the authority for accepted scope. The task or delegation records execution identity and results, the review records findings and disposition, and the PR records integration and readiness. Link these records; do not create competing task state.

## Work ownership

- **ChatGPT** investigates requirements, prepares and approves Codex plans, directly inspects source and tests, adjudicates reviews, and determines technical readiness.
- **Codex** implements in an isolated worktree and dedicated branch, runs validation, coordinates independent review, and publishes draft PRs.
- **The repository owner** decides material product, scope, architecture, and security trade-offs and explicitly authorizes merges.

Every change receives independent review from a separate non-authoring execution. ChatGPT must be able to inspect the final source directly. Confirmed in-scope or candidate-introduced/materially-worsened P0/P1 defects cannot be waived.

## Adoption

Apply the policy prospectively. Existing repositories adopt it at their next task and add adequate CI for applicable local suites when needed. New tasks and Skills pin the same current owner-approved immutable policy commit until an owner-approved migration. Do not distribute Skills from this initial bootstrap before the policy commit has been approved.

The CI foundation in this repository checks the actual GitHub pull-request synthetic merge commit and its committed diff. This documentation-only slice has no application test suite and does not claim a code-coverage result.

## Follow-up slices

These open issues own the work intentionally excluded from Issue #1:

- [#2 — Implement development-orchestrator ChatGPT Skill](https://github.com/danielbyon/development-process/issues/2)
- [#3 — Implement development-review ChatGPT Skill](https://github.com/danielbyon/development-process/issues/3)
- [#4 — Implement delegation-executor Codex Skill](https://github.com/danielbyon/development-process/issues/4)
- [#5 — Package and install three Skills with immutable policy pinning and smoke tests](https://github.com/danielbyon/development-process/issues/5)

Issue #1 does not implement or install those Skills or an installer.
