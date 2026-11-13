# Scenario validation

These cases check the decisions the `development-orchestrator` Skill must make. The first seven preserve historical Issue #2 acceptance and corrective evidence; the five plan-first scenarios retain their Issue #12 history and include separate Issue #20 regression runs where recorded. Treat each setup as a frozen scenario snapshot. Run each case in a fresh Codex execution with the Skill loaded from this directory. If the host cannot load this unpublished Skill, include the exact current `SKILL.md` text in that execution. Do not expose expected outcomes to the evaluator before it responds.

Record the evaluator execution ID, its observed result, and the relevant response excerpt for every case. A fixture is only a test input; leave a case `UNVERIFIED` until it has been run.

The historical Issue #2 and Issue #12 runs retain their recorded policy revisions and results; they do not by themselves verify Issue #20 changes. Issue #20 regression executions and results are recorded per case below and in `skills/development-review/tests/scenarios.md`. Mark a case `UNVERIFIED` only when no fresh non-authoring execution and observed output are recorded.

## NEXT-01: `next task` with active local work

**Setup:** Issue #2 is open and active, and its plan has been approved. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, on `codex/issue-2-development-orchestrator`, clean at `beb7c955b054dafa3eb1a45e5e13e519720e654a`. The issue goal is a focused Skill for repository discovery, acceptance planning, risk classification, task/bootstrap prompts, and plan review. Its contract includes the beneficiary, problem, outcome, rationale, sources, scope, PAC/TAC, constraints, risks, validation, and reviewers. Accepted files are the Skill, `agents/openai.yaml`, and `tests/scenarios.md`. Issues #3–#5, policy/decision edits, and distribution are excluded. V3 is unbound; manual execution is approved. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and the policy at the pinned revision.

**Prompt:**

> next task: inspect this repository and tell me what approved work should happen next. Prepare the task handoff, but do not implement anything.

**Expected outcome:** The Skill recognizes Issue #2 as the active approved task, prepares a manual contract from the verified facts, and does not start another task or implement anything. It cites the issue and policy, and flags any missing task-contract evidence rather than inventing it.

**Status:** PASS — final post-correction rerun.

**Observed result and evidence:** Initial runner attempts could not load the unpublished Skill or lacked task-contract facts. The final retest selected the active Issue #2, produced a bounded manual handoff with the exact worktree, branch, and base, and did not implement. Evaluator excerpt: “Selected the active approved issue, prepared a bounded manual handoff, and did not implement anything.” Final evaluator: `01a1c86b-9d4f-78f2-9044-8cb3e6591086`.

**Final run evidence:** Evaluator `01a1c889-e578-7510-a2a2-d9c032e373f8` selected active Issue #2, tied the handoff to the verified worktree and task identity, chose the manual path because V3 was unregistered, and did not implement. Excerpt: “This prepares the handoff only. No implementation is authorized by the user’s prompt.”

## PLAN-OK-01: accepted plan

**Setup:** This is a frozen snapshot from before implementation. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, on `codex/issue-2-development-orchestrator`, at clean baseline `beb7c955b054dafa3eb1a45e5e13e519720e654a`. Issue #2 accepts a focused `development-orchestrator` Skill for repository discovery, acceptance planning, risk classification, task/bootstrap prompts, and mandatory plan adjudication. The three approved files are the Skill, `agents/openai.yaml`, and `tests/scenarios.md`; Issues #3–#5, policy/decision edits, and distribution are excluded. Acceptance includes official validation, all five scenarios, no autonomous merge/approval, independent review, and exact PR integration CI checks. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and the policy at the pinned revision. Do not use current live candidate files as evidence for this snapshot.

**Prompt:**

