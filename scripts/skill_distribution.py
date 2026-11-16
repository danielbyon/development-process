#!/usr/bin/env python3
"""Validate, package, verify, and stage the repository's three Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


MANIFEST_PATH = PurePosixPath("skills/distribution.json")
VALIDATOR_PATH = Path("scripts/vendor/quick_validate.py")
MARKER_NAME = ".skill-distribution.json"
STAGING_MARKER_NAME = ".codex-skill-staging.json"
STAGING_MARKER = {
    "schema_version": 1,
    "purpose": "issue5-codex-skill-staging",
}
SKILL_NAMES = {
    "development-orchestrator",
    "development-review",
    "delegation-executor",
}
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
# Validate inline links and images; honor escaped brackets and even backslash runs.
LOCAL_LINK_PATTERN = re.compile(
    r"(?<!\\)(?:\\\\)*(?:!\[[^\]]*\]|(?<!!)\[[^\]]*\])\(([^)]+)\)"
)


class DistributionError(Exception):
    """Raised when a package, policy pin, or staging target is unsafe."""


def _git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace").strip()
        raise DistributionError(f"Git could not verify source provenance: {detail}") from error
    return result.stdout


def _require_revision(root: Path, revision: str) -> None:
    if not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        raise DistributionError("A full 40-character lowercase Git revision is required.")
    resolved = _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if resolved.decode("ascii", errors="replace").strip() != revision:
        raise DistributionError(f"Git revision does not resolve exactly: {revision}")


def _committed_file(root: Path, revision: str, path: str) -> bytes:
    _require_revision(root, revision)
    return _git(root, "show", f"{revision}:{path}")


def _policy_file_exists(root: Path, revision: str) -> None:
    try:
        _committed_file(root, revision, "docs/PROCESS.md")
    except DistributionError as error:
        raise DistributionError(
            f"Policy revision {revision} is missing or has no docs/PROCESS.md."
        ) from error


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DistributionError(f"Could not read {description}: {error}") from error
    if not isinstance(value, dict):
        raise DistributionError(f"{description} must contain a JSON object.")
    return value


def load_manifest(root: Path) -> dict[str, Any]:
    """Read the distribution manifest without changing the repository."""
    return _read_json(root / MANIFEST_PATH.as_posix(), "Skill distribution manifest")


def _relative_path(value: Any, description: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise DistributionError(f"{description} must be a relative POSIX path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DistributionError(f"{description} contains an unsafe path: {value!r}.")
    return path


def _source_path(root: Path, source_dir: PurePosixPath, relative: PurePosixPath) -> Path:
    combined = source_dir / relative
    candidate = root.joinpath(*combined.parts)
    try:
        resolved = candidate.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise DistributionError(f"Missing Skill source file: {candidate}") from error
    if not resolved.is_relative_to(root_resolved):
        raise DistributionError(f"Skill source escapes the repository: {candidate}")
    cursor = root
    for part in combined.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise DistributionError(f"Symlinks are not permitted in Skill sources: {cursor}")
    if not resolved.is_file():
        raise DistributionError(f"Skill source is not a regular file: {candidate}")
    return resolved


def _frontmatter(skill_md: Path) -> dict[str, Any]:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DistributionError(f"Could not read {skill_md}: {error}") from error
    if not text.startswith("---\n"):
        raise DistributionError(f"{skill_md} must begin with YAML frontmatter.")
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        raise DistributionError(f"{skill_md} has an unclosed YAML frontmatter block.")
    try:
        value = yaml.safe_load(parts[0][4:])
    except yaml.YAMLError as error:
        raise DistributionError(f"Invalid YAML frontmatter in {skill_md}: {error}") from error
    if not isinstance(value, dict):
        raise DistributionError(f"YAML frontmatter in {skill_md} must be an object.")
    return value


def _validate_links(skill_md: Path, included_files: set[str]) -> None:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DistributionError(f"Could not read {skill_md}: {error}") from error
    for match in LOCAL_LINK_PATTERN.finditer(text):
        destination = match.group(1).strip().split("#", 1)[0]
        if not destination or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destination):
            continue
        relative = _relative_path(destination, "Skill resource link")
        if relative.as_posix() not in included_files:
            raise DistributionError(
                f"Skill resource link is not included in the archive: {destination}"
            )
        _source_path(skill_md.parent, PurePosixPath("."), relative)


def _skill_entries(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_manifest(root)
    schema = manifest.get("schema_version")
    if schema not in (1, 2):
        raise DistributionError("Unsupported distribution manifest schema_version.")
    revision = manifest.get("policy_revision")
    if schema == 1:
        _policy_file_exists(root, revision)
    else:
        if manifest.get("policy_reference") != "{{release_tag}}" or manifest.get("transform_version") != 1:
            raise DistributionError("Unsupported release template contract.")
        revision = "{{release_tag}}"
    raw_skills = manifest.get("skills")
    if not isinstance(raw_skills, list):
        raise DistributionError("The distribution manifest must list its Skills.")

    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in raw_skills:
        if not isinstance(raw, dict):
            raise DistributionError("Each Skill manifest entry must be a JSON object.")
        name = raw.get("name")
        if not isinstance(name, str) or name not in SKILL_NAMES or name in names:
            raise DistributionError(f"Unexpected or duplicate Skill name: {name!r}")
        names.add(name)
        source_dir = _relative_path(raw.get("source_dir"), f"{name} source_dir")
        if source_dir.as_posix() != f"skills/{name}":
            raise DistributionError(f"{name} must use its repository Skill directory.")
        raw_files = raw.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise DistributionError(f"{name} must list its archive files.")
        files = [_relative_path(item, f"{name} archive file") for item in raw_files]
        file_names = [item.as_posix() for item in files]
        if len(file_names) != len(set(file_names)):
            raise DistributionError(f"{name} lists a duplicate archive file.")
        if not {"SKILL.md", "agents/openai.yaml"}.issubset(file_names):
            raise DistributionError(f"{name} must include SKILL.md and agents/openai.yaml.")
        if any(item.parts[0] in {"tests", ".git", "__pycache__"} for item in files):
            raise DistributionError(f"{name} must not package tests or repository metadata.")

        directory = root.joinpath(*source_dir.parts)
        if directory.is_symlink() or not directory.is_dir():
            raise DistributionError(f"Invalid Skill source directory: {directory}")
        for relative in files:
            _source_path(root, source_dir, relative)
        frontmatter = _frontmatter(directory / "SKILL.md")
        if frontmatter.get("name") != name:
            raise DistributionError(f"{name}/SKILL.md frontmatter name does not match.")
        if not isinstance(frontmatter.get("description"), str) or not frontmatter["description"].strip():
            raise DistributionError(f"{name}/SKILL.md needs a nonempty description.")
        skill_text = (directory / "SKILL.md").read_text(encoding="utf-8")
        policy_url = (
            "https://github.com/danielbyon/development-process/blob/"
            f"{revision}/docs/PROCESS.md"
        )
        if revision not in skill_text or policy_url not in skill_text:
            raise DistributionError(
                f"{name}/SKILL.md policy reference differs from the manifest pin."
            )
        if schema == 2:
            if skill_text.count(policy_url) != 1 or skill_text.count(revision) != 1:
                raise DistributionError(f"{name} has an unexpected release token outside its canonical policy URL.")
            for relative in files:
                if relative.as_posix() != "SKILL.md" and b"{{release_tag}}" in (directory / relative).read_bytes():
                    raise DistributionError(f"{name} has an unexpected release token in {relative}.")
        metadata_path = directory / "agents" / "openai.yaml"
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise DistributionError(f"Invalid agents/openai.yaml for {name}: {error}") from error
        interface = metadata.get("interface") if isinstance(metadata, dict) else None
        if not isinstance(interface, dict) or not all(
            isinstance(interface.get(key), str) and interface[key].strip()
            for key in ("display_name", "short_description")
        ):
            raise DistributionError(f"{name} needs valid agents/openai.yaml interface metadata.")
        _validate_links(directory / "SKILL.md", set(file_names))

        entries.append(
            {
                "name": name,
                "source_dir": source_dir,
                "files": files,
                "frontmatter": frontmatter,
            }
        )

    if names != SKILL_NAMES:
        missing = ", ".join(sorted(SKILL_NAMES - names))
        raise DistributionError(f"Distribution manifest is missing Skills: {missing}")
    return manifest, entries


def validate_distribution(root: Path) -> list[str]:
    """Run the official frontmatter validator and repository-specific checks."""
    root = Path(root).resolve(strict=True)
    _, entries = _skill_entries(root)
    validator = root / VALIDATOR_PATH
    if not validator.is_file():
        raise DistributionError(f"Vendored OpenAI Skill validator is missing: {validator}")
    for entry in entries:
        skill_dir = root.joinpath(*entry["source_dir"].parts)
        result = subprocess.run(
            [sys.executable, str(validator), str(skill_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            message = (result.stdout + result.stderr).strip()
            raise DistributionError(f"Official validator rejected {entry['name']}: {message}")
    return [entry["name"] for entry in entries]


def resolve_task_policy(root: Path, task_policy_revision: str | None = None) -> str:
    """Keep an existing task's pin; new tasks use the approved manifest pin."""
    root = Path(root).resolve(strict=True)
    manifest = load_manifest(root)
    selected = (
        manifest.get("policy_revision")
        if task_policy_revision is None
        else task_policy_revision
    )
    if task_policy_revision is None and manifest.get("schema_version") == 2:
        raise DistributionError("Use resolve-task to select a verified immutable release.")
    _policy_file_exists(root, selected)
    return selected


