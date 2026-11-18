# Skill release operations

## 1. Authority and bootstrap

A release distributes the policy and three Skills. It does not install or activate them. The owner dispatches the release workflow on `main`; the workflow takes its source from that run's `github.sha`. Merge, dispatch, credential provisioning and activation remain separate actions. Pull request CI never publishes.

The owner is the repository's sole maintainer. The approved trust model treats an authenticated owner merge as sufficient; a compromised owner account is outside its scope.

Before the first immutable release, new-task resolution returns `NO_IMMUTABLE_RELEASE`. Existing tasks keep their recorded pins. A release can run from trusted `main` without a promotion PR or an installed-Skill upgrade.

The PR #27 bootstrap at `e47c8882e590c3ec41d2d46f461d18ed73132534` is historical and is superseded as the proposed first-production-release source. Its review-provenance gap remains unresolved. That gap is part of the historical record; it is not a release gate for a corrected commit in trusted `main`, and no later statement should be presented as a review that did not occur.

## 2. Credentials and repository settings

The workflow authenticates the repository and owner through GitHub's repository and Actions endpoints. `RELEASE_ADMIN_READ_TOKEN` is used only for `GET /repos/danielbyon/development-process/immutable-releases`, the immutable-release capability endpoint. The owner provisions that token in the `release-verification` and `release-publication` environments. The workflow does not use it to inspect branch rules, rulesets, collaborator counts or historical pull-request checks.

The workflow uses its declared GitHub token permissions. Preflight reads repository and Actions state. The attestation job receives OIDC token write and Attestations write, verifies the bundle, then signs the release manifest. Publication receives Contents write and Attestations read. GitHub rejects operations when the required permission is absent. There is no Workflows-write escalation or secondary authorization flag.

CalVer tag rules are optional hardening. They may restrict updates and deletion while allowing tag creation. Their absence does not block publication; an unexpected existing tag or remote asset still blocks an unsafe mutation.

