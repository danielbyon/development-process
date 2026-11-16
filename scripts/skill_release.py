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
from datetime import datetime, date
from zoneinfo import ZoneInfo
from github_releases import GitHubAPI, APIError

REPOSITORY='danielbyon/development-process'
BOOTSTRAP_BASELINE='e47c8882e590c3ec41d2d46f461d18ed73132534'
BASE='/repos/'+REPOSITORY
SHA=re.compile(r'[0-9a-f]{40}')
SUITES=('test_workflow_contract.py','test_skill_distribution.py','test_distribution_smoke.py',
        'test_primary_main_fast_forward.py','test_skill_releases.py','test_github_releases.py')
class ReleaseError(RuntimeError):
    """A mandatory release prerequisite could not be verified."""

def require(condition, message):
    if not condition: raise ReleaseError(message)

def digest(value): return hashlib.sha256(value).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def git(root,*args):
    try: return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
    except subprocess.CalledProcessError as error: raise ReleaseError('Git identity or history unavailable') from error

def revision(root,value):
    require(isinstance(value,str) and SHA.fullmatch(value),'Full immutable revision required')
    require(git(root,'rev-parse',value+'^{commit}').decode().strip()==value,'Revision mismatch')
    return value

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

def load_evidence_export(reference,fetch):
    """Read an owner-authenticated normalization without rewriting old records."""
    repository=fetch(BASE)
    record=fetch(reference)
    require(record.get('user',{}).get('id')==repository.get('owner',{}).get('id'),
            'Normalized export must be owner authenticated')
    try: exported=json.loads(record.get('body',''))
    except ValueError as error: raise ReleaseError('Normalized evidence export must be JSON') from error
    require(exported.get('repository')==REPOSITORY,'Normalized export repository mismatch')
    evidence=exported.get('evidence')
    require(isinstance(evidence,dict),'Normalized evidence missing')
    evidence['normalization_export']={'ref':reference,'sha256':digest(canonical(record))}
    return evidence

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

def execution_provenance(entry,fetch,owner_id,role,integration,normalized=False):
    """Check an authenticated execution export and its exact role and range."""
    record=fetch(entry.get('ref'))
    require(record.get('user',{}).get('id')==owner_id and
            digest(canonical(record))==entry.get('sha256'),'Execution provenance export unverified')
    if 'normalized_execution' in entry:
        require(normalized,'Owner-authenticated execution normalization required')
        provenance=entry['normalized_execution']
        require(provenance.get('transcript')==record.get('body'),
                'Execution normalization differs from actual transcript')
    else:
        try: provenance=json.loads(record.get('body',''))
        except ValueError as error: raise ReleaseError('Parsed execution provenance required') from error
    require(provenance.get('schema_version')==1 and provenance.get('repository')==REPOSITORY,
            'Execution repository/schema mismatch')
    require(provenance.get('role')==role and isinstance(provenance.get('execution_id'),str)
            and provenance['execution_id'],'Exact execution role/identity required')
    expected={'base_revision':integration.get('base_revision'),'head_revision':integration.get('reviewed_revision')}
    require(all(isinstance(v,str) and SHA.fullmatch(v) for v in expected.values()) and
            provenance.get('reviewed_range')==expected,'Execution reviewed range mismatch')
    require(isinstance(provenance.get('transcript'),str) and provenance['transcript'],
            'Actual execution transcript required')
    return provenance

