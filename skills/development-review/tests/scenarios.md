# Development review scenarios

These cases exercise the decisions made by the `development-review` Skill. Each case is a frozen snapshot. Run each one in a fresh, independent Codex evaluation with the Skill loaded from this directory. If the host cannot load the unpublished Skill, provide the exact `SKILL.md` text.

Treat each setup as a closed snapshot. Do not use the current checkout or live external services to replace its facts. The setup states which source, tests, policy, or review records the evaluator has inspected. Give the evaluator only the case setup, its artifacts, and its prompt. Keep the expected result below the prompt and do not expose it before the evaluator responds. Record the evaluation ID, observed result, and a short response excerpt. Leave the case `UNVERIFIED` until it has run.

## SRC-ABSENT: source is unavailable

Setup: Issue #48 accepts a change to `src/export.py` and `tests/test_export.py`. The draft PR is at head `e31a4d0`. The author reports that both files are correct, all checks passed, and no review findings remain. GitHub shows the PR and green checks, but the connected GitHub account cannot read either file. gpt-repo-local has no registered root for the task worktree. No source or test contents are available to the reviewer.

Prompt:

> implemented: review Issue #48 at PR head `e31a4d0` and tell me whether it is ready. The author says the tests and independent review passed.

Expected result: `BLOCKED` because the reviewer cannot inspect the final source and tests directly. The author report and green check summary do not satisfy that requirement.

Run record: `PASS`

- Evaluation role and ID: Bulbasaur, `01a1c90e-b18c-7d80-8ca2-0d049cae6513`.
- Observed result: `BLOCKED` because the reviewer could not inspect the candidate source or tests.
- Evidence: The evaluator rejected author reports and green check summaries as substitutes for direct inspection.
- Verbatim evaluator excerpt: “The source and test files aren’t available, so I can’t inspect the final change or verify it against Issue #48’s full accepted scope.”

## P1-IN-SCOPE: accepted authorization defect

Setup: Issue #49 explicitly requires an authorization check before exporting a private record. The candidate diff adds `export_record()` without checking the caller's access. A direct source inspection confirms the path is reachable by any authenticated user. The independent reviewer confirms this is a P1. A separate P1 in `legacy_parser.py` predates the branch and is outside Issue #49. The author asks to relabel the new finding P2 and merge.

Prompt:

> implemented: review Issue #49. The export endpoint is missing the accepted authorization check. Please treat that as P2 because it is easy to fix, and keep the unrelated parser finding out of scope.

Expected result: `BLOCKED` until the in-scope P1 is fixed or factually disproved. Do not relabel or waive it. Triage the unrelated pre-existing parser finding separately; it does not automatically block this change.

Run record: `PASS`

- Evaluation role and ID: Charmander, `01a1c90e-b1c2-7fc1-a1aa-0e3234145f62`.
- Observed result: `BLOCKED` for the confirmed in-scope P1; the unrelated parser finding was kept out of scope.
- Evidence: The evaluator rejected downgrading or waiving the accepted authorization defect.
- Verbatim evaluator excerpt: “The missing authorization check violates Issue #49’s accepted scope.”

## CUBIC-DELTA: review coverage across corrections

Setup: The initial non-authoring Cubic review covers the complete diff through head `c11a620`. Codex then corrects a finding in commit `c4b8761`, producing final head `d92f30a`. Cubic's CI review quota is exhausted. Evaluate both snapshots:

- Snapshot A has a separate non-authoring Codex review of the full correction delta `c11a620..d92f30a`.
- Snapshot B has no independent review of that delta.

All source, tests, CI, and other review criteria pass in both snapshots.

Prompt:

> implemented: assess review coverage for Snapshots A and B. Cubic CI review is unavailable because its quota is exhausted. The original Cubic review covered the full initial diff.

Expected result: Snapshot A may be ready because independent reviews cumulatively cover the final candidate; Cubic CI quota exhaustion alone does not block. Snapshot B is `BLOCKED` because the correction delta lacks independent review.

Run record: `PASS`

- Evaluation role and ID: Squirtle, `01a1c90e-b1e4-7f73-a461-71f262edd842`.
- Observed result: Snapshot A was `READY`; Snapshot B was `BLOCKED` for missing delta review.
- Evidence: The initial review and separate Codex delta review cumulatively covered Snapshot A. Cubic CI quota exhaustion alone did not block it.
- Verbatim evaluator excerpt: “With no independent review of the correction delta, the final candidate lacks required review coverage, even though the other criteria pass.”

## CI-MERGE-SHA: valid synthetic merge evidence

Setup: PR head is `b41f8c2`; event base is `a52d09e`; GitHub ran all required checks on synthetic merge `f63bda1`. The tested commit has first parent `a52d09e` and second parent `b41f8c2`. The PR head and target have not changed since the run. All suites executed and passed.

