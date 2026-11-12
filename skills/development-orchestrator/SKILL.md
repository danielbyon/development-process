---
name: development-orchestrator
description: "Plan software-development work, produce read-only Codex Plan-mode prompts and separate post-approval execution handoffs, and review Codex plans. Use for `next task`, `codex plan`, new-project planning, design decisions, and delegation preparation."
---

# Development Orchestrator

This Skill helps ChatGPT sessions select approved work, prepare task handoffs, and review Codex plans. Issues define accepted scope; the canonical policy defines authority and process.

## Policy and evidence

For new tasks, read the policy pin in `skills/distribution.json` from the distributed source revision. Read [`docs/PROCESS.md` at the approved revision `142422527de28b8e20dea1158d2f54d020dcdcd5`](https://github.com/danielbyon/development-process/blob/142422527de28b8e20dea1158d2f54d020dcdcd5/docs/PROCESS.md) before applying the workflow. Keep already-started tasks on their recorded policy and Skill revisions unless the owner approves migration.

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
4. When a Codex plan is required, return **one read-only Plan-mode prompt only**. Include the accepted issue, verified source revision and expected baseline, the branch and worktree as *proposed* when they do not exist, and exactly one designated bootstrap owner. Do not include an execution/bootstrap handoff in this response. Do not tell Plan mode to create or edit files, branches, worktrees, MCP configuration, or Delegation v3 artifacts. An absent task worktree is not an approval blocker.
5. When a task is straightforward and no Codex plan is produced, the no-plan path may return the execution/bootstrap handoff directly after accepted scope and source state are verified. An explicitly authorized pre-plan bootstrap remains separate from Plan mode.
6. After plan approval and verified worktree bootstrap, prefer native Delegation v3 only when worktree-bound registration and administration are also verified. Manual Codex execution remains the default, and a queued runner is not required. If V3 materialization is unavailable, use a truthful manual task contract tied to the verified worktree and issue. Never bind work to a proposed worktree, stale primary checkout, or invented lineage.

For new-project planning, design decisions, or delegation preparation, gather repository evidence first. Ask only about choices that materially affect scope, architecture, security, or acceptance; resolve routine technical choices within the approved design and leave material owner decisions with the owner.

## `codex plan`

When asked to review a Codex plan:

1. Read the actual plan, accepted issue and specifications, decision provenance, relevant source and tests, project instructions, and verified repository checkout evidence. Inspect task worktree identity when one already exists; do not assume one has been created during Plan mode.
2. Compare the plan with accepted scope, interfaces, constraints, safety invariants, failure modes, feasibility, validation, review ownership, and rollout requirements.
3. Return an explicit `APPROVE` or `REVISE` verdict and name the evidence behind it and each material gap.
4. On `APPROVE`, return exactly one directly pasteable execution/bootstrap handoff. It names the approved issue, baseline, proposed branch/worktree if they do not exist, and the sole bootstrap owner. It requires identity and cleanliness checks before edits, drift reassessment, and isolation before source changes or worktree-bound delegation.
5. On `REVISE`, return only a directly pasteable plan-correction prompt. Do not include an execution/bootstrap handoff.
6. Approve only a plan that fits accepted scope and is verifiable from available source. An absent task worktree alone is not a blocker. False worktree claims, missing source access, policy drift, unresolved material owner decisions, or Plan-mode writes require revision. Material plan revisions need another review.

A plan approval authorizes only the reviewed plan. Inspect final source and tests directly before determining technical readiness.

## Authority and MCP boundaries

- The owner decides material product, scope, architecture, and security trade-offs, substantive exceptions, and whether to merge. Codex implements, validates, coordinates independent review, and may prepare a draft pull request. Do not merge or imply merge authorization.
- Every change needs a full-diff review by local Cubic; if it is unavailable, use a separate non-authoring Codex execution. Re-review correction deltas, then inspect the final source and tests directly in ChatGPT. Do not assume a separate manual human code review will occur.
- Discover the exact active MCP configuration before changing repository registration. Change only verified, authorized entries and validate configuration statically.
- If the active configuration cannot be identified or safely updated, stop the registration attempt. Never edit a guessed file or claim registration is verified. When manual execution fits the approved task, provide its contract; if V3 registration is required, ask the owner to identify or authorize the configuration before changing it.
- MCP server lifecycle is owner-only. Never start, stop, restart, reload, kill, replace, reconnect, or otherwise manage the server, including through scripts or recovery tools.
- If a configuration change requires a restart, report `MCP RESTART REQUIRED — OWNER ACTION`, the exact verified config path and changed entries, static validation, and pending MCP-dependent checks. Resume read-only verification only after the owner confirms reconnection.

Do not auto-merge, approve unseen source, claim unverified validation or review, or expand the issue into another Skill, installer, or distribution task.
