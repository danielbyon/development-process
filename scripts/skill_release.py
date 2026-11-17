"""Qualify immutable Skill releases using frozen source and inspectable evidence.

Commands print JSON. Publication requires prior qualification and refreshes live
prerequisites before each mutation. Unknown remote state is preserved.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import yaml
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from github_releases import GitHubAPI, APIError
from release_evidence import audit as evidence_audit
from release_evidence import baseline as evidence_baseline
from release_evidence import discovery as evidence_discovery
from release_evidence import integrations as evidence_integrations
from release_evidence import qualification as evidence_qualification
from release_evidence import records as evidence_records
from release_evidence.common import (
    BASE, BOOTSTRAP_BASELINE, REPOSITORY, SHA, SUITES, ReleaseError,
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


def select_anchor(root,api,source,builder):
    """Choose nearest verified common-ancestor release by history, not CalVer."""
    applicable=[]
    candidates=[]
    for item in api.releases():
        if item.get('draft') is not False or item.get('prerelease') is not False: continue
        try: key=version_key(item['tag_name'])
        except ReleaseError: continue
        candidates.append((key,item['tag_name']))
    for _,tag in sorted(candidates,reverse=True):
        anchor=verify_release(root,api,tag)
        baseline=anchor['source_revision']
        try:
            git(root,'merge-base','--is-ancestor',baseline,source)
            git(root,'merge-base','--is-ancestor',baseline,builder)
        except ReleaseError: continue
        distance=len(git(root,'rev-list','--first-parent',baseline+'..'+source).split())
        applicable.append((distance,tag,baseline))
    if not applicable: return None
    _,tag,baseline=min(applicable)
    return baseline,tag


def check_settings(api,context):
    settings=api.settings(); repo=settings['repository']
    require(repo.get('full_name')==REPOSITORY and repo.get('default_branch')=='main','Repository/default branch mismatch')
    owner=repo.get('owner',{})
    require(owner.get('login')=='danielbyon' and owner.get('id')==context['owner_id'],'Owner identity mismatch')
    require(settings['immutability'].get('enabled') is True,'Immutable releases disabled or unverifiable')
    rules=settings['rules']; kinds={r.get('type') for r in rules}
    require({'pull_request','required_status_checks','non_fast_forward','deletion'}<=kinds,'Main protections missing')
    require(settings.get('rulesets') and all(r.get('enforcement')=='active' and not r.get('bypass_actors') for r in settings['rulesets']),'Main ruleset bypass or unverifiable enforcement')
    collaborators=settings.get('collaborators')
    require(isinstance(collaborators,list) and len(collaborators)==1 and collaborators[0].get('id')==context['owner_id'] and collaborators[0].get('permissions',{}).get('admin') is True,'Publishing collaborator boundary changed')
    checks=[c.get('context') for r in rules if r.get('type')=='required_status_checks' for c in r.get('parameters',{}).get('required_status_checks',[])]
    require('Validate committed PR integration diff' in checks,'Required integration check missing')
    require(any(c.get('context')=='Validate committed PR integration diff' and c.get('integration_id')==15368 for r in rules if r.get('type')=='required_status_checks' for c in r.get('parameters',{}).get('required_status_checks',[])),'Required check must be bound to GitHub Actions app')
    run=api.run(context['run_id'])
    require(run.get('event')=='workflow_dispatch' and run.get('head_branch')=='main','Trusted main dispatch required')
    require(run.get('head_sha')==context['builder_revision'],'Builder revision mismatch')
    require(run.get('actor',{}).get('id')==context['owner_id'] and run.get('triggering_actor',{}).get('id')==context['owner_id'],'Owner-only dispatch/rerun required')
    require(run.get('run_attempt')==context.get('validation_attempt',context['run_attempt']),'Partial or stale run attempt')
    require(run.get('created_at')==context['created_at'],'Original run identity mismatch')
    require(run.get('path','').split('@')[0]=='.github/workflows/skill-release.yml','Unexpected dispatch workflow')
    return settings


def admit_anchor(root,api,evidence,*,source=None,builder=None,dispatch_run_id=None):
    """Verify a prospective baseline or reuse an immutable release anchor."""
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
            'New evidence cannot use the legacy bootstrap baseline')
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


def _verify_evidence_origin(root,api,evidence,source,builder,dispatch_run_id):
    """Resolve ordinary receipts or the independently admitted baseline proof."""
    if evidence.get('origin',{}).get('kind')=='prospective_baseline':
        snapshots=evidence_baseline.verify_baseline_admission(
            root,api,evidence,source,builder,dispatch_run_id)
        return snapshots,snapshots
    return evidence_qualification.verify_evidence(evidence,api.record,root),None


def _qualify_candidate_evidence(root,api,evidence,source,builder,*,
                                dispatch_run_id):
    """Apply origin-specific trust checks and cover both release revisions."""
    snapshots,baseline_proof=_verify_evidence_origin(
        root,api,evidence,source,builder,dispatch_run_id)
    if baseline_proof is None:
        admit_anchor(root,api,evidence)
        evidence_integrations.verify_live_integrations(api,evidence,root)
    coverage_proof=[]
    for target in (source,builder):
        if baseline_proof is None:
            proof=evidence_qualification.verify_coverage(
                root,evidence,target,admitted=True)
        else:
            proof=evidence_qualification.verify_coverage(
                root,evidence,target,baseline_admission=baseline_proof)
        require(isinstance(proof,dict),'Git coverage verification did not return a proof')
        coverage_proof.append(proof)
    return snapshots,baseline_proof,coverage_proof


class EvidenceAuthority:
    """Freeze authenticated API reads for later signed, offline verification."""
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

def preflight(root,api,source,evidence,run_id,run_attempt):
    source=revision(root,source); builder=revision(root,git(root,'rev-parse','HEAD').decode().strip())
    authority=EvidenceAuthority(api); repo=authority.record(BASE); run=authority.run(run_id)
    context={'repository':REPOSITORY,'source_revision':source,'builder_revision':builder,'owner_id':repo['owner']['id'],
             'run_id':int(run_id),'run_attempt':int(run_attempt),'created_at':run['created_at'],'transform_version':1}
    check_settings(api,context)
    git(root,'merge-base','--is-ancestor',source,builder)
    workflows_differ=git(root,'ls-tree','-r',source,'--','.github/workflows')!=git(root,'ls-tree','-r',builder,'--','.github/workflows')
    context['requires_workflows_write']=workflows_differ
    # Preflight cannot provision credentials or infer owner authorization.
    if workflows_differ:
        require(os.environ.get('RELEASE_WORKFLOW_WRITE_AUTHORIZED')=='true','Separate owner authorization for Workflows write required')
    snapshots,_,_=_qualify_candidate_evidence(
        root,authority,evidence,source,builder,dispatch_run_id=run_id)
    policy=git(root,'log','--first-parent','-1','--format=%H',source,'--','docs/PROCESS.md').decode().strip()
    require(git(root,'show',policy+':docs/PROCESS.md')==git(root,'show',source+':docs/PROCESS.md'),'Policy derivation mismatch')
    original=api.original_context(run_id)
    if original is not None:
        require(original.get('run_id')==int(run_id) and original.get('source_revision')==source and original.get('builder_revision')==builder,'Original frozen identity mismatch')
        require(original.get('evidence_digest')==digest(canonical(snapshots)),'Original evidence changed')
        original['validation_attempt']=int(run_attempt)
        check_settings(api,original)
        return original
    occupied=[r['tag_name'] for r in api.releases()]+[r['ref'].removeprefix('refs/tags/') for r in api.tags()]
    context.update(policy_revision=policy,release_version=allocate_version(context['created_at'],occupied),
                   evidence=evidence,evidence_snapshots=snapshots,evidence_digest=digest(canonical(snapshots)),
        authenticated_evidence=authority.data)
    return context

def require_tests(result):
    require(result.testsRun>0 and not result.failures and not result.errors and not result.skipped and not result.unexpectedSuccesses,'Mandatory qualification failed, skipped or empty')

def independent_build(root,destination,context):
    """Run the trusted builder in a fresh interpreter with frozen inputs."""
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'context.json';path.write_bytes(canonical(context))
        result=subprocess.run([sys.executable,str(root/'scripts/skill_distribution.py'),'release-package',
            '--root',str(root),'--context',str(path),'--output-dir',str(destination)],capture_output=True,text=True)
        require(result.returncode==0,'Independent release build failed: '+result.stderr)

def qualify(root,context,artifacts):
    import skill_distribution as package
    require(git(root,'rev-parse','HEAD').decode().strip()==context['builder_revision'],'Trusted builder checkout required')
    results=[]
    for pattern in SUITES:
        suite=unittest.TestLoader().discover(str(root/'tests'),pattern=pattern)
        stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        require_tests(result); results.append({'suite':pattern,'tests':result.testsRun})
    artifacts=Path(artifacts)
    require(not artifacts.exists() or not list(artifacts.iterdir()),'Artifact destination must be empty')
    if 'qualification' in context:
        require(context['qualification']['suites']==results,'Fresh qualification differs from frozen results')
    else:
        context['qualification']={'run_attempt':context['run_attempt'],'suites':results}
    frozen={k:v for k,v in context.items() if k not in ('qualified_artifacts','validation_attempt')}
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
    require(type(attempt) is int and attempt>=context['qualification']['run_attempt'],'Signing validation attempt predates qualification')
    expected={
        'GITHUB_REPOSITORY':REPOSITORY,
        'GITHUB_SHA':context['builder_revision'],
        'GITHUB_REF':'refs/heads/main',
        'GITHUB_RUN_ID':str(context['run_id']),
        'GITHUB_RUN_ATTEMPT':str(attempt),
        'GITHUB_WORKFLOW_REF':REPOSITORY+'/.github/workflows/skill-release.yml@refs/heads/main',
    }
    require(context.get('repository')==REPOSITORY,'Signing repository mismatch')
    require(context['run_attempt']==context['qualification']['run_attempt'],'Signing requires fresh qualification')
    for key,value in expected.items():
        require(os.environ.get(key)==value,'Signing dispatch mismatch: '+key)
    require(git(root,'rev-parse','HEAD').decode().strip()==context['builder_revision'],'Signing builder checkout mismatch')

def verify_bundle(root,directory,context):
    """Exclude transport metadata and reconstruct all release assets."""
    import skill_distribution as package
    frozen={k:v for k,v in context.items() if k not in ('qualified_artifacts','validation_attempt')}
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
    check_settings(api,context)
    evidence=context['evidence']
    snapshots,baseline_proof,coverage_proof=_qualify_candidate_evidence(
        root,api,evidence,context['source_revision'],context['builder_revision'],
        dispatch_run_id=context.get('run_id'))
    require(snapshots==context['evidence_snapshots'],'Evidence drift')
    qualification=context.get('qualification',{})
    require(qualification.get('run_attempt')==context['run_attempt'],'Fresh qualification required')
    require({x['suite'] for x in qualification.get('suites',[])}==set(SUITES) and all(x['tests']>0 for x in qualification['suites']),'Mandatory suites missing')
    require(artifact_hashes(directory)==context.get('qualified_artifacts'),'Qualified artifact mismatch')
    verify_bundle(root,directory,context)
    if context.get('requires_workflows_write'):
        require(os.environ.get('RELEASE_WORKFLOW_WRITE_AUTHORIZED')=='true' and os.environ.get('RELEASE_WORKFLOW_WRITE_TOKEN'),'Separately authorized Workflows-write capability unavailable')
        api.authorize_historical_publication()
    api.verify_qualification_attestation(directory,context)
    identity=digest(canonical({k:v for k,v in context.items() if k not in ('qualified_artifacts','validation_attempt')}))
    body='Release context: '+identity
    releases=[r for r in api.releases() if r['tag_name']==context['release_version']]
    require(len(releases)<=1,'Ambiguous release ownership')
    if releases:
        release=releases[0]
        require(release.get('body')==body,'Unknown draft ownership')
        if not release.get('draft'): return verify_remote(api,release,context,directory,True)
    else:
        require(not any(t['ref']=='refs/tags/'+context['release_version'] for t in api.tags()),'Orphaned tag: preserve and block')
        release=api.create_draft(context,body)
    expected=artifact_hashes(directory)
    assets=release.get('assets',[])
    require(len({a['name'] for a in assets})==len(assets),'Duplicate remote assets')
    for asset in assets:
        require(asset['name'] in expected and digest(api.asset(asset))==expected[asset['name']],'Conflicting draft asset')
    for name in expected:
        if name not in {a['name'] for a in assets}: api.upload(release['id'],Path(directory)/name)
    tags=[t for t in api.tags() if t['ref']=='refs/tags/'+context['release_version']]
    if not tags: api.create_tag(context['release_version'],context['source_revision'])
    release=api.release(release['id']); verify_remote(api,release,context,directory,False)
    check_settings(api,context)
    final_snapshots,final_baseline_proof,final_coverage_proof=_qualify_candidate_evidence(
        root,api,evidence,context['source_revision'],context['builder_revision'],
        dispatch_run_id=context.get('run_id'))
    require(final_snapshots==snapshots and final_baseline_proof==baseline_proof,
            'Evidence drift before publication')
    require(final_coverage_proof==coverage_proof,
            'Coverage changed before publication')
    api.publish(release['id'])
    return verify_remote(api,api.release(release['id']),context,directory,True)

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
        manifest=json.loads((directory/'release-manifest.json').read_text())
        context=manifest.get('context',manifest)
        require(context.get('release_version')==tag and context.get('repository')==REPOSITORY,'Manifest release identity mismatch')
        package.verify_release_packages(root,directory,context)
        require(context.get('evidence_digest')==digest(canonical(context.get('evidence_snapshots'))),'Qualification evidence digest missing/mismatched')
        # Signature verification authenticates the frozen API evidence and test
        # results independently of mutable release notes or disposable run logs.
        api.verify_qualification_attestation(directory,context)
        frozen=EvidenceAuthority(data=context.get('authenticated_evidence',{}))
        repository=api.record(BASE)
        require(repository.get('owner',{}).get('id')==context.get('owner_id'),
                'Frozen publisher owner mismatch')
        evidence=context.get('evidence')
        if evidence.get('schema_version')==1:
            snapshots=verify_frozen_release_evidence(evidence,frozen.record)
            require(snapshots==context['evidence_snapshots'],
                    'Frozen schema v1 qualification authority unverified')
            if evidence.get('anchor_release'):
                admit_anchor(root,api,evidence)
            else:
                admit_anchor(root,frozen,evidence)
            evidence_integrations.verify_live_integrations(frozen,evidence,root)
            evidence_qualification.verify_coverage(root,evidence,context['source_revision'],admitted=True)
            evidence_qualification.verify_coverage(root,evidence,context['builder_revision'],admitted=True)
        else:
            snapshots,_,_=_qualify_candidate_evidence(
                root,frozen,evidence,context['source_revision'],context['builder_revision'],
                dispatch_run_id=context.get('run_id'))
            require(snapshots==context['evidence_snapshots'],
                    'Frozen qualification authority unverified')
        suites=context.get('qualification',{}).get('suites',[])
        require({s.get('suite') for s in suites}==set(SUITES) and all(s.get('tests',0)>0 for s in suites),
                'Release mandatory qualification absent')
        verify_remote(api,release,context,directory,True)
        payloads={}
        for sidecar in directory.glob('*.provenance.json'):
            provenance=json.loads(sidecar.read_text())
            name=provenance['skill_name']
            payloads[name]={str(Path(member).relative_to(name)):value
                            for member,value in provenance['payload_sha256'].items()}
        return {**context,'verified_payload_identities':payloads}

def resolve_task(api,existing_pin=None,installed_payload=None,root=None,compatibility=None,*,skill=None,installed_path=None):
    if existing_pin is not None:
        require(bool(SHA.fullmatch(existing_pin)) or bool(version_key(existing_pin)),'Invalid recorded task pin')
        return {'task_pin':existing_pin}
    candidates=[]
    for release in api.releases():
        try: key=version_key(release['tag_name'])
        except ReleaseError: continue
        if release.get('draft') is False and release.get('prerelease') is False: candidates.append((key,release['tag_name']))
    require(candidates,'NO_IMMUTABLE_RELEASE')
    tag=max(candidates)[1]; context=verify_release(Path(root),api,tag)
    require(installed_payload is None,'Caller-supplied payload claims are not installation evidence')
    expected=context.get('verified_payload_identities',{}).get(skill)
    require(isinstance(expected,dict) and expected and installed_path is not None,
            'Requested Skill and installed path required')
    directory=Path(installed_path)
    require(directory.is_dir() and not directory.is_symlink(),'Installed Skill directory unavailable')
    inspected={}
    for member in expected:
        relative=Path(member)
        require(not relative.is_absolute() and '..' not in relative.parts,'Unsafe installed member')
        path=directory/relative
        require(all(not (directory/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)),
                'Installed Skill symlink forbidden')
        require(path.is_file(),'Installed Skill file missing: '+member)
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
        require(record.get('user',{}).get('id')==context.get('owner_id'),'Compatibility author unverified')
        marker='<!-- release-evidence\n'; body=record.get('body','')
        require(marker in body,'Inspectable compatibility report required')
        report=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
        require(report.get('gate')=='compatibility' and report.get('skill')==skill and report.get('revision')==context['source_revision'] and report.get('policy_revision')==context['policy_revision'],'Compatibility target mismatch')
        require(report.get('installed_payload')==installed_payload and SHA.fullmatch(report.get('installed_source','')) and report.get('differences') and report.get('validation') and report.get('execution_id') and report.get('verdict')=='pass','Incomplete compatibility inspection')
    return {'task_pin':tag,'provenance':context}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('preflight','qualify','verify-bundle','publish','verify-release','resolve-task'):
        p=sub.add_parser(command)
        p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
        if command=='preflight':
            p.add_argument('--source-revision','--source',dest='source',required=True)
            p.add_argument('--builder-revision',required=True)
            p.add_argument('--evidence',type=Path,default=os.environ.get('RELEASE_EVIDENCE_FILE'))
            p.add_argument('--evidence-reference',default=os.environ.get('RELEASE_EVIDENCE_REFERENCE'))
            p.add_argument('--supersedes',default=''); p.add_argument('--correction-reason',default='')
        if command in ('preflight','qualify','verify-bundle','publish'):
            p.add_argument('--context',type=Path,required=True)
        if command in ('preflight','publish'):
            p.add_argument('--run-id',default=os.environ.get('GITHUB_RUN_ID'))
            p.add_argument('--run-attempt',default=os.environ.get('GITHUB_RUN_ATTEMPT'))
        if command=='verify-bundle': p.add_argument('--for-attestation',action='store_true')
        if command=='qualify': p.add_argument('--output-dir',type=Path,required=True)
        if command in ('verify-bundle','publish'): p.add_argument('--artifact-dir',type=Path,required=True)
        if command=='verify-release': p.add_argument('--tag',required=True)
        if command=='resolve-task':
            p.add_argument('--existing-pin'); p.add_argument('--skill'); p.add_argument('--installed-path',type=Path); p.add_argument('--compatibility',type=Path)
    audit_parser=sub.add_parser('audit')
    audit_parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    audit_parser.add_argument('--pr',type=int,required=True)
    audit_parser.add_argument('--token-env',required=True,
                              help='Name of the environment variable containing the read-only GitHub token')
    capture_parser=sub.add_parser('capture-execution')
    capture_parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    capture_parser.add_argument('--gate',choices=('author_execution','independent_review',
        'chatgpt_inspection','baseline_review'),required=True)
    capture_parser.add_argument('--system',choices=('local_cubic','separate_codex','chatgpt'),required=True)
    capture_parser.add_argument('--reviewed-range',type=Path,required=True)
    capture_parser.add_argument('--report',type=Path,required=True)
    capture_parser.add_argument('--transcript-file',type=Path)
    capture_parser.add_argument('--output',type=Path,required=True)
    capture_parser.add_argument('execution_command',nargs=argparse.REMAINDER)
    owner_parser=sub.add_parser('owner-receipt')
    owner_parser.add_argument('--gate',choices=('owner_authorization','baseline_admission'),required=True)
    owner_parser.add_argument('--revision',required=True)
    owner_parser.add_argument('--output',type=Path,required=True)
    index_parser=sub.add_parser('prepare-index')
    index_parser.add_argument('--pr',type=int,required=True)
    index_parser.add_argument('--evidence',type=Path,required=True)
    index_parser.add_argument('--token-env',required=True)
    index_parser.add_argument('--normalizes-reference')
    index_parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='audit':
            require(re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',args.token_env) is not None,
                    'Audit credential must be selected by environment-variable name')
            token=os.environ.get(args.token_env)
            require(bool(token),'Selected read-only audit credential is unavailable')
            api=GitHubAPI.for_read_only_audit(token)
            result=evidence_audit.audit_pull_request(args.root,api,args.pr)
            print(json.dumps(result,sort_keys=True))
            statuses=result['gates'].values()
            if 'FAIL' in statuses: return 1
            if 'MISSING_EVIDENCE' in statuses: return 2
            return 0
        if args.command=='capture-execution':
            require(not (args.transcript_file and args.execution_command),
                    'Choose a command or a transcript file')
            command=args.execution_command
            if command[:1]==['--']: command=command[1:]
            transcript=args.transcript_file.read_text() if args.transcript_file else None
            require(bool(transcript) or bool(command),'Captured command or ChatGPT transcript required')
            result=evidence_records.capture_execution(args.root,args.gate,args.system,command,
                json.loads(args.report.read_text()),json.loads(args.reviewed_range.read_text()),transcript)
            require(len(result['body'].encode())<=60000,
                    'Captured receipt exceeds the supported GitHub comment size')
            args.output.write_text(result['body']+'\n')
            print(json.dumps({'output':str(args.output),'execution_id':
                result['event']['execution']['execution_id'],'exit_code':result['exit_code']},sort_keys=True))
            return 0 if result['exit_code']==0 else 1
        if args.command=='owner-receipt':
            args.output.write_text(evidence_records.build_owner_receipt(args.gate,args.revision)+'\n')
            print(json.dumps({'output':str(args.output),'gate':args.gate},sort_keys=True))
            return 0
        if args.command=='prepare-index':
            require(re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',args.token_env) is not None,
                    'Read-only credential must be selected by environment-variable name')
            token=os.environ.get(args.token_env)
            require(bool(token),'Selected read-only credential is unavailable')
            api=GitHubAPI.for_read_only_audit(token)
            evidence=json.loads(args.evidence.read_text())
            body=evidence_records.prepare_readiness_index(evidence,args.pr,api,
                                         normalizes_reference=args.normalizes_reference)
            args.output.write_text(body+'\n')
            print(json.dumps({'output':str(args.output),'pull_request':args.pr,
                              'origin':evidence.get('origin',{}).get('kind')},sort_keys=True))
            return 0
        api=GitHubAPI()
        if args.command=='preflight':
            require(git(args.root,'rev-parse','HEAD').decode().strip()==args.builder_revision,'Dispatch builder checkout mismatch')
            require(bool(args.supersedes)==bool(args.correction_reason),'Supersession requires correction reason')
            require(not (args.evidence and args.evidence_reference),'Choose one evidence input')
            evidence=(load_evidence_export(args.evidence_reference,api.record) if args.evidence_reference else
                      json.loads(Path(args.evidence).read_text()) if args.evidence else
                      evidence_discovery.discover_evidence(args.root, api, args.source,
                          args.builder_revision, select_anchor=select_anchor))
            result=preflight(args.root,api,args.source,evidence,args.run_id,args.run_attempt)
            result.update(supersedes=args.supersedes,correction_reason=args.correction_reason)
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
        elif args.command=='verify-release': result=verify_release(args.root,api,args.tag)
        else: result=resolve_task(api,existing_pin=args.existing_pin,root=args.root,compatibility=json.loads(args.compatibility.read_text()) if args.compatibility else None,skill=args.skill,installed_path=args.installed_path)
        print(json.dumps(result,sort_keys=True)); return 0
    except (ReleaseError,APIError,OSError,ValueError,KeyError,TypeError) as error:
        print(f'ERROR: {error}',file=sys.stderr); return 1


if __name__=='__main__': sys.exit(main())