def verify_evidence(evidence,fetch):
    """Resolve record references and require exact content and candidate binding.

    Exported reports are accepted only through an authenticated repository record
    containing the report, execution identity and reviewed revision. Booleans and
    summaries without those records cannot satisfy a gate.
    """
    require(isinstance(evidence,dict) and evidence.get('schema_version')==1,'Evidence schema required')
    repository=fetch(BASE)
    owner_id=repository.get('owner',{}).get('id')
    require(repository.get('full_name')==REPOSITORY and owner_id==evidence.get('owner_id'),'Evidence owner differs from repository owner')
    normalization=evidence.get('normalization_export')
    if normalization:
        exported=load_evidence_export(normalization['ref'],fetch)
        require(exported==evidence,'Normalized evidence export changed')
    snapshots=[]
    for integration in evidence.get('integrations',[]):
        target=integration.get('reviewed_revision')
        require(isinstance(target,str) and SHA.fullmatch(target),'Reviewed revision required')
        records=integration.get('records',{})
        author_entry=integration.get('author_execution',{})
        author=execution_provenance(author_entry,fetch,owner_id,'author',integration,bool(normalization))
        require(author['execution_id']==integration.get('author_execution_id'),'Author execution identity mismatch')
        for gate in ('independent_review','chatgpt_inspection','owner_authorization','ci'):
            entry=records.get(gate)
            require(isinstance(entry,dict) and entry.get('ref') and entry.get('sha256'),f'Missing {gate} record')
            actual=fetch(entry['ref'])
            require(digest(canonical(actual))==entry['sha256'],f'Stale {gate} record')
            require(isinstance(actual,dict),f'Invalid {gate} record')
            if gate=='ci':
                require(actual.get('conclusion')=='success' and actual.get('status')=='completed','CI incomplete')
                require(actual.get('head_sha')==integration.get('reviewed_revision'),'CI tested revision mismatch')
                require(actual.get('run_attempt')==entry.get('run_attempt'),'CI attempt mismatch')
            else:
                body=actual.get('body','')
                marker='<!-- release-evidence\n'
                if 'normalized_report' in entry:
                    require(normalization,'Authenticated normalization export required')
                    report=entry['normalized_report']
                    require(isinstance(report,dict) and report.get('report') and report['report'] in body,
                            'Original report text not bound to normalization')
                else:
                    require(marker in body and '\n-->' in body,'Inspectable structured execution report required')
                    try: report=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
                    except (ValueError,IndexError) as error: raise ReleaseError('Malformed execution report') from error
                require(report.get('revision')==target and report.get('gate')==gate,'Report candidate/gate mismatch')
                require(report.get('execution_id') and report.get('report') and report.get('verdict')=='pass','Execution/report missing')
                require(actual.get('user',{}).get('id')==entry.get('author_id'),
                        'Original report author mismatch')
                require(normalization or entry.get('author_id')==owner_id,
                        'Owner-authenticated evidence export required')
                execution=entry.get('execution',{})
                exported=execution_provenance(execution,fetch,owner_id,gate,integration,bool(normalization))
                require(exported['execution_id']==report['execution_id'],'Exact report execution identity mismatch')
                transcript=exported['transcript']
                require(report['report'] in transcript,'Actual report/transcript binding unavailable')
                if 'normalized_report' in entry:
                    # Bind each normalized claim to inspectable execution text.
                    claims=[report['execution_id'],target,report['report']]
                    if gate=='independent_review': claims += ['full-diff']
                    if gate=='chatgpt_inspection': claims += report.get('source_files',[])+report.get('test_files',[])
                    if gate=='owner_authorization': claims += ['merge']
                    require(all(isinstance(c,str) and c in transcript for c in claims),
                            'Normalized claims lack actual execution proof')
                if gate=='independent_review':
                    require(execution.get('ref')!=author_entry.get('ref') and
                            execution.get('sha256')!=author_entry.get('sha256') and
                            exported['execution_id']!=author['execution_id'],
                            'Author cannot independently review')
                    require(report.get('coverage')=='full-diff' and report.get('findings')==[],'Review coverage/findings unresolved')
                if gate=='chatgpt_inspection':
                    require(report.get('source_files') and report.get('test_files'),'Source/test inspection missing')
                if gate=='owner_authorization':
                    require(actual.get('user',{}).get('id')==evidence.get('owner_id'),'Owner authorization identity mismatch')
                    require(report.get('action')=='merge','Merge authorization required')
            snapshots.append({'gate':gate,'ref':entry['ref'],'sha256':entry['sha256'],'record':actual})
    require(snapshots or evidence.get('anchor_release'),'No admitted evidence')
    return snapshots