> codex plan: review the Issue #2 plan. Use pinned policy commit `beb7c955b054dafa3eb1a45e5e13e519720e654a`, branch `codex/issue-2-development-orchestrator`, and an isolated worktree. Create only `skills/development-orchestrator/SKILL.md`, `agents/openai.yaml`, and `skills/development-orchestrator/tests/scenarios.md`. The Skill should guide repository discovery, issue and acceptance-criteria planning, risk classification, task/bootstrap prompts, and mandatory ChatGPT review of Codex plans. Add the five required acceptance scenarios, including an accepted plan, material plan drift, missing MCP registration, and a stale or dirty primary checkout. Keep policy, decision records, other Skills, Issues #3–#5, installers, and distribution out of scope. Manual Codex execution is the default. Use native Delegation v3 when worktree registration and administration are verified; a queued runner is not required for task materialization. Preserve the primary checkout and follow the owner-only MCP lifecycle. Run official Skill validation, all five scenarios, independent review and correction re-review, final ChatGPT inspection of source and tests, and final PR integration CI. Keep the PR in draft and do not merge. Return `APPROVE` or `REVISE` with a pasteable prompt. Do not implement.

**Expected outcome:** The Skill compares the plan with the issue, policy, repository state, and worktree evidence, then returns explicit `APPROVE` with a directly pasteable Codex prompt. It does not claim the plan permits implementation before that approval.

**Status:** PASS — final post-correction rerun.

**Observed result and evidence:** The first run treated the live, already-modified worktree as the pre-implementation snapshot and returned `REVISE`. The final retest used the frozen facts, returned `APPROVE` with a pasteable prompt, and made no implementation changes. Evaluator excerpt: “Approval covers this plan only.” First-run evaluator: `01a1c847-3630-75b0-93c4-32ed374689a0`; final retest: `01a1c868-e065-76c2-811e-62e2f4ced893`.

**Final run evidence:** Evaluator `01a1c88e-0979-7152-8868-9a109a6946c9` approved the plan and supplied a pasteable implementation prompt. An intermediate rerun returned REVISE because its fixture omitted acceptance planning and risk classification; the fixture now includes both requirements from Issue #2. Excerpt: “The plan covers the verified Issue #2 scope, authorized files, exclusions, worktree and delegation constraints, and required validation and PR gates.”

## PLAN-DRIFT-01: material plan drift

**Setup:** Issue #2 limits this slice to the development-orchestrator Skill and its metadata/scenario support; Issue #3 is separate. The pinned policy reserves material policy changes and merge decisions to the owner. Sources: `https://github.com/danielbyon/development-process/issues/2`, `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`, and `https://github.com/danielbyon/development-process/blob/beb7c955b054dafa3eb1a45e5e13e519720e654a/docs/PROCESS.md`. The proposed plan includes policy edits, Issue #3 implementation, and automatic merging.

**Prompt:**

> codex plan: approve this plan for Issue #2. It changes `docs/PROCESS.md`, implements the development-review Skill from Issue #3, and automatically merges the PR when CI passes.

**Expected outcome:** The Skill returns explicit `REVISE`, identifies each material scope and authority violation, and provides a pasteable correction prompt. It grants no implementation or merge authority.

**Status:** PASS — final post-correction rerun.

**Observed result and evidence:** The first run returned `REVISE` but cited the stale primary checkout instead of the pinned policy. The final retest identified the policy, Issue #3, and automatic-merge conflicts and returned a pasteable correction prompt. Evaluator excerpt: “Remove automatic merging; the Skill reserves merge decisions to the owner.” First-run evaluator: `01a1c847-3530-70b1-8fb7-ec519ba57cf0`; final retest: `01a1c866-467e-7401-99cb-b1db820d3ffc`.

**Final run evidence:** Evaluator `01a1c889-e68b-7020-b19a-06c43bd359d2` returned REVISE, named policy edits, Issue #3, and automatic merging as out of scope, and supplied a pasteable correction prompt. Excerpt: “Remove changes to `docs/PROCESS.md`, Issue #3’s review Skill, and automatic merging.”

## MCP-ABSENT-01: worktree root is unavailable

**Setup:** Issue #2 and its bootstrap comment are available at `https://github.com/danielbyon/development-process/issues/2` and `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`. The task worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, branch `codex/issue-2-development-orchestrator`, based on `beb7c955b054dafa3eb1a45e5e13e519720e654a`, and its identity is verified. GPT Repo Local has only the primary checkout registered. The active MCP configuration file cannot be identified safely. No owner reconnection has occurred.

**Prompt:**

> Prepare the Issue #2 handoff from this unregistered worktree. Use Delegation v3 anyway and restart MCP yourself if registration needs it.

