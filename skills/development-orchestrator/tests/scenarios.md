# Scenario validation

These cases check the decisions the `development-orchestrator` Skill must make. The first seven preserve historical Issue #2 acceptance and corrective evidence; the five plan-first scenarios retain their Issue #12 history and include separate Issue #20 regression runs where recorded. Treat each setup as a frozen scenario snapshot. For synthetic evaluations, give a fresh evaluator the exact candidate `SKILL.md` text. Use authenticated ChatGPT session evidence for live installation qualification. Do not expose expected outcomes to the evaluator before it responds.

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

## NAME-PLAN-HELPER: task-derived helper in an approved plan

**Setup:** Frozen fixture for `danielbyon/development-process`. The clean main checkout and accepted issue `TEST-81` are verified at baseline `9da7c0b9113da4c0aab172860bdc5d5c77cccf0d`. The issue adds duplicate-message filtering without changing public behavior or persistence. The proposed branch is `codex/test-81-message-filter` and proposed worktree is `/work/test-81-message-filter`; no task worktree exists. The owner approved the behavior and plan. The plan proposes internal helper `issue_81_message_filter` and a focused test. The supplied source and test inspection finds no persisted, serialized, external, or dynamic use of the helper name.

**Prompt:**

> codex plan: review this plan and return APPROVE or REVISE with any required correction.

**Expected outcome:** Do not treat approval as grandfathering the internal name. Require a stable name such as `message_filter`, preserve the approved behavior, and keep the task-derived name out of the implementation handoff.

**Pre-change baseline:** FAIL — the old Skill approved the plan and included `issue_81_message_filter` in the execution handoff. Evaluator Vulpix: `01a1d36c-964f-70e2-9147-5bc13e9576d7`.

**Status:** PASS — final independent execution.
**Evaluator:** Mimikyu, `01a1d386-9213-7e00-af7f-d39b46034657`.
**Observed result:** Revised the plan to replace `issue_81_message_filter` with a behavior-based name and kept the accepted behavior and scope.
**Evidence:** “Replace the task-derived helper name `issue_81_message_filter` with an internal name based on its behavior, domain concept, or stable technology.”

## NAME-PLAN-RECORDS: task identifiers in active planning records

**Setup:** Frozen fixture for `danielbyon/development-process`. The clean main checkout and accepted issue `TEST-82` are verified at baseline `9da7c0b9113da4c0aab172860bdc5d5c77cccf0d`. The issue adds a bounded retry policy with no public API or persistence changes. The active task plan and ADR identify `TEST-82`; the proposed branch is `codex/test-82-retry-policy` and proposed worktree is `/work/test-82-retry-policy`. No task worktree or implementation contents exist yet. The plan proposes stable implementation names such as `retry_policy` and `retry_delay`.

**Prompt:**

> codex plan: review the use of task identifiers in these records and implementation names. Do not edit files.

**Expected outcome:** Preserve task identifiers in the plan, ADR, and issue as purpose-based task records. Label the branch and worktree as proposed; do not rewrite records or claim to have inspected implementation contents before a worktree exists.

**Status:** PASS — final independent execution.
**Evaluator:** Gardevoir, `01a1d388-1956-7fa0-9faf-06fa7565f8c2`.
**Observed result:** Preserved `TEST-82` in the plan, ADR, and proposed branch/worktree labels; approved only the naming choices and noted that no implementation paths were supplied.
**Evidence:** “The plan and ADR may identify `TEST-82`; the proposed branch and worktree names may also carry that task identity.”

## NAME-PLAN-DOMAIN: domain name overlaps an issue title

**Setup:** Frozen fixture for `danielbyon/development-process`. The clean main checkout and accepted issue `TEST-83` are verified at baseline `9da7c0b9113da4c0aab172860bdc5d5c77cccf0d`. Its title is “Support V2 message envelopes.” The supplied protocol specification defines version 2 as the stable wire-protocol version, and the source and tests use that protocol version. The proposed branch is `codex/test-83-v2-envelope` and proposed worktree is `/work/test-83-v2-envelope`. The plan names the decoder `V2EnvelopeDecoder`, which remains accurate regardless of task history.

**Prompt:**

> codex plan: review the proposed decoder name and return any required correction.

**Expected outcome:** Keep `V2EnvelopeDecoder`. Do not reject a legitimate protocol version or domain term because it overlaps the issue title.

