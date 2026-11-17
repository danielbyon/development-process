"""Ordinary pull request and CI integration verification."""

from __future__ import annotations

import json

from .common import (
    BASE, JSON, REPOSITORY, SHA, ReleaseError, _EvidenceAPI, canonical, digest, git,
    require, revision,
)
from .records import (
    _evidence_timestamp, load_readiness_index, verify_ci_pull_request,
    verify_ci_suites, verify_event_chronology,
)

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

def _required_ci_job(api, ci, attempt, *, completion_required,
                     job_error, steps_error):
    jobs=api.ci_jobs(ci['id'],attempt)
    required=[job for job in jobs
              if job.get('name')=='Validate committed PR integration diff']
    valid=len(required)==1 and required[0].get('conclusion')=='success'
    if valid and completion_required:
        valid=(required[0].get('status')=='completed' and
               required[0].get('completed_at'))
    require(valid,job_error)
    job=required[0]
    steps=job.get('steps',[])
    require(steps and all(step.get('conclusion')=='success' for step in steps),
                steps_error)
    return job,steps

def _verify_ci_log_identity(logs, integration, *, candidate):
    identities=(('PR HEAD','reviewed_revision'),
                ('Tested integration revision','tested_revision'),
                ('Tested base revision','base_revision'))
    for label,key in identities:
        value=integration.get(key)
        if candidate:
            require(isinstance(value,str) and SHA.fullmatch(value) and
                        label+': '+value in logs,
                        'Candidate CI identity missing: '+label)
        else:
            require(isinstance(value,str) and SHA.fullmatch(value),
                        f'Missing {key}')
            require(label+': '+value in logs,
                        'CI synthetic merge identity not established')

def _verify_ci_suites_for_revision(root, revision, logs, steps):
    manifest=json.loads(git(root,'show',revision+':skills/distribution.json'))
    workflow=git(root,'show',revision+':.github/workflows/ci.yml').decode()
    verify_ci_suites(logs, manifest.get('schema_version'), steps, workflow)

def verify_live_integrations(api: _EvidenceAPI,
                             evidence: JSON,
                             root: RepositoryPath | None = None) -> list[JSON]:
    """Check merged PR identity and actual required CI job execution."""
    version=evidence.get('schema_version')
    for integration in evidence.get('integrations',[]):
        number=integration.get('pull_request')
        require(type(number) is int and number>0,'Merged PR reference required')
        pr=api.record(BASE+f'/pulls/{number}')
        require(pr.get('merged') is True and pr.get('base',{}).get('ref')=='main','Reviewed PR not merged to main')
        require(pr.get('head',{}).get('sha')==integration['reviewed_revision'],'Reviewed PR head mismatch')
        require(pr.get('merge_commit_sha')==integration['integrated_revision'],'Integrated PR revision mismatch')
        if version==2:
            require(pr.get('number')==number and
                    pr.get('base',{}).get('repo',{}).get('full_name')==REPOSITORY and
                    pr.get('head',{}).get('repo',{}).get('full_name')==REPOSITORY,
                    'Merged PR repository or number identity mismatch')
        entry=integration['records']['ci']
        ci=api.record(entry['ref'])
        require(ci.get('repository',{}).get('full_name')==REPOSITORY,'CI repository mismatch')
        require(ci.get('event')=='pull_request','PR integration CI required')
        if version==2:
            verify_ci_pull_request(ci,number,integration['reviewed_revision'],
                                   integration['base_revision'])
        required,steps=_required_ci_job(api,ci,entry['run_attempt'],completion_required=False,
            job_error='Required CI job unavailable',
            steps_error='CI contains failed or skipped steps')
        if version==2:
            merged_at=pr.get('merged_at')
            require(merged_at,'Provider merge timestamp required')
            require(required.get('status')=='completed' and required.get('completed_at'),
                    'Required CI job completion timestamp unavailable')
            records=integration.get('records',{})
            receipt_records={}
            for key in ('author_execution','chatgpt_inspection','owner_authorization'):
                receipt=records.get(key)
                require(isinstance(receipt,dict),'Required pre-merge receipt missing: '+key)
                receipt_records[key]=api.record(receipt['ref'])
            reviews=records.get('independent_reviews',[])
            if not reviews and isinstance(records.get('independent_review'),dict):
                reviews=[records['independent_review']]
            require(reviews,'Independent review receipts required')
            review_records=[api.record(receipt['ref']) for receipt in reviews]
            qualification_records=[receipt_records['author_execution'],*review_records,
                                   receipt_records['chatgpt_inspection'],ci,required]
            verify_event_chronology(qualification_records,
                                    receipt_records['owner_authorization'].get('created_at'))
            binding=integration.get('readiness_index',{})
            index_ref=binding.get('normalization_ref') or binding.get('index_ref')
            loaded=load_readiness_index(index_ref,api.record,number)
            require(loaded['index_ref']==binding.get('index_ref') and
                    loaded['index_sha256']==binding.get('index_sha256') and
                    loaded['original_ref']==binding.get('original_ref') and
                    loaded['original_sha256']==binding.get('original_sha256') and
                    loaded['normalization_ref']==binding.get('normalization_ref') and
                    loaded['normalization_sha256']==binding.get('normalization_sha256'),
                    'Readiness index provider binding changed')
            original_index=loaded['original_record']
            verify_event_chronology([*qualification_records,receipt_records['owner_authorization']],
                                    original_index.get('created_at'))
            receipts=[*qualification_records,receipt_records['owner_authorization'],original_index]
            verify_event_chronology(receipts,merged_at)
            if loaded['normalization_record'] is not None:
                require(_evidence_timestamp(loaded['normalization_record'].get('created_at'))>=
                        _evidence_timestamp(merged_at),
                        'Readiness normalization predates the actual merge')
        logs=api.job_log(required['id'])
        _verify_ci_log_identity(logs,integration,candidate=False)
        require(root is not None,'Committed CI applicability source required')
        _verify_ci_suites_for_revision(root,integration['integrated_revision'],logs,steps)
        verify_membership(api,integration)