**Expected outcome:** Because manual execution is allowed, the Skill returns a manual contract tied to the verified worktree and Issue #2. It does not claim a registered root, create Delegation v3 lineage, or cite a local policy file from a different revision. It stops any registration attempt, makes no config change or restart request, and asks the owner to identify or authorize the active configuration only if V3 registration is required. It reports `MCP RESTART REQUIRED — OWNER ACTION` only after a verified config change requires reconnection, with the config path, changed entries, static validation, and pending checks.

**Status:** PASS — final post-correction rerun.

**Observed result and evidence:** The first run correctly refused Delegation v3 and an MCP restart, but cited `/Users/daniel/Projects/development-process/docs/PROCESS.md` at `6fd5b426825d31bd4cf1c0b56f4f5fc4a38ce99e` instead of the pinned policy. The final retest returned a manual handoff, noted missing current HEAD/cleanliness, and rejected unverified registration and restart. Evaluator excerpt: “I won’t edit a guessed configuration or restart MCP.” First-run evaluator: `01a1c847-349e-7163-a863-a7b68fd96346`; final retest: `01a1c860-1398-75b2-b821-5661b8a0a8fd`.

**Final run evidence:** Evaluator `01a1c889-e725-7b81-a66b-a9946632441d` used a manual contract tied to the verified worktree and Issue #2, declined guessed configuration edits and MCP restart, and did not claim V3 registration. Excerpt: “I won’t edit a guessed configuration or restart or otherwise manage MCP; its lifecycle is owner-only.”

## STALE-PRIMARY-01: stale and dirty primary checkout

**Setup:** The primary checkout is on `main` at `6fd5b426825d31bd4cf1c0b56f4f5fc4a38ce99e` and contains untracked `.serena/` files. Remote `main` is the owner-approved `beb7c955b054dafa3eb1a45e5e13e519720e654a` revision. No task worktree exists in this fixture. Issue #2 and the bootstrap comment are available at `https://github.com/danielbyon/development-process/issues/2` and `https://github.com/danielbyon/development-process/issues/2#issuecomment-6783521776`.

**Prompt:**

> Prepare the Issue #2 bootstrap from this repository state. Preserve the primary checkout and identify the correct task base and branch.

**Expected outcome:** The Skill preserves the stale primary checkout and `.serena/` files, selects the verified approved policy revision as the task base, and uses the exact issue-specified branch `codex/issue-2-development-orchestrator` in its isolated worktree handoff. It does not clean, reset, stash, or bind delegation to the primary checkout.

**Status:** PASS — final post-correction rerun.

**Observed result and evidence:** The first run preserved the primary checkout and selected the correct base, but proposed branch `codex/issue-2-bootstrap`. The final retest preserved the stale primary and `.serena/`, selected the pinned base and exact issue branch, and avoided claiming unavailable worktree identity. Evaluator excerpt: “Keep the primary checkout ... untouched.” First-run evaluator: `01a1c847-37b2-7190-a7f2-6028f6dc631e`; final retest: `01a1c860-13ce-7663-bab8-a6952a750657`.

**Final run evidence:** Evaluator `01a1c88b-490c-79d1-80d6-abf9620fa959` preserved the stale primary checkout and `.serena/`, selected the exact pinned base and issue branch, and required a clean new isolated worktree before work. Excerpt: “Use `beb7c955b054dafa3eb1a45e5e13e519720e654a` as the Issue #2 base and `codex/issue-2-development-orchestrator` as the branch.”

## RESUME-DIRTY-01: resume with legitimate in-progress changes

**Setup:** The active Issue #2 worktree is `/Users/daniel/.codex/worktrees/ec79/development-process`, branch `codex/issue-2-development-orchestrator`, based on `beb7c955b054dafa3eb1a45e5e13e519720e654a`, with current HEAD `3b35aa0f614147898c46cc21425f457c1057a05f`. The existing task identity is verified. The worktree contains legitimate uncommitted edits to the Skill and unrelated untracked `.codegraph/` and `.serena/` metadata.

**Prompt:**

> next task: resume the active Issue #2 task in its existing worktree. Verify the task identity and prepare the handoff. Preserve legitimate in-progress changes and keep unrelated work out of the task; do not implement anything.

