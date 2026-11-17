# Skill release operations

## 1. Authority and bootstrap

A release distributes the policy and three Skills; it does not install or activate them. Only the owner dispatches the release workflow on protected main, selecting an explicit full source SHA. Merge, dispatch, credential provisioning and activation are separate actions. PR CI never publishes.

No real release or live activation is established by this implementation. Before the first release, default resolution returns `NO_IMMUTABLE_RELEASE`. Existing tasks continue under their recorded pins. The owner may run the merged workflow without another promotion PR or installed-Skill upgrade once all prerequisites pass.

The PR #27 bootstrap at `e47c8882e590c3ec41d2d46f461d18ed73132534` is historical and is superseded as the proposed first-production-release baseline. Its review-provenance inspection gap remains unresolved, so it cannot support first-release admission. Keep that limitation in the record; never reconstruct an approval that did not occur.

The proposed prospective baseline for the first production release is the future corrected Issue #32 merge commit. It must pass full-baseline review, direct ChatGPT inspection, correction-PR CI and owner admission before the original release dispatch. The first release's source and builder must equal that exact merge commit.

## 2. Credentials and repository settings

The owner must provision repository-scoped Administration-read verification access, including mandatory Metadata read. This is a proposed prerequisite, pending configuration and endpoint verification; release immutability being enabled does not prove that the workflow can inspect it. Keep verification and publishing credentials separate. The workflow expects `RELEASE_ADMIN_READ_TOKEN` in the verification and publication environments. Only the owner configures it. For the separately authorized historical capability, the owner sets `RELEASE_WORKFLOW_WRITE_AUTHORIZED=true` and provisions `RELEASE_WORKFLOW_WRITE_TOKEN` for publication. An absent authorization flag never becomes approval merely because a token exists.

Ordinary qualification runs read-only without owner secrets. A separate attestation job receives only Contents read, OIDC token write and Attestations write. It reconstructs the qualified bundle, verifies the exact manifest digest, and signs only that manifest through the trusted main workflow. Registry upload and artifact storage-record creation are explicitly disabled; the pinned action only uses artifact-metadata permission inside its registry storage-record branch, so file-subject signing requires no artifact-metadata grant. Publication receives Attestations read alongside its existing scoped permissions and verifies the signature, manifest digest, signer workflow, builder, original run and a validated signing attempt no earlier than the frozen qualification before any release mutation. Missing permissions, missing or invalid signatures, changed subjects, wrong signer identity and verification-service failure block publication. Ordinary publication uses Contents write. If GitHub requires Workflows write for a selected historical target, block before mutation unless the owner separately authorizes and provisions that capability. It never authorizes workflow-file edits. Do not escalate automatically on a failed API request.

Runtime verifies repository identity, owner and rerun initiator, protected-main workflow/builder, main protections, evidence, release immutability and required permissions. Changed prerequisites block without changing frozen provenance.

CalVer tag rules are optional hardening. The optional template restricts tag update/deletion while permitting creation without bypass; the controller validates dates and suffixes separately. Importing the template is a one-time owner action, not a routine release step. Absence does not fail publication. Unexpected existing restrictions or tag states still block unsafe operations.