def verify_premerge_integrations(api: _EvidenceAPI,
                                 evidence: JSON,
                                 root: RepositoryPath) -> list[JSON]:
    """Verify PR evidence and successful candidate CI without claiming a merge."""
    for integration in evidence.get('integrations',[]):
        number=integration.get('pull_request')
        require(type(number) is int and number>0,'Pull request reference required')
        pr=api.record(BASE+f'/pulls/{number}')
        require(pr.get('base',{}).get('ref')=='main' and
                pr.get('base',{}).get('repo',{}).get('full_name',REPOSITORY)==REPOSITORY,
                'Candidate pull request must target this repository main')
        require(pr.get('head',{}).get('repo',{}).get('full_name',REPOSITORY)==REPOSITORY and
                pr.get('head',{}).get('sha')==integration.get('reviewed_revision'),
                'Candidate pull request head identity mismatch')
        require(not pr.get('merged_at'),'Use post-merge verification for an integrated pull request')
        require(pr.get('base',{}).get('sha',integration.get('base_revision'))==
                integration.get('base_revision'),'Candidate pull request base revision mismatch')
        ci_entry=integration.get('records',{}).get('ci',{})
        ci=api.record(ci_entry.get('ref'))
        require(digest(canonical(ci))==ci_entry.get('sha256') and
                ci.get('repository',{}).get('full_name')==REPOSITORY and
                ci.get('event')=='pull_request' and ci.get('status')=='completed' and
                ci.get('conclusion')=='success' and
                ci.get('head_sha')==integration.get('reviewed_revision') and
                ci.get('run_attempt')==ci_entry.get('run_attempt') and ci.get('completed_at'),
                'Successful candidate CI provider record required')
        verify_ci_pull_request(ci,number,integration.get('reviewed_revision'),
                               integration.get('base_revision'))
        required,steps=_required_ci_job(api,ci,ci_entry['run_attempt'],completion_required=True,
            job_error='Required completed candidate CI job unavailable',
            steps_error='Candidate CI contains failed or skipped steps')
        logs=api.job_log(required['id'])
        _verify_ci_log_identity(logs,integration,candidate=True)
        revision(root,integration['reviewed_revision'])
        _verify_ci_suites_for_revision(root,integration['reviewed_revision'],logs,steps)
        records=integration.get('records',{})
        reviews=records.get('independent_reviews',[])
        if not reviews and isinstance(records.get('independent_review'),dict):
            reviews=[records['independent_review']]
        owner_entry=records.get('owner_authorization',{})
        require(owner_entry.get('ref'),'Pre-merge owner authorization receipt required')
        qualifications=[api.record(records['author_execution']['ref'])]
        qualifications.extend(api.record(entry['ref']) for entry in reviews)
        qualifications.append(api.record(records['chatgpt_inspection']['ref']))
        qualifications.extend([ci,required])
        owner_record=api.record(owner_entry['ref'])
        verify_event_chronology(qualifications,owner_record.get('created_at'))
        binding=integration.get('readiness_index',{})
        index_ref=binding.get('normalization_ref') or binding.get('index_ref')
        loaded=load_readiness_index(index_ref,api.record,number)
        require(loaded['index_ref']==binding.get('index_ref') and
                loaded['index_sha256']==binding.get('index_sha256') and
                loaded['original_ref']==binding.get('original_ref') and
                loaded['original_sha256']==binding.get('original_sha256') and
                loaded['normalization_ref']==binding.get('normalization_ref') and
                loaded['normalization_sha256']==binding.get('normalization_sha256'),
                'Readiness index provider binding changed')
        verify_event_chronology([*qualifications,owner_record],
                                loaded['original_record'].get('created_at'))