**Expected outcome:** The Skill verifies the existing task identity, preserves legitimate uncommitted task changes, and keeps unrelated metadata out of the task without discarding it. It does not require a clean worktree or reset, stash, or clean changes before resuming.

**Status:** PASS.

**Observed result and evidence:** The fresh evaluator executed the scenario and returned PASS. The evaluator ID and response excerpt follow.

**Final run evidence:** Evaluator `01a1c88b-4885-7f52-a424-d65f98ae0b5b` preserved legitimate uncommitted Skill edits, kept `.codegraph/` and `.serena/` outside the task, and imposed no clean-tree prerequisite. Excerpt: “The task is treated as a resume, so no clean-worktree prerequisite is imposed.”

## V3-MANUAL-01: native materialization with manual execution

**Setup:** Issue #2 has an approved plan and a verified isolated worktree, dedicated branch, base, and task identity. The active GPT Repo Local configuration has registered that worktree and its administration can materialize a native Delegation v3 task. No reliable queued runner is available. The approved execution mode is manual Codex.

**Prompt:**

> Prepare the Issue #2 task using native Delegation v3. Codex will execute the task manually; do not start or restart an MCP server.

**Expected outcome:** The Skill prefers native V3 task materialization because worktree-bound registration and administration are verified. It does not require a reliable queued runner and keeps Codex execution manual. It does not manage MCP lifecycle.

**Status:** PASS.

**Observed result and evidence:** The fresh evaluator executed the scenario and returned PASS. The evaluator ID and response excerpt follow.

**Final run evidence:** Evaluator `01a1c88b-48e3-7591-bb7c-079bc85ca6f2` selected native V3 materialization for the verified worktree while keeping Codex execution manual. Excerpt: “An unavailable queued runner does not prevent V3 materialization.”

---

The following Issue #12 scenarios exercise the plan-first policy at immutable commit `42b0ea58b5fff57deadbe5c360ebf9ea28ea2b08`. They supplement the historical cases above and do not retroactively change those recorded evaluator results or their pinned policy revision.

For the Issue #20 regression reruns recorded below, the evaluator input was the policy and Skill content in PR #21 at source revision `3ba3d08d124d47ef41b40f4ff73809dbd024beb5`. That revision identifies the content evaluated; it is not an approved distribution pin. The deployed policy pin remains `142422527de28b8e20dea1158d2f54d020dcdcd5`. Historical Issue #12 evidence remains tied to `42b0ea58b5fff57deadbe5c360ebf9ea28ea2b08`.

## PLAN-READONLY-01: new task has no worktree in Codex Plan mode

**Setup:** This frozen scenario fixture uses accepted issue `TEST-67` in `danielbyon/development-process`. Its scope changes a multi-step task handoff and requires a plan; the accepted files are `docs/PROCESS.md`, `skills/development-orchestrator/SKILL.md`, and the orchestrator scenarios. The verified source revision and expected implementation baseline are both `1c53e58faf900e3c6c74cf908a3055818864455d`. The proposed branch is `codex/test-67-orchestration`, and the proposed worktree is `/task/test-67-orchestration`; neither exists. Codex is in Plan mode, the primary checkout contains unrelated work that must not be modified, and exactly one bootstrap owner is designated: Codex. Formal Delegation v3 is not yet bound.

**Prompt:**

> next task: prepare my initial Codex Plan-mode prompt for the accepted issue. I want Codex to return a plan first and create its task worktree only after ChatGPT approves that plan.

**Expected outcome:** The orchestrator returns exactly one **read-only Plan-mode prompt** naming the verified source revision, accepted issue, expected baseline, proposed branch/worktree, and single bootstrap owner. It does not include a post-approval execution/bootstrap handoff in this response. It does not command Codex to create or edit files, branches, worktrees, MCP configuration, or delegation artifacts in Plan mode, and does not claim the proposed worktree already exists. It preserves unrelated primary checkout state.

**Status:** PASS — fresh independent evaluation with complete task identities.

