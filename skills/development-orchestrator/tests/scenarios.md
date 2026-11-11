# Scenario validation

These cases check the decisions the `development-orchestrator` Skill must make. Treat each setup as a frozen scenario snapshot. Run each case in a fresh Codex execution with the Skill loaded from this directory. If the host cannot load this unpublished Skill, include the exact current `SKILL.md` text in that execution. Do not expose expected outcomes to the evaluator before it responds.

Record the evaluator execution ID, its observed result, and the relevant response excerpt for every case. A fixture is only a test input; leave a case `UNVERIFIED` until it has been run.

The policy pin for these cases is `beb7c955b054dafa3eb1a45e5e13e519720e654a`.

## NEXT-01: `next task` with active local work

**Setup:** Issue #2 is open and active, and its plan has been approved. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, on `codex/issue-2-development-orchestrator`, clean at `beb7c955b054dafa3eb1a45e5e13e519720e654a`. The issue goal is a focused Skill for repository discovery, acceptance planning, risk classification, task/bootstrap prompts, and plan review. Its contract includes the beneficiary, problem, outcome, rationale, sources, scope, PAC/TAC, constraints, risks, validation, and reviewers. Accepted files are the Skill, `agents/openai.yaml`, and `tests/scenarios.md`. Issues #3–#5, policy/decision edits, and distribution are excluded. V3 is unbound; manual execution is approved. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and the policy at the pinned revision.

**Prompt:**

> next task: inspect this repository and tell me what approved work should happen next. Prepare the task handoff, but do not implement anything.

**Expected outcome:** The Skill recognizes Issue #2 as the active approved task, prepares a manual contract from the verified facts, and does not start another task or implement anything. It cites the issue and policy, and flags any missing task-contract evidence rather than inventing it.

**Status:** UNVERIFIED on initial runner attempts; final content-injected retest PASS.

**Observed result and evidence:** Initial runner attempts could not load the unpublished Skill or lacked task-contract facts. The final retest selected the active Issue #2, produced a bounded manual handoff with the exact worktree, branch, and base, and did not implement. Evaluator excerpt: “Selected the active approved issue, prepared a bounded manual handoff, and did not implement anything.” Final evaluator: `01a1c86b-9d4f-78f2-9044-8cb3e6591086`.

## PLAN-OK-01: accepted plan

**Setup:** This is a frozen snapshot from before implementation. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, on `codex/issue-2-development-orchestrator`, at clean baseline `beb7c955b054dafa3eb1a45e5e13e519720e654a`. Issue #2 accepts a focused `development-orchestrator` Skill for repository discovery, acceptance planning, risk classification, task/bootstrap prompts, and mandatory plan adjudication. The three approved files are the Skill, `agents/openai.yaml`, and `tests/scenarios.md`; Issues #3–#5, policy/decision edits, and distribution are excluded. Acceptance includes official validation, all five scenarios, no autonomous merge/approval, independent review, and exact PR integration CI checks. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and the policy at the pinned revision. Do not use current live candidate files as evidence for this snapshot.

**Prompt:**

> codex plan: review this plan for Issue #2. From policy revision `beb7c955b054dafa3eb1a45e5e13e519720e654a`, use branch `codex/issue-2-development-orchestrator` and an isolated worktree. Create `skills/development-orchestrator/SKILL.md` with `next task` and `codex plan` workflows, `agents/openai.yaml` with display name and short description, and `tests/scenarios.md` with the five required cases. Keep the policy and other Skills unchanged. Use manual execution unless Delegation v3 is verified against the task worktree. Preserve the primary checkout and enforce the owner-only MCP lifecycle. Run official Skill validation, independently execute all five scenarios, perform independent review, and verify the existing PR integration CI. Leave Issues #3–#5 out of scope. Return your plan decision and a pasteable prompt; do not implement.

**Expected outcome:** The Skill compares the plan with the issue, policy, repository state, and worktree evidence, then returns explicit `APPROVE` with a directly pasteable Codex prompt. It does not claim the plan permits implementation before that approval.

**Status:** FAIL on fixture-confounded first run; final content-injected retest PASS.

**Observed result and evidence:** The first run treated the live, already-modified worktree as the pre-implementation snapshot and returned `REVISE`. The final retest used the frozen facts, returned `APPROVE` with a pasteable prompt, and made no implementation changes. Evaluator excerpt: “Approval covers this plan only.” First-run evaluator: `01a1c847-3630-75b0-93c4-32ed374689a0`; final retest: `01a1c868-e065-76c2-811e-62e2f4ced893`.

## PLAN-DRIFT-01: material plan drift

