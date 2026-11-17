"""Evidence provenance, chronology, admission and coverage validation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class EvidenceContext:
    BASE: str
    REPOSITORY: str
    SHA: re.Pattern[str]
    BOOTSTRAP_BASELINE: str
    SUITES: tuple[str, ...]
    ReleaseError: type[Exception]
    APIError: type[Exception]
    require: Callable[..., Any]
    canonical: Callable[..., Any]
    digest: Callable[..., Any]
    git: Callable[..., Any]
    revision: Callable[..., Any]
    select_anchor: Callable[..., Any]
    utc_now: Callable[..., Any]

from release_evidence_records import (
    build_owner_receipt, capture_execution, prepare_readiness_index)
from release_evidence_qualification import (
    BaselineQualification, VerifiedBaselineAdmission, verify_baseline_admission,
    verify_coverage, verify_evidence, verify_pending_baseline_coverage)
from release_evidence_integrations import (
    verify_live_integrations, verify_premerge_integrations)
from release_evidence_audit import audit_pull_request, discover_evidence

class EvidenceService:
    """Expose release evidence operations through one controller-facing boundary."""
    def __init__(self,context_provider):
        self._context_provider=context_provider

    def _call(self,operation,*args,**kwargs):
        return operation(self._context_provider(),*args,**kwargs)

    def capture_execution(self,*args,**kwargs):
        return self._call(capture_execution,*args,**kwargs)

    def build_owner_receipt(self,*args,**kwargs):
        return self._call(build_owner_receipt,*args,**kwargs)

    def prepare_readiness_index(self,*args,**kwargs):
        return self._call(prepare_readiness_index,*args,**kwargs)

    def verify_evidence(self,*args,**kwargs):
        return self._call(verify_evidence,*args,**kwargs)

    def verify_coverage(self,*args,**kwargs):
        return self._call(verify_coverage,*args,**kwargs)

    def verify_baseline_admission(self,*args,**kwargs):
        return self._call(verify_baseline_admission,*args,**kwargs)

    def verify_pending_baseline_coverage(self,*args,**kwargs):
        return self._call(verify_pending_baseline_coverage,*args,**kwargs)

    def verify_live_integrations(self,*args,**kwargs):
        return self._call(verify_live_integrations,*args,**kwargs)

    def verify_premerge_integrations(self,*args,**kwargs):
        return self._call(verify_premerge_integrations,*args,**kwargs)

    def audit_pull_request(self,*args,**kwargs):
        return self._call(audit_pull_request,*args,**kwargs)

    def discover_evidence(self,*args,**kwargs):
        return self._call(discover_evidence,*args,**kwargs)

__all__=('EvidenceContext','EvidenceService','BaselineQualification',
         'VerifiedBaselineAdmission')