GitHub references: [release API and permissions](https://docs.github.com/en/rest/releases/releases), [immutable-release configuration access](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository), [immutable-release guarantees](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

## 3. Trusted source and policy selection

The workflow accepts no source or builder SHA input. It reads the authenticated run and requires an owner-triggered `workflow_dispatch` for this repository on `main`, with the expected workflow path and attempt. The run's full `head_sha`, `GITHUB_SHA` and checked-out `HEAD` must agree. That commit is recorded as both release source and builder.

At preflight and again before publication, the controller reads the authenticated `main` ref and verifies through GitHub's compare endpoint that the selected source is an ancestor of its current tip. A normal advance of `main` is allowed while the original source remains in its history. A removed commit, unmerged head, unrelated commit or equal-tree substitute fails identity checks.

The policy revision is derived separately from the last first-parent commit that changed `docs/PROCESS.md`. The controller verifies that the policy bytes at that revision match the source tree. The package verifier checks the same relationship while rebuilding the release.

The merge process owns independent review, direct ChatGPT source/test inspection, required CI and explicit owner merge authorization. The release controller trusts the authenticated merge into `main` and does not fetch review receipts, reconstruct historical PR chronology, admit a prospective baseline or require a separate promotion PR. The old receipt formats remain only where needed to verify already signed historical releases.

## 4. Qualification and assets

The controller operations are `preflight`, `qualify`, `verify-bundle`, `publish`, `verify-release` and `resolve-task`. Use the merged controller's help for supported flags. Dispatch the workflow on `main` through GitHub Actions. The authenticated dispatch event's `github.sha` selects the source and builder; the workflow accepts no source SHA input. Never run publication merely to test a candidate. Optional supersession context identifies a prior release and correction. Version allocation is automatic.

Preflight freezes repository and run identity, original creation time, Pacific date/version, source/policy/builder and transformation identity. A repository-wide concurrency lock serializes publication. Derive `YYYY.MM.DD` from original run creation in `America/Los_Angeles`; additional releases use `.2`, `.3`, and so on. Queue delay, midnight, DST and retry do not change the frozen date/version. Check occupied drafts and tags before allocation; a frozen collision blocks rather than silently renumbering.

Qualification runs all six required test suites against the checked-out source. A failed, skipped or empty suite blocks the release. Two independent builds must produce identical bytes, and the package verifier reconstructs and checks the same bundle before staging and publication.

Read exact source Git objects, enforce allowed files and regular modes, and reconstruct transformed bytes independently. Source templates use `{{release_tag}}` only in the canonical policy binding. Replace it deterministically with the allocated tag. Supported legacy adapters replace only the exact canonical policy reference and associated revision label. Reject ambiguous substitutions and unknown formats. Preserve unrelated bytes and historical references.

Exactly eight assets are required:

1. `development-orchestrator.zip` and `development-orchestrator.provenance.json`.
2. `development-review.zip` and `development-review.provenance.json`.
3. `delegation-executor.zip` and `delegation-executor.provenance.json`.
4. `release-manifest.json`.
5. `SHA256SUMS`.

Each ZIP contains only its Skill directory, `SKILL.md` and `agents/openai.yaml`. Sidecars bind payload and archive hashes. The manifest hashes the six package assets and binds release, source, policy, builder, transformation and qualification identities. Checksums cover those six assets plus the manifest, excluding themselves. The verifier reconstructs bytes from committed inputs.

## 5. Draft-first publication and recovery

Finish rebuilding and verification before exposing publishing credentials. The build uses trusted workflow code and reads committed source files as data. Create an owned draft targeting the selected source, upload only missing expected assets, verify the complete set, then create and verify the lightweight source tag. Recheck dispatch identity, source ancestry, release ownership, tag and assets immediately before publication.

Verify title/tag equality, tag target, `draft=false`, `prerelease=false`, `immutable=true`, all eight asset bindings and GitHub's native release attestation. The attestation binds the manifest to the trusted workflow and source; the release workflow separately runs and records its qualification suites. GitHub permits some presentation metadata changes after publication; resolvers recheck those fields.

| Interrupted state | Required action |
|---|---|
| Matching owned partial draft | Reconstruct the frozen bundle; upload verified missing assets only |
| Mismatched draft or asset | Preserve and block; never overwrite to repair ambiguity |
| Unexpected existing tag | Preserve and block, even if its target matches |
| Tag creation timeout | Reconcile original-run evidence and owned draft; ambiguity blocks |
| Publication timeout | Inspect remote state before retrying |
| Exact release already published | Complete verification only |
| Published with unavailable/failed verification | Report published, verification pending/blocked; never republish or repair in place |

For recovery, rerun the complete workflow so all six suites and both builds run again. Keep the original run ID, source, policy, builder, date and version. The first completed qualification fixes the suite results and package hashes. Later attempts preserve the manifest contents and must produce an attestation for the current attempt. A preflight-only context can be resumed by a later attempt, which records the first completed qualification. Draft notes alone cannot establish ownership. The concurrency lock does not exclude manual/API writers, so reconcile remote state before every retry.

Correct published content with a new CalVer and supersession context. Never delete assets, retag or rewrite published history.

## 6. Resolution, compatibility and staging

Discover all eligible published immutable CalVer releases with pagination and numeric ordering. Ignore drafts, prereleases and `latest`. Verify the highest candidate's metadata, tag, attestation, assets and reconstructed provenance. An invalid newer eligible candidate blocks rather than silently selecting an older one. Record the selected tag once; continuing tasks retain their recorded SHA or CalVer.

For a new task, pass `--skill` and `--installed-path` to `resolve-task`. The controller hashes the requested Skill’s installed files and compares them with that Skill’s verified release payload. Caller-supplied digests cannot establish installation identity. Missing files, symlinks and unexpected files block resolution. The existing `.skill-distribution.json` installation marker is allowed after its structure, Skill identity and recorded payload hashes are checked against the inspected files; it never substitutes for inspecting payload bytes. An older payload requires inspected compatibility evidence naming the requested Skill, inspected payload/source, selected policy/source, differences and applicable validation. Matching frontmatter or policy SHA alone is insufficient. Unknown compatibility blocks until manual compatible installation or explicit verified historical selection.

Legacy schema-1 packages and explicit historical SHA pins remain supported. Preserve the serialized `issue5-codex-skill-staging` marker; changing it requires separate compatibility migration authorization. Temporary staging preserves unrelated Skills, verifies existing markers/files, refuses drift and cross-policy migration, and has no implicit production target.

Production installation, fresh-session ChatGPT/Codex qualification, global instruction changes and active-task migration remain separately owner-authorized. Synthetic CI/staging results cannot prove live activation. The workflow never manages MCP services or configuration.
