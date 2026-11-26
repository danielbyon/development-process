"""Qualify immutable Skill releases from an owner-dispatched main commit.

Commands print JSON. Publication requires prior qualification and refreshes live
prerequisites before each mutation. Unknown remote state is preserved.
"""
from __future__ import annotations
import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, date
from zoneinfo import ZoneInfo
from github_releases import GitHubAPI, APIError
from release_evidence import baseline as evidence_baseline
from release_evidence import integrations as evidence_integrations
from release_evidence import qualification as evidence_qualification
from release_evidence.common import (
    BASE, BOOTSTRAP_BASELINE, REPOSITORY, SHA, SUITES, MissingEvidenceError, ReleaseError,
    canonical, digest, git, require, revision,
)
from release_evidence.legacy import load_evidence_export, verify_frozen_release_evidence

def version_key(tag):
    match=re.fullmatch(r'(\d{4})\.(\d{2})\.(\d{2})(?:\.([2-9]|[1-9]\d+))?',tag)
    require(match is not None,'Invalid CalVer')
    y,m,d,n=match.groups()
    try: day=date(int(y),int(m),int(d))
    except ValueError as error: raise ReleaseError('Invalid calendar date') from error
    return day,int(n or 1)

def allocate_version(created_at,occupied):
    instant=datetime.fromisoformat(created_at.replace('Z','+00:00'))
    require(instant.tzinfo is not None,'Run creation must include timezone')
    day=instant.astimezone(ZoneInfo('America/Los_Angeles')).date()
    seq=1
    for tag in occupied:
        try: tagged,n=version_key(tag)
        except ReleaseError: continue
        if tagged==day: seq=max(seq,n+1)
    return day.strftime('%Y.%m.%d')+('' if seq==1 else f'.{seq}')


def check_settings(api,context,*,settings=None,run=None):
    """Check release authority, dispatch identity, and immutable-release support."""
    verify_trusted_main_context(context)
    settings=api.settings() if settings is None else settings
    repo=settings['repository']
    require(repo.get('full_name')==REPOSITORY and repo.get('default_branch')=='main',
            'Repository/default branch mismatch')
    owner=repo.get('owner',{})
    require(owner.get('login')=='danielbyon' and type(owner.get('id')) is int and
            owner['id']>0 and owner['id']==context['owner_id'],
            'Owner identity mismatch')
    require(settings.get('immutability',{}).get('enabled') is True,
            'Immutable releases disabled or unverifiable')
    source=context.get('source_revision')
    builder=context.get('builder_revision')
    require(source==builder and isinstance(source,str) and SHA.fullmatch(source),
            'Source and builder must equal the full dispatch commit SHA')
    run=api.run(context['run_id']) if run is None else run
    require(run.get('id')==context['run_id'] and
            run.get('event')=='workflow_dispatch' and run.get('head_branch')=='main',
            'Trusted main dispatch required')
    require(run.get('head_sha')==source,'Dispatch source/builder revision mismatch')
    require(run.get('actor',{}).get('id')==context['owner_id'] and
            run.get('triggering_actor',{}).get('id')==context['owner_id'],
            'Owner-only dispatch/rerun required')
    expected_attempt=context.get('validation_attempt',context['run_attempt'])
    require(run.get('run_attempt')==expected_attempt,'Partial or stale run attempt')
    require(run.get('created_at')==context['created_at'],'Original run identity mismatch')
    require(run.get('path') in (
            '.github/workflows/skill-release.yml',
            '.github/workflows/skill-release.yml@refs/heads/main'),
            'Unexpected dispatch workflow')
    require(isinstance(context.get('created_at'),str) and context['created_at'],
            'Dispatch creation time unavailable')
    try:
        created_at=datetime.fromisoformat(context['created_at'].replace('Z','+00:00'))
    except ValueError as error:
        raise ReleaseError('Dispatch creation time malformed') from error
    require(created_at.tzinfo is not None,'Dispatch creation time must include timezone')
    api.verify_main_ancestry(source)
    return settings


def verify_dispatch_environment(root,run_id,run_attempt,source):
    """Bind workflow inputs and checkout to the authenticated run identity."""
    workflow_ref=REPOSITORY+'/.github/workflows/skill-release.yml@refs/heads/main'
    expected={'GITHUB_REPOSITORY':REPOSITORY,'GITHUB_SHA':source,
        'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':str(run_id),
        'GITHUB_RUN_ATTEMPT':str(run_attempt),'GITHUB_ACTOR':'danielbyon',
        'GITHUB_TRIGGERING_ACTOR':'danielbyon','GITHUB_WORKFLOW_REF':workflow_ref}
    for name,value in expected.items():
        require(os.environ.get(name)==value,'Workflow dispatch context mismatch: '+name)
    require(git(root,'rev-parse','HEAD').decode().strip()==source,
            'Release checkout differs from the dispatch source')


def verify_trusted_main_context(context):
    """Reject legacy evidence fields from newly qualified trusted-main releases."""
    require(type(context.get('release_context_schema_version')) is int and
            context['release_context_schema_version']==1,
            'Trusted-main release context schema required')
    require(context.get('repository')==REPOSITORY,
            'Trusted-main release repository mismatch')
    source=context.get('source_revision')
    require(isinstance(source,str) and SHA.fullmatch(source) and
            source==context.get('builder_revision'),
            'Trusted-main source and builder must be the same full commit SHA')
    require(type(context.get('owner_id')) is int and context['owner_id']>0 and
            type(context.get('run_id')) is int and context['run_id']>0 and
            type(context.get('run_attempt')) is int and context['run_attempt']>0 and
            isinstance(context.get('created_at'),str) and context['created_at'],
            'Trusted-main owner and run identity required')
    attempt=context.get('validation_attempt',context['run_attempt'])
    require(type(attempt) is int and attempt>=context['run_attempt'],
            'Trusted-main validation attempt mismatch')
    legacy_fields=('evidence','evidence_snapshots','evidence_digest',
                   'authenticated_evidence','baseline_admission')
    require(not any(key in context for key in legacy_fields),
            'Legacy evidence fields cannot qualify a new trusted-main release')


