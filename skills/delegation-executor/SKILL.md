---
name: delegation-executor
description: Execute approved repository tasks in Codex, isolated worktree bootstrap and truthful delegation through implementation, validation, independent review, and draft PR preparation. Use scope approval; not read-only planning, review adjudication, or merging.
---

# Delegation Executor

Use this Skill to carry out an approved repository task. GitHub Issues hold the accepted scope, and the repository's canonical process defines authority and execution rules. Keep task records linked so they do not compete as separate sources of truth.

## Policy and authority

For a new task, resolve the newest verified immutable published CalVer release and record its release tag once. Read [the canonical policy for this release](https://github.com/danielbyon/development-process/blob/{{release_tag}}/docs/PROCESS.md) before applying the workflow. The packager must replace the token in the policy link; an unresolved template is not an approved distribution.

Verify release identity, tag target, native attestation, all eight assets, checksums and reconstructed provenance. Ignore GitHub's `latest` designation. If the newest eligible release cannot be verified, block rather than fall back silently. Record source, policy and builder revisions as separate internal evidence. If no immutable release exists, return `NO_IMMUTABLE_RELEASE`; do not select a static SHA default.

Check that the installed Skill exactly matches the selected release payload, or inspect explicit compatibility evidence identifying the installed payload/source, selected policy/source, behavioral differences and applicable validation. Unknown compatibility blocks until a compatible manual installation or explicit verified historical selection. A matching policy SHA or frontmatter alone is insufficient.

Continue an existing task using its recorded SHA or CalVer and Skill source identity. Resolve and inspect its exact policy without reselecting the newest release. Verify local policy bytes and provenance before relying on them. Preserve historical pins unless the owner explicitly approves migration. Publication never installs Skills, changes global instructions or migrates active tasks.
- Follow the accepted issue, approved plan, and project instructions. Do not widen scope or silently change the task contract.
- ChatGPT approves plans, directly inspects final source and tests, adjudicates review, and decides technical readiness. The repository owner decides material product, scope, architecture, and security trade-offs and explicitly authorizes merges.
- This Skill does not authorize a merge, waive a required gate, or permit an external action outside the approved task.

## Verify the task before editing

1. Read the accepted issue, relevant specifications and decision records, project instructions, source, tests, and active task records. Record the outcome, PAC/TAC, authorized paths, constraints, exclusions, policy pin, baseline, validation requirements, and reviewer requirements. Use acceptance identifiers and criteria from approved records. If PAC/TAC are absent, say so instead of inventing them.
2. In Codex Plan mode, investigate read-only. Do not change files, branches, worktrees, MCP configuration, or delegation records. State the verified checkout and expected baseline. Label any uncreated branch or worktree as proposed, and name one bootstrap owner. The task worktree does not need to exist for planning.
3. After producing a plan, wait for ChatGPT approval before implementation. The designated owner then creates or verifies isolation in Agent/execution mode. A separately authorized bootstrap before planning must also run as a distinct execution-mode step; never perform it in Plan mode.
4. Before editing source or materializing a worktree-bound Delegation v3 task, verify repository identity and root, worktree path, task branch, baseline commit, current HEAD, cleanliness for a new task, and task-root identity when required. Compare these facts with the approved plan. Stop for ChatGPT reassessment if material drift changes its assumptions.
5. A new task needs a clean, isolated starting tree. When resuming, verify the task identity and preserve legitimate in-progress edits. Do not reset, stash, clean, delete, or mix unrelated changes, even in response to a general request to make the tree clean. Keep unrelated work out of the task diff. If it blocks progress, ask for a specific, owner-approved disposition before moving or deleting it. Preserve stale or dirty primary checkouts and work in the isolated task root.
6. If the repository has no HEAD, stop until it has a valid baseline. Do not invent source identity, task IDs, or Delegation v3 lineage.

## Xcode MCP workspace targeting

For approved tasks that require Xcode MCP, complete the canonical workflow in docs/PROCESS.md §4 after verifying the task worktree and before the first workspace-dependent MCP operation.

- Access Xcode MCP only through the existing configured client; system-managed on-demand activation is allowed. Server lifecycle and global authorization remain owner-only under the canonical process. A native-only task does not require MCP initialization or authorization.
- Inspect installed tool schemas before choosing operations. The catalog inspected for Issue #16 exposes XcodeOpenWorkspace with absolute-path input and workspaceIdentifier plus optional workspacePath output, and XcodeListWorkspaces for resolving an exact identifier. Confirm the selected workspace or project type is supported and its identity can be resolved; otherwise report the limitation and block that MCP operation. Recheck actual schemas before use.
- After the canonical process verifies the selected workspace, pass its workspaceIdentifier to every supported workspace-scoped operation and record the selection, identity, and operation evidence in the existing task record.
- Native builds and tests may continue when their command and target are scoped to the verified task worktree. Record those results separately; a passing native check does not turn an unavailable or failed MCP check into PASS.

## MCP registration and delegation

- Follow policy §4 to identify the running GPT Repo MCP instance and its exact server root registry. Use Codex client connection settings only to identify the connection. Verify the launch path and context before choosing the registry. `repo_list_roots` reports active recognition and cannot identify the backing file by itself.
- After worktree verification, compare the exact repo ID and canonical root in the server file and active root listing. An exact existing disk entry is a no-op. Stop on an ID or root conflict. For an authorized add, use supported offline administration with the explicit absolute registry path and minimum authorized permissions. Verify before writing that the method preserves unrelated entries and settings and the file's ownership and access permissions. Validate offline afterward. If the file or safe administration cannot be verified, stop the edit.
- Record the verified registry path, repo ID and root, disk action, offline result, active result, and pending owner action. Keep credentials out of evidence. Distinguish a verified absence from an unverified state.
- MCP server lifecycle is owner-only. Never start, stop, restart, reload, kill, reconnect, replace, or otherwise manage the server, including indirectly through scripts, process managers, tunnel wrappers, cleanup commands, or tools.
- If a verified configuration change requires owner reconnection, report `MCP RESTART REQUIRED — OWNER ACTION`, the exact configuration path, changed entries, static validation result, and pending recognition checks. Do not claim activation until the owner confirms reconnection; then verify recognized configuration read-only.
- Prefer native, worktree-bound Delegation v3 materialization after plan approval and identity checks whenever registration of the actual task root and the required administration capabilities are verified. Use manual Codex execution by default, including when native V3 materialization is used; a queued runner is not required. Materialize only the approved outcome, PAC/TAC, scope, constraints, exclusions, and policy pin; do not add acceptance criteria.
- When native root registration, required administration capabilities, or required lineage is unavailable, use a truthful, cross-referenced manual task contract. Preserve the real source identity, issue, outcome, PAC/TAC, scope, constraints, exclusions, policy pin, results, and review evidence. Never fabricate task IDs, child lineage, attestations, registration, or success.

## Implement and validate

- During implementation, apply the task-independent naming supplement below. Inspect changed names, strings, comments, and paths with their references, including task-named worktree contents. Record confirmed candidate violations and compatibility-sensitive items needing migration; keep unrelated tracked debt separate.

**Task-independent naming supplement (existing task pins remain unchanged): Scope includes types, functions, methods, variables, and constants; tests and fixtures; scripts and first-party generators; maintained technical documentation and source comments; logging, diagnostic, and configuration strings; and implementation-owned files and directories. Keep task IDs in purpose-based task records and preserve stable domain and protocol identifiers. Preserve compatibility-sensitive public APIs, persisted keys, serialized fields and data, wire formats, reflection-visible names, and dynamic string lookups; verify consumers before changing configuration, logging, or diagnostic strings. This supplement authorizes no behavior or compatibility change. Treat confirmed compatibility-sensitive changes as Tier 2 and require separate owner-approved migration scope.**
- Fix confirmed naming violations introduced or materially worsened by this task, and violations within its accepted slice, before completion. Record unrelated pre-existing debt for separate cleanup without letting it block an otherwise complete slice.
- Use the repository's native build, lint, type-check, static-analysis, and test commands. Record the commands and results. Label each check passed, failed, skipped, or unavailable. An equivalent local check does not turn an unavailable MCP result into a pass.
- Aim for 90% meaningful coverage of testable first-party code. Treat this as a target, not a numerical merge gate. Do not add brittle tests merely to raise coverage. Report the metric's scope and exclusions. Identify relevant hardware qualification or state `N/A` when it does not apply.
- Keep changes within the accepted scope. Do not force-push or run broad, destructive cleanup.

## Independent review and draft PR

- Obtain a full-diff review from a separate, non-authoring execution. Prefer local Cubic. If Cubic is unavailable, use a separate Codex execution; the author cannot serve as the independent reviewer.
- Have an independent reviewer inspect every correction delta. Keep cumulative review evidence tied to the exact source revision. Rerun only validation invalidated by each change.
- ChatGPT must directly inspect the final source and tests before technical readiness. Do not claim that inspection happened unless it did.
- After local checks and independent review, prepare a draft PR that references the accepted issue. Verify actual CI jobs and logs, including which suites ran, were skipped, or failed. Record the PR HEAD, tested integration SHA, and base relationship; a green summary alone is insufficient.
- Keep the PR in draft and the issue open until the owner authorizes the next step. Never merge.

## Safe closeout

After an owner-authorized merge, verify the merge result and applicable checks. Once required post-merge checks pass, follow the canonical process in §11 for primary-main synchronization and its verification.

When §11's checks allow a fast-forward, run `git merge --ff-only --no-overwrite-ignore --no-autostash origin/main` from the verified primary root. This safe fast-forward is required without a second owner approval. Do not interpret the prohibition on force-updating `main` as a prohibition on this operation. Preserve the checkout and follow §11's disposition when a required precondition fails. Never use reset, rebase, stash, or branch switching to bypass a safety check.

Before removing the task worktree, verify its identity and integration. Confirm a verified backup or preserve valuable unmerged changes and sole-copy artifacts in an owner-approved destination. If preservation is unresolved, retain the worktree and report `MERGED — CLEANUP PENDING`.

Verify the exact task registration in the server root registry and active listing. Record verified absence only if both verified views show the root absent and no task registration removal is pending verification. For a registered root, remove only the authorized exact disk entry by a method that preserves unrelated settings and the file's ownership and access permissions. Require successful offline validation while the worktree still exists. Wait for any required owner restart and confirmation of availability, then verify active absence read-only. Retain the directory and report `MERGED — CLEANUP PENDING` while either view, validation, or owner action is unresolved. After an owner handoff, verify the running instance and its backing file again. Recheck disk and active absence immediately before deleting the exact task worktree. For a removed entry, verify offline validation still applies to the current file. Retain the worktree on registry drift. Recheck identity, integration, and preservation before removal.