def _source_files(entry: dict[str, Any]) -> dict[str, str]:
    return {
        f"{entry['name']}/{relative.as_posix()}":
        (entry["source_dir"] / relative).as_posix()
        for relative in entry["files"]
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _read_committed_payload(
    root: Path, source_revision: str, source_path: str
) -> bytes:
    payload = _committed_file(root, source_revision, source_path)
    working = (root / source_path).read_bytes()
    if working != payload:
        raise DistributionError(
            f"Working tree differs from source revision at {source_path}; "
            "package from a committed source tree."
        )
    return payload


def build_packages(root: Path, output_dir: Path, source_revision: str) -> list[Path]:
    """Build one deterministic ZIP and external provenance file per Skill."""
    root = Path(root).resolve(strict=True)
    output_dir = Path(output_dir)
    _require_revision(root, source_revision)
    names = validate_distribution(root)
    manifest, entries = _skill_entries(root)
    if manifest.get("schema_version") != 1:
        raise DistributionError("Use release-package with a frozen context for schema-2 sources.")
    try:
        committed_manifest = _committed_file(
            root, source_revision, MANIFEST_PATH.as_posix()
        )
        working_manifest = (root / MANIFEST_PATH.as_posix()).read_bytes()
    except OSError as error:
        raise DistributionError(f"Could not read the committed distribution manifest: {error}") from error
    if committed_manifest != working_manifest:
        raise DistributionError(
            "Working distribution manifest differs from the declared package source revision."
        )
    if set(names) != {entry["name"] for entry in entries}:
        raise DistributionError("Skill validation and manifest results disagree.")

    output_dir.mkdir(parents=True, exist_ok=True)
    packages: list[Path] = []
    for entry in entries:
        file_map = _source_files(entry)
        payloads = {
            member: _read_committed_payload(root, source_revision, source)
            for member, source in sorted(file_map.items())
        }
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for member, payload in sorted(payloads.items()):
                info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        archive_bytes = buffer.getvalue()
        package_path = output_dir / f"{entry['name']}.zip"
        _atomic_write(package_path, archive_bytes)

        provenance = {
            "schema_version": 1,
            "skill_name": entry["name"],
            "policy_revision": manifest["policy_revision"],
            "source_revision": source_revision,
            "source_files": file_map,
            "payload_sha256": {
                member: hashlib.sha256(payload).hexdigest()
                for member, payload in sorted(payloads.items())
            },
            "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "hash_scope": "archive members only; this sidecar is external",
        }
        sidecar = package_path.with_suffix(".provenance.json")
        _atomic_write(
            sidecar,
            (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        packages.append(package_path)
    return packages


def _safe_zip_members(
    archive: zipfile.ZipFile, expected_members: set[str]
) -> dict[str, bytes]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise DistributionError("Archive contains duplicate member names.")
    if set(names) != expected_members:
        raise DistributionError("Archive members do not match the package manifest.")
    payloads: dict[str, bytes] = {}
    for info in infos:
        path = PurePosixPath(info.filename)
        if (
            path.is_absolute()
            or "\\" in info.filename
            or any(part in {"", ".", ".."} for part in path.parts)
            or info.is_dir()
        ):
            raise DistributionError(f"Archive contains an unsafe path: {info.filename!r}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)):
            raise DistributionError(f"Archive contains a non-regular file: {info.filename}")
        try:
            payloads[info.filename] = archive.read(info)
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise DistributionError(f"Could not read archive member {info.filename}: {error}") from error
    return payloads


def _verify_archive(
    root: Path,
    archive_path: Path,
    expected_source_revision: str | None = None,
) -> dict[str, Any]:
    manifest, entries = _skill_entries(root)
    if not archive_path.is_file() or archive_path.is_symlink():
        raise DistributionError(f"Package archive is missing or unsafe: {archive_path}")
    sidecar_path = archive_path.with_suffix(".provenance.json")
    if sidecar_path.is_symlink():
        raise DistributionError("Package provenance sidecar must not be a symlink.")
    provenance = _read_json(sidecar_path, "package provenance")
    skill_name = archive_path.stem
    matches = [entry for entry in entries if entry["name"] == skill_name]
    if len(matches) != 1 or provenance.get("skill_name") != skill_name:
        raise DistributionError(f"Package is not a listed standalone Skill: {archive_path.name}")
    if provenance.get("schema_version") != 1:
        raise DistributionError("Unsupported package provenance schema.")
    if provenance.get("policy_revision") != manifest.get("policy_revision"):
        raise DistributionError("Package policy revision differs from the approved manifest pin.")
    source_revision = provenance.get("source_revision")
    _require_revision(root, source_revision)
    _policy_file_exists(root, provenance["policy_revision"])
    try:
        committed_manifest = _committed_file(
            root, source_revision, MANIFEST_PATH.as_posix()
        )
        working_manifest = (root / MANIFEST_PATH.as_posix()).read_bytes()
    except OSError as error:
        raise DistributionError(f"Could not read the committed distribution manifest: {error}") from error
    if committed_manifest != working_manifest:
        raise DistributionError("Package source commit has a different distribution manifest.")
    if expected_source_revision and source_revision != expected_source_revision:
        raise DistributionError("Package source revision does not match the requested source commit.")
    archive_bytes = archive_path.read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != provenance.get("archive_sha256"):
        raise DistributionError("Package archive SHA-256 does not match its provenance sidecar.")

    entry = matches[0]
    source_files = _source_files(entry)
    if provenance.get("source_files") != source_files:
        raise DistributionError("Package source paths do not match the distribution manifest.")
    expected_members = set(source_files)
    expected_hashes = provenance.get("payload_sha256")
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != expected_members:
        raise DistributionError("Package payload hash list does not match its archive members.")
    try:
        with zipfile.ZipFile(archive_path, "r") as package:
            payloads = _safe_zip_members(package, expected_members)
    except (OSError, zipfile.BadZipFile) as error:
        raise DistributionError(f"Invalid ZIP archive: {error}") from error
    for member, payload in payloads.items():
        if hashlib.sha256(payload).hexdigest() != expected_hashes[member]:
            raise DistributionError(f"Payload SHA-256 mismatch for {member}.")
        committed = _committed_file(root, source_revision, source_files[member])
        if payload != committed:
            raise DistributionError(f"Package payload does not match committed source: {member}")
    if provenance.get("hash_scope") != "archive members only; this sidecar is external":
        raise DistributionError("Package provenance does not declare the supported hash scope.")
    return provenance


def verify_packages(
    root: Path, artifact_dir: Path, source_revision: str
) -> list[Path]:
    """Verify every manifest Skill archive against its committed source."""
    root = Path(root).resolve(strict=True)
    _require_revision(root, source_revision)
    _, entries = _skill_entries(root)
    artifact_dir = Path(artifact_dir)
    verified: list[Path] = []
    for entry in entries:
        archive_path = artifact_dir / f"{entry['name']}.zip"
        _verify_archive(root, archive_path, source_revision)
        verified.append(archive_path)
    return verified


def _installed_files_match(target: Path, marker: dict[str, Any]) -> bool:
    files = marker.get("payload_sha256")
    if not isinstance(files, dict) or not files:
        return False
    expected_top_level = {
        PurePosixPath(name).parts[0] for name in set(files) | {MARKER_NAME}
    }
    if {path.name for path in target.iterdir()} != expected_top_level:
        return False
    for relative, expected_hash in files.items():
        safe = _relative_path(relative, "Installed Skill file")
        path = target.joinpath(*safe.parts)
        cursor = target
        for part in safe.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        if not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            return False
    if any(path.is_symlink() for path in target.rglob("*")):
        return False
    actual_files = {
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and path != target / MARKER_NAME
    }
    return actual_files == set(files)


def _require_external_staging_root(source_root: Path, staging_root: Path) -> Path:
    staging_root = Path(staging_root)
    if staging_root.is_symlink():
        raise DistributionError("Staging root must not be a symlink.")
    try:
        root = staging_root.resolve(strict=True)
    except OSError as error:
        raise DistributionError(f"Staging root must already exist: {staging_root}") from error
    if not root.is_dir():
        raise DistributionError(f"Staging root is not a directory: {root}")
    if root.is_relative_to(source_root) or source_root.is_relative_to(root):
        raise DistributionError(
            "Staging root must be separate from the source repository; production promotion is manual."
        )
    personal_skills = Path.home().resolve() / ".agents" / "skills"
    if (
        root == Path.home().resolve()
        or root.is_relative_to(personal_skills)
        or personal_skills.is_relative_to(root)
    ):
        raise DistributionError("Personal Skill paths and their parents are not staging roots.")
    return root


def _staging_layout(staging_root: Path) -> Path:
    root = Path(staging_root)
    if root.is_symlink():
        raise DistributionError("Staging root must not be a symlink.")
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise DistributionError(f"Staging root must already exist: {root}") from error
    if not root.is_dir():
        raise DistributionError(f"Staging root is not a directory: {root}")
    personal_skills = Path.home().resolve() / ".agents" / "skills"
    agents = root / ".agents"
    skills = agents / "skills"
    if (
        root == Path.home().resolve()
        or root.is_relative_to(personal_skills)
        or personal_skills.is_relative_to(root)
    ):
        raise DistributionError("Personal Skill installation paths are not staging roots.")
    if agents.is_symlink():
        raise DistributionError("Staging .agents directory must not be a symlink.")
    if skills.is_symlink():
        raise DistributionError("Staging .agents/skills must not be a symlink.")
    if agents.exists() and not agents.is_dir():
        raise DistributionError("Staging .agents path must be a directory.")
    if skills.exists() and not skills.is_dir():
        raise DistributionError("Staging .agents/skills path must be a directory.")
    return skills


def initialize_staging_root(source_root: Path, staging_root: Path) -> Path:
    """Mark an empty directory as an isolated Codex Skill staging root."""
    source_root = Path(source_root).resolve(strict=True)
    root = _require_external_staging_root(source_root, staging_root)
    if any(root.iterdir()):
        raise DistributionError("Initialize staging only in an empty directory.")
    _staging_layout(root)
    marker = root / STAGING_MARKER_NAME
    marker.write_text(
        json.dumps(STAGING_MARKER, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return marker


def _staging_skills_dir(staging_root: Path) -> Path:
    skills = _staging_layout(staging_root)
    marker_path = skills.parent.parent / STAGING_MARKER_NAME
    if marker_path.is_symlink() or not marker_path.is_file():
        raise DistributionError("Staging root is not explicitly initialized.")
    marker = _read_json(marker_path, "staging root marker")
    if marker != STAGING_MARKER:
        raise DistributionError("Staging root marker is invalid.")
    return skills


def install_archive(
    root: Path,
    archive_path: Path,
    staging_root: Path,
    expected_policy_revision: str,
    upgrade: bool = False,
) -> dict[str, str]:
    """Install one verified Skill into a Codex-compatible staging project only."""
    root = Path(root).resolve(strict=True)
    provenance = _verify_archive(root, Path(archive_path))
    manifest = load_manifest(root)
    if expected_policy_revision != manifest.get("policy_revision"):
        raise DistributionError("Requested task policy pin differs from the approved distribution pin.")
    _policy_file_exists(root, expected_policy_revision)
    if provenance["policy_revision"] != expected_policy_revision:
        raise DistributionError("Package policy pin does not match the requested task policy.")

    return _install_verified(root, archive_path, staging_root, expected_policy_revision, provenance, upgrade)


def _install_verified(root, archive_path, staging_root, expected_policy_revision, provenance, upgrade=False):
    """Stage independently verified payloads with the shared drift and rollback guards."""
    staging_root = _require_external_staging_root(root, Path(staging_root))
    skills_dir = _staging_skills_dir(staging_root)
    target = skills_dir / provenance["skill_name"]
    if target.is_symlink():
        raise DistributionError(f"Refusing to replace a symlinked Skill target: {target}")
    previous: dict[str, Any] | None = None
    if target.exists():
        marker_path = target / MARKER_NAME
        if not target.is_dir() or marker_path.is_symlink() or not marker_path.is_file():
            raise DistributionError(
                f"Existing Skill is unmanaged; refusing to overwrite it: {target}"
            )
        previous = _read_json(marker_path, "installed Skill marker")
        if previous.get("schema_version") != 1:
            raise DistributionError("Installed Skill marker uses an unknown schema.")
        if previous.get("skill_name") != provenance["skill_name"]:
            raise DistributionError("Installed Skill marker belongs to another Skill.")
        if previous.get("policy_revision") != expected_policy_revision:
            raise DistributionError("Installed Skill has a different policy pin; migration is not automatic.")
        if not _installed_files_match(target, previous):
            raise DistributionError("Installed Skill has local drift; refusing to overwrite it.")
        same_package = (
            previous.get("source_revision") == provenance["source_revision"]
            and previous.get("archive_sha256") == provenance["archive_sha256"]
        )
        if same_package:
            return {"skill": provenance["skill_name"], "status": "unchanged"}
        if not upgrade:
            raise DistributionError("A different source is installed; pass --upgrade for explicit replacement.")
        if previous.get("policy_revision") != provenance["policy_revision"]:
            raise DistributionError("Policy migration is not supported by the staging installer.")

    try:
        with zipfile.ZipFile(archive_path, "r") as package:
            payloads = _safe_zip_members(
                package,
                set(provenance["payload_sha256"]),
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise DistributionError(f"Invalid ZIP archive: {error}") from error
    for member, payload in payloads.items():
        expected_hash = provenance["payload_sha256"].get(member)
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise DistributionError(
                f"Payload changed after package verification: {member}"
            )

    skills_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage-", dir=skills_dir))
    backup: Path | None = None
    try:
        for member, payload in sorted(payloads.items()):
            relative = PurePosixPath(member).relative_to(provenance["skill_name"])
            destination = temporary.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        marker = {
            "schema_version": 1,
            "skill_name": provenance["skill_name"],
            "policy_revision": provenance["policy_revision"],
            "source_revision": provenance["source_revision"],
            "archive_sha256": provenance["archive_sha256"],
            "payload_sha256": {
                PurePosixPath(member).relative_to(provenance["skill_name"]).as_posix(): digest
                for member, digest in provenance["payload_sha256"].items()
            },
        }
        (temporary / MARKER_NAME).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=skills_dir)
            )
            backup.rmdir()
            os.replace(target, backup)
        try:
            os.replace(temporary, target)
        except OSError:
            if backup is not None:
                os.replace(backup, target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
    except (OSError, ValueError) as error:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise DistributionError(f"Could not stage {provenance['skill_name']}: {error}") from error

    return {
        "skill": provenance["skill_name"],
        "status": "upgraded" if previous else "installed",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate shipped Skill sources")
    validate.add_argument("--root", type=Path, default=Path.cwd())

    package = commands.add_parser("package", help="build deterministic Skill archives")
    package.add_argument("--root", type=Path, default=Path.cwd())
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--source-revision", required=True)

    verify = commands.add_parser("verify", help="verify archives against committed sources")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify.add_argument("--artifact-dir", type=Path, required=True)
    verify.add_argument("--source-revision", required=True)

    stage = commands.add_parser("stage", help="stage one Skill in an isolated project root")
    stage.add_argument("--root", type=Path, default=Path.cwd())
    stage.add_argument("--archive", type=Path, required=True)
    stage.add_argument("--staging-root", type=Path, required=True)
    stage.add_argument("--policy-revision", required=True)
    stage.add_argument("--upgrade", action="store_true")

    initialize = commands.add_parser(
        "init-staging", help="mark an empty directory as an isolated staging root"
    )
    initialize.add_argument("--root", type=Path, default=Path.cwd())
    initialize.add_argument("--staging-root", type=Path, required=True)

    policy = commands.add_parser("policy", help="resolve a new or in-flight task policy pin")
    policy.add_argument("--root", type=Path, default=Path.cwd())
    policy.add_argument("--task-policy-revision")
    for command in ("release-package", "release-verify", "release-stage"):
        release = commands.add_parser(command, help="operate on a source-bound release candidate")
        release.add_argument("--root", type=Path, default=Path.cwd())
        release.add_argument("--context", type=Path, required=True)
        if command == "release-package":
            release.add_argument("--output-dir", type=Path, required=True)
        else:
            release.add_argument("--artifact-dir", type=Path, required=True)
        if command == "release-stage":
            release.add_argument("--staging-root", type=Path, required=True)
            release.add_argument("--upgrade", action="store_true")
    return parser



def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _regular_blob(root: Path, revision: str, path: str) -> bytes:
    """Read a regular Git blob; historical symlinks are never followed."""
    listing = _git(root, "ls-tree", revision, "--", path).decode().strip()
    if not listing or listing.split()[0] not in {"100644", "100755"}:
        raise DistributionError(f"Expected regular committed file: {revision}:{path}")
    return _committed_file(root, revision, path)


def _release_bundle(root: Path, context: dict) -> dict[str, bytes]:
    """Reconstruct the complete release using trusted code and committed data only.

    Required context fields are release_version, source_revision, policy_revision,
    and builder_revision. Extra JSON fields are frozen into the manifest. This
    operation neither resolves release authority nor requires a remote tag.
    """
    import datetime
    import io

    if not isinstance(context, dict):
        raise DistributionError("Release context must be an object.")
    version = context.get("release_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}(?:\.[2-9]|\.[1-9][0-9]+)?", version):
        raise DistributionError("Invalid release CalVer.")
    try:
        datetime.datetime.strptime(version[:10], "%Y.%m.%d")
        _json_bytes(context)
    except (ValueError, TypeError) as error:
        raise DistributionError("Invalid release date or context.") from error
    if context.get("transform_version", 1) != 1:
        raise DistributionError("Unsupported transformation version.")
    for key in ("source_revision", "policy_revision", "builder_revision"):
        _require_revision(root, context.get(key))
    source = context["source_revision"]
    policy = _regular_blob(root, context["policy_revision"], "docs/PROCESS.md")
    if policy != _regular_blob(root, source, "docs/PROCESS.md"):
        raise DistributionError("Source and policy content differ.")
    try:
        manifest = json.loads(_regular_blob(root, source, MANIFEST_PATH.as_posix()))
    except (ValueError, UnicodeDecodeError) as error:
        raise DistributionError("Invalid committed manifest.") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in (1, 2):
        raise DistributionError("Unsupported committed manifest.")
    bundle = {}
    # Materialize data for existing validators; never execute historical code.
    with tempfile.TemporaryDirectory(prefix="release-source-") as temporary:
        snapshot = Path(temporary)
        (snapshot / "skills").mkdir()
        (snapshot / MANIFEST_PATH).write_bytes(_json_bytes(manifest))
        raw_entries = manifest.get("skills")
        if not isinstance(raw_entries, list):
            raise DistributionError("Committed manifest must list Skills.")
        for entry in raw_entries:
            if not isinstance(entry, dict) or entry.get("name") not in SKILL_NAMES:
                raise DistributionError("Invalid committed Skill entry.")
            name = entry["name"]
            if entry.get("source_dir") != f"skills/{name}" or entry.get("files") != ["SKILL.md", "agents/openai.yaml"]:
                raise DistributionError("Release requires the exact standalone payload allowlist.")
            for relative in entry["files"]:
                path = f"skills/{name}/{relative}"
                destination = snapshot / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(_regular_blob(root, source, path))
        # Legacy validation needs Git access for its recorded policy revision.
        (snapshot / ".git").write_text(f"gitdir: {_git(root, 'rev-parse', '--absolute-git-dir').decode().strip()}\n")
        _, entries = _skill_entries(snapshot)
        for entry in entries:
            result = subprocess.run([sys.executable, str(Path(root).resolve() / VALIDATOR_PATH),
                str(snapshot / entry["source_dir"])], capture_output=True, text=True)
            if result.returncode:
                raise DistributionError(f"Official validator rejected {entry['name']}: {result.stdout}{result.stderr}")
            mapping = _source_files(entry)
            originals = {member: (snapshot / path).read_bytes() for member, path in mapping.items()}
            payloads = dict(originals)
            member = f"{entry['name']}/SKILL.md"
            original = payloads[member]
            if manifest["schema_version"] == 2:
                token = b"{{release_tag}}"
                canonical = b"https://github.com/danielbyon/development-process/blob/" + token + b"/docs/PROCESS.md"
                if original.count(canonical) != 1 or original.count(token) != 1:
                    raise DistributionError("Missing or ambiguous policy template reference.")
                payloads[member] = original.replace(canonical, canonical.replace(token, version.encode()))
            else:
                pin = manifest["policy_revision"].encode()
                url = b"https://github.com/danielbyon/development-process/blob/" + pin + b"/docs/PROCESS.md"
                label = b"`" + pin + b"`"
                if original.count(url) != 1 or original.count(label) != 1:
                    raise DistributionError("Unsupported historical policy binding.")
                payloads[member] = original.replace(url, url.replace(pin, version.encode())).replace(label, b"`" + version.encode() + b"`")
            # Validate the exact transformed bytes that will become archive members.
            # The executable remains the trusted checkout's validator, never source data.
            for payload_member, payload in payloads.items():
                (snapshot / mapping[payload_member]).write_bytes(payload)
            result = subprocess.run([sys.executable, str(Path(root).resolve() / VALIDATOR_PATH),
                str(snapshot / entry["source_dir"])], capture_output=True, text=True)
            if result.returncode:
                raise DistributionError(
                    f"Official validator rejected transformed {entry['name']}: {result.stdout}{result.stderr}"
                )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path, payload in sorted(payloads.items()):
                    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            archive_name = f"{entry['name']}.zip"
            bundle[archive_name] = buffer.getvalue()
            provenance = dict(schema_version=2, skill_name=entry["name"], release_version=version,
                              source_revision=source, policy_revision=context["policy_revision"],
                              builder_revision=context["builder_revision"], transform_version=1,
                              source_files=mapping, original_sha256={k:hashlib.sha256(v).hexdigest() for k,v in originals.items()},
                              payload_sha256={k:hashlib.sha256(v).hexdigest() for k,v in payloads.items()},
                              archive_sha256=hashlib.sha256(bundle[archive_name]).hexdigest())
            bundle[f"{entry['name']}.provenance.json"] = _json_bytes(provenance)
    names = sorted([*bundle, "release-manifest.json", "SHA256SUMS"])
    bundle["release-manifest.json"] = _json_bytes(dict(schema_version=2, context=context, assets=names,
        asset_sha256={k:hashlib.sha256(v).hexdigest() for k,v in sorted(bundle.items())}))
    bundle["SHA256SUMS"] = "".join(f"{hashlib.sha256(v).hexdigest()}  {k}\n" for k,v in sorted(bundle.items())).encode()
    return bundle


def build_release_packages(root: Path, output_dir: Path, context: dict) -> list[Path]:
    """Build eight artifacts atomically; existing output must match exactly."""
    root, output_dir = Path(root), Path(output_dir)
    bundle = _release_bundle(root, context)
    if output_dir.exists():
        return verify_release_packages(root, output_dir, context)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".release-bundle-", dir=output_dir.parent))
    try:
        for name, payload in bundle.items():
            (temporary / name).write_bytes(payload)
        os.rename(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return [output_dir / name for name in sorted(bundle)]


def verify_release_packages(root: Path, artifact_dir: Path, context: dict) -> list[Path]:
    """Verify bytes against independent committed-source reconstruction."""
    bundle = _release_bundle(Path(root), context)
    artifact_dir = Path(artifact_dir)
    try:
        if artifact_dir.is_symlink() or {p.name for p in artifact_dir.iterdir()} != set(bundle):
            raise DistributionError("Release asset set differs from expected eight assets.")
        for name, expected in bundle.items():
            path = artifact_dir / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
                raise DistributionError(f"Release asset differs from reconstructed source: {name}")
    except OSError as error:
        raise DistributionError(f"Could not read release assets: {error}") from error
    return [artifact_dir / name for name in sorted(bundle)]


def stage_release_packages(root: Path, artifact_dir: Path, staging_root: Path, context: dict, upgrade: bool = False) -> list[dict]:
    """Stage a reconstructed candidate using existing isolation and drift guards."""
    verify_release_packages(root, artifact_dir, context)
    results = []
    bundle = _release_bundle(Path(root), context)
    for name in sorted(SKILL_NAMES):
        provenance = json.loads(bundle[f"{name}.provenance.json"])
        results.append(_install_verified(Path(root).resolve(), Path(artifact_dir) / f"{name}.zip",
            staging_root, context["policy_revision"], provenance, upgrade))
    return results

def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command.startswith("release-"):
            context = _read_json(args.context, "release context")
            if args.command == "release-package":
                results = build_release_packages(args.root, args.output_dir, context)
            elif args.command == "release-verify":
                results = verify_release_packages(args.root, args.artifact_dir, context)
            else:
                results = stage_release_packages(args.root, args.artifact_dir, args.staging_root, context, args.upgrade)
            for result in results:
                print(f"PASS {args.command} {result}")
        elif args.command == "validate":
            for name in validate_distribution(args.root):
                print(f"PASS validate {name}")
        elif args.command == "package":
            for package in build_packages(args.root, args.output_dir, args.source_revision):
                print(f"PASS package {package}")
        elif args.command == "verify":
            for package in verify_packages(args.root, args.artifact_dir, args.source_revision):
                print(f"PASS verify {package}")
        elif args.command == "stage":
            result = install_archive(
                args.root,
                args.archive,
                args.staging_root,
                expected_policy_revision=args.policy_revision,
                upgrade=args.upgrade,
            )
            print(f"PASS {result['status']} {result['skill']}")
        elif args.command == "init-staging":
            marker = initialize_staging_root(args.root, args.staging_root)
            print(f"PASS initialized staging root {marker.parent}")
        elif args.command == "policy":
            print(
                resolve_task_policy(
                    args.root,
                    task_policy_revision=args.task_policy_revision,
                )
            )
    except DistributionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
