# Development Process

This public repository holds the owner-approved development policy and its focused Skills. [docs/PROCESS.md](docs/PROCESS.md) is the canonical policy. This README explains the repository records, Skill distribution, and adoption.

## Source of truth

- [Unified Development Process v1.0](docs/PROCESS.md) is the normative policy.
- [Issue #1](https://github.com/danielbyon/development-process/issues/1) records the approved foundation scope.
- [docs/DECISIONS.md](docs/DECISIONS.md) records approved rationale, alternatives, and known limits.
- [PR #6](https://github.com/danielbyon/development-process/pull/6) records the initial bootstrap and review evidence.
- [AGENTS.md](AGENTS.md) points repository work to the canonical policy.
- [The CI workflow](.github/workflows/ci.yml) verifies the synthetic pull-request commit and runs the Skill checks on that integration revision.
- [skills/distribution.json](skills/distribution.json) defines release packaging and the file allowlist for the three Skills.

Issues define accepted scope. Task or delegation records identify execution and results, review records capture findings, and pull requests record integration and readiness. Link these records instead of creating competing task state.

## Work ownership

- ChatGPT investigates requirements, prepares and approves Codex plans, inspects final source, adjudicates review, and decides technical readiness.
- Codex implements in an isolated worktree, runs validation, obtains independent review, and publishes draft pull requests.
- The repository owner decides material product, scope, architecture, and security trade-offs and authorizes merges.

Every change receives a full review from a separate, non-authoring execution. ChatGPT must be able to inspect the final source directly. Confirmed in-scope or candidate-introduced P0/P1 defects cannot be waived.

## Skill distribution

New tasks use the identity embedded in the Skill active when the task begins and read the canonical policy at its recorded policy revision. Publishing a newer CalVer does not activate it or change a task already underway. Ordinary admission does not retrieve release assets or workflow records. Release qualification remains the successful owner-triggered workflow on reviewed and CI-approved merged `main`, followed by immutable publication. `verify-release` remains available for explicit audits, and Codex's local file and compatibility checks remain separate runtime safety checks. The user installs and updates Skills manually; publication does not install or activate them. Missing or conflicting identity references stop policy-dependent work.

Existing tasks retain their recorded SHA or CalVer. Historical pins include `aa8dc7784641dd5416befdebc246ed081bfd7ade`, `93a86127a3721d6044f4a8e993a764731fbda4e5`, `142422527de28b8e20dea1158d2f54d020dcdcd5`, `9da7c0b9113da4c0aab172860bdc5d5c77cccf0d`, `6fea1f50e0745c189685849f560f10a946e04091`, and `e2afa055d1126763c69f0e0392d25b86bab98014`. None is an implicit new-task default.

The owner-triggered workflow uses trusted main tooling to qualify explicitly selected source, prepare a complete draft, and publish eight verified assets immutably. Implementation merge does not publish or activate anything. See [Skill release operations](docs/skill-releases.md) for credentials, evidence, first-release blockers and recovery. Legacy SHA packaging and staging remain available for historical sources using schema 1; the commands below describe that legacy interface and do not publish a release.

### Validate and package

The following legacy commands apply only inside a verified schema-1 source checkout. They do not apply to the schema-2 source templates in current main. For current release candidates, use the qualified context and controller procedure in the operator guide.

Install the CI dependency, then validate and package that historical committed source tree:

```bash
python3 -m pip install -r requirements-ci.txt
python3 scripts/skill_distribution.py validate

ARTIFACT_DIR="$(mktemp -d)"
SOURCE_REVISION="$(git rev-parse HEAD)"
python3 scripts/skill_distribution.py package \
  --output-dir "$ARTIFACT_DIR" \
  --source-revision "$SOURCE_REVISION"
python3 scripts/skill_distribution.py verify \
  --artifact-dir "$ARTIFACT_DIR" \
  --source-revision "$SOURCE_REVISION"
```

The builder writes one ZIP per Skill. Each archive contains a single Skill directory with `SKILL.md` and `agents/openai.yaml`; test scenarios and repository metadata are excluded. An external `.provenance.json` sidecar records the policy revision, actual source commit, source paths, payload hashes, and archive SHA-256. Payload hashes cover archive members only. The sidecar stays outside the ZIP, so its hashes are nonrecursive. Verification compares the manifest and every packaged file with the specified Git commit.

OpenAI's [Skill Creator validator](https://github.com/openai/codex/blob/e58bf8f5233b51e7cd1679d947e3028c1ed91b06/codex-rs/skills/src/assets/samples/skill-creator/scripts/quick_validate.py) checks Skill frontmatter. Deterministic archives and Git-backed provenance require additional checks. OpenAI documents [Plugins for distributing reusable Skills](https://developers.openai.com/codex/). Issue #5 requires one individually installable ChatGPT Skill archive per Skill, so this repository reuses the official validator and adds a small packager for the required archive and provenance checks.

### Stage and promote manually

Codex loads project Skills from `.agents/skills` and user Skills from `~/.agents/skills`, as described in the [Codex Skill documentation](https://developers.openai.com/codex/skills/). The staging command takes an explicit staging root outside the source repository and writes only under that root's `.agents/skills` directory. It requires an empty root to be initialized first, refuses the personal Skill path and its parent directories, and has no global-install option.

Create a disposable Codex-compatible staging root and stage one verified archive:

```bash
STAGING_ROOT="$(mktemp -d)"
python3 scripts/skill_distribution.py init-staging \
  --staging-root "$STAGING_ROOT"
python3 scripts/skill_distribution.py stage \
  --archive "$ARTIFACT_DIR/delegation-executor.zip" \
  --staging-root "$STAGING_ROOT" \
  --policy-revision e2afa055d1126763c69f0e0392d25b86bab98014
```

Continue in the same shell so `ARTIFACT_DIR` still points to the verified packages. Inspect the staged directory at `$STAGING_ROOT/.agents/skills/<skill-name>`. Repeating the same installation is a no-op. A different source requires `--upgrade`; the installer checks the existing marker and files first. It refuses an unknown installation, local file drift, a mismatched policy, or an automatic policy migration. It changes only the named Skill and preserves other entries.

After the change merges, environment activation remains a manual owner step. For Codex, review the staged `delegation-executor` before copying it into the intended project's `.agents/skills` directory. Inspect any existing target before replacing it. The command has no implicit production target, and it does not provide auto-sync.

In ChatGPT, open Plugins from the sidebar and select Skills. Choose Create, then Upload from computer. Upload the `development-orchestrator` and `development-review` archives separately. Availability depends on the workspace plan and administrator settings. ChatGPT scans uploaded Skills and may require review or block an upload; review the source before installation. The upload flow is described in [Skills in ChatGPT](https://help.openai.com/en/articles/20001066-skills-in-chatgpt). The user is responsible for installing and updating both Skills. Release publication does not upload or activate them. Use `python3 scripts/skill_release.py verify-release` for an explicit release audit or diagnosis; ordinary task startup does not require it. New-task admission uses the identity in the active Skill. For an explicit Codex runtime check, use `python3 scripts/skill_release.py resolve-task --task-pin <CalVer-or-existing-SHA> --source-revision <SHA> --policy-revision <SHA> --builder-revision <SHA> --skill delegation-executor --installed-path <Codex Skill directory>`. To return an existing task pin without checking installed files, use `python3 scripts/skill_release.py resolve-task --existing-pin <SHA-or-CalVer>`. See the [release resolution and audit procedure](docs/skill-releases.md#6-resolution-audits-and-staging).

### Checks

Run the checks from the repository root:

```bash
python3 -m unittest discover -s tests -p test_workflow_contract.py -v
python3 -m unittest discover -s tests -p test_skill_distribution.py -v
python3 -m unittest discover -s tests -p test_distribution_smoke.py -v
python3 -m unittest discover -s tests -p test_primary_main_fast_forward.py -v
python3 -m unittest discover -s tests -p test_skill_releases.py -v
python3 -m unittest discover -s tests -p test_github_releases.py -v
```

The workflow contract tests structurally inspect the shipped Skill files and CI source-revision binding; they do not execute a Skill through an LLM. The distribution suite exercises validation, deterministic archives, source provenance, historical pin resolution, migration refusal, and temporary staging behavior. The CLI smoke test builds and stages all three archives in a disposable project containing an unrelated Skill. The primary-main suite checks safe fast-forward cleanup. These checks do not perform a live ChatGPT upload, MCP registration, or MCP server check.

CI checks the GitHub synthetic merge commit's parents and diff, then runs these checks and verifies packages against the PR head commit. A green skipped suite is not evidence that the suite ran.

## Adoption

Apply policy prospectively. Existing repositories adopt it on their next task and add CI for relevant local suites when needed. New tasks use the identity in the active Skill; existing tasks retain their recorded pins. Do not rewrite historical task records.

## Follow-up slices

Approved work is tracked in:

- [#2 — Development Orchestrator Skill](https://github.com/danielbyon/development-process/issues/2)
- [#3 — Development Review Skill](https://github.com/danielbyon/development-process/issues/3)
- [#4 — Delegation Executor Skill](https://github.com/danielbyon/development-process/issues/4)
- [#5 — Skill packaging and distribution](https://github.com/danielbyon/development-process/issues/5)

Issue #1 established the repository policy foundation. It did not implement or install the Skills or their distribution tooling.