# These paths verify frozen release records created before the trusted-main rule.
def verify_historical_anchor(root,api,evidence,*,source=None,builder=None,dispatch_run_id=None):
    """Verify an anchor recorded in a previously signed release."""
    if evidence.get('origin',{}).get('kind')=='prospective_baseline':
        require(source is not None and builder is not None and dispatch_run_id is not None,
                'Prospective baseline requires exact source, builder, and dispatch identities')
        return evidence_baseline.verify_baseline_admission(root,api,evidence,source,builder,dispatch_run_id)
    baseline=evidence['baseline_revision']
    if evidence.get('anchor_release'):
        anchor=verify_release(root,api,evidence['anchor_release'])
        require(anchor['source_revision']==baseline,'Trusted release anchor mismatch')
        return
    require(evidence.get('schema_version')==1,
            'Unsupported frozen legacy baseline')
    if baseline==BOOTSTRAP_BASELINE:
        return
    entry=evidence.get('baseline_admission',{})
    record=api.record(entry.get('ref'))
    require(digest(canonical(record))==entry.get('sha256'),'Baseline admission evidence mismatch')
    require(record.get('user',{}).get('id')==evidence['owner_id'],'Owner baseline admission required')
    body=record.get('body',''); marker='<!-- release-evidence\n'
    if 'normalized_report' in entry:
        normalization=evidence.get('normalization_export',{})
        require(normalization and load_evidence_export(normalization['ref'],api.record)==evidence,
                'Authenticated baseline normalization required')
        report=entry['normalized_report']
        require(all(report.get(k) and report[k] in body for k in ('revision','report','execution_id')),
                'Actual baseline qualification report missing')
    else:
        require(marker in body,'Inspectable baseline admission required')
        report=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
    require(report.get('revision')==baseline and report.get('action')=='admit-baseline' and
            report.get('report') and report.get('execution_id'),
            'Unverified baseline admission')


def _verify_historical_evidence_origin(root,api,evidence,source,builder,dispatch_run_id):
    """Resolve evidence origins stored in a previously signed release."""
    if evidence.get('origin',{}).get('kind')=='prospective_baseline':
        snapshots=evidence_baseline.verify_baseline_admission(
            root,api,evidence,source,builder,dispatch_run_id)
        return snapshots,snapshots
    return evidence_qualification.verify_evidence(evidence,api.record,root),None


def _verify_historical_candidate_coverage(root,api,evidence,source,builder,*,
                                         dispatch_run_id):
    """Check frozen legacy evidence and Git coverage for a signed release."""
    snapshots,baseline_proof=_verify_historical_evidence_origin(
        root,api,evidence,source,builder,dispatch_run_id)
    if baseline_proof is None:
        verify_historical_anchor(root,api,evidence)
        evidence_integrations.verify_live_integrations(
            api,evidence,root,ordinary_evidence=snapshots)
    coverage_proof=[]
    for target in (source,builder):
        if baseline_proof is None:
            proof=evidence_qualification.verify_coverage(
                root,evidence,target,admitted=True,ordinary_evidence=snapshots)
        else:
            proof=evidence_qualification.verify_coverage(
                root,evidence,target,baseline_admission=baseline_proof)
        require(isinstance(proof,dict),'Git coverage verification did not return a proof')
        coverage_proof.append(proof)
    return snapshots,baseline_proof,coverage_proof


class FrozenHistoricalEvidenceAuthority:
    """Provide the immutable provider snapshots embedded in a signed release."""
    def __init__(self,api=None,data=None):
        self.api=api
        self.data=data if data is not None else {'records':{},'jobs':{},'logs':{},'pages':{},'runs':{}}
    def __getattr__(self,name):
        if self.api is None: raise ReleaseError('Frozen evidence lacks '+name)
        return getattr(self.api,name)
    def _read(self,kind,key,method,*args):
        if self.api is not None: self.data[kind][key]=getattr(self.api,method)(*args)
        require(key in self.data.get(kind,{}),'Frozen authenticated evidence missing: '+key)
        return self.data[kind][key]
    def pages(self,ref): return self._read('pages',ref,'pages',ref)
    def record(self,ref): return self._read('records',ref,'record',ref)
    def ci_jobs(self,run,attempt): return self._read('jobs',str(run)+'/'+str(attempt),'ci_jobs',run,attempt)
    def job_log(self,job): return self._read('logs',str(job),'job_log',job)
    def run(self,run_id): return self._read('runs',str(run_id),'run',run_id)

