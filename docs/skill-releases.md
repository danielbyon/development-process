# Skill release operations

## 1. Authority and bootstrap

A release distributes the policy and three Skills; it does not install or activate them. Only the owner dispatches the release workflow on protected main, selecting an explicit full source SHA. Merge, dispatch, credential provisioning and activation are separate actions. PR CI never publishes.

No real release or live activation is established by this implementation. Before the first release, default resolution returns `NO_IMMUTABLE_RELEASE`. Existing tasks continue under their recorded pins. The owner may run the merged workflow without another promotion PR or installed-Skill upgrade once all prerequisites pass.

The candidate baseline is `e47c8882e590c3ec41d2d46f461d18ed73132534`. It is not automatically admitted. Admission requires inspectable legacy distribution approval, exact source/policy identities, independent review, ChatGPT source/test inspection, actual CI and owner merge authorization. PR #27's disclosed review-provenance inspection gap remains a blocker until supported by actual evidence. Never reconstruct an approval that did not occur.

## 2. Credentials and repository settings

The owner must provision repository-scoped Administration-read verification access, including mandatory Metadata read. This is a proposed prerequisite, pending configuration and endpoint verification; release immutability being enabled does not prove that the workflow can inspect it. Keep verification and publishing credentials separate. The workflow expects `RELEASE_ADMIN_READ_TOKEN` in the verification and publication environments. Only the owner configures it. For the separately authorized historical capability, the owner sets `RELEASE_WORKFLOW_WRITE_AUTHORIZED=true` and provisions `RELEASE_WORKFLOW_WRITE_TOKEN` for publication. An absent authorization flag never becomes approval merely because a token exists.

Ordinary qualification runs read-only without owner secrets. A separate attestation job receives only Contents read, OIDC token write and Attestations write. It reconstructs the qualified bundle, verifies the exact manifest digest, and signs only that manifest through the trusted main workflow. Publication receives Attestations read alongside its existing scoped permissions and verifies the signature, manifest digest, signer workflow, builder, original run and a validated signing attempt no earlier than the frozen qualification before any release mutation. Missing permissions, missing or invalid signatures, changed subjects, wrong signer identity and verification-service failure block publication. Ordinary publication uses Contents write. If GitHub requires Workflows write for a selected historical target, block before mutation unless the owner separately authorizes and provisions that capability. It never authorizes workflow-file edits. Do not escalate automatically on a failed API request.

Runtime verifies repository identity, owner and rerun initiator, protected-main workflow/builder, main protections, evidence, release immutability and required permissions. Changed prerequisites block without changing frozen provenance.

CalVer tag rules are optional hardening. The optional template restricts tag update/deletion while permitting creation without bypass; the controller validates dates and suffixes separately. Importing the template is a one-time owner action, not a routine release step. Absence does not fail publication. Unexpected existing restrictions or tag states still block unsafe operations.

GitHub references: [release API and permissions](https://docs.github.com/en/rest/releases/releases), [immutable-release configuration access](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository), [immutable-release guarantees](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

## 3. Source and evidence selection

Select a reviewed main-history source, independently of the trusted current-main builder. Derive the policy commit from the last first-parent policy-content change at that source; verify exact policy-byte equality. Record source, policy and builder separately. Equality is content evidence, not owner approval.

The readiness record indexes original evidence with repository/PR, final head/base, integrated result, review execution/ranges, correction coverage, ChatGPT inspection, CI run/attempt/tested identity, findings/dispositions and explicit owner merge authorization. Fetch and inspect linked records. Hash normalized evidence and retain verified snapshots in provenance. A comment's authenticated author does not authenticate every assertion in its text. Passing booleans and secondhand summaries cannot replace mandatory records.

Verify all uncovered integrations between an applicable admitted anchor and selected source, and separately the builder. Cover complete changes, not just Skill files. A final PR's review cannot cover unrelated earlier changes. For squash/rebase merges, establish tree/range/parent relationships between reviewed, tested and integrated snapshots. Reject unexplained commits or gaps.

A verified earlier immutable release can anchor applicable ancestry. Its CalVer alone cannot prove ancestry. Source before the bootstrap baseline needs an applicable earlier anchor or complete evidence from the evidenced repository bootstrap. Legacy records may be normalized without cosmetic PR edits; retain their original provenance and do not invent retrospective structured records. Missing, contradictory or stale mandatory evidence blocks with the affected integration and gate identified.

## 4. Qualification and assets

The controller operations are `preflight`, `qualify`, `verify-bundle`, `publish`, `verify-release` and `resolve-task`. Use the merged controller's help for supported flags. Dispatch the workflow through GitHub Actions with the full selected source SHA; never run publication merely to test a candidate. Optional supersession context identifies a prior release and correction. Version allocation is automatic.

Preflight freezes repository/run identity, original creation time, Pacific date/version, source/policy/builder, evidence and transformation identity. A repository-wide concurrency lock serializes publication. Derive `YYYY.MM.DD` from original run creation in `America/Los_Angeles`; additional releases use `.2`, `.3`, and so on. Queue delay, midnight, DST and retry do not change the frozen date/version. Check occupied drafts/tags before allocation and immediately before mutation; a frozen collision blocks rather than silently renumbering.

Qualification uses trusted builder validators and tests, treating historical blobs and configuration as data. All mandatory suites must execute with nonzero counts and no missing/skipped mandatory coverage. A supported adapter must establish historical applicability. Run two independent builds in the recorded toolchain and compare every output byte. Cross-toolchain reproducibility requires separate evidence.

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

Require exact installed-payload identity or inspected compatibility evidence naming installed payload/source, selected policy/source, differences and applicable validation. Matching frontmatter or policy SHA alone is insufficient. Unknown compatibility blocks until manual compatible installation or explicit verified historical selection.

Legacy schema-1 packages and explicit historical SHA pins remain supported. Preserve the serialized `issue5-codex-skill-staging` marker; changing it requires separate compatibility migration authorization. Temporary staging preserves unrelated Skills, verifies existing markers/files, refuses drift and cross-policy migration, and has no implicit production target.

Production installation, fresh-session ChatGPT/Codex qualification, global instruction changes and active-task migration remain separately owner-authorized. Synthetic CI/staging results cannot prove live activation. The workflow never manages MCP services or configuration.
