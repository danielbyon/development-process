"""Shared identities and primitives for release evidence verification."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

REPOSITORY = 'danielbyon/development-process'

BASE = '/repos/' + REPOSITORY

BOOTSTRAP_BASELINE = 'e47c8882e590c3ec41d2d46f461d18ed73132534'

SHA = re.compile(r'[0-9a-f]{40}')

SUITES = (
    'test_workflow_contract.py', 'test_skill_distribution.py',
    'test_distribution_smoke.py', 'test_primary_main_fast_forward.py',
    'test_skill_releases.py', 'test_github_releases.py')
CI_WORKFLOW_ID = 413585893
CI_WORKFLOW_PATH = '.github/workflows/ci.yml'
CI_WORKFLOW_NAME = 'CI'
CI_REQUIRED_JOB_NAME = 'Validate committed PR integration diff'
CI_REVISION_CHECK_STEP_NAME = 'Verify revision and check committed diff'

JSON = dict[str, Any]

RepositoryPath = str | Path

class ReleaseError(RuntimeError):
    """A mandatory release prerequisite could not be verified."""

class MissingEvidenceError(ReleaseError):
    """A required evidence record or qualification has not been supplied."""

class _EvidenceAPI(Protocol):
    """Read-only provider operations used to authenticate release evidence."""

    def request(self, method: str, endpoint: str, data: JSON | None = None,
                raw: bool = False) -> Any: ...
    def pages(self, endpoint: str) -> list[Any]: ...
    def record(self, reference: str) -> JSON: ...
    def ci_jobs(self, run_id: int | str, attempt: int) -> list[JSON]: ...
    def job_log(self, job_id: int | str) -> str: ...
    def run(self, run_id: int | str) -> JSON: ...
    def releases(self) -> list[JSON]: ...

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)

def require_present(value: Any, message: str) -> Any:
    """Return a required value or raise when the provider omitted it."""
    if value is None:
        raise MissingEvidenceError(message)
    return value

def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def git(root: RepositoryPath, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ['git', '-C', str(root), *arguments], check=True,
            capture_output=True).stdout
    except subprocess.CalledProcessError as error:
        raise ReleaseError('Git identity or history unavailable') from error

def revision(root: RepositoryPath, value: str) -> str:
    require(isinstance(value, str) and SHA.fullmatch(value),
            'Full immutable revision required')
    require(git(root, 'rev-parse', value + '^{commit}').decode().strip() == value,
            'Revision mismatch')
    return value

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