GitHub references: [release API and permissions](https://docs.github.com/en/rest/releases/releases), [immutable-release configuration access](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository), [immutable-release guarantees](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

## 3. Source and evidence selection

Select a reviewed main-history source, independently of the trusted current-main builder. Derive the policy commit from the last first-parent policy-content change at that source; verify exact policy-byte equality. Record source, policy and builder separately. Equality is content evidence, not owner approval.

The readiness record indexes original evidence with repository/PR, final head/base, integrated result, review execution/ranges, correction coverage, ChatGPT inspection, CI run/attempt/tested identity, findings/dispositions and explicit owner merge authorization. Fetch and inspect linked records. Hash normalized evidence and retain verified snapshots in provenance. A comment's authenticated author does not authenticate every assertion in its text. Passing booleans and secondhand summaries cannot replace mandatory records.

Verify all uncovered integrations between an applicable admitted anchor and selected source, and separately the builder. Cover complete changes, not just Skill files. A final PR's review cannot cover unrelated earlier changes. For squash/rebase merges, establish tree/range/parent relationships between reviewed, tested and integrated snapshots. Reject unexplained commits or gaps.

A verified earlier immutable release can anchor applicable ancestry. Its CalVer alone cannot prove ancestry. Source before the bootstrap baseline needs an applicable earlier anchor or complete evidence from the evidenced repository bootstrap. Legacy records may be normalized without cosmetic PR edits; retain their original provenance and do not invent retrospective structured records. Missing, contradictory or stale mandatory evidence blocks with the affected integration and gate identified.

### 3.1 Ordinary evidence and chronology

New ordinary records use schema version 2 and identify an `ordinary` evidence origin. Each integration names its exact repository PR, base revision, reviewed head, tested revision and actual merged revision. The provider PR record supplies the PR number, repository identities, target branch, final head, `merged_at` and merge commit. A matching head SHA on a different PR does not qualify.

The controller calls typed operations implemented in the `scripts/release_evidence/` package. Focused modules handle provider-bound records, qualification, baseline admission, integration verification, read-only audits and evidence discovery. `scripts/github_releases.py` supplies authenticated provider records.

Each review, inspection and owner decision is an original `release-evidence-v2` provider comment. The controller checks the GitHub comment ID, owner account, complete comment record digest, parsed report digest, execution ID derived from the captured command and output, and exact reviewed range. The record's provider `created_at` and `updated_at` timestamps, together with the provider merge time, establish order. Every receipt and the selected successful CI job must be created, unchanged and completed before merge. Missing, malformed, timezone-free or equal-at-source-resolution timestamps fail closed when order cannot be established.

`origin_status: owner_attested` means the authenticated repository owner preserved the supplied execution transcript. The execution ID and output hashes bind the report to those bytes; they do not cryptographically prove that Codex or Cubic produced them. Use the actual originating system and retain its output. Do not treat an arbitrary execution ID, a later summary, or the GitHub account alone as an independent signature.

Review evidence preserves its history. A chain starts with a full-diff review and may continue through contiguous correction-delta reviews. Each step names the revisions it actually examined, retains its findings and records explicit dispositions. P0, P1 and P2 findings must be fixed. A full final-candidate review is also supported. A pre-commit review may cover uncommitted bytes only when its recorded digest equals the final candidate diff. Reviewer records must be separate from the author execution; giving two executions different labels does not make them independent.

ChatGPT inspection names the changed source and test files and binds each name to the Git blob at the reviewed revision. CI records bind one successful attempt to the exact PR number, head and base. For the repository's synthetic-merge workflow, the provider commit record for the tested SHA must name exactly two ordered parents: the recorded base and reviewed PR head. Its tree must match the integrated revision. Direct-head CI qualifies only when the committed workflow checks out the PR head, verifies that the base is its ancestor, and the CI run identifies the exact PR, head and base. SHA labels in logs corroborate these records; they do not establish identity by themselves. The required integration job and suite steps must finish successfully before merge. A retry that finishes after merge cannot qualify the already merged integration.

For an ordinary PR, post-merge normalization may add only the actual merge SHA and its contiguous integrated-commit membership. It must cite the exact original pre-merge index record and digest. The verifier confirms that the original comment has not changed since before merge and that all other indexed evidence is identical. The later normalization timestamp provides no proof about when the original review, inspection, authorization or CI happened. Schema version 1 remains available for verification of already frozen signed releases; it cannot admit new evidence.

### 3.2 Prospective first-release baseline

A prospective baseline is a separate schema v2 origin, `prospective_baseline`. It begins at the exact corrected PR merge commit. The first release's source and builder must both equal that commit. Derive the policy revision from first-parent policy-content history and verify its bytes separately; source, policy and builder remain distinct identities.

After the correction merges, qualify that exact tree with a non-authoring full-baseline review, direct ChatGPT inspection of source and tests, and successful correction-PR CI bound to its exact head, base, tested tree and required jobs. The review and inspection receipts must name the actual merged baseline and tree. The owner then records `admit-baseline` after those gates and before the original release dispatch. The readiness index is posted after admission and before that dispatch. A rerun after late admission cannot repair the original run.

Admission requires zero ordinary integrations after the baseline. The pre-dispatch audit, release preflight and publication check that protected `main` still points exactly to the baseline. The authenticated ref record is included in the frozen evidence, so later release verification does not depend on the current branch tip. This origin does not qualify earlier PRs, ancestors, unrelated branches, or commits that happen to have an equivalent tree. Every later integration and the trusted builder must satisfy ordinary evidence and complete Git coverage from the admitted root. The implementation does not itself admit the production baseline or dispatch a release.

### 3.3 Capturing evidence before merge

Capture the original output before posting a receipt. Keep the range and report JSON used for each command with the task evidence. `capture-execution` runs a command or imports a direct ChatGPT transcript, derives the execution ID from captured bytes, and writes a comment body. The report's `summary` must appear verbatim in that output. ChatGPT reports must list every inspected source and test path; the command checks those files against the candidate's Git blobs.

For example, an ordinary review range file contains the final PR base and head:

```json
{"base_revision":"<full base SHA>","head_revision":"<full reviewed head SHA>"}
```

The independent review report contains the exact coverage step, findings and dispositions. Run the actual local Cubic or separate non-authoring review command and capture its output:

```sh
python3 scripts/skill_release.py capture-execution \
  --gate independent_review --system local_cubic \
  --reviewed-range review-range.json --report review-report.json \
  --output review-receipt.txt -- cubic review
```

Use `--system separate_codex` when that is the actual reviewer. For a correction-delta review, retain the previous reviewed head as the next step's base and preserve all prior findings and dispositions. Do not relabel the author execution as the reviewer.

Capture ChatGPT's direct source/test inspection transcript and report separately:

```sh
python3 scripts/skill_release.py capture-execution \
  --gate chatgpt_inspection --system chatgpt \
  --reviewed-range inspection-range.json --report inspection-report.json \
  --transcript-file chatgpt-inspection.txt --output chatgpt-receipt.txt
```

Capture the actual author command the same way with `--gate author_execution` and the system that produced it. Post each generated receipt as an unchanged comment on the exact PR. The owner authorization receipt is created with `owner-receipt --gate owner_authorization --revision <full head SHA>` only after the owner has decided to authorize that merge; the command formats the decision but does not make it.

After all pre-merge records exist, prepare and post the original index using a separately selected read-only credential:

```sh
python3 scripts/skill_release.py prepare-index \
  --pr <PR number> --evidence readiness-evidence.json \
  --token-env <READ_ONLY_TOKEN_VARIABLE> --output readiness-index.txt
```

Run the audit before merge with the same explicit read-only credential:

```sh
python3 scripts/skill_release.py audit \
  --root . --pr <PR number> --token-env <READ_ONLY_TOKEN_VARIABLE>
```

The audit verifies that the selected credential belongs to `danielbyon` and uses a dedicated GET-only transport. It reports `PASS`, `FAIL`, `MISSING_EVIDENCE` or `NOT_RUN` per gate. An open ordinary PR reports merge and integrated-revision checks as `NOT_RUN`. A merged prospective baseline can pass qualification and exact-main coverage while release dispatch, runtime and publication remain `NOT_RUN`. Read the gate results; exit code zero does not mean an unrun dispatch happened.

After an authorized ordinary merge, prepare a normalization that names the original readiness comment through `--normalizes-reference <repository API comment path>`. The controller fetches the actual PR merge record and can add only its merge SHA and commit membership. Preserve and link the original comment; never edit it to add retrospective claims. A prospective baseline index is created after qualification and owner admission, so it has no pre-merge normalization.

## 4. Qualification and assets

The controller operations are `preflight`, `qualify`, `verify-bundle`, `publish`, `verify-release` and `resolve-task`. Use the merged controller's help for supported flags. Dispatch the workflow through GitHub Actions with the full selected source SHA; never run publication merely to test a candidate. Optional supersession context identifies a prior release and correction. Version allocation is automatic.

Preflight freezes repository/run identity, original creation time, Pacific date/version, source/policy/builder, evidence and transformation identity. A repository-wide concurrency lock serializes publication. Derive `YYYY.MM.DD` from original run creation in `America/Los_Angeles`; additional releases use `.2`, `.3`, and so on. Queue delay, midnight, DST and retry do not change the frozen date/version. Check occupied drafts/tags before allocation and immediately before mutation; a frozen collision blocks rather than silently renumbering.

Qualification uses trusted builder validators and tests, treating historical blobs and configuration as data. For each mandatory suite, the controller reads the selected revision’s committed CI workflow and requires its exact suite command, matching successful step, and a bounded verbose test result with a nonzero count and no failures or skips. Historical schema-1 sources require four suites; schema-2 sources require six. Filename mentions and unrelated aggregate counts do not establish execution. A supported adapter must establish historical applicability. Run two independent builds in the recorded toolchain and compare every output byte. Cross-toolchain reproducibility requires separate evidence.

Read exact source Git objects, enforce allowed files and regular modes, and reconstruct transformed bytes independently. Source templates use `{{release_tag}}` only in the canonical policy binding. Replace it deterministically with the allocated tag. Supported legacy adapters replace only the exact canonical policy reference and associated revision label. Reject ambiguous substitutions and unknown formats. Preserve unrelated bytes and historical references.

Exactly eight assets are required:

1. `development-orchestrator.zip` and `development-orchestrator.provenance.json`.
2. `development-review.zip` and `development-review.provenance.json`.
3. `delegation-executor.zip` and `delegation-executor.provenance.json`.
4. `release-manifest.json`.
5. `SHA256SUMS`.

Each ZIP contains only its Skill directory, `SKILL.md` and `agents/openai.yaml`. Sidecars bind payload/archive hashes; the manifest hashes the six package assets and binds release, revisions, transformation, evidence and qualification. Checksums cover those six assets plus the manifest, excluding themselves. Hash agreement alone is insufficient: reconstruct bytes from committed inputs.

## 5. Draft-first publication and recovery

Finish rebuilding and verification before exposing publishing credentials. Historical source must not execute in that step. Create an owned draft targeting selected source, upload missing expected assets only, download and verify the complete set, then create/verify the lightweight source tag. Refresh prerequisites, ownership, tag and asset checks immediately before publishing the exact draft.

Verify title/tag equality, tag target, `draft=false`, `prerelease=false`, `immutable=true`, all eight asset bindings and GitHub's native release attestation. Attestation does not establish independent review or successful qualification. GitHub permits some presentation metadata changes after publication; resolvers recheck those fields.

| Interrupted state | Required action |
|---|---|
| Matching owned partial draft | Reconstruct the frozen bundle; upload verified missing assets only |
| Mismatched draft or asset | Preserve and block; never overwrite to repair ambiguity |
| Unexpected existing tag | Preserve and block, even if its target matches |
| Tag creation timeout | Reconcile original-run evidence and owned draft; ambiguity blocks |
| Publication timeout | Inspect remote state before retrying |
| Exact release already published | Complete verification only |
| Published with unavailable/failed verification | Report published, verification pending/blocked; never republish or repair in place |

Rerun all jobs. Reject partial reruns that reuse qualification without fresh gates. Same-run recovery must retain original source/policy/builder, date/version, hashes and provenance; record fresh retry checks separately. Draft notes alone cannot establish ownership. The concurrency lock does not exclude manual/API writers, so reconcile server state before every retry.

Correct published content with a new CalVer and supersession context. Never delete assets, retag or rewrite published history.

## 6. Resolution, compatibility and staging

Discover all eligible published immutable CalVer releases with pagination and numeric ordering. Ignore drafts, prereleases and `latest`. Verify the highest candidate's metadata, tag, attestation, assets and reconstructed provenance. An invalid newer eligible candidate blocks rather than silently selecting an older one. Record the selected tag once; continuing tasks retain their recorded SHA or CalVer.

For a new task, pass `--skill` and `--installed-path` to `resolve-task`. The controller hashes the requested Skill’s installed files and compares them with that Skill’s verified release payload. Caller-supplied digests cannot establish installation identity. Missing files, symlinks and unexpected files block resolution. The existing `.skill-distribution.json` installation marker is allowed after its structure, Skill identity and recorded payload hashes are checked against the inspected files; it never substitutes for inspecting payload bytes. An older payload requires inspected compatibility evidence naming the requested Skill, inspected payload/source, selected policy/source, differences and applicable validation. Matching frontmatter or policy SHA alone is insufficient. Unknown compatibility blocks until manual compatible installation or explicit verified historical selection.

Legacy schema-1 packages and explicit historical SHA pins remain supported. Preserve the serialized `issue5-codex-skill-staging` marker; changing it requires separate compatibility migration authorization. Temporary staging preserves unrelated Skills, verifies existing markers/files, refuses drift and cross-policy migration, and has no implicit production target.

Production installation, fresh-session ChatGPT/Codex qualification, global instruction changes and active-task migration remain separately owner-authorized. Synthetic CI/staging results cannot prove live activation. The workflow never manages MCP services or configuration.