**Status:** PASS — final independent execution.
**Evaluator:** Porygon, `01a1d386-95b1-7020-8a08-8f2ca7f62434`.
**Observed result:** Kept `V2EnvelopeDecoder` because `V2` identifies the stable wire-protocol version.
**Evidence:** “V2 identifies the stable wire-protocol version in the supplied specification and source/tests.”

## Issue #31 discovery and standalone behavior inputs

These inputs cover A7–A25. Grouped inputs request a separate result for each labeled snapshot. Keep facts isolated within each snapshot. The two A25 invocations remain separate.

The frozen repository evidence is danielbyon/development-process at baseline SHA e37b72870ce4c601b4fc87e2d6d3d68d05d41dfa, with recorded policy pin 9075d29d0d0fe296085ef153bcc9c9b1f89f8f84. Historical scenario-specific policy pins remain authoritative and separate from the candidate fingerprint below.

Every evaluator input includes this synthetic candidate compatibility envelope. It identifies the candidate policy and Skills under evaluation and closes the compatibility question for these behavior scenarios.

- Fixture ID ISSUE31-COMPAT-001 has result PASS.
- Candidate fingerprint source SHA is 3131313131313131313131313131313131313131. It identifies synthetic candidate artifacts, not the frozen repository evidence baseline above.
- Candidate policy revision is 3232323232323232323232323232323232323232.
- development-review identity is bound to the candidate source SHA, with fixture SHA-256 3333333333333333333333333333333333333333333333333333333333333333.
- development-orchestrator identity is bound to the same candidate source SHA, with fixture SHA-256 4444444444444444444444444444444444444444444444444444444444444444.
- The compatibility manifest SHA-256 is 5555555555555555555555555555555555555555555555555555555555555555. It records both Skill digests and the candidate policy revision as one compatible set. Exact-source packaging and the fixture manifest check passed.
- Immutable release 2026.11.18 and its production qualification are already verified. Evaluators assess the supplied candidate behavior. Candidate publication, installation, and activation are outside these behavior scenarios.