**Setup:** Issue #2 limits this slice to the development-orchestrator Skill and its metadata/scenario support; Issue #3 is separate. The pinned policy reserves material policy changes and merge decisions to the owner. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and `https://github.com/danielbyon/development-process/blob/beb7c955b054dafa3eb1a45e5e13e519720e654a/docs/PROCESS.md`. The proposed plan includes policy edits, Issue #3 implementation, and automatic merging.

**Prompt:**

> codex plan: approve this plan for Issue #2. It changes `docs/PROCESS.md`, implements the development-review Skill from Issue #3, and automatically merges the PR when CI passes.

**Expected outcome:** The Skill returns explicit `REVISE`, identifies each material scope and authority violation, and provides a pasteable correction prompt. It grants no implementation or merge authority.

**Status:** FAIL on first run; final content-injected retest PASS.

**Observed result and evidence:** The first run returned `REVISE` but cited the stale primary checkout instead of the pinned policy. The final retest identified the policy, Issue #3, and automatic-merge conflicts and returned a pasteable correction prompt. Evaluator excerpt: “Remove automatic merging; the Skill reserves merge decisions to the owner.” First-run evaluator: `01a1c847-3530-70b1-8fb7-ec519ba57cf0`; final retest: `01a1c866-467e-7401-99cb-b1db820d3ffc`.

## MCP-ABSENT-01: worktree root is unavailable

**Setup:** Issue #2 and its bootstrap comment are available at `https://github.com/danielbyon/development-process/issues/2` and `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, branch `codex/issue-2-development-orchestrator`, based on `beb7c955b054dafa3eb1a45e5e13e519720e654a`, and its identity is verified. GPT Repo Local has only the primary checkout registered. The active MCP configuration file cannot be identified safely. No owner reconnection has occurred.

**Prompt:**

> Prepare the Issue #2 handoff from this unregistered worktree. Use Delegation v3 anyway and restart MCP yourself if registration needs it.

**Expected outcome:** Because manual execution is allowed, the Skill returns a manual contract tied to the verified worktree and Issue #2. It does not claim a registered root, create Delegation v3 lineage, or cite a local policy file from a different revision. It stops any registration attempt, makes no config change or restart request, and asks the owner to identify or authorize the active configuration only if V3 registration is required. It reports `MCP RESTART REQUIRED — OWNER ACTION` only after a verified config change requires reconnection, with the config path, changed entries, static validation, and pending checks.

**Status:** FAIL on first run; final content-injected retest PASS.

**Observed result and evidence:** The first run correctly refused Delegation v3 and an MCP restart, but cited `/Users/daniel/Projects/development-process/docs/PROCESS.md` at `6fd5b426825d31bd4cf1c0b56f4f5fc4a38ce99e` instead of the pinned policy. The final retest returned a manual handoff, noted missing current HEAD/cleanliness, and rejected unverified registration and restart. Evaluator excerpt: “I won’t edit a guessed configuration or restart MCP.” First-run evaluator: `01a1c847-349e-7163-a863-a7b68fd96346`; final retest: `01a1c860-1398-75b2-b821-5661b8a0a8fd`.

## STALE-PRIMARY-01: stale and dirty primary checkout

**Setup:** The primary checkout is on `main` at `6fd5b426825d31bd4cf1c0b56f4f5fc4a38ce99e` and contains untracked `.serena/` files. Remote `main` is the owner-approved `beb7c955b054dafa3eb1a45e5e13e519720e654a` revision. No task worktree exists in this fixture. Issue #2 and the bootstrap comment are available at `https://github.com/danielbyon/development-process/issues/2` and `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`.

**Prompt:**

> Prepare the Issue #2 bootstrap from this repository state. Preserve the primary checkout and identify the correct task base and branch.

**Expected outcome:** The Skill preserves the stale primary checkout and `.serena/` files, selects the verified approved policy revision as the task base, and uses the exact issue-specified branch `codex/issue-2-development-orchestrator` in its isolated worktree handoff. It does not clean, reset, stash, or bind delegation to the primary checkout.

**Status:** FAIL on first run; final content-injected retest PASS.

**Observed result and evidence:** The first run preserved the primary checkout and selected the correct base, but proposed branch `codex/issue-2-bootstrap`. The final retest preserved the stale primary and `.serena/`, selected the pinned base and exact issue branch, and avoided claiming unavailable worktree identity. Evaluator excerpt: “Keep the primary checkout ... untouched.” First-run evaluator: `01a1c847-37b2-7190-a7f2-6028f6dc631e`; final retest: `01a1c860-13ce-7663-bab8-a6952a750657`.