def preflight(root,api,run_id,run_attempt,*,supersedes='',correction_reason=''):
    run_id=int(run_id); run_attempt=int(run_attempt)
    run=api.run(run_id); settings=api.settings(); repo=settings['repository']
    source=revision(root,run.get('head_sha'))
    require(git(root,'rev-parse','HEAD').decode().strip()==source,
            'Release checkout differs from the dispatch source')
    import skill_distribution as package
    try:
        committed_manifest = json.loads(git(
            root, 'show', f'{source}:{package.MANIFEST_PATH.as_posix()}'))
        transform_version = package.release_transform_version(committed_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError, package.DistributionError) as error:
        raise ReleaseError(f'Committed distribution manifest is invalid: {error}') from error
    verify_dispatch_environment(root,run_id,run_attempt,source)
    require(bool(supersedes)==bool(correction_reason),
            'Supersession requires correction reason')
    owner=repo.get('owner',{})
    context={'release_context_schema_version':1,'repository':REPOSITORY,
        'source_revision':source,'builder_revision':source,'owner_id':owner.get('id'),
        'run_id':run_id,'run_attempt':run_attempt,'validation_attempt':run_attempt,
        'created_at':run.get('created_at'),'transform_version':transform_version,
        'supersedes':supersedes,'correction_reason':correction_reason}
    check_settings(api,context,settings=settings,run=run)
    policy=git(root,'log','--first-parent','-1','--format=%H',source,
               '--','docs/PROCESS.md').decode().strip()
    require(bool(policy) and git(root,'show',policy+':docs/PROCESS.md')==
            git(root,'show',source+':docs/PROCESS.md'),'Policy derivation mismatch')
    original=api.original_context(run_id)
    require(original is not None or run_attempt==1,
            'Retry has no recoverable original release context; preserve and block')
    if original is not None:
        verify_trusted_main_context(original)
        for key,value in {'repository':REPOSITORY,'source_revision':source,
            'builder_revision':source,'owner_id':context['owner_id'],'run_id':run_id,
            'created_at':context['created_at'],'policy_revision':policy,
            'supersedes':supersedes,'correction_reason':correction_reason}.items():
            require(original.get(key)==value,'Original frozen identity mismatch: '+key)
        require(type(original.get('transform_version', 1)) is int and
                original.get('transform_version', 1) == transform_version,
                'Original frozen transformation identity mismatch')
        require(type(original.get('run_attempt')) is int and
                1<=original['run_attempt']<=run_attempt,
                'Original run attempt identity mismatch')
        original.pop('current_validation',None)
        original['validation_attempt']=run_attempt
        check_settings(api,original,settings=settings,run=run)
        return original
    occupied=[r['tag_name'] for r in api.releases()]+[
        r['ref'].removeprefix('refs/tags/') for r in api.tags()]
    context.update(policy_revision=policy,
        release_version=allocate_version(context['created_at'],occupied))
    return context

def require_tests(result):
    require(result.testsRun>0 and not result.failures and not result.errors and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses,'Mandatory qualification failed, skipped or empty')

_ATTEMPT_LOCAL_CONTEXT_FIELDS=frozenset((
    'qualified_artifacts','validation_attempt','current_validation'))

def frozen_release_context(context):
    """Return the context fields that define the immutable package identity."""
    return {key:value for key,value in context.items()
            if key not in _ATTEMPT_LOCAL_CONTEXT_FIELDS}

def _valid_suite_results(suites):
    return (isinstance(suites,list) and len(suites)==len(SUITES) and
        {item.get('suite') for item in suites if isinstance(item,dict)}==set(SUITES) and
        all(isinstance(item,dict) and type(item.get('tests')) is int and item['tests']>0
            for item in suites))

def require_current_validation(context,attempt):
    """Require successful suite results from this exact workflow attempt."""
    current=context.get('current_validation')
    require(isinstance(current,dict) and type(current.get('run_attempt')) is int and
            current['run_attempt']==attempt,
            'Fresh current-attempt validation required')
    qualification=context.get('qualification')
    require(isinstance(qualification,dict) and
            type(qualification.get('run_attempt')) is int and
            context['run_attempt']<=qualification['run_attempt']<=attempt and
            _valid_suite_results(qualification.get('suites')) and
            _valid_suite_results(current.get('suites')),
            'Mandatory current-attempt validation missing or failed')
    require(current['suites']==qualification['suites'],
            'Current-attempt validation differs from frozen qualification')

def independent_build(root,destination,context):
    """Run the trusted builder in a fresh interpreter with frozen inputs."""
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'context.json';path.write_bytes(canonical(context))
        result=subprocess.run([sys.executable,str(root/'scripts/skill_distribution.py'),'release-package',
            '--root',str(root),'--context',str(path),'--output-dir',str(destination)],capture_output=True,text=True)
        require(result.returncode==0,'Independent release build failed: '+result.stderr)

def qualify(root,context,artifacts):
    import skill_distribution as package
    verify_trusted_main_context(context)
    require(git(root,'rev-parse','HEAD').decode().strip()==context['builder_revision'],'Trusted builder checkout required')
    results=[]
    for pattern in SUITES:
        suite=unittest.TestLoader().discover(str(root/'tests'),pattern=pattern)
        stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        try:
            require_tests(result)
        except ReleaseError as error:
            raise ReleaseError(f'Qualification suite {pattern} failed:\n{stream.getvalue()}') from error
        results.append({'suite':pattern,'tests':result.testsRun})
    artifacts=Path(artifacts)
    require(not artifacts.exists() or not list(artifacts.iterdir()),'Artifact destination must be empty')
    attempt=context.get('validation_attempt',context['run_attempt'])
    if 'qualification' in context:
        require(isinstance(context['qualification'],dict) and
                context['qualification'].get('suites')==results,
                'Fresh qualification differs from frozen results')
    else:
        context['qualification']={'run_attempt':attempt,'suites':results}
    context['current_validation']={'run_attempt':attempt,'suites':results}
    require_current_validation(context,attempt)
    frozen=frozen_release_context(context)
    with tempfile.TemporaryDirectory() as first_root, tempfile.TemporaryDirectory() as second_root:
        first=Path(first_root)/'bundle'; second=Path(second_root)/'bundle'
        independent_build(root,Path(first),frozen)
        independent_build(root,Path(second),frozen)
        a=artifact_hashes(Path(first)); b=artifact_hashes(Path(second))
        require(a==b,'Independent builds differ')
        require(not context.get('qualified_artifacts') or context['qualified_artifacts']==a,'Recovered frozen artifact hashes changed')
        package.verify_release_packages(root,Path(first),frozen)
        with tempfile.TemporaryDirectory() as stage_parent:
            stage=Path(stage_parent)/'stage'; stage.mkdir()
            package.initialize_staging_root(root,stage)
            package.stage_release_packages(root,Path(first),stage,frozen)
        artifacts.mkdir(parents=True,exist_ok=True)
        for path in Path(first).iterdir(): shutil.copyfile(path,artifacts/path.name)
    context['qualified_artifacts']=a
    return context

