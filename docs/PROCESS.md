# Unified Development Process v1.0

- **Status:** Owner-approved contract
- **Canonical source:** This document
- **Approved scope:** [danielbyon/development-process Issue #1](https://github.com/danielbyon/development-process/issues/1)

This policy is the complete v1.0 process. Project instructions and future Skills adapt it; they do not replace or override it.

The final amendments are incorporated in the policy: every task uses an isolated worktree and dedicated branch (§4); one non-waivable predicate covers confirmed in-scope or candidate-introduced/materially-worsened P0/P1 defects (§6); and tasks and Skills pin the current owner-approved immutable policy revision (§12).

## 1. Roles and authority

- ChatGPT owns requirements investigation, planning, Codex plan approval or revision, independent direct source and test inspection through MCP or GitHub, review adjudication, technical readiness, and correction and closeout guidance. **No ChatGPT source access means no approval.**
- Codex owns code implementation, isolated worktree and delegation setup, local validation, local Cubic review coordination, draft PR publication, authorized corrections, and cleanup.
- Every change, including trivial non-code changes, requires independent review from a separate non-authoring review execution. Local Cubic is preferred; a separate Codex subagent is the fallback. Cubic CI review is supplementary when quota permits.
- The owner approves product and material architectural trade-offs, substantive gate exceptions, substantive policy revisions, and merging. No human manual code review is assumed.

## 2. Scope, planning, risk

- Substantive tasks use a GitHub issue with proportionate acceptance criteria, relevant specifications, constraints, and exclusions. Serial implementation per repository is the default; explicitly independent parallel work is supported.
- Normal or routine work has clear requirements and existing patterns, with no unresolved material design decisions. Elevated-risk work involves consequential data, privacy, authorization, persistence, recovery, destructive, or hardware behavior; specify failure modes and targeted verification.
- Straightforward changes may omit a separate Codex plan. Every plan Codex produces requires ChatGPT approval before implementation, and material plan revisions require another review. Read-only Codex planning and ChatGPT plan approval may precede worktree bootstrap; isolated execution remains mandatory under §4.
- Preserve decisions with their rationale, rejected alternatives, invariants, and failure modes. ChatGPT approves routine technical choices within the accepted design; the owner decides material scope, product, architecture, and security trade-offs.

## 3. Engineering choices

- Before implementing a substantial custom subsystem, investigate native capabilities and maintained libraries or frameworks. Assess functionality, license, maintenance, security, integration, and complexity.
- Avoid adversarial overengineering outside the approved threat model. Escalate meaningful trade-offs to the owner.

## 4. Worktrees and Delegation v3

- **Each implementation task uses an isolated Git worktree and a dedicated task branch.** Read-only task planning and approval may use a verified repository checkout before the task worktree exists. Once bootstrapped, verify a clean starting state for a new task. When resuming, preserve verified in-progress task changes and exclude unrelated work.
- **Default sequence: plan first, bootstrap second.** ChatGPT prepares a Codex Plan-mode prompt with the accepted issue, verified source revision and expected implementation baseline, proposed branch/worktree identity, and exactly one designated bootstrap owner. Codex Plan mode performs read-only investigation and returns a proposed plan. It must not create or change files, branches, worktrees, MCP configuration, or delegation artifacts, and must not claim that proposed task isolation already exists. ChatGPT reviews and approves the plan before implementation.
- **Execution-mode bootstrap.** After plan approval (or after scope verification when no separate Codex plan was produced), the designated bootstrap owner creates the isolated worktree and task branch in Codex Agent/execution mode (or ChatGPT creates them using an authorized capable tool). Codex reuses an explicitly supplied existing worktree after verification. Before modifying implementation files or binding worktree-scoped Delegation v3, verify the actual repository/root, worktree, branch, baseline commit, current HEAD, cleanliness for a new task, and registered identity where needed. Recompare these facts with the approved plan; if material drift invalidates its assumptions, stop for ChatGPT reassessment instead of silently applying the plan to a different baseline.
- **Optional pre-plan bootstrap.** An explicit authorized execution-mode step may create the worktree before planning when read-only inspection is insufficient or isolation is specifically required. It remains a separate step, never an instruction embedded in a Codex Plan-mode prompt. Whether planning comes first or not, no implementation starts before any produced plan receives ChatGPT approval.
- **Conditional Xcode MCP bootstrap.** Run only for approved Xcode tasks after the execution-mode task worktree is verified and before the first Xcode operation.
  - **Discover and select.** Resolve the worktree root canonically. Search for .xcworkspace and .xcodeproj candidates only beneath it; resolve symlinks and keep only canonical paths equal to or descended from the root by path components. Do not use string-prefix checks. Match the repository’s documented build or test entrypoint against this contained candidate set. If the documented path resolves outside the root, stop and report it rather than selecting a neighboring candidate. If no valid candidate exists or the documentation does not identify exactly one contained candidate, stop and report the candidates.
  - **Verify workspace identity.** Inspect installed Xcode MCP schemas, then use the existing configured client and a supported workspace-opening operation on the selected absolute path. Capture the returned workspaceIdentifier and associated path; if the open result omits a path, resolve that exact identifier through the supported workspace-list operation. Verify the canonical returned path equals the selected candidate within the task worktree. Do not infer identity from MCP reachability, the active Xcode window, or a default workspace.
  - **Scope and record.** Explicitly pass the verified workspaceIdentifier to every later workspace-scoped operation whose installed schema supports it. Block operations whose target cannot be bound deterministically. Record the absolute worktree root, branch, selected path, selection rationale, workspace identifier and path, and operation and validation evidence in the existing task record.
  - **Owner boundary.** Ordinary access through the existing configured MCP client is allowed, including system-managed on-demand service activation. When that access opens and verifies the new worktree, proceed without waiting for owner acknowledgement or a manual GUI open. Codex must not start, stop, restart, reload, kill, reconnect, or otherwise manage the MCP server lifecycle directly or through scripts or commands. Do not change machine-wide Xcode MCP authorization or configuration, or enable --unsafe-always-allow-all-agents or other unsafe global permissions. If authorization or service access fails, give the owner the exact worktree and selected project paths, the applicable owner action, and the affected blocked or unavailable checks. When applicable, the safe owner action is open -a Xcode "<absolute selected path>". Continue independent work; resume Xcode-dependent work only after the owner action and renewed authorization and workspace-identity verification.
- For MCP root registration and configuration maintenance, Codex discovers and verifies the exact **active MCP configuration file**, changes only authorized entries, preserves unrelated configuration, and performs static/offline validation. If the active config cannot be identified or safely updated, stop and ask the owner; do not modify a guessed file or claim an unverified registration is active.
- **MCP server lifecycle is owner-only.** Codex must never start, stop, restart, reload, kill, reconnect, replace, or otherwise manage the MCP server, directly or indirectly through scripts, process managers, tunnel wrappers, or tools. This prohibition also applies when registering/removing roots, applying configuration changes, recovering access, or troubleshooting a stale server view. When a configuration change requires a restart, Codex reports **`MCP RESTART REQUIRED — OWNER ACTION`**, the exact configuration path, changed entries, static validation outcome, and pending MCP-dependent verification. The owner performs the restart and reconnection. Codex may resume read-only verification of the server's recognized configuration only after the owner confirms availability; until then, report the change as configured but not activated.
- Prefer Delegation v3 bound to the actual worktree. Use manual Codex execution by default until a queued runner is reliable. Use native corrective lineage where supported. If native registration, task materialization, or corrective lineage is unavailable, use a cross-referenced manual contract with the real source identity, scope, criteria, results, and review evidence.
- Do not fabricate lineage or attestations, use an unrelated identity, bypass access controls, or make provenance-only limitations an artificial merge blocker.

## 5. Validation and coverage

- Use repository-native build, lint, typecheck, static-analysis, test, and physical-qualification checks. When MCP validation cannot execute a valid command, run the native equivalent and preserve its evidence.
- Aim for **90% meaningful coverage of testable first-party code**, especially new or substantially changed code. This is a target, not an unconditional numerical merge gate. Report the metric, scope, and exclusions; important missing behavior remains a concern at any percentage. Do not create brittle tests for coverage theater.

## 6. Independent review

- Every change requires independent review and direct ChatGPT inspection of the source and tests. Cumulative review must cover the final implementation and correction deltas. Targeted follow-up is acceptable when earlier evidence remains valid. The independent reviewer must not author approved changes.
- A confirmed P0/P1 defect that is introduced or materially worsened by the candidate, or is included in the accepted task scope, **cannot be waived**. Fix it or factually disprove it before merge. Unrelated pre-existing defects do not automatically block.
- Material in-scope P2 findings require fixes. Justified unrelated or out-of-scope deferral is allowed. P3 findings are advisory unless evidence warrants elevation. Do not reclassify a true P1 merely to merge.
- Corrections ordinarily stay on the same worktree and PR. Create a new corrective delegation only when warranted or required by the tool.
- Use evidence-driven debugging; do not make indefinite speculative retries.

## 7. CI and integration context

- New executable-code projects have CI. The first task under this process in an existing repository must integrate applicable existing local suites into CI when they are inadequate.
- CI onboarding means the intended suites actually run successfully. A green but skipped or misconfigured job is insufficient. Process-required checks apply even without branch protection. Track hardware or unavailable-platform gaps explicitly.
- Required CI covers final PR changes in the applicable integration context. Record the PR HEAD and the actual tested head, test-merge, or merge-group SHA; verify that the assessed changes and relevant target state are current before merge. A change invalidates only affected review and validation, which must be refreshed proportionately.
- Investigate CI infrastructure failures and flakiness. Local Cubic quota exhaustion alone is not blocking when independent local review is complete.

## 8. Merge readiness

- ChatGPT must be able to inspect the source directly through MCP or GitHub. It reviews the final implementation and integration, PAC/TAC status, validation and coverage, cumulative independent findings, actual CI execution, qualifications, risks, and exceptions.
- Readiness verdicts are **READY**, **BLOCKED**, or **READY WITH EXPLICIT EXCEPTION**. The P0/P1 rule in §6 is non-waivable. Administrative-only provenance limitations may be accepted with alternative evidence.
- ChatGPT determines technical readiness. The owner explicitly authorizes merging, including through “merge” or “close this out.”

## 9. Exceptions and qualification

- Merge permission is not a substantive waiver. Identify each unmet requirement, residual risk, permitted scope, and follow-up. A failed check remains failed; an unrun check remains unverified, even if integration is authorized.
- Distinguish integration from product, hardware, and release qualification. Keep every deferred criterion’s ID, content, rationale, and status open, or move it to a linked issue without losing the obligation.
- Transferring already-authorized tracking is bookkeeping. Changing accepted scope or deferring a substantive requirement requires owner authorization; existing authorization may suffice.
- Exceptions never waive a confirmed in-scope P0/P1 defect, required direct source access, actual independent review, or an approved security boundary. A separately approved architectural revision may intentionally change the approved design; that is not a waiver.

## 10. PR and review feedback

- Codex may publish draft PRs after local checks, but may not merge them. ChatGPT checks feedback and CI when a PR is published or updated, when the user requests review feedback, and before merge. It adjudicates valid in-scope findings, false positives, and out-of-scope follow-ups.
- Do not continuously monitor a PR unless monitoring is configured.

## 11. Merge/closeout/cleanup

- After an authorized merge, verify the merge commit and applicable validation. Keep closeout open and report pending or failed post-merge checks; investigate rather than automatically reverting. Do not require a new post-merge pipeline unless an existing requirement calls for one.
- Close the issue when its accepted scope is complete. Keep a durable record of accepted behavior, rationale, reviewed and tested revision, remaining obligations, and exceptions outside a disposable worktree.
- Before deleting a worktree, prove that no valuable unmerged or uncommitted changes or sole-copy evidence would be lost; safely preserve or transfer them first. Retain the worktree for chained tasks, investigation, recovery, or uncertain disposition, and report **MERGED — CLEANUP PENDING** when appropriate.
- When safe, remove the exact worktree and MCP root registration. MCP registration removals and their restart handoffs follow the owner-only lifecycle in §4. If a tool cannot perform an authorized cleanup action, provide verified exact terminal commands. Never use broad destructive cleanup without guards.

## 12. Distribution/pinning

- The single canonical private repository, [danielbyon/development-process](https://github.com/danielbyon/development-process), holds policy, decision records, focused Skill source, templates, and installation and update guidance.
- The three focused Skills are:
  - **development-orchestrator:** ChatGPT planning, delegation, and plan review.
  - **development-review:** ChatGPT source review, review adjudication, readiness, and merge guidance.
  - **delegation-executor:** Codex worktree and delegation setup, implementation, validation, and PR preparation.
- Skills operationally adapt the canonical policy; they do not duplicate its full governance text. Keep project-specific AGENTS.md instructions minimal and preserve native commands and constraints. Auxiliary Skills cannot override authority or gates; resolve conflicts explicitly.
- New tasks pin the current owner-approved immutable policy commit revision. A task and its Skills use that same pinned revision until an owner-approved migration. Do not silently apply newly installed Skills to ongoing tasks.
- Updating canonical policy or Skill source does not update its immutable distributed revision. After this change merges, obtain an owner-approved distribution/policy revision and migration decision before distributing the revised guidance. Keep existing task pins unchanged until that approval.
- Authoritative records are: the issue for accepted scope; the task or delegation for execution and result identity; the review for findings and disposition; and the PR for integration and readiness summary. Link these records and do not create competing task state.

## 13. Adoption and vocabulary

- Apply this process prospectively to all current and future projects; do not retroactively re-author historical delegations. Existing repositories adopt it at their next task and add adequate CI for local suites when needed.
- **next task:** inspect the repository, issues, and requirements; select the next approved slice; prepare a read-only Plan-mode handoff and a separate post-approval bootstrap/delegation handoff when a Codex plan is required.
- **codex plan:** read the plan, specification, and actual repository evidence; explicitly approve or provide a revision prompt.
- **implemented:** inspect source, tests, and independent findings; determine corrections and readiness.
- **review feedback:** inspect PR reviews, triage findings, and prepare targeted corrections.
- **close this out:** subject to quality gates and explicit authorization, merge, verify applicable CI, close the issue, and clean up the worktree safely.

## 14. Governance and initial bootstrap

- Substantive process changes require owner authorization. Technical Skill and documentation fixes follow the normal reviewed workflow.
- The initial repository bootstrap contract identifies exact unavailable prerequisites and the narrow accommodation. It does not waive source inspection, independent review, the P0/P1 rule, or truthful evidence. Reuse existing authorizations rather than adding ceremonial duplicate approval stages.
- Version 1 does not add centralized orchestration, redundant provenance, universal CI abstraction, a custom coordination framework, or fixed retry quotas.

## 15. Invariant

**Correctness and independently inspectable evidence are mandatory. Administrative completeness is not a substitute for correctness and must not obstruct otherwise valid work. No exception fabricates success, conceals defects, bypasses direct source inspection or independent review, or weakens an approved security boundary.**