def verify_coverage(root,evidence,target):
    baseline=revision(root,evidence.get('baseline_revision'))
    require(baseline==BOOTSTRAP_BASELINE or evidence.get('anchor_release') or evidence.get('baseline_admission'),'Unadmitted bootstrap baseline')
    revision(root,target)
    git(root,'merge-base','--is-ancestor',baseline,target)
    required=set(git(root,'rev-list','--first-parent',baseline+'..'+target).decode().split())
    covered=set()
    for integration in evidence.get('integrations',[]):
        result=revision(root,integration.get('integrated_revision'))
        reviewed=revision(root,integration.get('reviewed_revision'))
        tested=revision(root,integration.get('tested_revision'))
        require(git(root,'rev-parse',result+'^{tree}')==git(root,'rev-parse',tested+'^{tree}'),'Integration tree differs from tested tree')
        # The tested integration must contain the reviewed candidate as a parent.
        parents=git(root,'show','-s','--format=%P',tested).decode().split()
        require(reviewed in parents or git(root,'rev-parse',reviewed+'^{tree}')==git(root,'rev-parse',tested+'^{tree}'),'Reviewed candidate relationship unverified')
        covered.add(result)
        members=integration.get('integrated_commits',[result])
        require(isinstance(members,list) and members and len(set(members))==len(members)
                and members[-1]==result,'Invalid integrated commit membership')
        expected=git(root,'rev-list','--first-parent','--max-count='+str(len(members)),result).decode().split()[::-1]
        require(members==expected,'Integration membership is not a contiguous first-parent range')
        covered.update(members)
    require(required<=covered,'Uncovered main integrations')
    require(evidence.get('anchor_release') or any(x.get('integrated_revision')==baseline for x in evidence.get('integrations',[])),'Bootstrap baseline admission missing')

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

def admit_anchor(root,api,evidence):
    """Reuse a verified release or inspect an explicit owner baseline admission."""
    baseline=evidence['baseline_revision']
    if evidence.get('anchor_release'):
        anchor=verify_release(root,api,evidence['anchor_release'])
        require(anchor['source_revision']==baseline,'Trusted release anchor mismatch')
        return
    if baseline==BOOTSTRAP_BASELINE: return
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
    require(report.get('revision')==baseline and report.get('action')=='admit-baseline' and report.get('report') and report.get('execution_id'),'Unverified baseline admission')

def merged_pr_members(api,commit):
    return [pr for pr in api.pages(BASE+'/commits/'+commit+'/pulls')
            if pr.get('merged_at') and pr.get('base',{}).get('ref')=='main']

def verify_membership(api,integration):
    """Bind rebased commits to their actual PR instead of a broad CI interval."""
    number=integration['pull_request']; result=integration['integrated_revision']
    members=integration.get('integrated_commits',[result])
    original=api.pages(BASE+f'/pulls/{number}/commits')
    require(isinstance(original,list) and original,'PR commit membership unavailable')
    require(len(members)==1 or len(members)==len(original),'Rebase PR commit count mismatch')
    for commit in members:
        matches=merged_pr_members(api,commit)
        require(len(matches)==1 and matches[0].get('number')==number and
                matches[0].get('merge_commit_sha')==result,'Unverified or unrelated integrated commit')

def verify_ci_suites(logs,schema,steps,workflow):
    """Bind each suite result to its committed command and successful CI step."""
    require(schema in (1,2),'Unsupported CI source schema')
    contract=yaml.safe_load(workflow)
    jobs=[j for j in contract.get('jobs',{}).values()
          if j.get('name')=='Validate committed PR integration diff']
    require(len(jobs)==1 and not any(k in jobs[0] for k in ('if','continue-on-error','strategy')),
            'Conditional or ambiguous mandatory CI job')
    expected=list(SUITES if schema==2 else SUITES[:4])
    workflow_steps=jobs[0].get('steps',[])
    if schema==1 and any('test_issue5_workflow.py' in x.get('run','') for x in workflow_steps):
        expected[0]='test_issue5_workflow.py'
    text=re.sub(r'^\d{4}-\d\d-\d\dT\S+ ', '', logs, flags=re.M)
    groups=list(re.finditer(r'^##\[group\]Run (.+)\n',text,re.M))
    for suite in expected:
        command='python3 -m unittest discover -s tests -p '+suite+' -v'
        matches=[x for x in workflow_steps if x.get('run','').strip()==command]
        require(len(matches)==1,'Missing or altered mandatory suite command: '+suite)
        step=matches[0]
        require(not any(k in step for k in ('if','continue-on-error','working-directory','env')),
                'Conditional or altered suite execution: '+suite)
        actual=[x for x in steps if x.get('name')==step.get('name')]
        require(len(actual)==1 and actual[0].get('conclusion')=='success',
                'Mandatory suite step not successful: '+suite)
        executed=[(i,g) for i,g in enumerate(groups) if shlex.split(g.group(1))==shlex.split(command)]
        require(len(executed)==1,'Missing or repeated suite command execution: '+suite)
        i,group=executed[0]
        section=text[group.end():groups[i+1].start() if i+1<len(groups) else len(text)]
        require('##[endgroup]\n' in section,'Suite command boundary absent')
        output=section.split('##[endgroup]\n',1)[1]
        summaries=re.findall(r'^Ran ([0-9]+) tests? in [^\n]+$',output,re.M)
        result_output=re.split(r'^-{5,}$|^Ran [0-9]+ tests?',output,maxsplit=1,flags=re.M)[0]
        labels=list(re.finditer(r'^test\S+ \(.+\)',result_output,re.M))
        statuses=[]
        for index,label in enumerate(labels):
            result=result_output[label.end():labels[index+1].start() if index+1<len(labels) else len(result_output)]
            statuses.append(bool(re.search(r'(?:^|\n|\.\.\. )ok\s*$',result)))
        require(len(summaries)==1 and int(summaries[0])>0 and
                len(labels)==int(summaries[0]) and all(statuses) and
                len(re.findall(r'^OK$',output,re.M))==1 and
                not re.search(r'^FAILED(?: |$)|^OK \(',output,re.M),
                'Mandatory suite execution failed, skipped or absent: '+suite)