def artifact_hashes(directory):
    paths=[p for p in Path(directory).iterdir() if p.name!='release-context.json']
    require(len(paths)==8 and all(p.is_file() and not p.is_symlink() for p in paths),'Exactly eight regular assets required')
    return {p.name:digest(p.read_bytes()) for p in sorted(paths)}

def verify_signing_context(root,context):
    """Bind signing to this trusted main-workflow checkout and qualification attempt."""
    attempt=context.get('validation_attempt',context['run_attempt'])
    verify_trusted_main_context(context)
    require(type(attempt) is int and attempt>=context['run_attempt'],
            'Signing attempt identity mismatch')
    require_current_validation(context,attempt)
    expected={
        'GITHUB_REPOSITORY':REPOSITORY,
        'GITHUB_SHA':context['builder_revision'],
        'GITHUB_REF':'refs/heads/main',
        'GITHUB_RUN_ID':str(context['run_id']),
        'GITHUB_RUN_ATTEMPT':str(attempt),
        'GITHUB_WORKFLOW_REF':REPOSITORY+'/.github/workflows/skill-release.yml@refs/heads/main',
    }
    require(context.get('repository')==REPOSITORY,'Signing repository mismatch')
    for key,value in expected.items():
        require(os.environ.get(key)==value,'Signing dispatch mismatch: '+key)
    require(git(root,'rev-parse','HEAD').decode().strip()==context['builder_revision'],'Signing builder checkout mismatch')

def verify_bundle(root,directory,context):
    """Exclude transport metadata and reconstruct all release assets."""
    import skill_distribution as package
    verify_trusted_main_context(context)
    require(git(root,'rev-parse','HEAD').decode().strip()==context['builder_revision'],
            'Bundle verifier checkout differs from the frozen builder')
    frozen=frozen_release_context(context)
    require(artifact_hashes(directory)==context.get('qualified_artifacts'),'Qualified artifact mismatch')
    with tempfile.TemporaryDirectory() as temporary:
        clean=Path(temporary)
        for name in artifact_hashes(directory): shutil.copyfile(Path(directory)/name,clean/name)
        package.verify_release_packages(root,clean,frozen)

def verify_remote(api,release,context,directory,published):
    require(release.get('tag_name')==context['release_version'] and release.get('name')==context['release_version'],'Release identity mismatch')
    require(release.get('prerelease') is False,'Prerelease forbidden')
    assets=release.get('assets',[]); expected=artifact_hashes(directory)
    require(len(assets)==len(expected) and {a['name'] for a in assets}==set(expected),'Remote asset set mismatch')
    for asset in assets: require(digest(api.asset(asset))==expected[asset['name']],'Remote asset bytes differ')
    tags=[t for t in api.tags() if t['ref']=='refs/tags/'+context['release_version']]
    require(len(tags)==1 and tags[0]['object']['sha']==context['source_revision'] and tags[0]['object']['type']=='commit','Tag target mismatch')
    if published:
        require(release.get('draft') is False and release.get('immutable') is True,'Publication is not immutable')
        api.verify_attestation(context['release_version'],directory)
    return release

def publish(root,api,context,directory):
    import skill_distribution as package
    attempt=context.get('validation_attempt',context['run_attempt'])
    verify_dispatch_environment(root,context['run_id'],attempt,context['source_revision'])
    check_settings(api,context)
    verify_trusted_main_context(context)
    require(git(root,'rev-parse','HEAD').decode().strip()==context['source_revision'],
            'Publication checkout differs from the frozen source')
    require_current_validation(context,attempt)
    require(artifact_hashes(directory)==context.get('qualified_artifacts'),'Qualified artifact mismatch')
    verify_bundle(root,directory,context)
    api.verify_qualification_attestation(directory,context)
    identity=digest(canonical(frozen_release_context(context)))
    body='Release context: '+identity
    releases=[r for r in api.releases() if r['tag_name']==context['release_version']]
    require(len(releases)<=1,'Ambiguous release ownership')
    if releases:
        release=releases[0]
        require(release.get('body')==body,'Unknown draft ownership')
        if not release.get('draft'): return verify_remote(api,release,context,directory,True)
    else:
        require(not any(t['ref']=='refs/tags/'+context['release_version'] for t in api.tags()),'Orphaned tag: preserve and block')
        check_settings(api,context)
        release=api.create_draft(context,body)
    expected=artifact_hashes(directory)
    assets=release.get('assets',[])
    require(len({a['name'] for a in assets})==len(assets),'Duplicate remote assets')
    for asset in assets:
        require(asset['name'] in expected and digest(api.asset(asset))==expected[asset['name']],'Conflicting draft asset')
    for name in expected:
        if name not in {a['name'] for a in assets}: api.upload(release['id'],Path(directory)/name)
    tags=[t for t in api.tags() if t['ref']=='refs/tags/'+context['release_version']]
    if not tags:
        check_settings(api,context)
        api.create_tag(context['release_version'],context['source_revision'])
    release_id=release.get('id')
    require(type(release_id) is int and release_id>0,'Release ID unavailable for final verification')
    current=api.release(release_id)
    require(isinstance(current,dict),'Final release state unavailable')
    require(type(current.get('id')) is int and current['id']==release_id,
            'Final release ID mismatch')
    require(current.get('body')==body,'Unknown draft ownership at publication')
    require(current.get('draft') is True,'Expected owned draft before publication')
    verify_remote(api,current,context,directory,False)
    check_settings(api,context)
    api.publish(release_id)
    return verify_remote(api,api.release(release_id),context,directory,True)

_VERIFYING_RELEASES=set()

