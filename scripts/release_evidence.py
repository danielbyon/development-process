"""Evidence provenance, chronology, admission and coverage validation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

JSON = dict[str, Any]
RepositoryPath = str | Path


class _EvidenceAPI(Protocol):
    """Read-only GitHub operations required by release evidence checks."""

    def request(self, method: str, endpoint: str, data: JSON | None = None,
                raw: bool = False) -> Any: ...
    def pages(self, endpoint: str) -> list[Any]: ...
    def record(self, reference: str) -> JSON: ...
    def ci_jobs(self, run_id: int | str, attempt: int) -> list[JSON]: ...
    def job_log(self, job_id: int | str) -> str: ...
    def run(self, run_id: int | str) -> JSON: ...
    def releases(self) -> list[JSON]: ...


class _GitCommand(Protocol):
    def __call__(self, root: RepositoryPath, *arguments: str) -> bytes: ...

@dataclass(frozen=True)
class EvidenceContext:
    BASE: str
    REPOSITORY: str
    SHA: re.Pattern[str]
    BOOTSTRAP_BASELINE: str
    SUITES: tuple[str, ...]
    ReleaseError: type[Exception]
    APIError: type[Exception]
    require: Callable[[bool, str], None]
    canonical: Callable[[Any], bytes]
    digest: Callable[[bytes], str]
    git: _GitCommand
    revision: Callable[[RepositoryPath, str], str]
    select_anchor: Callable[[RepositoryPath, _EvidenceAPI, str, str], JSON | None]
    utc_now: Callable[[], str]

from release_evidence_records import (
    build_owner_receipt, capture_execution, prepare_readiness_index)
from release_evidence_baseline import verify_baseline_admission
from release_evidence_qualification import (
    BaselineQualification, VerifiedBaselineAdmission, verify_coverage,
    verify_evidence, verify_pending_baseline_coverage)
from release_evidence_integrations import (
    verify_live_integrations, verify_premerge_integrations)
from release_evidence_audit import audit_pull_request, discover_evidence

class EvidenceService:
    """Expose release evidence operations through one controller-facing boundary."""
    def __init__(self, context_provider: Callable[[], EvidenceContext]):
        self._context_provider=context_provider

    def capture_execution(self, root: RepositoryPath, gate: str, system: str,
                          command: Sequence[str], report: JSON,
                          reviewed_range: JSON,
                          transcript: str | Path | None = None) -> JSON:
        return capture_execution(self._context_provider(), root, gate, system,
                                 command, report, reviewed_range, transcript)

    def build_owner_receipt(self, gate: str, revision_id: str) -> str:
        return build_owner_receipt(self._context_provider(), gate, revision_id)

    def prepare_readiness_index(self, evidence: JSON, pull_request: int,
                                api: _EvidenceAPI, *,
                                normalizes_reference: str | None = None) -> str:
        return prepare_readiness_index(self._context_provider(), evidence,
                                       pull_request, api,
                                       normalizes_reference=normalizes_reference)

    def verify_evidence(self, evidence: JSON,
                        source: _EvidenceAPI | Callable[[str], Any],
                        root: RepositoryPath | None = None, *,
                        dispatch_run_id: int | None = None
                        ) -> list[JSON] | VerifiedBaselineAdmission:
        context=self._context_provider()
        origin=evidence.get('origin',{}) if isinstance(evidence,dict) else {}
        if origin.get('kind')=='prospective_baseline':
            context.require(root is not None,
                    'Git checkout required to bind reviewed diff and inspected files')
            api=(getattr(source,'__self__',None) if callable(source) else
                 source if hasattr(source,'record') else None)
            context.require(api is not None and hasattr(api,'run') and
                    dispatch_run_id is not None,
                    'Prospective evidence requires an authenticated API and original dispatch identity')
            return verify_baseline_admission(context,root,api,evidence,
                origin.get('source_revision'),origin.get('builder_revision'),
                dispatch_run_id)
        return verify_evidence(context, evidence, source, root,
                               dispatch_run_id=dispatch_run_id)

    def verify_coverage(self, root: RepositoryPath, evidence: JSON, target: str,
                        *, admitted: bool = False,
                        baseline_admission: VerifiedBaselineAdmission | None = None
                        ) -> None:
        return verify_coverage(self._context_provider(), root, evidence, target,
                               admitted=admitted,
                               baseline_admission=baseline_admission)

    def verify_baseline_admission(self, root: RepositoryPath, api: _EvidenceAPI,
                                  evidence: JSON, source: str, builder: str,
                                  dispatch_run_id: int
                                  ) -> VerifiedBaselineAdmission:
        return verify_baseline_admission(self._context_provider(), root, api,
                                         evidence, source, builder,
                                         dispatch_run_id)

    def verify_pending_baseline_coverage(
            self, root: RepositoryPath, evidence: JSON,
            qualification: BaselineQualification, target: str,
            main_revision: str) -> None:
        return verify_pending_baseline_coverage(
            self._context_provider(), root, evidence, qualification, target,
            main_revision)

    def verify_live_integrations(self, api: _EvidenceAPI, evidence: JSON,
                                 root: RepositoryPath | None = None) -> list[JSON]:
        return verify_live_integrations(self._context_provider(), api, evidence,
                                        root)

    def verify_premerge_integrations(self, api: _EvidenceAPI, evidence: JSON,
                                     root: RepositoryPath) -> list[JSON]:
        return verify_premerge_integrations(self._context_provider(), api,
                                            evidence, root)

    def audit_pull_request(self, root: RepositoryPath, api: _EvidenceAPI,
                           number: int) -> JSON:
        return audit_pull_request(self._context_provider(), root, api, number)

    def discover_evidence(self, root: RepositoryPath, api: _EvidenceAPI,
                          source: str, builder: str) -> JSON:
        return discover_evidence(self._context_provider(), root, api, source,
                                 builder)

__all__=('EvidenceContext','EvidenceService','BaselineQualification',
         'VerifiedBaselineAdmission')
