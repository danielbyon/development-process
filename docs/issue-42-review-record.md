# Issue #42 review record

## Prior local Cubic full-diff review

- Reviewer: the local Cubic CLI review.
- Execution reference: the original invocation did not retain a review ID or raw log. It completed with exit status 1 and reported one finding. The available record is the finding copied below.
- Reviewed change set: the uncommitted tracked diff later committed as `df9c1e893de671bb91d13106534ed934fd2a3c4b`, relative to baseline `9eb2a48cbe55e44f8c223d361b58940db7f9e1d0`.
- Tracked scope: `README.md`, `docs/DECISIONS.md`, `docs/PROCESS.md`, `docs/adr/0001-immutable-skill-releases.md`, `docs/skill-releases.md`, `scripts/skill_distribution.py`, `scripts/skill_release.py`, the three Skill instructions and two scenario files, `tests/fixtures/workflow_contract.json`, `tests/test_skill_releases.py`, and `tests/test_workflow_contract.py`.
- Worktree state: `.codegraph/` and Python cache directories were present as untracked artifacts and were not part of the committed diff. The review result does not establish whether Cubic inspected them.
- Naming coverage: the result did not document applying the task-independent naming requirements. Naming coverage from this review is unverified.
- Repository review context: Cubic reported that repository-specific review context was unavailable.

### Complete finding

> [P1] Release assets are not bound to the successful workflow. Resolution checks that a matching workflow run succeeded, but it never verifies that the run attested to the published manifest or its assets. It also trusts the manifest's archive hashes without downloading and hashing the ZIPs. Consequently, an immutable release can pass resolution with payload identities from fabricated sidecars that were not produced by the qualifying workflow, undermining the stated release-qualification boundary.

### Disposition

The owner-approved Issue #42 policy defines a successful owner-triggered release workflow on reviewed and CI-approved `main`, followed by immutable publication, as the qualification event. Rechecking attestations or hashing ZIPs during ordinary task startup would restore the per-task verification gate that the policy removes. The release workflow continues to run its qualification suites, deterministic packaging, provenance, attestation and publication checks.

ChatGPT adjudicated this as inconsistent with the approved runtime trust boundary, not a confirmed in-scope P1. The finding is retained here so the policy decision and review result remain inspectable.

## Focused correction review

### Independent review 1

- Reviewer: independent Codex subagent, execution/agent ID `01a1fc96-89b2-7c31-8d48-0abafad95ee0`.
- Reviewed range: tracked working-tree delta on top of `df9c1e893de671bb91d13106534ed934fd2a3c4b`; `HEAD` and the requested base both resolved to that commit when reviewed.
- Tracked files inspected: `docs/PROCESS.md`, `docs/skill-releases.md`, `scripts/github_releases.py`, `scripts/skill_release.py`, `skills/development-review/SKILL.md`, `tests/fixtures/workflow_contract.json`, `tests/test_github_releases.py`, `tests/test_skill_releases.py`, and `tests/test_workflow_contract.py`.
- Worktree scope: the reviewer read this review record and inventoried untracked files. It reported `.codegraph/.gitignore` and 17 Python cache files, but did not open the generated files. They are unrelated and remain preserved.
- Task-independent naming coverage: the initial response did not say; the final review confirmed §3 naming was covered.
- Tests and GitHub inspection: the reviewer did not run tests or contact GitHub.

#### Complete findings

1. **[P2] §12 could regain a hosted compatibility gate without failing contract tests.** The new guard covered the post-closeout Skill contract and §11, but §12 had no equivalent admission-gate check. Adding hosted Skill or session compatibility language there could pass the existing policy contract.
2. **[P2] An in-progress rerun preserving an earlier publication was untested.** The failed-rerun regression covered a prior success followed by failure, but the in-progress case had no earlier successful qualifying attempt.

#### Disposition

Both findings are in scope. The workflow-contract fixture and guard now include §12 hosted, payload and session compatibility gate phrases. A separate regression now verifies an earlier successful publication remains selected while a later attempt is in progress. The focused delta is being sent back for independent follow-up review.

### Independent follow-up review

- Reviewer: Codex subagent **Pikachu**, agent ID `01a1fc96-89b2-7c31-8d48-0abafad95ee0`; review turn reference `01a1fcb2-8674-78a1-acf0-665eabf17848`.
- Reviewed range: the focused working-tree delta against `df9c1e893de671bb91d13106534ed934fd2a3c4b`.
- Tracked scope: 10 files across `docs/`, `scripts/`, `skills/`, and `tests/`. Untracked scope: `.codegraph/.gitignore` and 17 cache files under `scripts/`, `scripts/release_evidence/`, and `tests/`; generated files were inventoried, not opened.
- Naming coverage: the reviewer confirmed inspection against task-independent naming requirements in §3.
- Complete finding: **[P2] Missing regression for a later successful non-owner rerun.** The resolver skips such an attempt in favor of an earlier owner-qualified publication, but the tests covered only failed and in-progress reruns.

#### Disposition