def verify_release(root,api,tag):
    """Reject cyclic anchor chains while verifying each release independently."""
    identity=(str(Path(root).resolve()),tag)
    require(identity not in _VERIFYING_RELEASES,'Cyclic trusted release anchor')
    _VERIFYING_RELEASES.add(identity)
    try: return _verify_release(root,api,tag)
    finally: _VERIFYING_RELEASES.remove(identity)

def _verify_release(root,api,tag):
    import skill_distribution as package
    version_key(tag)
    matches=[r for r in api.releases() if r['tag_name']==tag]
    require(len(matches)==1,'Release unavailable or ambiguous')
    release=matches[0]
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary)
        for asset in release.get('assets',[]):
            name=asset['name']
            require(name==Path(name).name and name not in ('.','..') and not (directory/name).exists(),'Unsafe/duplicate asset name')
            (directory/name).write_bytes(api.asset(asset))
        try:
            manifest = json.loads((directory / 'release-manifest.json').read_text())
        except ValueError as error:
            raise ReleaseError('Malformed release manifest') from error
        require(isinstance(manifest, dict), 'Malformed release manifest')
        context=manifest.get('context',manifest)
        require(isinstance(context, dict), 'Malformed release manifest context')
        require(context.get('release_version')==tag and context.get('repository')==REPOSITORY,'Manifest release identity mismatch')
        try:
            package.verify_release_packages(root, directory, context)
        except package.DistributionError as error:
            raise ReleaseError(str(error)) from error
        repository=api.record(BASE)
        require(repository.get('owner',{}).get('id')==context.get('owner_id'),
                'Frozen publisher owner mismatch')
        if context.get('release_context_schema_version')==1:
            verify_trusted_main_context(context)
            suites=context.get('qualification',{}).get('suites',[])
            require({s.get('suite') for s in suites}==set(SUITES) and
                    all(type(s.get('tests')) is int and s['tests']>0 for s in suites),
                    'Release mandatory qualification absent')
            qualification=context.get('qualification',{})
            attempt=context.get('run_attempt')
            require(type(context.get('run_id')) is int and context['run_id']>0 and
                    type(attempt) is int and attempt>0 and
                    type(qualification.get('run_attempt')) is int and
                    qualification['run_attempt']>=attempt,
                    'Frozen release run identity mismatch')
            # The signed manifest preserves the original run and qualification
            # results; verification does not depend on disposable Actions logs.
            api.verify_qualification_attestation(directory,context)
        else:
            require(context.get('evidence_digest')==digest(canonical(context.get('evidence_snapshots'))),
                    'Qualification evidence digest missing/mismatched')
            # Historical signatures authenticate the frozen provider records
            # independently of mutable release notes and expired run logs.
            api.verify_qualification_attestation(directory,context)
            frozen=FrozenHistoricalEvidenceAuthority(data=context.get('authenticated_evidence',{}))
            evidence=context.get('evidence')
            if evidence.get('schema_version')==1:
                snapshots=verify_frozen_release_evidence(evidence,frozen.record)
                require(snapshots==context['evidence_snapshots'],
                        'Frozen schema v1 qualification authority unverified')
                if evidence.get('anchor_release'):
                    verify_historical_anchor(root,api,evidence)
                else:
                    verify_historical_anchor(root,frozen,evidence)
                evidence_integrations.verify_live_integrations(frozen,evidence,root)
                evidence_qualification.verify_coverage(root,evidence,context['source_revision'],admitted=True)
                evidence_qualification.verify_coverage(root,evidence,context['builder_revision'],admitted=True)
            else:
                snapshots,_,_=_verify_historical_candidate_coverage(
                    root,frozen,evidence,context['source_revision'],context['builder_revision'],
                    dispatch_run_id=context.get('run_id'))
                require(snapshots==context['evidence_snapshots'],
                        'Frozen qualification authority unverified')
            suites=context.get('qualification',{}).get('suites',[])
            require({s.get('suite') for s in suites}==set(SUITES) and
                    all(s.get('tests',0)>0 for s in suites),
                    'Release mandatory qualification absent')
        verify_remote(api,release,context,directory,True)
        payloads={}
        for sidecar in directory.glob('*.provenance.json'):
            provenance=json.loads(sidecar.read_text())
            name=provenance['skill_name']
            payloads[name]={str(Path(member).relative_to(name)):value
                            for member,value in provenance['payload_sha256'].items()}
        return {**context,'verified_payload_identities':payloads}

def _newest_release_tag(api):
    candidates = []
    for release in api.releases():
        try:
            key = version_key(release['tag_name'])
        except ReleaseError:
            continue
        if release.get('draft') is False and release.get('prerelease') is False:
            candidates.append((key, release['tag_name']))
    return max(candidates)[1] if candidates else None


def _verify_selected_release(root, api, tag=None):
    """Verify the selected release without falling back after a failure."""
    try:
        selected = _newest_release_tag(api) if tag is None else tag
        if selected is not None:
            return selected, verify_release(Path(root), api, selected)
    except (ReleaseError, APIError, OSError, ValueError, KeyError, TypeError) as error:
        raise ReleaseError(f'RELEASE_VERIFICATION_FAILED: {error}') from error
    raise ReleaseError('NO_IMMUTABLE_RELEASE')


