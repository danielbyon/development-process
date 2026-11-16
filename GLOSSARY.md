# Glossary

1. **Source revision:** Commit containing the selected policy and Skill inputs.
2. **Policy revision:** Commit identifying the canonical policy contents at the selected source; distinct from distribution approval.
3. **Builder revision:** Trusted protected-main workflow and tooling commit fixed at dispatch.
4. **Release pin:** Verified immutable Pacific CalVer tag recorded once for a new task.
5. **Historical task pin:** Existing recorded SHA or CalVer retained during continuation.
6. **Baseline admission:** Evidence-backed acceptance of a bounded historical trust anchor; a candidate baseline has not passed admission.
7. **Integration frontier:** Main-history position through which source changes must have verified integration evidence.
8. **Readiness record:** Index into inspectable review, inspection, CI and authorization records.
9. **Compatibility evidence:** Inspected evidence relating an installed Skill payload to selected policy/source and validation.
10. **Activation:** Owner-controlled installation and environment adoption, separate from release publication.
11. **Patch-forward release:** New immutable version correcting or superseding an earlier release while preserving history.
