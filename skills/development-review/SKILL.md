---
name: development-review
description: Use when a user says `implemented`, asks for `review feedback` or merge readiness, says `merge`, or asks to `close this out`.
---

# Development review

Use this Skill for `implemented`, `review feedback`, readiness, `merge`, and `close this out` requests. This Skill applies the pinned policy to review and closeout; it does not replace the policy or create a separate approval authority.

The issue defines accepted scope, and the pinned policy governs roles and process. If the issue, approved plan, or task contract conflicts with the pinned policy, or material scope is unclear, state the conflict and stop the affected decision for owner adjudication. This Skill does not expand scope or authorize an action by itself. The owner must explicitly authorize a merge for the current task.

## Policy and source access

- Read [`docs/PROCESS.md` at the approved policy revision `142422527de28b8e20dea1158d2f54d020dcdcd5`](https://github.com/danielbyon/development-process/blob/142422527de28b8e20dea1158d2f54d020dcdcd5/docs/PROCESS.md) before applying the workflow. Verify that any local policy copy has the same source revision; otherwise read the pinned file through GitHub. Do not silently adopt a newer policy.
- Verify the repository, issue, task identity, worktree, branch, baseline, HEAD, PR, and candidate paths from current evidence. Read relevant instructions and accepted specifications.
- Always inspect the candidate source directly through gpt-repo-local or the GitHub connection for the repository owner. Reports and summaries do not establish source-review evidence. If source is unavailable, return `BLOCKED` for readiness.
- Inspect applicable source-adjacent tests and validation evidence. If applicable tests exist but cannot be inspected, record them as `UNVERIFIED` and return `BLOCKED`. If no tests apply, such as for a documentation-only change, record that determination and its rationale and assess the applicable validation evidence. Do not block solely because no tests apply, and do not report absent or unrun tests as passing.
- Separate evidence from inference. Report unavailable or stale evidence as `UNVERIFIED` until checked.

## Review a completed change

When the user says `implemented` or asks for readiness:

1. Read the accepted issue and approved plan. Verify the candidate identity and compare the complete change with accepted scope, exclusions, and the approved plan. Inspect final source, applicable tests, and validation evidence directly.
2. Check each PAC/TAC and required validation criterion. Record each as `PASS`, `FAIL`, `UNVERIFIED`, or `WAIVED` only when a real authorized waiver applies. Preserve the actual failure or unrun state when an integration exception is granted.
3. Verify a separate, non-authoring execution reviewed the full diff. Confirm that later corrections also received independent review and that the cumulative evidence covers the final candidate. Prefer local Cubic; use a separate Codex execution when local Cubic is unavailable. Do not assume a human review will occur. Cubic CI quota exhaustion does not block when independent local review is complete.
4. Assess findings against policy §6. Fix or factually disprove a confirmed P0/P1 defect that the candidate introduces, materially worsens, or includes in accepted scope. A true in-scope P0/P1 cannot be waived. Fix material in-scope P2 findings. Track justified out-of-scope P2 deferrals; report P3 findings as advisory unless evidence supports elevating them.
5. Report tests, meaningful coverage, scope exclusions, qualification gaps, review evidence, residual risk, and owner decisions. The 90% meaningful coverage figure is a target, not a standalone merge gate.

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
3. After the merge, verify the merge commit and applicable checks. Do not require a new post-merge pipeline unless an existing policy or repository requirement calls for one. Close the implementation issue only when required post-merge checks pass and accepted scope is complete. Keep deferred qualification, product, and release obligations tracked with their identifiers and status.
4. Verify the exact task worktree identity and preserve the rationale, findings, review identities, CI evidence, and any sole-copy artifacts before cleanup. Remove only that verified worktree after confirming it contains no valuable unmerged changes or sole-copy evidence. If cleanup safety is uncertain, report `MERGED — CLEANUP PENDING` and retain the worktree.
5. If a task-specific MCP root registration exists, verify its identity and discover and validate the exact active MCP configuration file before changing it. Remove only that registration and preserve unrelated configuration. Validate the change statically or offline; do not assume a configuration path or claim that the active server recognizes a change that has not been verified. If no task registration exists, record that determination.
6. If authorized cleanup is blocked by available tooling, provide exact guarded operator commands using verified absolute paths and the precise registration identity. Do not use broad or unguarded removal commands. Retain the worktree and report `MERGED — CLEANUP PENDING` while a stale registration, unverified config change, or other cleanup risk remains.
7. If activation requires a restart, report `MCP RESTART REQUIRED — OWNER ACTION` with the configuration path, exact changes, validation results, and pending verification. Never start, stop, restart, reload, kill, reconnect, replace, or otherwise manage an MCP server. Leave any required lifecycle action to the owner.

## Response format

Keep the report tied to the exact candidate revision. State the verdict, evidence, findings and dispositions, check statuses, owner authorization, residual risk, and next action. For `review feedback`, include the targeted Codex prompt when corrections are needed. For closeout, report the merge commit, issue state, applicable checks, and cleanup disposition.