def _resolve_pinned_release(api, tag, source_revision, policy_revision, builder_revision):
    """Authenticate executor payload identities from one immutable CalVer release."""
    import skill_distribution as package

    if re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', tag):
        published = api.release_by_tag(tag)
    else:
        published = api.request('GET', api.base + '/releases/tags/' + tag)
    require(isinstance(published, dict), 'Pinned release data unavailable')
    require(type(published.get('id')) is int and published['id'] > 0 and
            published.get('tag_name') == tag and published.get('name') == tag,
            'Pinned release CalVer mismatch')
    require(published.get('draft') is False and published.get('prerelease') is False and
            published.get('immutable') is True,
            'Pinned release is not immutably published')

    skill_names = set(package.SKILL_NAMES)
    expected_assets = {
        name
        for skill in skill_names
        for name in (f'{skill}.zip', f'{skill}.provenance.json')
    } | {'release-manifest.json', 'SHA256SUMS'}
    remote_assets = published.get('assets')
    if not isinstance(remote_assets, list):
        raise MissingEvidenceError('Pinned release asset list unavailable')
    assets_by_name = {}
    for asset in remote_assets:
        require(isinstance(asset, dict), 'Malformed pinned release asset')
        name = asset.get('name')
        require(isinstance(name, str) and name not in assets_by_name,
                'Duplicate or malformed pinned release asset')
        assets_by_name[name] = asset
    missing = expected_assets - set(assets_by_name)
    if missing:
        raise MissingEvidenceError('Pinned release asset missing: ' + ', '.join(sorted(missing)))
    require(set(assets_by_name) == expected_assets,
            'Pinned release asset names differ from the release contract')

    def asset_digest(asset, name):
        value = asset.get('digest')
        if not isinstance(value, str):
            raise MissingEvidenceError('GitHub SHA-256 asset digest unavailable: ' + name)
        match = re.fullmatch(r'sha256:([0-9a-f]{64})', value)
        if match is None:
            raise MissingEvidenceError('GitHub SHA-256 asset digest unavailable: ' + name)
        return match.group(1)

    def download(name):
        asset = assets_by_name[name]
        if type(asset.get('id')) is not int or asset['id'] <= 0:
            raise MissingEvidenceError('Pinned release asset ID unavailable: ' + name)
        content = api.asset(asset)
        if not isinstance(content, bytes):
            raise MissingEvidenceError('Pinned release asset bytes unavailable: ' + name)
        require(digest(content) == asset_digest(asset, name),
                'Pinned release asset SHA-256 mismatch: ' + name)
        return content

    try:
        manifest = json.loads(download('release-manifest.json'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError('Malformed pinned release manifest') from error
    require(isinstance(manifest, dict) and type(manifest.get('schema_version')) is int and
            manifest['schema_version'] == 2,
            'Unsupported pinned release manifest')
    manifest_assets = manifest.get('assets')
    require(isinstance(manifest_assets, list) and
            all(isinstance(name, str) for name in manifest_assets) and
            len(manifest_assets) == len(set(manifest_assets)) and
            set(manifest_assets) == expected_assets,
            'Pinned release manifest asset list mismatch')
    asset_hashes = manifest.get('asset_sha256')
    hash_names = expected_assets - {'release-manifest.json', 'SHA256SUMS'}
    require(isinstance(asset_hashes, dict) and set(asset_hashes) == hash_names and
            all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for value in asset_hashes.values()),
            'Pinned release manifest asset hashes unavailable')

    context = manifest.get('context')
    require(isinstance(context, dict), 'Pinned release manifest context unavailable')
    require(context.get('repository') == REPOSITORY and
            context.get('release_version') == tag and
            context.get('source_revision') == source_revision and
            context.get('policy_revision') == policy_revision and
            context.get('builder_revision') == builder_revision,
            'Pinned release manifest identity mismatch')
    require(all(isinstance(context.get(key), str) and SHA.fullmatch(context[key])
                for key in ('source_revision', 'policy_revision', 'builder_revision')) and
            not any(key in context for key in _ATTEMPT_LOCAL_CONTEXT_FIELDS) and
            source_revision == builder_revision and
            type(context.get('release_context_schema_version')) is int and
            context['release_context_schema_version'] == 1 and
            type(context.get('owner_id')) is int and context['owner_id'] > 0 and
            type(context.get('transform_version', 1)) is int and
            context.get('transform_version', 1) in (1, 2),
            'Pinned release manifest context is incomplete or unsupported')
    expected_body = 'Release context: ' + digest(canonical(frozen_release_context(context)))
    require(published.get('body') == expected_body,
            'Pinned release body does not bind its frozen context')

    tags = [item for item in api.tags()
            if isinstance(item, dict) and item.get('ref') == 'refs/tags/' + tag]
    require(len(tags) == 1 and isinstance(tags[0].get('object'), dict) and
            tags[0]['object'].get('sha') == source_revision and
            tags[0]['object'].get('type') == 'commit',
            'Pinned release tag target mismatch')

    skill = 'delegation-executor'
    sidecar_name = f'{skill}.provenance.json'
    sidecar_bytes = download(sidecar_name)
    try:
        sidecar = json.loads(sidecar_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError('Malformed pinned executor provenance sidecar') from error
    expected_sources = {
        f'{skill}/SKILL.md': f'skills/{skill}/SKILL.md',
        f'{skill}/agents/openai.yaml': f'skills/{skill}/agents/openai.yaml',
    }
    hashes = sidecar.get('payload_sha256') if isinstance(sidecar, dict) else None
    if (not isinstance(sidecar, dict) or not isinstance(hashes, dict) or
            set(expected_sources) - set(hashes)):
        raise MissingEvidenceError('Pinned executor payload hashes unavailable')
    zip_name = f'{skill}.zip'
    zip_digest = asset_digest(assets_by_name[zip_name], zip_name)
    require(isinstance(sidecar, dict) and
            type(sidecar.get('schema_version')) is int and sidecar['schema_version'] == 2 and
            sidecar.get('skill_name') == skill and
            sidecar.get('release_version') == tag and
            sidecar.get('source_revision') == source_revision and
            sidecar.get('policy_revision') == policy_revision and
            sidecar.get('builder_revision') == builder_revision and
            type(sidecar.get('transform_version')) is int and
            sidecar.get('transform_version') == context.get('transform_version', 1) and
            sidecar.get('source_files') == expected_sources and
            isinstance(hashes, dict) and set(hashes) == set(expected_sources) and
            all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for value in hashes.values()) and
            sidecar.get('archive_sha256') == asset_hashes.get(zip_name) == zip_digest and
            asset_hashes.get(sidecar_name) == digest(sidecar_bytes),
            'Pinned executor provenance identity or manifest binding mismatch')
    return {
        **context,
        'verified_payload_identities': {
            skill: {
                member.removeprefix(skill + '/'): value
                for member, value in hashes.items()
            }
        },
    }


def resolve_task(api, existing_pin=None, compatibility=None, *, task_pin=None,
                 source_revision=None, policy_revision=None, builder_revision=None,
                 skill=None, installed_path=None):
    """Pass through old pins or verify an explicitly selected executor release."""
    native_options = (task_pin, source_revision, policy_revision, builder_revision,
                      skill, installed_path, compatibility)
    if existing_pin is not None:
        require(not any(value is not None for value in native_options),
                'EXISTING_PIN_INCOMPATIBLE_OPTIONS: recorded pins cannot request runtime verification')
        require(isinstance(existing_pin, str) and
                (bool(SHA.fullmatch(existing_pin)) or bool(version_key(existing_pin))),
                'Invalid recorded task pin')
        return {'task_pin': existing_pin}
    if task_pin is None:
        if any(value is not None for value in native_options[1:]):
            raise ReleaseError('NATIVE_VERIFICATION_ARGUMENTS_REQUIRED: pass --task-pin and the recorded identity')
        raise ReleaseError(
            'EXPLICIT_TASK_PIN_REQUIRED: ordinary task admission uses the activated Skill policy; '
            'native delegation verification requires an explicit --task-pin.'
        )
    if not isinstance(task_pin, str):
        raise ReleaseError('INVALID_TASK_PIN: expected a full SHA or CalVer')
    is_sha = bool(SHA.fullmatch(task_pin))
    if not is_sha:
        try:
            version_key(task_pin)
        except (ReleaseError, TypeError) as error:
            raise ReleaseError('INVALID_CALVER_TASK_PIN: expected a valid YYYY.MM.DD CalVer') from error
    revisions = (source_revision, policy_revision, builder_revision)
    if any(value is not None and
           (not isinstance(value, str) or not SHA.fullmatch(value))
           for value in revisions):
        raise ReleaseError('INVALID_RECORDED_IDENTITY: revisions must be full commit SHA values')
    if any(value is None for value in revisions):
        raise ReleaseError(
            'NATIVE_VERIFICATION_ARGUMENTS_REQUIRED: pass the recorded source, policy, and builder revisions'
        )
    if skill != 'delegation-executor':
        raise ReleaseError('NATIVE_VERIFICATION_SKILL_UNSUPPORTED: use --skill delegation-executor')
    if installed_path is None:
        raise ReleaseError('NATIVE_VERIFICATION_ARGUMENTS_REQUIRED: pass --installed-path')

    directory = Path(installed_path)
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseError('LOCAL_INSTALLATION_UNAVAILABLE: installed Skill directory unavailable or unsafe')
    if isinstance(compatibility, Path):
        try:
            compatibility = json.loads(compatibility.read_text())
        except (OSError, ValueError) as error:
            raise ReleaseError('INVALID_COMPATIBILITY_EVIDENCE: could not read compatibility record reference') from error
    if compatibility is not None:
        require(isinstance(compatibility, dict) and
                isinstance(compatibility.get('ref'), str) and compatibility['ref'] and
                isinstance(compatibility.get('sha256'), str) and
                re.fullmatch(r'[0-9a-f]{64}', compatibility['sha256']),
                'INVALID_COMPATIBILITY_EVIDENCE: expected a record reference and SHA-256 digest')

    if is_sha:
        raise ReleaseError(
            'LOCAL_INSTALLATION_UNAVAILABLE: historical SHA pin has no authenticated task-bound '
            'payload evidence; use manual execution.'
        )

    try:
        context = _resolve_pinned_release(
            api, task_pin, source_revision, policy_revision, builder_revision
        )
    except (APIError, MissingEvidenceError) as error:
        raise ReleaseError(f'LOCAL_INSTALLATION_UNAVAILABLE: {error}') from error
    except (ReleaseError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ReleaseError(f'LOCAL_INSTALLATION_MISMATCH: {error}') from error

    expected = context['verified_payload_identities']['delegation-executor']
    try:
        _verify_local_installation(
            api, context, 'delegation-executor', expected, directory, compatibility
        )
    except MissingEvidenceError as error:
        raise ReleaseError(f'LOCAL_INSTALLATION_UNAVAILABLE: {error}') from error
    except (ReleaseError, APIError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ReleaseError(f'LOCAL_INSTALLATION_MISMATCH: {error}') from error
    return {
        'task_pin': task_pin,
        'provenance': context,
        'local_installation_verified': True,
    }


def _verify_local_installation(api, context, skill, expected, installed_path, compatibility):
    """Inspect the files loaded by Codex and authenticate any compatibility record."""
    if installed_path is None:
        raise MissingEvidenceError('Pass --installed-path for the installed Codex delegation-executor.')
    directory = Path(installed_path)
    require(not directory.is_symlink(), 'Installed Skill symlink forbidden')
    if not directory.is_dir():
        raise MissingEvidenceError(f'Installed Skill directory unavailable: {directory}')
    if isinstance(compatibility, Path):
        compatibility = json.loads(compatibility.read_text())
    inspected={}
    for member in expected:
        relative=Path(member)
        require(not relative.is_absolute() and '..' not in relative.parts,'Unsafe installed member')
        path=directory/relative
        require(all(not (directory/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)),
                'Installed Skill symlink forbidden')
        if not path.is_file():
            raise MissingEvidenceError('Installed Skill file missing: ' + member)
        inspected[member]=digest(path.read_bytes())
    files={path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file() or path.is_symlink()}
    marker_name='.skill-distribution.json'
    if marker_name in files:
        marker_path=directory/marker_name
        require(marker_path.is_file() and not marker_path.is_symlink(),'Unsafe installed metadata')
        try: marker=json.loads(marker_path.read_text())
        except (ValueError,OSError) as error: raise ReleaseError('Malformed installed metadata') from error
        require(isinstance(marker,dict) and set(marker)=={'schema_version','skill_name','policy_revision',
                'source_revision','archive_sha256','payload_sha256'},'Invalid installed metadata fields')
        require(type(marker['schema_version']) is int and marker['schema_version']==1 and
                marker['skill_name']==skill,'Installed metadata Skill/schema mismatch')
        require(all(isinstance(marker[key],str) and SHA.fullmatch(marker[key])
                    for key in ('source_revision','policy_revision')) and
                isinstance(marker['archive_sha256'],str) and
                re.fullmatch(r'[0-9a-f]{64}',marker['archive_sha256']),
                'Invalid installed metadata provenance')
        require(marker['payload_sha256']==inspected,'Installed metadata does not match inspected bytes')
        files.remove(marker_name)
    require(files==set(expected),'Unexpected installed Skill files')
    installed_payload=digest(canonical(inspected))
    if inspected!=expected:
        require(isinstance(compatibility,dict),'Installed Skill compatibility unverified')
        record=api.record(compatibility.get('ref'))
        require(digest(canonical(record))==compatibility.get('sha256'),'Compatibility record drift')
        user = record.get('user') if isinstance(record, dict) else None
        require(isinstance(user, dict) and user.get('id') == context.get('owner_id'),
                'Compatibility author unverified')
        marker='<!-- release-evidence\n'; body=record.get('body','')
        require(isinstance(body, str) and marker in body,'Inspectable compatibility report required')
        report=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
        require(isinstance(report, dict), 'Malformed compatibility report')
        require(report.get('gate')=='compatibility' and report.get('skill')==skill and report.get('revision')==context['source_revision'] and report.get('policy_revision')==context['policy_revision'],'Compatibility target mismatch')
        require(report.get('installed_payload')==installed_payload and SHA.fullmatch(report.get('installed_source','')) and report.get('differences') and report.get('validation') and report.get('execution_id') and report.get('verdict')=='pass','Incomplete compatibility inspection')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('preflight','qualify','verify-bundle','publish','verify-release','resolve-task'):
        p=sub.add_parser(command)
        p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
        if command=='preflight':
            p.add_argument('--supersedes',default=''); p.add_argument('--correction-reason',default='')
        if command in ('preflight','qualify','verify-bundle','publish'):
            p.add_argument('--context',type=Path,required=True)
        if command in ('preflight','publish'):
            p.add_argument('--run-id',default=os.environ.get('GITHUB_RUN_ID'))
            p.add_argument('--run-attempt',default=os.environ.get('GITHUB_RUN_ATTEMPT'))
        if command=='verify-bundle': p.add_argument('--for-attestation',action='store_true')
        if command=='qualify': p.add_argument('--output-dir',type=Path,required=True)
        if command in ('verify-bundle','publish'): p.add_argument('--artifact-dir',type=Path,required=True)
        if command=='verify-release':
            p.add_argument('--tag', help='Verify this release tag. Defaults to the newest eligible release.')
        if command=='resolve-task':
            p.add_argument('--existing-pin', help='Pass through a recorded task pin without runtime verification.')
            p.add_argument('--task-pin', help='Explicit CalVer release for native executor verification.')
            p.add_argument('--source-revision', help='Recorded full source commit SHA.')
            p.add_argument('--policy-revision', help='Recorded full policy commit SHA.')
            p.add_argument('--builder-revision', help='Recorded full builder commit SHA.')
            p.add_argument('--skill', help='Skill to inspect; native verification supports delegation-executor.')
            p.add_argument('--installed-path', type=Path, help='Installed delegation-executor directory.')
            p.add_argument('--compatibility', type=Path, help='Path to JSON containing an authenticated record reference and SHA-256.')
    args=parser.parse_args(argv)
    try:
        api=GitHubAPI()
        if args.command=='preflight':
            require(args.run_id and args.run_attempt,'GitHub run identity unavailable')
            result=preflight(args.root,api,args.run_id,args.run_attempt,
                supersedes=args.supersedes,correction_reason=args.correction_reason)
            args.context.write_bytes(canonical(result)+b'\n')
        elif args.command in ('qualify','verify-bundle','publish'):
            context=json.loads(args.context.read_text())
            if args.command=='qualify':
                result=qualify(args.root,context,args.output_dir)
                args.context.write_bytes(canonical(result)+b'\n')
                (args.output_dir/'release-context.json').write_bytes(canonical(result)+b'\n')
            elif args.command=='verify-bundle':
                if args.for_attestation: verify_signing_context(args.root,context)
                import skill_distribution as package
                require(artifact_hashes(args.artifact_dir)==context.get('qualified_artifacts'),'Artifact transport mismatch')
                verify_bundle(args.root,args.artifact_dir,context)
                result={'verified':True}
            else:
                require(int(args.run_id)==context['run_id'] and int(args.run_attempt)==context.get('validation_attempt',context['run_attempt']),'Run recovery identity mismatch')
                result=publish(args.root,api,context,args.artifact_dir)
        elif args.command=='verify-release':
            _, result = _verify_selected_release(args.root, api, args.tag)
        else:
            result = resolve_task(
                api,
                existing_pin=args.existing_pin,
                task_pin=args.task_pin,
                source_revision=args.source_revision,
                policy_revision=args.policy_revision,
                builder_revision=args.builder_revision,
                compatibility=args.compatibility,
                skill=args.skill,
                installed_path=args.installed_path,
            )
        print(json.dumps(result,sort_keys=True)); return 0
    except (ReleaseError,APIError,OSError,ValueError,KeyError,TypeError) as error:
        print(f'ERROR: {error}',file=sys.stderr); return 1


if __name__=='__main__': sys.exit(main())