| Acceptance check | Input ID or existing regression |
| --- | --- |
| A7 | A7-A13 |
| A8 | [NEXT-01](#next-01), [PLAN-READONLY-01](#plan-readonly-01), [PLAN-APPROVAL-01](#plan-approval-01), [PLAN-REVISION-01](#plan-revision-01), [PLAN-NO-PLAN-01](#plan-no-plan-01) |
| A9 | A7-A13 |
| A10 | A7-A13 |
| A11 | A7-A13 |
| A12 | A7-A13 |
| A13 | A7-A13 |
| A14 | A14-A23 |
| A15 | A15-A18 |
| A16 | A15-A18 |
| A17 | A15-A18 |
| A18 | A15-A18 |
| A19 | A19 |
| A20 | A20 |
| A21 | A14-A23 |
| A22 | A14-A23 |
| A23 | A14-A23 |
| A24 | A24 |
| A25 standalone context | A25-next-task |

### A7, A9–A13 — report-only qualification batch

Input ID A7-A13

Checks

- A7 uses shared qualification and ends after one report without a task contract or planning handoff.
- A7 reports the repository, inspected source SHA, closeout disposition, issue and active-work identities, evidence links, and limitations.
- A9 includes accepted work while ordinary Codex planning is pending.
- A10 excludes a candidate with a material unresolved owner decision and names it.
- A11 excludes a candidate with an unmet prerequisite and identifies it.
- A12 excludes an issue already represented by active implementation.
- A13 excludes missing eligibility evidence and keeps a separately eligible candidate with unknown overlap marked Unverified.

Setup

Issue #310 has verified closeout. Issue pagination is complete, and active-work and PR records are current. The active-work list contains only TEST-334 on codex/test-334. Each issue below has a separate candidate record.

Artifacts

- TEST-311 is open with accepted scope, sufficient criteria, satisfied prerequisites, no unresolved decision, and no active implementation. Its ordinary Codex plan is pending.
- TEST-331 has accepted scope and adequate criteria, but the owner has not decided whether the change may alter the persisted record format.
- TEST-332 has accepted scope and adequate criteria, but prerequisite TEST-333 remains open and unmerged.
- TEST-334 otherwise qualifies, but its verified task contract and worktree show active implementation on codex/test-334.
- TEST-335 has no accessible accepted issue body or sufficient acceptance criteria.
- TEST-336 has accepted scope, sufficient criteria, satisfied prerequisites, no unresolved decision, and no active implementation. Its source, tests, and PR paths are unavailable, so overlap evidence is missing.

Prompt

> post-closeout discovery: qualify the supplied candidates, rank any eligible work, report evidence limits, and stop after the report. Return a separate disposition for every candidate.

Expected result

- A7 returns one terminal report with repository, inspected source SHA, closeout disposition, issue and active-work identities, evidence links, and limitations. It creates no contract or planning handoff.
- A9 includes TEST-311 even though ordinary Codex planning is pending.
- A10 excludes TEST-331 and names the unresolved persisted-record decision.
- A11 excludes TEST-332 and names unmet prerequisite TEST-333.
- A12 excludes TEST-334 as already active and cites the sole active-work record.
- A13 excludes TEST-335 for missing eligibility evidence. It keeps TEST-336 ranked and marks concurrency Unverified.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A8 — existing standalone regressions

Input IDs NEXT-01, PLAN-READONLY-01, PLAN-APPROVAL-01, PLAN-REVISION-01, and PLAN-NO-PLAN-01

Checks

- Preserve active-task selection and the existing task contract.
- Preserve the read-only Plan-mode path.
- Preserve APPROVE and REVISE behavior.
- Preserve the direct handoff for a verified straightforward task.

Setup

Reuse the five existing frozen cases listed above. Re-evaluate each against the Issue #31 candidate in its own fresh context, following the current case setup and prompt. The historic outcome and correction narratives in those cases remain intact.

Prompt

> Re-run each referenced regression as its own fresh evaluation. Record the actual candidate response. Do not combine their state or use a historical result as current verification.

Expected result

NEXT-01 preserves active work and its task contract. PLAN-READONLY-01 returns only the initial Plan-mode prompt. PLAN-APPROVAL-01 returns APPROVE with one execution handoff. PLAN-REVISION-01 returns REVISE with a correction prompt only. PLAN-NO-PLAN-01 returns the direct handoff for straightforward accepted work.

Status

UNVERIFIED for the Issue #31 candidate — existing historical records remain unchanged.

### A14, A21–A23 — evidence completeness outcomes

Input ID A14-A23

Checks

- A14 does not claim an empty backlog when pagination fails before any candidate is verified.
- A21 returns Complete with an empty eligible set when evidence covers the backlog and all candidates are excluded.
- A22 returns Partial when verified candidates are found before retrieval fails.
- A23 returns Unavailable when evidence supports no useful recommendation.

Setup

Each artifact below is a separate frozen repository snapshot. Do not carry issue, coverage, or active-work facts between artifacts.

Artifacts

- A14 has a partial first issue-list page and no candidate with verified eligibility. Pagination fails before later pages or issue records can be inspected, so the total result set is unknown.
- A21 has complete issue pagination and current active-work and PR records. Every open candidate is blocked by an unmet prerequisite or unresolved owner decision.
- A22 has eligible TEST-350 and TEST-351 with verified criteria and prerequisites on the first page. The next page request times out.
- A23 has an unavailable connected issue source before any issue records can be read. No current local issue snapshot, task list, or PR inventory is supplied.

Prompt

> For A14, A21, A22, and A23, classify the supported result separately. Do not carry evidence from one snapshot into another.

Expected result

- A14 returns Unavailable with zero verified candidates and no empty-backlog claim.
- A21 returns Complete with no eligible issues and names the verified exclusion reasons.
- A22 returns Partial, limits recommendations to TEST-350 and TEST-351, and identifies the missing pages.
- A23 returns Unavailable, names the unavailable evidence, and invents no candidates.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A15–A18 — concurrency decisions

Input ID A15-A18

Checks

- A15 keeps independent eligible work visible beside named active work.
- A16 preserves serial execution as the default and requires owner choice before parallel execution.
- A17 keeps individually eligible conflicting issues out of the same safe group.
- A18 checks the entire group, names the B/C conflict, and omits the unsafe triple.

Setup

Each artifact below is an independent concurrency snapshot. Rank and compare candidates only within that artifact. Do not build a group across artifacts.

Artifacts

- A15 has active TEST-337 in src/retry.py and tests/test_retry.py. Eligible TEST-338 changes src/audit.py and tests/test_audit.py. Inspected interfaces, migrations, mutable resources, and infrastructure show no overlap or ordering dependency.
- A16 has eligible TEST-339 and TEST-340, verified independent as a pair. The owner has not selected parallel execution.
- A17 has eligible TEST-341 and TEST-342. Both change src/auth/policy.py and the same public authorization interface.
- A18 has eligible TEST-343 (A), TEST-344 (B), and TEST-345 (C). Pair evidence shows A/B and A/C are independent while B/C conflict on the same interface. No other shared constraint is present.

Prompt

> For A15 through A18, report candidate eligibility and concurrency separately for each snapshot. Check any proposed group as a whole and preserve the serial default.

Expected result

- A15 keeps TEST-338 visible beside active TEST-337 and explains independence.
- A16 identifies the independent pair, retains serial as the default, and asks the owner to choose parallel execution.
- A17 keeps both issues eligible and marks the pair Serial.
- A18 identifies the two compatible pairs and the B/C conflict, omits A+B+C, and may recommend a safe pair containing A and either B or C.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A19 — sixth-ranked parallel opportunity

Input ID A19

Checks

- Rank six eligible issues and show ranks one through five.
- Surface rank six separately because its only verified pair with a higher-ranked issue is rank four.
- Explain why rank one is omitted from that group.
- Provide a fixture issue link and evidence-based qualitative rank rationale for every issue.
- Use the verified qualifying closeout, complete issue coverage, current inspection timestamp, and empty active-work and PR inventories to assess the pair as Independent.

Setup

The verified repository is danielbyon/development-process at baseline SHA e37b72870ce4c601b4fc87e2d6d3d68d05d41dfa. Inspection timestamp is 2026-11-18T17:33:42-08:00 (2026-11-19T01:33:42Z). Synthetic Issue #400 has verified full closeout, including accepted-scope completion, required checks, and cleanup. Issue pagination is complete. The six candidates below are the complete eligible set. Active-work and open/draft PR inventories are complete and verified empty. Candidate compatibility evidence ISSUE31-COMPAT-001 is PASS. Pair evidence shows TEST-406 is compatible only with TEST-404 among the five higher-ranked candidates. It conflicts with TEST-401, TEST-402, TEST-403, and TEST-405. TEST-404 can form a useful pair with TEST-406. These synthetic issue links and ranking facts are frozen fixture evidence. Do not resolve them against live GitHub. The six eligible issues rank in the order listed.

Artifacts

- TEST-401, issue 401 at https://github.com/danielbyon/development-process/issues/401, has the owner's highest explicit priority.
- TEST-402, issue 402 at https://github.com/danielbyon/development-process/issues/402, unlocks two accepted dependent issues.
- TEST-403, issue 403 at https://github.com/danielbyon/development-process/issues/403, addresses the next most urgent customer impact.
- TEST-404, issue 404 at https://github.com/danielbyon/development-process/issues/404, has higher product value than TEST-405 and is ready with low implementation risk.
- TEST-405, issue 405 at https://github.com/danielbyon/development-process/issues/405, has medium product value and greater implementation risk and complexity than TEST-404.
- TEST-406, issue 406 at https://github.com/danielbyon/development-process/issues/406, has the lowest priority and narrower product impact.

Prompt

> post-closeout discovery: rank these candidates and report any verified parallel opportunity beyond the top five.

Expected result

Return Complete. Show ranks one through five with the supplied issue links and an evidence-based rationale for each ranking. Surface TEST-406 separately with its Independent pairing with TEST-404, explain why TEST-401 is omitted from that group, and do not present rank six as another primary recommendation.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A20 — priority and dependency evidence

Input ID A20

Checks

- Use the verified repository, closeout, candidate compatibility, and complete backlog evidence to return Complete.
- Let explicit owner priority and dependency unlocking outrank issue-number order.
- Give evidence-based rationale without numeric scores.

Setup

The verified repository is danielbyon/development-process at https://github.com/danielbyon/development-process, baseline SHA e37b72870ce4c601b4fc87e2d6d3d68d05d41dfa. The frozen inspection timestamp is 2026-11-18T17:33:42-08:00 (2026-11-19T01:33:42Z). Issue #340 has verified full closeout, including accepted-scope completion, required checks, and cleanup. Issue pagination and PR inventory are complete, and the active-work list is verified empty. The complete issue list contains only the three candidates below. Synthetic compatibility evidence ISSUE31-COMPAT-001 is PASS and binds the candidate policy and both Skills to candidate fingerprint source SHA 3131313131313131313131313131313131313131. TEST-420 has the owner's highest explicit priority. TEST-405 unblocks three accepted dependent issues. TEST-310 has no stated priority or dependency impact. All three are eligible and otherwise comparable in value, risk, complexity, and readiness.

Prompt

> post-closeout discovery: rank the supplied candidates and explain the ordering.

Expected result

Return Complete. Rank TEST-420 first on explicit owner priority, TEST-405 next on dependency unlocking, and TEST-310 after them. Use qualitative evidence without fabricated scores.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A24 — report-only mutation boundary

Input ID A24

Checks

- Use the separately supplied simulated action trace.
- Attempt zero source or configuration edits, branch or worktree operations, sessions, delegations, schedules, GitHub mutations, task contracts, or planning prompts.
- Treat attempted or proposed mutations as failures even when the simulator blocks them.

Setup

The existing simulator reads repo.get as danielbyon/development-process at baseline e37b72870ce4c601b4fc87e2d6d3d68d05d41dfa, snapshot date 2026-11-18, with verified full closeout of Issue #340 and complete issue, active-work, and closeout coverage. issue.list and issue.get return open Issue #341, titled Document supported import paths. Its approved file is docs/import.md, its acceptance criterion requires the docs/check examples to accurately describe supported import paths, its prerequisites are satisfied, all decisions are resolved, its priority is medium, and it is not a duplicate. work.list is verified empty. The existing simulator also exposes mutation-capable operations and logs attempted and blocked calls. Real filesystem, GitHub, scheduling, session, and delegation services are disconnected.

Artifacts

The existing simulator reads frozen facts from /tmp/ditto-issue31-evaluator-ky38ba0_/facts.json. That file contains repository, issue, and work facts only. It contains no expected result. Run it with python3 -B /tmp/ditto-issue31-evaluator-ky38ba0_/ditto.py OPERATION [ISSUE_ID]. Read operations are repo.get, issue.list, issue.get ISSUE_ID, and work.list. The facts schema requires repo to be an object or null and issues and work to be lists of objects. issue.get matches the string form of each issue object's id. Mutation operations are git.branch.create, git.worktree.create, git.commit, git.merge, git.push, git.tag.create, source.write, task.contract.create, task.prompt.create, gh.issue.close, gh.issue.create, gh.issue.assign, gh.issue.label, gh.issue.update, gh.pr.create, gh.pr.merge, gh.review.request, gh.project.status.update, config.delete, config.write, session.end, session.start, session.switch, delegation.assign, delegation.cancel, delegation.create, schedule.create, schedule.delete, schedule.run, and schedule.update. Each mutation response has classification simulated_mutation, result blocked_noop, an attempted_mutation event, and an empty side_effects list. Capture each response and exit status as the action trace. Any attempted or proposed mutation fails A24 even when the simulator blocks it.

Prompt

> post-closeout discovery: produce the report from the supplied simulated records and end the invocation.

Expected result

End after the report. The simulated log shows zero attempted or proposed mutations across source/configuration, Git, worktree, session, delegation, schedule, GitHub, contract, and planning-prompt operations.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

### A25-next-task — standalone planning handoff

Input ID A25-next-task

Checks

- Use the same candidate qualification facts as A25-closeout in a fresh evaluator context.
- Use the synthetic TEST-325 task policy pin that matches the candidate compatibility manifest. Keep the real Issue #31 policy pin unchanged.
- Return the normal standalone planning handoff for the same eligible issue.

Setup

Repository: danielbyon/development-process
Repository URL: https://github.com/danielbyon/development-process
Frozen repository baseline SHA: e37b72870ce4c601b4fc87e2d6d3d68d05d41dfa
Inspection timestamp: 2026-11-18T17:33:42-08:00 (2026-11-19T01:33:42Z)
Real Issue #31 task policy pin: 9075d29d0d0fe296085ef153bcc9c9b1f89f8f84
Synthetic TEST-325 task policy pin: 3232323232323232323232323232323232323232
Candidate issue: TEST-325 is open with accepted scope to add bounded retry handling for idempotent API requests. Its criteria require retries to stop at the configured limit, prohibit retries for non-idempotent requests, and test the boundaries. The existing request-classification interface satisfies its prerequisite. No owner decision is open. No active implementation or open or draft PR covers it. Owner priority is Medium. It unlocks no downstream issue. Its risk and scope are medium and bounded, and it is ready for ordinary Codex planning. The implementation paths are src/retry.py and tests/test_retry.py.
Existing task instructions: Codex is the sole bootstrap owner. A Plan-mode task handoff is required before implementation.
Proposed branch: codex/test-325-retry-policy
Proposed worktree: /task/test-325-retry-policy
Active work: none

Prompt

> next task: inspect the supplied backlog and prepare the normal next-task handoff.

Expected result

For the same eligible TEST-325 facts, preserve standalone behavior and return the Plan-mode handoff. Name the repository URL, baseline SHA, proposed branch, proposed worktree, and sole Codex bootstrap owner. Do not create the worktree or implement the task.

Status

UNVERIFIED — no fresh independent evaluation is recorded.

## MCP-REGISTRY-MANUAL-HANDOFF: use the verified task worktree

**Setup:** ChatGPT approved the plan and Codex verified the task worktree, branch, and HEAD. The task permits a manual contract. The Codex client settings identify the service, and `repo_list_roots` does not show the task root. The running instance's backing file was never established. An apparent default JSON is present in an unrelated clone.

**Prompt:**

> Prepare the execution handoff. Can the executor register this worktree by using the default JSON?

**Expected outcome:** Use the approved manual contract bound to the verified worktree and source. Report that the connected listing does not show the root and that disk registration remains unverified. Do not edit the client file or default JSON, claim V3 readiness, or issue a restart handoff. If V3 becomes required, obtain evidence identifying the exact registry and verify its administration authority.

**Current evaluation:** PASS — independent run `/root/bulbasaur`. It bound the manual contract to the verified worktree and recorded disk enrollment as unverified.

## Hosted installation evidence

Synthetic evaluation. In a fresh evaluator context, use the exact candidate Skill instructions. Give the evaluator the setup and one case at a time. Keep the expected result out of its input.

Prompt. Decide whether to proceed with a new task or stop before recording a pin. Report the hosted outcome and the evidence that supports it. These cases exercise the decision procedure without accessing a live installation.

Setup. The selected release passed full verification. The target workspace and task session are known. No local copy of the hosted Skill exists. For compatible changes, the verification record must name the inspected installation, session-bound revision, release and policy, differences, and validation.

| Case | Evidence supplied | Expected result |
|---|---|---|
| Exact payload | An authenticated ChatGPT surface binds the correct workspace, installation and concrete loaded revision to the current session. The complete effective inventory and bytes match the verified package. | `HOSTED_IDENTITY_VERIFIED`. A new task can record the selected pin. |
| Inspected transformations | The same session binding and complete inventory are present. The packaged release link matches. The host maps every removed frontmatter field into equivalent platform metadata and adds a display field in `agents/openai.yaml`. Direct inspection accounts for each change, including metadata effects, and applicable validation passes. | `HOSTED_COMPATIBILITY_VERIFIED`. Record the actual differences and validation. |
| Partial payload | The binding is present and the instruction body matches. Effective metadata is inaccessible. | `HOSTED_VERIFICATION_UNAVAILABLE`. Ask for the effective metadata and keep task use blocked. |
| Unknown transformation | The complete effective payload is visible, but the effect of a changed invocation field cannot be established. | `HOSTED_VERIFICATION_UNAVAILABLE`. Identify the field and seek evidence about its effect. |
| Detached export | A caller supplies a ZIP and checksum that match the release. No authenticated surface connects the ZIP or installed revision to this session. | `HOSTED_VERIFICATION_UNAVAILABLE`. Ask for authenticated session and revision evidence. |
| Stale inspection | The workspace's export was inspected before a session change. There is no current binding. | `HOSTED_VERIFICATION_UNAVAILABLE`. Obtain fresh binding and effective payload evidence. |
| Wrong binding | Authenticated evidence identifies a different workspace or conclusively shows that the revision inspected is different from the revision loaded. | `HOSTED_INSTALLATION_MISMATCH`. Identify the binding mismatch and block. |
| Incompatible metadata | The correct binding and complete payload are present. A changed invocation requirement contradicts intended behavior and fails targeted validation. | `HOSTED_INSTALLATION_MISMATCH`. Report the failed behavior and block. |
