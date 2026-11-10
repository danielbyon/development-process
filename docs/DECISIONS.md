# Decision record

This record summarizes decisions present in the owner-approved v1.0 contract. The contract in [docs/PROCESS.md](PROCESS.md) remains authoritative.

## Provenance

Issue #1 states that the owner approved v1.0 after a 50-question governance interview and two external review passes. It does not include the individual questions and answers or identify the external reviewers. This record preserves the stated provenance without inventing missing interview or reviewer details.

The issue also identifies three final amendments: tasks use an isolated worktree and dedicated branch; one predicate makes confirmed in-scope or candidate-introduced/materially-worsened P0/P1 defects non-waivable; tasks and Skills pin the current owner-approved immutable policy revision.

## Decisions and rationale

1. **Keep one canonical private policy source.** Project instructions and focused Skills adapt the canonical policy rather than copying the full governance text. This keeps policy authority and change history in one place.
2. **Separate requirements, execution, review, and integration records.** The issue is authoritative for accepted scope; the task or delegation for execution and result identity; the review for findings and disposition; and the PR for integration and readiness. Linking these records avoids competing task state.
3. **Require independent review for every change.** A separate non-authoring review execution and direct ChatGPT inspection preserve review independence even for small documentation changes. Local Cubic is preferred; a separate Codex review execution is the fallback. Cubic CI review is supplementary.
4. **Make the P0/P1 rule non-waivable within its defined scope.** A confirmed P0/P1 defect introduced or materially worsened by the candidate, or included in accepted scope, must be fixed or factually disproved before merge. Unrelated pre-existing defects do not automatically block.
5. **Treat 90% meaningful coverage as a target, not a numeric merge gate.** Report scope and exclusions, and do not write brittle tests to inflate coverage. Missing important behavior still matters at any measured percentage.
6. **Validate in the real integration context.** Required CI must execute checks on the final PR changes and record the tested integration revision. A green skipped or misconfigured job is not evidence of success. Qualification gaps remain distinct from integration.
7. **Allow a narrow, truthful bootstrap accommodation.** An empty root commit may establish an otherwise unborn main branch. It does not authorize unreviewed substantive changes on main or waive source inspection, independent review, the P0/P1 rule, or truthful evidence.
8. **Keep implementation and governance proportional.** The contract rejects centralized orchestration, redundant provenance, universal CI abstractions, a custom coordination framework, and fixed retry quotas in v1. Manual Codex execution remains the default until queued execution is reliable; native worktree-bound Delegation v3 is preferred when available.
9. **Preserve obligations when work is deferred.** Record criterion identifiers, content, rationale, and status; transfer tracking only when authorized. Distinguish merge permission from a substantive waiver and keep failed or unrun checks truthful.
10. **Scope Issue #1 to the repository foundation.** Do not implement or install the three Skills or an installer here. Existing follow-up issues #2–#5 own those slices. The policy must have an owner-approved immutable commit revision before Skills are distributed.
11. **Adopt prospectively and clean up only with evidence.** Do not rewrite historical delegations. Before deleting a worktree, prove that no valuable unmerged work or sole-copy evidence would be lost.

## Rejected alternatives and constraints

The approved contract explicitly declines duplicated full policy text in Skills, a new central coordination system, a universal CI layer, retroactive rewriting of prior work, fixed retry quotas, and coverage theater. It also rules out fabricated delegation lineage, access-control bypass, reclassification of true P1 findings to permit merge, automatic merge, and broad destructive cleanup.

Changes to product scope, architecture, security trade-offs, substantive exceptions, or substantive policy require owner authorization. Routine technical choices remain within the accepted design; this decision record does not broaden those authorities.

## Known limitations

This slice creates no application code, test suite, or Skill implementation. Its validation is limited to documentation integrity and the executable PR integration-diff check. There is no code-coverage result. Hardware or unavailable-platform qualification does not apply to this documentation-only change.

The detailed Q1–Q50 interview record and the external review reports are not included in Issue #1. Their absence is recorded rather than reconstructed.