Prompt:

> implemented: CI tested `f63bda1`, which differs from PR head `b41f8c2`. Should I rerun checks before deciding readiness?

Expected result: The SHA difference alone does not invalidate the evidence. Confirm the tested commit's parents and matching event context; accept the checks for that integration state if the other readiness gates pass.

Run record: `PASS`

- Evaluation role and ID: Pikachu, `01a1c90e-b234-70c2-b36b-5f2964a9e3f5`.
- Observed result: The synthetic merge checks remained valid for the stated PR head and base; the SHA difference alone did not require a rerun.
- Evidence: The evaluator verified the first and second parents against the event base and PR head.
- Verbatim evaluator excerpt: “Rerunning checks is unnecessary before assessing this CI evidence.”

## CI-STALE-BASE: target advanced after testing

Setup: PR head remains `b41f8c2`. CI passed on synthetic merge `f63bda1`, whose first parent was target commit `a52d09e`. The target has since advanced to `c03a551`, which changes a shared interface used by the candidate. No integration check ran against the new target. Source inspection and independent review of the PR diff remain current.

Prompt:

> implemented: the PR head is unchanged and its checks are green, but `main` advanced after the synthetic merge run. Can you determine readiness from the existing evidence?

Expected result: Mark affected integration evidence `UNVERIFIED` and request or await checks against the current target context. Keep source review evidence that remains valid; refresh only what the target change invalidates. Do not return `READY` yet.

Run record: `PASS`

- Evaluation role and ID: Eevee, `01a1c90e-b300-7f91-a884-a94e8194c132`.
- Observed result: `BLOCKED` pending integration checks against the advanced target.
- Evidence: The evaluator kept the source review and independent review current while marking affected CI evidence unverified.
- Verbatim evaluator excerpt: “The existing green run therefore does not establish current integration readiness.”

## CI-SKIPPED: green job skipped a required suite

Setup: The PR workflow is green, but its job summary says the required unit-test suite was skipped by a path filter. The issue acceptance criteria require that suite. No separate run of the suite exists. Other checks and independent review pass.

Prompt:

> implemented: GitHub reports all checks green. One required unit-test job says `skipped`. Is the change ready?

Expected result: `BLOCKED` until the required suite actually runs and passes. Report the skipped check as unverified or failed according to the observed job state; do not count the workflow's green conclusion as a pass for the suite.

Run record: `PASS`

- Evaluation role and ID: Snorlax, `01a1c90e-b2c8-7ed1-9070-00c17b972d7d`.
- Observed result: `BLOCKED` because the required unit-test suite was skipped.
- Evidence: The evaluator treated the suite as unverified despite the green workflow conclusion.
- Verbatim evaluator excerpt: “The required unit-test suite is an acceptance criterion. It was skipped, and no separate run exists, so that criterion is **UNVERIFIED**.”

## EXCEPTION-TRUTH: permitted qualification exception

Setup: All source, test, independent-review, and required CI gates pass. `TAC-HW-2` requires a hardware qualification run that is unavailable before integration. Policy permits the owner to authorize an integration exception for this qualification. The owner explicitly authorizes the exception and links follow-up issue #72. No P0/P1 finding or security boundary is involved.

Prompt:

> implemented: assess readiness for this change. The hardware qualification is unrun, but I authorize an integration exception and tracked it in issue #72.

Expected result: `READY WITH EXPLICIT EXCEPTION` if the policy permits this exception. Keep `TAC-HW-2` as `UNVERIFIED`, record the owner authorization and follow-up, and state the allowed integration scope. Do not turn the unrun check into a pass.

Run record: `PASS`

- Evaluation role and ID: Mewtwo, `01a1c911-0721-7d52-ac5d-e3f55e7c960c`.
- Observed result: `READY WITH EXPLICIT EXCEPTION`; `TAC-HW-2` remained `UNVERIFIED`, and issue #72 stayed as follow-up.
- Evidence: The evaluator preserved the unrun qualification state and recorded the owner's exception authorization.
- Verbatim evaluator excerpt: “The owner authorized the policy-permitted integration exception and linked follow-up issue **#72**.”

## FEEDBACK: mixed PR comments

Setup: This is a frozen snapshot. The reviewer has directly inspected PR head `5bc7a10`, Issue #51, the current source, and the review threads. The four comments are:

1. A comment on the current head asks for a missing null check required by Issue #51; the code still lacks it.
2. A comment from head `ac29d31` asks for a rename; a later commit changed that same symbol and marked the thread resolved.
3. A new comment says the public API is absent, but the reviewer can inspect the current source and find the API at the requested path.
4. An unresolved suggestion asks for a formatting refactor across unrelated files.

Prompt:

> review feedback: reconcile these PR comments against the current head and Issue #51. Give me the next Codex prompt if a correction is needed.