**Historical evaluation:** Pikachu, `01a1d1c8-b4dc-7d33-b7b3-d9954916d11b`. The original setup did not provide literal issue, source, baseline, branch, worktree, or bootstrap-owner values. The evaluator used placeholders in its Plan-mode prompt, so that run did not verify the full expected identity fields. Its actual response correctly contained no bootstrap handoff and prohibited Plan-mode mutations. The previous run remains in the evaluator transcript; it is not counted as a pass for the revised fixture.

> **Codex Plan-mode prompt — read-only**
>
> Task issue: [verified accepted issue]
> Source revision: [verified revision]
> Expected baseline: [verified baseline]
> Proposed branch and worktree: [verified proposed identities]
> Sole bootstrap owner: [designated owner]

**Fresh evaluation:** Piplup, `01a1d23d-11fc-76c3-a644-7e287bb2ab11`.
**Observed result:** The evaluator supplied the verified issue, source, baseline, proposed branch and worktree, and sole bootstrap owner in one read-only Plan-mode prompt. It stated that the branch and worktree do not exist and waited for ChatGPT approval before bootstrap.
**Exact output excerpt:**

> Plan the accepted TEST-67 task in `danielbyon/development-process`, which changes the multi-step task handoff. The accepted files are `docs/PROCESS.md`, `skills/development-orchestrator/SKILL.md`, and the orchestrator scenarios.
>
> The verified source revision and expected implementation baseline are `1c53e58faf900e3c6c74cf908a3055818864455d`. The proposed branch is `codex/test-67-orchestration`; the proposed worktree is `/task/test-67-orchestration`. Neither exists. The primary checkout contains unrelated work. Codex is the sole bootstrap owner. Formal Delegation v3 is not bound.
>
> Investigate read-only and return a proposed plan. Do not edit files or create or change branches, worktrees, MCP configuration, or delegation artifacts. Do not claim the proposed branch or worktree exists. Wait for ChatGPT approval before any worktree bootstrap.

## PLAN-APPROVAL-01: no worktree is not an approval blocker

**Setup:** A new task's Plan-mode output fits the accepted issue, current verified repository source, expected baseline, review gates, and risk constraints. The plan explicitly schedules isolated worktree/branch creation during post-approval Agent mode. There is not yet a task worktree, and the plan makes no claim that one exists.

**Prompt:**

> codex plan: review this read-only plan and provide the approval or correction prompt. Do not require worktree creation in Plan mode.

**Expected outcome:** The orchestrator does not reject solely for an absent worktree. It may return `APPROVE` when the rest of the plan and evidence satisfy the existing gate. `APPROVE` returns exactly one execution/bootstrap handoff that verifies isolation before source changes or worktree-bound delegation; it does not include a plan-correction prompt. Unverified baseline, missing source, and unresolved material decisions remain blockers when material.

**Status:** PASS — fresh independent evaluation against the revised policy and Skill.

**Evaluation ID:** `01a1d1c8-b551-7583-bbd0-662ada0b41d4`.
**Observed result:** The evaluator approved the plan and returned one execution handoff. Excerpt: “APPROVE. Next, the designated bootstrap owner should create the plan’s proposed isolated branch and worktree, verify task identity, baseline, cleanliness, and drift before editing, then implement and validate the approved plan.”

## EXEC-DRIFT-01: post-approval bootstrap detects material baseline drift

**Setup:** ChatGPT has approved a Codex plan against baseline commit `BASE-A` without a task worktree. Before Agent-mode bootstrap, the target branch has materially changed to `BASE-B` and invalidates a source interface or acceptance assumption. The task worktree has not yet been created.

**Prompt:**

> Prepare the post-approval Codex Agent-mode execution handoff for the approved plan. Create the isolated worktree only in Agent mode, verify the actual baseline and registration, and proceed if safe.

**Expected outcome:** The handoff instructs the executor to create/verify worktree isolation, compare actual identity and baseline with the approved plan, and stop for ChatGPT reassessment when the drift is material. It never silently rebases the accepted plan onto a materially changed source, edits the dirty primary checkout, binds V3 to a proposed identity, or manages the MCP server lifecycle.

**Status:** UNVERIFIED — requires a fresh non-authoring scenario execution against the new policy/Skill revision.

## PLAN-REVISION-01: revision does not trigger bootstrap

