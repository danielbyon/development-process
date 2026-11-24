---
name: development-orchestrator
description: "Plan software-development work, produce read-only Codex Plan-mode prompts and separate post-approval execution handoffs, and review Codex plans. Use for `next task`, `codex plan`, new-project planning, design decisions, and delegation preparation."
---

# Development Orchestrator

This Skill helps ChatGPT sessions select approved work, prepare task handoffs, and review Codex plans. Issues define accepted scope; the canonical policy defines authority and process.

## Policy and evidence

For a historical task that adopts a cleanup amendment, use its qualified immutable release tag and the full policy revision resolved from that tag. Record both in existing task-bound cleanup evidence as the `cleanup_amendment` reference. Apply the amendment only to the historical pin's superseded cleanup provisions; the original task pin, provenance, and unrelated gates remain unchanged. For a historical manual task without a structured record, use existing task-bound evidence such as the issue, PR, approved plan, branch, and worktree identity. Creating, migrating, exporting, or preserving a worktree-local task record is not a cleanup prerequisite; no new task-record schema or migration framework is required.

For a new task, select the newest eligible qualified immutable published CalVer release and record its tag and policy identity once. Read [the canonical policy for this release](https://github.com/danielbyon/development-process/blob/{{release_tag}}/docs/PROCESS.md) before applying it. The packager replaces the token in this policy link; an unresolved template is not an approved distribution.

Successful release workflow execution and immutable publication qualify the release after its changes have merged into protected `main` through review and CI and the owner dispatches the workflow against that revision. The resolver checks the published release, tag, frozen context, provenance sidecars and successful workflow identity. Record the existing `task_pin` and `provenance` fields, including source, policy, builder, owner and payload identities. Ignore GitHub's `latest` designation. Missing or inconsistent evidence for the newest eligible release blocks selection without fallback. If no qualified immutable release exists, return `NO_IMMUTABLE_RELEASE`.

The workflow remains responsible for its six qualification suites, deterministic packaging, provenance, signed attestation and immutable publication. Task resolution does not run `verify-release`, rebuild assets, reconstruct attestations or require a hosted installation or session revision check. Keep `verify-release` available for explicit audits and diagnostics.

Successful release qualification does not install this Skill. The user manually installs and updates `development-orchestrator` and `development-review` in ChatGPT and Codex. Publication does not upload or activate Skills.

Continue an existing task with its recorded SHA or CalVer and source, policy and builder identities. Do not select a new release, repin or repeat release qualification during continuation. Preserve historical pins unless the owner explicitly approves migration.

- Use `gpt-repo-local` first for connected repository source. Use the GitHub connection that matches the repository owner for issues and pull requests.
- Verify the repository root, read-only checkout revision, and active task identity from current evidence. If a task worktree exists, verify its path, branch, HEAD, and task identity; if none exists during planning, label any worktree/branch as proposed rather than verified. Inspect project instructions, accepted issues and specifications, decision records, source, tests, and active work as relevant.
- Read the policy at the recorded task pin and verify its resolved immutable commit. Before relying on a local `docs/PROCESS.md`, verify that its source revision matches the pin; otherwise retrieve the exact commit through an available source or report that it is unavailable. Cite the immutable policy revision in the decision; never cite an unverified local copy as the pinned policy.
- Separate verified facts from inferences. If the issue, source, policy pin, or task identity cannot be inspected, report the gap and stop at the affected decision.
- Do not silently change the pinned policy. If the task cites another revision or the approved source has moved, identify the revisions and request owner adjudication.

## Approved backlog qualification

Use the same eligibility criteria for `next task` and post-closeout discovery. Inspect the approved issue backlog, project instructions, applicable specifications and decisions, dependencies, relevant source and tests, active task and worktree records, and open or draft pull requests as needed to establish eligibility. In standalone `next task`, gather only the evidence needed to select eligible work. The broader coverage and ranking requirements below apply only to the post-closeout report. Use the GitHub connection that matches the repository owner. Bind findings to the repository and inspected source revision.

An issue is eligible when its accepted scope is clear, sufficient acceptance criteria exist, prerequisites are satisfied, material owner decisions are resolved, and no active implementation already covers it. An ordinary Codex plan may remain pending and does not block eligibility. Exclude issues with unmet prerequisites, unresolved material owner decisions, blocked scope, duplicate active implementation, or missing eligibility evidence, and name the reason. Missing overlap evidence does not exclude an otherwise eligible issue.

## `next task`

When asked to find or prepare the next task:

1. Apply the existing standalone active-work gate before selecting any backlog issue. When the gate directs continuation of existing work, identify that work and state clearly that no new issue starts. Honor the active task's established output contract.
2. Only when the gate permits selection, use Approved backlog qualification with the evidence needed to establish eligibility. Follow this branch's standalone task contract and Plan-mode or no-plan response rules below. Do not apply the post-closeout report's `Complete`, `Partial`, or `Unavailable` coverage labels or return a ranked discovery report. Follow the policy's serial-per-repository default; treat work as parallel only when its independence is explicit.
3. Select an approved slice without adding requirements. For a substantial custom subsystem, check native features and maintained libraries before proposing new tooling. Establish the task-contract facts needed to describe the slice:
   - beneficiary, current problem, desired outcome, and why the work is timely;
   - source issues and specifications, scope, exclusions, PAC/TAC, and constraints;
   - risk classification, relevant failure modes, validation, and independent review.
4. When a Codex plan is required, return **one read-only Plan-mode prompt only**. The reply must consist solely of that prompt. Use verified task-contract facts inside it as needed, but do not return a separate task contract, issue-ranking report, framing, explanation, or execution/bootstrap handoff. Include the accepted issue, verified source revision and expected baseline, the branch and worktree as *proposed* when they do not exist, and exactly one designated bootstrap owner. Do not tell Plan mode to create or edit files, branches, worktrees, MCP configuration, or Delegation v3 artifacts. An absent task worktree is not an approval blocker.
5. When a task is straightforward and no Codex plan is produced, the no-plan path may return the execution/bootstrap handoff directly after accepted scope and source state are verified. An explicitly authorized pre-plan bootstrap remains separate from Plan mode.
6. After plan approval and verified worktree bootstrap, prefer native Delegation v3 only when worktree-bound registration and administration are also verified. Manual Codex execution remains the default, and a queued runner is not required. If V3 materialization is unavailable, use a truthful manual task contract tied to the verified worktree and issue. Never bind work to a proposed worktree, stale primary checkout, or invented lineage.

For new-project planning, design decisions, or delegation preparation, gather repository evidence first. Ask only about choices that materially affect scope, architecture, security, or acceptance; resolve routine technical choices within the approved design and leave material owner decisions with the owner.

## Post-closeout issue discovery

Record the exact task worktree's enrollment disposition, supporting evidence, and rationale in cleanup evidence. Use three dispositions: `never-enrolled`, `registered-or-potentially-outstanding`, and `previously-registered-with-verified-removal`. `UNKNOWN_REPO` is not evidence of non-enrollment. An enrollment attempt with an unknown outcome remains potentially outstanding. A trusted registration for the exact task root overrides a prior `never-enrolled` finding. When reconciliation applies, use the correct stable repository ID and canonical root.

When local cleanup is the closeout disposition, verify that the exact worktree path and integrated task branch are absent. Follow the recorded enrollment disposition for post-cleanup verification. A never-enrolled root needs no registry check. A registered or potentially outstanding root uses the existing registration-removal checks. Reuse verified prior removal evidence unless contrary evidence or credible drift appears.

A verified remote-only disposition makes local cleanup inapplicable; do not require a local worktree, branch, or MCP registration for that path. For owner-approved intentional retention, verify the exact worktree identity, record the reason and deferred cleanup, and keep the worktree intentionally present. Run discovery after other required checks pass; retention alone is not `MERGED — CLEANUP PENDING`. Eligibility does not establish successful removal.

When `development-review` invokes post-closeout discovery after an eligible verified closeout, reuse Approved backlog qualification and return one report. Include named active work in concurrency checks, while continuing to assess other candidates even when work is active.

Ranking is qualitative. Apply explicit owner priority first, then dependency unlocking or critical-path impact, product value and urgency, and finally risk, complexity, and readiness. Do not invent numerical scores or let issue-number order override owner priority or dependency evidence. Explain each rank using verified owner priorities, dependencies, value and urgency, risk, complexity, and readiness; link to source records when available. The ranked recommendation list has a hard cap of five. Assess eligible candidates beyond fifth place, but never include them in that list or present them as ordinary ranked recommendations. Surface a lower-ranked candidate outside the list only when it enables a verified useful parallel group, and explain any group that omits the highest-ranked issue.

Assess each candidate against named active work and against the complete proposed group. Check ordering, overlapping files and interfaces, unstable contracts, migrations, mutable resources, shared tests or infrastructure, and hardware when relevant. Use `Independent` when compatibility is verified, `Conditional` when a concrete coordination requirement remains, `Serial` for a known conflict or ordering constraint, and `Unverified` when evidence is insufficient. Check the whole group because pairwise compatibility can miss a shared conflict. Recommend only groups verified as safe. Serial execution remains the default. Parallel execution requires the owner's explicit choice.

Set coverage to `Complete` when evidence establishes repository-wide coverage, including a verified result with zero qualifying issues. Set `Partial` when some useful candidates are supported but available evidence cannot establish full coverage. Set `Unavailable` only when evidence is insufficient and no useful candidate can be recommended. An interrupted or unavailable source must never be reported as a verified empty backlog.

Include the repository and inspected source SHA, inspection time, closeout disposition, issue and active-work identities, evidence links, stale or unavailable sources, and limitations. Issue and active-work state can change after inspection; report this as an evidence-freshness limitation. Do not frame revalidation as a next-step recommendation.

This path is report-only and ends the invocation after one report. It creates no task contract, planning or execution prompt, assignment, schedule, branch, worktree, task session, delegation, source or configuration change, or GitHub mutation. Do not include a call to action or recommendation to prepare a task, plan, execution prompt, or bootstrap. Do not echo prospective task-preparation details from shared input, including a proposed branch, worktree, or bootstrap owner. Mention an existing worktree or branch only when it supports eligibility or concurrency evidence. State revalidation only as an evidence-freshness limitation because issue and active-work state can change. Preserve the recorded closeout result if qualification or retrieval fails. Applicability or compatibility gaps stop discovery without changing that result.

## `codex plan`

When asked to review a Codex plan:

1. Read the actual plan, accepted issue and specifications, decision provenance, relevant source and tests, project instructions, and verified repository checkout evidence. Inspect task worktree identity when one already exists; do not assume one has been created during Plan mode.
2. Compare the plan with accepted scope, interfaces, constraints, safety invariants, failure modes, feasibility, validation, review ownership, and rollout requirements.
3. Return an explicit `APPROVE` or `REVISE` verdict and name the evidence behind it and each material gap.
4. On `APPROVE`, return exactly one directly pasteable execution/bootstrap handoff. It names the approved issue, baseline, proposed branch/worktree if they do not exist, and the sole bootstrap owner. It requires identity and cleanliness checks before edits, drift reassessment, and isolation before source changes or worktree-bound delegation.
5. On `REVISE`, return only a directly pasteable plan-correction prompt. Do not include an execution/bootstrap handoff.
6. Approve only a plan that fits accepted scope and is verifiable from available source. An absent task worktree alone is not a blocker. False worktree claims, missing source access, policy drift, unresolved material owner decisions, or Plan-mode writes require revision. Material plan revisions need another review.

During plan review, apply the task-independent naming supplement below to proposed names and strings. Require corrections within accepted scope, preserve its task-record exceptions and stable domain and protocol identifiers, and flag compatibility-sensitive changes for separate owner approval. A naming change does not authorize behavior or compatibility changes.

**Task-independent naming supplement (existing task pins remain unchanged): Scope includes types, functions, methods, variables, and constants; tests and fixtures; scripts and first-party generators; maintained technical documentation and source comments; logging, diagnostic, and configuration strings; and implementation-owned files and directories. Keep task IDs in purpose-based task records and preserve stable domain and protocol identifiers. Preserve compatibility-sensitive public APIs, persisted keys, serialized fields and data, wire formats, reflection-visible names, and dynamic string lookups; verify consumers before changing configuration, logging, or diagnostic strings. This supplement authorizes no behavior or compatibility change. Treat confirmed compatibility-sensitive changes as Tier 2 and require separate owner-approved migration scope.**

A plan approval authorizes only the reviewed plan. Inspect final source and tests directly before determining technical readiness.

## Authority and MCP boundaries

- The owner decides material product, scope, architecture, and security trade-offs, substantive exceptions, and whether to merge. Codex implements, validates, coordinates independent review, and may prepare a draft pull request. Do not merge or imply merge authorization.
- Every change needs a full-diff review by local Cubic; if it is unavailable, use a separate non-authoring Codex execution. Re-review correction deltas, then inspect the final source and tests directly in ChatGPT. Do not assume a separate manual human code review will occur.
- In the execution handoff, distinguish Codex client connection settings from the GPT Repo MCP server root registry. Have the executor identify the running instance and exact backing file through trusted launch or deployment evidence under §4. Require authorized offline administration against that verified path and separate evidence of active recognition.
- If the server instance, registry, or safe administration cannot be verified, stop enrollment. Record whether the task root is absent or unverified. Use the approved manual contract tied to the verified worktree when available. If V3 is required, ask the owner for the missing identification or authorization. Bind V3 only after the identified server recognizes the exact worktree root and the required administration is available.
- MCP server lifecycle is owner-only. Never start, stop, restart, reload, kill, replace, reconnect, or otherwise manage the server, including through scripts or recovery tools.
- If a configuration change requires a restart, report `MCP RESTART REQUIRED — OWNER ACTION`, the exact verified config path and changed entries, static validation, and pending MCP-dependent checks. Resume read-only verification only after the owner confirms reconnection.

Do not auto-merge, approve unseen source, claim unverified validation or review, or expand the issue into another Skill, installer, or distribution task.