def verify_live_integrations(api,evidence,root=None):
    """Check merged PR identity and actual required CI job execution."""
    for integration in evidence.get('integrations',[]):
        number=integration.get('pull_request')
        require(type(number) is int and number>0,'Merged PR reference required')
        pr=api.record(BASE+f'/pulls/{number}')
        require(pr.get('merged') is True and pr.get('base',{}).get('ref')=='main','Reviewed PR not merged to main')
        require(pr.get('head',{}).get('sha')==integration['reviewed_revision'],'Reviewed PR head mismatch')
        require(pr.get('merge_commit_sha')==integration['integrated_revision'],'Integrated PR revision mismatch')
        entry=integration['records']['ci']
        ci=api.record(entry['ref'])
        require(ci.get('repository',{}).get('full_name')==REPOSITORY,'CI repository mismatch')
        require(ci.get('event')=='pull_request','PR integration CI required')
        jobs=api.ci_jobs(ci['id'],entry['run_attempt'])
        required=[j for j in jobs if j.get('name')=='Validate committed PR integration diff']
        require(len(required)==1 and required[0].get('conclusion')=='success','Required CI job unavailable')
        steps=required[0].get('steps',[])
        require(steps and all(x.get('conclusion')=='success' for x in steps),'CI contains failed or skipped steps')
        logs=api.job_log(required[0]['id'])
        for label,key in (('PR HEAD','reviewed_revision'),('Tested integration revision','tested_revision'),('Tested base revision','base_revision')):
            value=integration.get(key)
            require(isinstance(value,str) and SHA.fullmatch(value),f'Missing {key}')
            require(label+': '+value in logs,'CI synthetic merge identity not established')
        require(root is not None,'Committed CI applicability source required')
        manifest=json.loads(git(root,'show',integration['integrated_revision']+':skills/distribution.json'))
        workflow=git(root,'show',integration['integrated_revision']+':.github/workflows/ci.yml').decode()
        verify_ci_suites(logs,manifest.get('schema_version'),steps,workflow)
        verify_membership(api,integration)

def discover_evidence(root,api,source,builder):
    """Read readiness indexes from existing merged PR comments.

    Indexes only locate records. Every referenced record and the actual PR/CI
    relationships are verified independently before admission.
    """
    anchor=select_anchor(root,api,source,builder)
    baseline,tag=anchor if anchor else (BOOTSTRAP_BASELINE,None)
    try:
        git(root,'merge-base','--is-ancestor',baseline,source)
        git(root,'merge-base','--is-ancestor',baseline,builder)
    except ReleaseError as error:
        raise ReleaseError('Historical source needs an applicable trusted release or evidenced earlier baseline export') from error
    revisions=git(root,'rev-list','--first-parent',baseline+'..'+builder).decode().split()
    if not tag: revisions.append(baseline)
    integrations=[]; discovered=set()
    for commit in revisions:
        if commit in discovered: continue
        prs=api.pages(BASE+f'/commits/{commit}/pulls')
        matches=[pr for pr in prs if pr.get('merge_commit_sha')==commit and pr.get('base',{}).get('ref')=='main']
        require(len(matches)==1,f'Unmapped integration {commit}')
        pr=matches[0]
        indexes=[]
        for comment in api.pages(BASE+f'/issues/{pr["number"]}/comments'):
            body=comment.get('body',''); marker='<!-- release-readiness\n'
            if marker not in body: continue
            try: index=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
            except (ValueError,IndexError) as error: raise ReleaseError('Malformed readiness index') from error
            if index.get('integrated_revision')==commit: indexes.append(index)
        require(len(indexes)==1,f'Missing or contradictory readiness index for {commit}')
        index=indexes[0]; index['pull_request']=pr['number']
        original=api.pages(BASE+f'/pulls/{pr["number"]}/commits')
        require(isinstance(original,list) and original,'PR commit membership unavailable')
        members=[]
        for candidate in git(root,'rev-list','--first-parent','--max-count='+str(len(original)),commit).decode().split():
            associated=merged_pr_members(api,candidate)
            if len(associated)!=1 or associated[0].get('number')!=pr['number'] or associated[0].get('merge_commit_sha')!=commit: break
            members.append(candidate)
        index['integrated_commits']=members[::-1]
        verify_membership(api,index)
        require(members and not (set(members)&discovered),'Overlapping or unavailable PR membership')
        discovered.update(members);integrations.append(index)
    repo=api.request('GET',BASE)
    result={'schema_version':1,'baseline_revision':baseline,'owner_id':repo['owner']['id'],'integrations':integrations}
    if tag: result['anchor_release']=tag
    return result