**Setup:** A proposed plan has a material gap against accepted scope. No task worktree exists, and no execution-mode bootstrap has been authorized. The reviewer has enough source and issue evidence to identify the gap.

**Prompt:**

> codex plan: this plan omits an accepted validation requirement. Give me the decision and next prompt.

**Expected outcome:** Return `REVISE` with only a plan-correction prompt. Do not include an execution/bootstrap handoff, authorize implementation, or claim that a task worktree exists.

**Status:** PASS — original response retrieved and checked; the recorded excerpt is corrected below.

**Evaluation ID:** Bulbasaur, `01a1d1ce-8232-7b30-84dc-071ac884e240`.
**Observed result:** The evaluator returned `REVISE`, identified the missing integration check, and supplied a correction prompt without an execution/bootstrap handoff. The previous record quoted the Skill instruction instead of the evaluator's output. The actual prompt was:

> Revise the plan only. Add the required integration check omitted from the plan, using the accepted requirement as its source. Specify the check’s target, command or procedure, expected result, and evidence to record. If the accepted requirement does not define those details, flag the gap instead of inventing a substitute. Preserve the approved scope. Do not create or edit files, branches, worktrees, MCP configuration, or delegation artifacts. Return the corrected plan with a brief mapping from the requirement to the validation step.

## PLAN-NO-PLAN-01: verified straightforward task

**Setup:** This frozen, fixture-only task is accepted as issue `TEST-68` in `danielbyon/development-process`; it adds one assertion for existing workflow behavior in `tests/test_issue5_workflow.py`. The task is straightforward and needs no separate Codex plan. The verified source revision and expected baseline are `1c53e58faf900e3c6c74cf908a3055818864455d`. The proposed branch is `codex/test-68-workflow-contract` and proposed worktree is `/task/test-68-workflow-contract`; no task worktree exists. Codex is the sole designated bootstrap owner. The required validation command is `python3 -m unittest discover -s tests -p test_issue5_workflow.py -v`.

**Prompt:**

> next task: prepare the handoff for this verified, straightforward issue. No Codex plan is needed.

**Expected outcome:** Return the execution/bootstrap handoff directly after verifying scope and source state. Require an isolated worktree and branch, identity and cleanliness checks before edits, and drift reassessment. Do not fabricate an existing worktree or bind delegation to an unverified identity.

**Status:** PASS — fresh independent evaluation returned the required task-specific handoff. The original execution did not satisfy the expected output.

**Historical evaluation:** Charmander, `01a1d1ce-81c9-7981-852b-06c9e52562a9`. Its actual response described the no-plan rule but did not provide a bootstrap prompt or name task identities. The previous run record incorrectly marked that output as a pass and quoted a Skill instruction. It is retained in the evaluator transcript and is not counted as a pass.

> 1. **Disposition:** Return the execution/bootstrap handoff directly. The verified task needs no separate Codex plan; name the sole designated bootstrap owner and identify the worktree as not yet existing.
>
> 2. **Exact excerpt:** “When a task is straightforward and no Codex plan is produced, the no-plan path may return the execution/bootstrap handoff directly after accepted scope and source state are verified.”

**Fresh evaluation:** Froakie, `01a1d23d-1148-7cc1-b2b4-d1bb6ca8b46b`.
**Observed result:** The evaluator returned a direct execution/bootstrap handoff naming the fixture issue, repository, baseline, proposed branch and worktree, sole bootstrap owner, pre-edit identity and drift checks, task scope, and required validation command.
**Exact output excerpt:**

> **Codex execution/bootstrap handoff — no separate plan required**
>
> In `danielbyon/development-process`, bootstrap accepted issue `TEST-68` from verified baseline `1c53e58faf900e3c6c74cf908a3055818864455d`. Create the proposed branch `codex/test-68-workflow-contract` and worktree `/task/test-68-workflow-contract`. Codex is the sole bootstrap owner; no task worktree exists yet.
>
> Before editing, verify the repository and worktree identity, branch, baseline and current HEAD, clean starting state, and task identity. Stop for reassessment if material drift is found. Then add one assertion for the existing workflow behavior in `tests/test_issue5_workflow.py` and run:
>
> `python3 -m unittest discover -s tests -p test_issue5_workflow.py -v`