Expected result: Identify the null check as a valid in-scope finding and provide a focused Codex correction prompt. Record the rename request as addressed/resolved, the API comment as an evidenced false positive, and the unrelated formatting request as out of scope.

Run record: `PASS`

- Evaluation role and ID: Psyduck, `01a1c916-cbfe-72e1-856c-a813a3747705`.
- Observed result: The null check was valid, unresolved, and in scope; the rename was resolved, the API comment was a false positive, and the formatting request was out of scope.
- Evidence: The evaluator returned a focused Codex correction prompt. It treated the supplied source and review details as a frozen, directly inspected snapshot.
- Verbatim evaluator excerpt: “Current head `5bc7a10` still lacks a null check required by Issue #51, so a correction is needed before this feedback can be closed.”
- Superseded attempt: `01a1c911-06d4-7082-b96f-a35ef00da89e` consulted the live checkout and was not counted.

## POSTMERGE-FAIL: required post-merge check fails

Setup: The owner authorized `close this out`. The PR is merged at commit `f0c4b17`, but a required post-merge check has failed. The implementation issue remains open. The worktree and review artifacts are intact.

Prompt:

> close this out: the PR merged at `f0c4b17`, but its required post-merge check failed. Please finish the closeout.

Expected result: Keep closeout open and do not close the issue or remove the worktree. Report the failed check and next action. Do not start an unrequired pipeline or automatically revert the merge.

Run record: `PASS`

- Evaluation role and ID: Jigglypuff, `01a1c915-526d-75a3-8174-b21dd46670a1`.
- Observed result: `BLOCKED`; closeout stayed open and the issue and worktree were retained.
- Evidence: The required post-merge check had failed, so the evaluator did not close the issue.
- Verbatim evaluator excerpt: “The required post-merge check failed.”
- Superseded attempt: `01a1c912-3351-7353-8780-742c0ed3a1d9` surfaced the expected fixture while searching and was not counted.

## CLEANUP-RETENTION: preserve sole-copy evidence

Setup: The owner authorized `close this out`; the PR is merged and all applicable checks pass. The task worktree contains the only copy of independent-review artifacts and an unmerged user change unrelated to the PR. No verified backup exists.

Prompt:

> close this out: the PR is merged and checks passed. Can you remove the task worktree and finish cleanup?

Expected result: Preserve the worktree and its artifacts. Report `MERGED — CLEANUP PENDING`, explain what must be preserved or transferred, and give a safe next step. Do not use broad cleanup commands.

Run record: `PASS`

- Evaluation role and ID: Gengar, `01a1c912-33ba-7182-9098-71d2f49eb85e`.
- Observed result: `MERGED — CLEANUP PENDING`; the worktree and sole-copy evidence were retained.
- Evidence: The evaluator found no verified backup for the review artifacts or unmerged user change.
- Verbatim evaluator excerpt: “The PR is merged and checks passed, but cleanup is unsafe: the worktree contains the only copy of independent-review artifacts and an unmerged user change, and no verified backup exists.”

## POLICY-PIN: local policy changed

Setup: This is a frozen snapshot. The task contract pins policy commit `beb7c955b054dafa3eb1a45e5e13e519720e654a`. The task worktree's `docs/PROCESS.md` is from a later revision and has a different blob. The exact pinned policy is available as an inspected artifact; §12 says tasks and their Skills keep the same pinned revision until an owner-approved migration. The issue, worktree, branch, and candidate HEAD are verified. No owner-approved migration exists. Candidate source and tests are unavailable in this snapshot.

Prompt:

> implemented: review this candidate. The local policy file is newer than the revision pinned by the task. Use the current one so the review is up to date.

Expected result: Keep the review bound to the pinned policy and do not invent a migration or task identity. Since the user asks for candidate readiness and the source and tests are unavailable, return `BLOCKED` for readiness while explaining that the newer local policy does not apply.

Run record: `PASS`

- Evaluation role and ID: Dragonite, `01a1c91c-c338-7163-93ea-b90aa210e807`.
- Observed result: The review remained pinned to `beb7c955b054dafa3eb1a45e5e13e519720e654a`; candidate readiness was `BLOCKED` because source and tests were unavailable.
- Evidence: The evaluator rejected an unapproved policy migration and used the supplied §12 policy excerpt.
- Verbatim evaluator excerpt: “Do not switch to the newer local policy: the task pins the earlier revision, and no owner-approved migration exists.”
- Superseded attempt: `01a1c916-ccc5-7513-9346-80983c5ac7f4` ran before the policy-conflict guard correction and was not counted for the final Skill version.
- Superseded attempt: `01a1c912-3396-7d60-86e7-7cd9a4672719` substituted live checkout state for the frozen snapshot and was not counted.