class EvidenceAuthority:
    """Freeze authenticated API reads for later signed, offline verification."""
    def __init__(self,api=None,data=None):
        self.api=api
        self.data=data if data is not None else {'records':{},'jobs':{},'logs':{},'pages':{}}
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

def preflight(root,api,source,evidence,run_id,run_attempt):
    source=revision(root,source); builder=revision(root,git(root,'rev-parse','HEAD').decode().strip())
    repo=api.request('GET',BASE); run=api.run(run_id)
    context={'repository':REPOSITORY,'source_revision':source,'builder_revision':builder,'owner_id':repo['owner']['id'],
             'run_id':int(run_id),'run_attempt':int(run_attempt),'created_at':run['created_at'],'transform_version':1}
    check_settings(api,context)
    git(root,'merge-base','--is-ancestor',source,builder)
    workflows_differ=git(root,'ls-tree','-r',source,'--','.github/workflows')!=git(root,'ls-tree','-r',builder,'--','.github/workflows')
    context['requires_workflows_write']=workflows_differ
    # Preflight cannot provision credentials or infer owner authorization.
    if workflows_differ:
        require(os.environ.get('RELEASE_WORKFLOW_WRITE_AUTHORIZED')=='true','Separate owner authorization for Workflows write required')
    authority=EvidenceAuthority(api)
    snapshots=verify_evidence(evidence,authority.record)
    admit_anchor(root,authority,evidence)
    verify_live_integrations(authority,evidence,root)
    verify_coverage(root,evidence,source); verify_coverage(root,evidence,builder)
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
    require(verify_evidence(context['evidence'],api.record)==context['evidence_snapshots'],'Evidence drift')
    admit_anchor(root,api,context['evidence'])
    verify_live_integrations(api,context['evidence'],root)
    verify_coverage(root,context['evidence'],context['source_revision']); verify_coverage(root,context['evidence'],context['builder_revision'])
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
    verify_evidence(context['evidence'],api.record)
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
        require(verify_evidence(context.get('evidence'),frozen.record)==context['evidence_snapshots'],
                'Frozen qualification authority unverified')
        if context['evidence'].get('anchor_release'):
            admit_anchor(root,api,context['evidence'])
        else:
            admit_anchor(root,frozen,context['evidence'])
        verify_live_integrations(frozen,context['evidence'],root)
        verify_coverage(root,context['evidence'],context['source_revision'])
        verify_coverage(root,context['evidence'],context['builder_revision'])
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
    args=parser.parse_args(argv); api=GitHubAPI()
    try:
        if args.command=='preflight':
            require(git(args.root,'rev-parse','HEAD').decode().strip()==args.builder_revision,'Dispatch builder checkout mismatch')
            require(bool(args.supersedes)==bool(args.correction_reason),'Supersession requires correction reason')
            require(not (args.evidence and args.evidence_reference),'Choose one evidence input')
            evidence=(load_evidence_export(args.evidence_reference,api.record) if args.evidence_reference else
                      json.loads(Path(args.evidence).read_text()) if args.evidence else
                      discover_evidence(args.root,api,args.source,args.builder_revision))
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
