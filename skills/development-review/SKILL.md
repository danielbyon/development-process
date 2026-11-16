---
name: development-review
description: Use when a user says `implemented`, asks for `review feedback` or merge readiness, says `merge`, or asks to `close this out`.
---

# Development review

Use this Skill for `implemented`, `review feedback`, readiness, `merge`, and `close this out` requests. This Skill applies the pinned policy to review and closeout; it does not replace the policy or create a separate approval authority.

The issue defines accepted scope, and the pinned policy governs roles and process. If the issue, approved plan, or task contract conflicts with the pinned policy, or material scope is unclear, state the conflict and stop the affected decision for owner adjudication. This Skill does not expand scope or authorize an action by itself. The owner must explicitly authorize a merge for the current task.

## Policy and source access

For a new task, resolve the newest verified immutable published CalVer release and record its release tag once. Read [the canonical policy for this release](https://github.com/danielbyon/development-process/blob/{{release_tag}}/docs/PROCESS.md) before applying the workflow. The packager must replace the token in the policy link; an unresolved template is not an approved distribution.

Verify release identity, tag target, native attestation, all eight assets, checksums and reconstructed provenance. Ignore GitHub's `latest` designation. If the newest eligible release cannot be verified, block rather than fall back silently. Record source, policy and builder revisions as separate internal evidence. If no immutable release exists, return `NO_IMMUTABLE_RELEASE`; do not select a static SHA default.

Check that the installed Skill exactly matches the selected release payload, or inspect explicit compatibility evidence identifying the installed payload/source, selected policy/source, behavioral differences and applicable validation. Unknown compatibility blocks until a compatible manual installation or explicit verified historical selection. A matching policy SHA or frontmatter alone is insufficient.

Continue an existing task using its recorded SHA or CalVer and Skill source identity. Resolve and inspect its exact policy without reselecting the newest release. Verify local policy bytes and provenance before relying on them. Preserve historical pins unless the owner explicitly approves migration. Publication never installs Skills, changes global instructions or migrates active tasks.
- Verify the repository, issue, task identity, worktree, branch, baseline, HEAD, PR, and candidate paths from current evidence. Read relevant instructions and accepted specifications.
- Always inspect the candidate source directly through gpt-repo-local or the GitHub connection for the repository owner. Reports and summaries do not establish source-review evidence. If source is unavailable, return `BLOCKED` for readiness.
- Inspect applicable source-adjacent tests and validation evidence. If applicable tests exist but cannot be inspected, record them as `UNVERIFIED` and return `BLOCKED`. If no tests apply, such as for a documentation-only change, record that determination and its rationale and assess the applicable validation evidence. Do not block solely because no tests apply, and do not report absent or unrun tests as passing.
- Separate evidence from inference. Report unavailable or stale evidence as `UNVERIFIED` until checked.

## Review a completed change

When the user says `implemented` or asks for readiness:

1. Read the accepted issue and approved plan. Verify the candidate identity and compare the complete change with accepted scope, exclusions, and the approved plan. Inspect final source, applicable tests, and validation evidence directly.
2. Check each PAC/TAC and required validation criterion. Record each as `PASS`, `FAIL`, `UNVERIFIED`, or `WAIVED` only when a real authorized waiver applies. Preserve the actual failure or unrun state when an integration exception is granted.
3. Verify a separate, non-authoring execution reviewed the full diff. Confirm that later corrections also received independent review and that the cumulative evidence covers the final candidate. The reviewer handoff must include the task-independent naming supplement below and state that worktree contents are in scope. Prefer local Cubic; use a separate Codex execution when local Cubic is unavailable. Do not assume a human review will occur. Cubic CI quota exhaustion does not block when independent local review is complete.
4. Assess findings against policy §6. Fix or factually disprove a confirmed P0/P1 defect that the candidate introduces, materially worsens, or includes in accepted scope. A true in-scope P0/P1 cannot be waived. Fix material in-scope P2 findings. Track justified out-of-scope P2 deferrals; report P3 findings as advisory unless evidence supports elevating them.
5. Inspect changed names, strings, comments, and paths under policy §3 and the task-independent naming supplement. Require correction of candidate-introduced violations within scope while preserving behavior and compatibility contracts. Unchanged, separately tracked legacy violations do not by themselves block a slice.
6. Report tests, meaningful coverage, scope exclusions, qualification gaps, review evidence, residual risk, and owner decisions. The 90% meaningful coverage figure is a target, not a standalone merge gate.

**Task-independent naming supplement (existing task pins remain unchanged): Scope includes types, functions, methods, variables, and constants; tests and fixtures; scripts and first-party generators; maintained technical documentation and source comments; logging, diagnostic, and configuration strings; and implementation-owned files and directories. Keep task IDs in purpose-based task records and preserve stable domain and protocol identifiers. Preserve compatibility-sensitive public APIs, persisted keys, serialized fields and data, wire formats, reflection-visible names, and dynamic string lookups; verify consumers before changing configuration, logging, or diagnostic strings. This supplement authorizes no behavior or compatibility change. Treat confirmed compatibility-sensitive changes as Tier 2 and require separate owner-approved migration scope.**

### Check PR integration evidence

- When a PR is published or updated, and before a merge, inspect its review feedback and actual check jobs and logs. Identify the suites and commands that ran, skipped, failed, or were misconfigured. A green workflow with a required skipped suite does not pass that requirement.
- Bind CI evidence to the exact PR HEAD, tested commit, and relevant target state. A synthetic merge SHA may differ from PR HEAD when its parents match the tested PR head and event base. If the PR head or relevant base changes, refresh the affected evidence.
- Refresh only evidence invalidated by a candidate or target change. Investigate infrastructure failures; do not report an unrun check as passing.

### Return a readiness verdict

Use exactly one verdict:

- `READY`: all mandatory gates pass.
- `BLOCKED`: a mandatory gate fails or remains unverified, source inspection or applicable test inspection is unavailable, or independent review does not cover the final candidate.
- `READY WITH EXPLICIT EXCEPTION`: the owner has authorized a policy-permitted integration exception, every non-waivable gate passes, and the report states the unmet criteria, evidence, residual risk, permitted scope, and follow-up.

Authorization does not change a failed or unverified criterion into a pass. A permitted exception cannot waive required source inspection, independent review, a confirmed in-scope P0/P1 defect, or an approved security boundary.

## Review PR feedback

When the user says `review feedback`:

1. Identify the current PR head and retrieve current and prior review threads, issue comments, and their resolution state.
2. Reconcile feedback as new, unresolved, addressed, resolved, stale, valid, false positive, or out of scope. Check the relevant code and accepted issue before deciding.
3. Fix valid in-scope defects through a focused, pasteable Codex correction prompt. Give evidence for false positives. Defer unrelated requests with traceable rationale instead of expanding the issue.
4. Preserve previous dispositions and review evidence. Require independent review of each correction delta and refresh only evidence affected by the change.

## Close out an authorized change

When the owner says `merge`, `close this out`, or gives another explicit merge instruction, treat it as merge authorization under policy §§8, 10, 11, and 13. Do not ask for redundant approval. That instruction authorizes the merge; it does not authorize a separate exception.

1. Independently determine current-head readiness from direct source and test inspection, independent review, required CI, issue scope, and policy. Merge only for `READY` or a `READY WITH EXPLICIT EXCEPTION` whose exception has separate owner authorization. If a mandatory gate fails or remains unverified, do not merge even when the owner authorized it.
2. Before merging, confirm the PR head, target branch, checks, and authorization still match the inspected candidate. ChatGPT may execute the merge under the owner's authorization. Codex does not approve or merge its own work.
3. After the merge, verify the merge commit and applicable checks. If required post-merge validation is pending or failed, keep closeout open, report `MERGED — CLEANUP PENDING` with the blocker, and give no destructive cleanup instruction. Close the issue only after required checks pass, accepted scope is complete, and §11's required primary-main synchronization has either completed as a fast-forward and passed verification or been verified as an already-current no-op. A verified remote-only exception under §11 makes local synchronization inapplicable and permits closure. If required synchronization is blocked or not yet verified, keep the issue open and report `MERGED — CLEANUP PENDING` with the blocker. Keep deferred obligations tracked; close an issue only when its obligations are complete or formally transferred to an explicitly linked, authorized follow-up. Close a repository-wide naming cleanup only after reconciliation resolves every confirmed violation or records an explicit owner-approved exception. Keep outstanding compatibility migrations open, and report approved exceptions and inspection limits.
4. Determine the original implementor from task or delegation provenance. Determine cleanup eligibility from verified provenance and available task-specific artifacts. A commit author or merge actor alone does not establish implementor. Inspect accessible task records for known local artifacts; a PR alone does not establish that a local worktree exists. If provenance or artifact state is unclear, report `MERGED — CLEANUP PENDING` with the missing evidence, retain any known worktree, and give no destructive instructions or cleanup-complete claim.
5. For an eligible Codex-implemented task, automatically include a task-specific, pasteable Codex cleanup prompt in the merge response. Name the verified repository, worktree root, branch, and PR/merge identity. Direct Codex to follow the canonical process in §11 for primary-checkout synchronization and its verification. The prompt must include `git merge --ff-only --no-overwrite-ignore --no-autostash origin/main` for an eligible fast-forward, with no additional approval after §11's checks pass. Preserve valuable task changes and sole-copy evidence, and remove only verified task-local artifacts and registrations when safe. Do not wait for a separate cleanup request.
6. For a ChatGPT-implemented task, ChatGPT performs applicable cleanup through supported, verified operations under the canonical process in §11. When its checks allow a primary-`main` fast-forward, run `git merge --ff-only --no-overwrite-ignore --no-autostash origin/main` without another approval. Do not generate a Codex cleanup prompt solely because the PR merged.
7. Use the remote-only path only for a genuinely trivial documentation or metadata edit with no substantive effect on policy, security boundaries, workflow behavior, or executable instructions. A Markdown extension alone does not establish eligibility. Require affirmative task evidence that implementation happened through GitHub, then inspect accessible records for known local artifacts. Do not require proof of global nonexistence. Verify issue and check state and relevant remote branch housekeeping; report no local cleanup applicable only when the records support that conclusion, and state what was checked. Do not invent or require a local worktree, branch, MCP registration, or Codex cleanup handoff.
8. If a verified task worktree is intentionally retained for future work, report the reason and defer the cleanup prompt until cleanup is eligible. Preserve the worktree and do not describe cleanup as complete.
9. If a task-specific MCP root registration exists, verify its identity and discover and validate the exact active MCP configuration file before changing it. Remove only that registration and preserve unrelated configuration. Validate the change statically or offline. If no task registration exists, record that determination.
10. If authorized cleanup is blocked by available tooling, give only guarded commands based on verified absolute paths and registration identity. Never use broad removal commands. Retain the worktree and report `MERGED — CLEANUP PENDING` while a stale registration, unverified config change, or other blocker remains.
11. If activation requires a restart, report `MCP RESTART REQUIRED — OWNER ACTION` with the configuration path, exact changes, validation results, and pending verification. Never start, stop, restart, reload, kill, reconnect, replace, or otherwise manage an MCP server. Leave any required lifecycle action to the owner.

## Response format

Keep the report tied to the exact candidate revision. State the verdict, evidence, findings and dispositions, check statuses, owner authorization, residual risk, and next action. For `review feedback`, include the targeted Codex prompt when corrections are needed. For closeout, report the merge commit, issue state, applicable checks, and cleanup disposition.

## Release readiness evidence

For release qualification, provide an index into actual issue, task/delegation, independent-review, inspection, CI and owner-authorization records. Include repository/PR identity, reviewed head/base and integration result, review ranges and correction coverage, source/test inspection identity, CI run/attempt and tested revision, and explicit owner merge authorization. Link inspectable original records and identify their provenance. Booleans or a readiness summary cannot establish another execution's review or authorization.

Verify every uncovered integration from an applicable admitted baseline through the selected source, and separately through the builder. Cover complete changes. For squash/rebase integration, verify tree, range and parent relationships instead of requiring identical commit IDs. Import genuine historical evidence without inventing structured records retrospectively. Missing, contradictory or stale mandatory evidence blocks publication. A candidate baseline is not admitted until its evidence passes; it cannot confer trust backwards onto older source. Reuse existing authoritative records without requiring cosmetic edits to old PRs.
