---
name: development-orchestrator
description: "Plan software-development work, produce read-only Codex Plan-mode prompts and separate post-approval execution handoffs, and review Codex plans. Use for `next task`, `codex plan`, new-project planning, design decisions, and delegation preparation."
---

# Development Orchestrator

This Skill helps ChatGPT sessions select approved work, prepare task handoffs, and review Codex plans. Issues define accepted scope; the canonical policy defines authority and process.

## Policy and evidence

This Skill is pinned to policy commit `beb7c955b054dafa3eb1a45e5e13e519720e654a`. Read [`docs/PROCESS.md` at that revision](https://github.com/danielbyon/development-process/blob/beb7c955b054dafa3eb1a45e5e13e519720e654a/docs/PROCESS.md) before applying the workflow.

- Use `gpt-repo-local` first for connected repository source. Use the GitHub connection that matches the repository owner for issues and pull requests.
- Verify the repository root, read-only checkout revision, and active task identity from current evidence. If a task worktree exists, verify its path, branch, HEAD, and task identity; if none exists during planning, label any worktree/branch as proposed rather than verified. Inspect project instructions, accepted issues and specifications, decision records, source, tests, and active work as relevant.
- Read the policy at its pinned commit. Before relying on a local `docs/PROCESS.md`, verify that its source revision matches the pin; otherwise retrieve the exact commit through an available source or report that it is unavailable. Cite the immutable policy revision in the decision; never cite an unverified local copy as the pinned policy.
- Separate verified facts from inferences. If the issue, source, policy pin, or task identity cannot be inspected, report the gap and stop at the affected decision.
- Do not silently change the pinned policy. If the task cites another revision or the approved source has moved, identify the revisions and request owner adjudication.

## `next task`

When asked to find or prepare the next task:

1. Inspect the current repository and approved issue backlog. Read the relevant specifications, decisions, project instructions, and active work before selecting a slice.
2. Continue an active task or report why no new task can start. Follow the policy's serial-per-repository default; treat work as parallel only when its independence is explicit.
3. Select an approved slice without adding requirements. For a substantial custom subsystem, check native features and maintained libraries before proposing new tooling. Prepare a task contract that states:
   - beneficiary, current problem, desired outcome, and why the work is timely;
   - source issues and specifications, scope, exclusions, PAC/TAC, and constraints;
   - risk classification, relevant failure modes, validation, and independent review.
4. When a Codex plan is required, provide **two separate prompts** with the branch name from the accepted issue or approved plan (do not invent a replacement) and exactly one designated bootstrap owner:
   - **Codex Plan-mode prompt:** read-only inspection of the verified repository checkout, issue, source, and expected baseline revision. Describe the intended task branch/worktree as *proposed* if not yet created. Ask Codex to return the plan and identified drift or decisions; do **not** instruct it to create or edit files, branches, worktrees, MCP configuration, or Delegation v3 artifacts. Do not require an existing task worktree to request or approve the plan.
   - **Post-approval Agent/execution-mode prompt:** after ChatGPT approves the plan, create or reuse the isolated worktree and dedicated task branch, verify repository/root, baseline, branch, current HEAD, and cleanliness for a new task, then check the actual state against the plan before changing source files. On material baseline/identity drift, stop for ChatGPT reassessment. Preserve any unrelated primary-checkout state. For a resumed task, verify its existing identity and preserve legitimate in-progress changes without imposing a clean-tree prerequisite.
   - When the task is straightforward and no Codex plan is produced, the bootstrap/execution handoff may proceed directly after the accepted scope is verified. A separately authorized pre-plan bootstrap is also permissible, but never as an instruction inside Plan mode.
5. Only after the actual worktree and registered identity are verified, prefer native Delegation v3 task materialization when administration is available. Task materialization and execution mode are separate choices: a reliable queued runner is not required, and manual Codex execution remains the default. If formal V3 materialization cannot be established, provide a truthful manual task contract tied to the verified worktree and issue. Never bind work to a proposed worktree, stale primary checkout, or invented lineage.

For new-project planning, design decisions, or delegation preparation, gather repository evidence first. Ask only about choices that materially affect scope, architecture, security, or acceptance; resolve routine technical choices within the approved design and leave material owner decisions with the owner.

## `codex plan`

When asked to review a Codex plan:

1. Read the actual plan, accepted issue and specifications, decision provenance, relevant source and tests, project instructions, and verified repository checkout evidence. Inspect task worktree identity when one already exists; do not assume one has been created during Plan mode.
2. Compare the plan with accepted scope, interfaces, constraints, safety invariants, failure modes, feasibility, validation, review ownership, and rollout requirements.
3. Return an explicit `APPROVE` or `REVISE` verdict and a directly pasteable Codex prompt. Name the evidence behind the verdict and each material gap.
4. Approve only a plan that fits the accepted scope and can be verified from available source. The absence of a not-yet-created task worktree alone does not prevent plan approval; false claims that it exists, missing source access, policy drift, or unresolved material owner decisions do. Plans that require writes from Codex Plan mode must be revised.
5. State that implementation may begin only after approval **and** verified execution-mode worktree bootstrap. The approval prompt must separate bootstrap from read-only planning and require reassessment for material baseline drift. Require another review when a revision materially changes the plan.

A plan approval authorizes only the reviewed plan. Inspect final source and tests directly before determining technical readiness.

## Authority and MCP boundaries

- The owner decides material product, scope, architecture, and security trade-offs, substantive exceptions, and whether to merge. Codex implements, validates, coordinates independent review, and may prepare a draft pull request. Do not merge or imply merge authorization.
- Every change needs a full-diff review by local Cubic; if it is unavailable, use a separate non-authoring Codex execution. Re-review correction deltas, then inspect the final source and tests directly in ChatGPT. Do not assume a separate manual human code review will occur.
- Discover the exact active MCP configuration before changing repository registration. Change only verified, authorized entries and validate configuration statically.
- If the active configuration cannot be identified or safely updated, stop the registration attempt. Never edit a guessed file or claim registration is verified. When manual execution fits the approved task, provide its contract; if V3 registration is required, ask the owner to identify or authorize the configuration before changing it.
- MCP server lifecycle is owner-only. Never start, stop, restart, reload, kill, replace, reconnect, or otherwise manage the server, including through scripts or recovery tools.
- If a configuration change requires a restart, report `MCP RESTART REQUIRED — OWNER ACTION`, the exact verified config path and changed entries, static validation, and pending MCP-dependent checks. Resume read-only verification only after the owner confirms reconnection.

Do not auto-merge, approve unseen source, claim unverified validation or review, or expand the issue into another Skill, installer, or distribution task.