The finding is in scope. `tests/test_skill_releases.py` now verifies that a later successful attempt from another actor does not replace the earlier owner-qualified publication.

### Independent re-review

- Reviewer: Codex subagent **Pikachu**, agent ID `01a1fc96-89b2-7c31-8d48-0abafad95ee0`; review turn reference `01a1fcb4-7b2f-7653-8100-d57826e53c84`.
- Reviewed range: the final test and review-record delta after the previous finding.
- Result: the P2 is resolved; the behavior-based regression name and purpose-exempt issue-numbered review record meet §3 naming requirements. No new findings.

### Local Cubic review 1

- Reviewer: local Cubic CLI (`cubic review`), execution reference `ses_e035b4b33ffe4V5vwKaw7Olh5g`.
- Reviewed range: the focused working-tree delta based on `df9c1e893de671bb91d13106534ed934fd2a3c4b`.
- Scope: all tracked correction files and this review record; candidate task-independent names and paths under `docs/PROCESS.md` §3; untracked worktree inventory `.codegraph/`, `scripts/__pycache__/`, `scripts/release_evidence/__pycache__/`, and `tests/__pycache__/`. The prompt identified generated directories as unrelated artifacts to preserve. Cubic reported repository-specific review context unavailable.
- Task-independent naming coverage: explicitly included in the review prompt, including worktree contents and purpose-based task-record exceptions.
- Complete findings: one P2.

> **[P2] Later failed reruns can invalidate an earlier successful publication.** The backward scan applied owner and source identity checks to later attempts before identifying whether they were qualifying publication attempts. A failed or in-progress rerun started by another actor could therefore block selection of an earlier owner-triggered successful publication.

#### Disposition

The finding is valid and has been addressed. The resolver now verifies the original dispatch identity, skips unsuccessful attempts after checking their run and attempt numbers, binds successful candidates to the frozen event, path, source, and creation identity, and selects only an owner-triggered successful publication. Regressions cover failed and in-progress non-owner reruns after a successful publication. The local Cubic review must be repeated on the final correction delta.

### Local Cubic review 2

- Reviewer: local Cubic CLI (`cubic review`), execution reference `ses_e0354f767ffeIFnffnZAEZh3DP`.
- Reviewed range: the focused working-tree delta based on `df9c1e893de671bb91d13106534ed934fd2a3c4b`, including the failed-rerun actor fix.
- Scope: the same tracked files, review record, and untracked worktree inventory listed for Local Cubic review 1. Task-independent naming under §3 was explicitly requested. Repository-specific Cubic review context remained unavailable.
- Complete findings: one P2.

> **[P2] Attempt selection makes unbounded sequential API calls.** The backward scan fetches attempts individually until it finds an owner-triggered success, so request count grows with the number of reruns and may slow resolution or consume API quota.

#### Disposition

This finding is disputed as written. GitHub currently limits a workflow to 50 reruns, so one resolution can inspect at most 51 attempt records; the scan is bounded by the provider rather than unbounded. A first-attempt success takes one attempt-record read. Each later attempt adds one read until the earlier success is found. A run that exhausts the rerun limit can therefore have higher resolution latency, which remains a known risk. A persistence layer or new caching machinery would exceed this focused correction and is not justified by the provider's current 50-rerun bound. See [GitHub's rerun limit](https://github.blog/changelog/2026-04-10-actions-workflows-are-limited-to-50-reruns/).

### Local Cubic final review

- Reviewer: local Cubic CLI (`cubic review`), execution reference `ses_e034ed5abffeIEzDnTuPrm4au9`.
- Reviewed range and scope: the final focused working-tree delta against `df9c1e893de671bb91d13106534ed934fd2a3c4b`, including the review record and the untracked worktree inventory above. The prompt explicitly included task-independent naming under §3 and asked Cubic to assess the bounded 50-rerun scan.
- Result: no issues found. Cubic again reported that repository-specific review context was unavailable.

### Local Cubic pre-commit review

- Reviewer: local Cubic CLI (`cubic review`), execution reference `ses_e034af8c4ffe2WROwHwQQqZB1H`.
- Reviewed range: the exact final correction diff against `df9c1e893de671bb91d13106534ed934fd2a3c4b`, including the non-owner-success regression and this updated review record.
- Scope: tracked changes and untracked worktree inventory above, with task-independent naming checks under §3 and the documented 50-rerun bound included in the review prompt.
- Result: no issues found. Repository-specific Cubic review context remained unavailable.

### Local Cubic exact pre-commit review

- Reviewer: local Cubic CLI (`cubic review`), execution reference `ses_e034898c8ffe00Hpsq0rqTmyrx`.
- Reviewed range: the exact current focused correction diff against `df9c1e893de671bb91d13106534ed934fd2a3c4b`, including the complete review record and non-owner-success regression.
- Scope: implementation, tests, workflow contracts, task-independent naming under §3, and the untracked worktree inventory above. The prompt included the 50-rerun provider bound and the approved trust boundary.
- Result: no issues found. Repository-specific Cubic review context remained unavailable.
