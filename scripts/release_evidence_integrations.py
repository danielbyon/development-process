"""Verify pull request evidence against actual Git integrations."""
from __future__ import annotations

import json

from release_evidence_records import _evidence_timestamp, load_readiness_index, verify_ci_pull_request, verify_ci_suites, verify_event_chronology

def merged_pr_members(ctx, api,commit):
    return [pr for pr in api.pages(ctx.BASE+'/commits/'+commit+'/pulls')
            if pr.get('merged_at') and pr.get('base',{}).get('ref')=='main']

def verify_membership(ctx, api,integration):
    """Bind rebased commits to their actual PR instead of a broad CI interval."""
    number=integration['pull_request']; result=integration['integrated_revision']
    members=integration.get('integrated_commits',[result])
    original=api.pages(ctx.BASE+f'/pulls/{number}/commits')
    ctx.require(isinstance(original,list) and original,'PR commit membership unavailable')
    ctx.require(len(members)==1 or len(members)==len(original),'Rebase PR commit count mismatch')
    for commit in members:
        matches=merged_pr_members(ctx, api,commit)
        ctx.require(len(matches)==1 and matches[0].get('number')==number and
                matches[0].get('merge_commit_sha')==result,'Unverified or unrelated integrated commit')

def verify_live_integrations(ctx, api,evidence,root=None):
    """Check merged PR identity and actual required CI job execution."""
    version=evidence.get('schema_version')
    for integration in evidence.get('integrations',[]):
        number=integration.get('pull_request')
        ctx.require(type(number) is int and number>0,'Merged PR reference required')
        pr=api.record(ctx.BASE+f'/pulls/{number}')
        ctx.require(pr.get('merged') is True and pr.get('base',{}).get('ref')=='main','Reviewed PR not merged to main')
        ctx.require(pr.get('head',{}).get('sha')==integration['reviewed_revision'],'Reviewed PR head mismatch')
        ctx.require(pr.get('merge_commit_sha')==integration['integrated_revision'],'Integrated PR revision mismatch')
        if version==2:
            ctx.require(pr.get('number')==number and
                    pr.get('base',{}).get('repo',{}).get('full_name')==ctx.REPOSITORY and
                    pr.get('head',{}).get('repo',{}).get('full_name')==ctx.REPOSITORY,
                    'Merged PR repository or number identity mismatch')
        entry=integration['records']['ci']
        ci=api.record(entry['ref'])
        ctx.require(ci.get('repository',{}).get('full_name')==ctx.REPOSITORY,'CI repository mismatch')
        ctx.require(ci.get('event')=='pull_request','PR integration CI required')
        if version==2:
            verify_ci_pull_request(ctx, ci,number,integration['reviewed_revision'],
                                   integration['base_revision'])
        jobs=api.ci_jobs(ci['id'],entry['run_attempt'])
        required=[j for j in jobs if j.get('name')=='Validate committed PR integration diff']
        ctx.require(len(required)==1 and required[0].get('conclusion')=='success','Required CI job unavailable')
        steps=required[0].get('steps',[])
        ctx.require(steps and all(x.get('conclusion')=='success' for x in steps),'CI contains failed or skipped steps')
        if version==2:
            merged_at=pr.get('merged_at')
            ctx.require(merged_at,'Provider merge timestamp required')
            ctx.require(required[0].get('status')=='completed' and required[0].get('completed_at'),
                    'Required CI job completion timestamp unavailable')
            records=integration.get('records',{})
            receipt_records={}
            for key in ('author_execution','chatgpt_inspection','owner_authorization'):
                receipt=records.get(key)
                ctx.require(isinstance(receipt,dict),'Required pre-merge receipt missing: '+key)
                receipt_records[key]=api.record(receipt['ref'])
            reviews=records.get('independent_reviews',[])
            if not reviews and isinstance(records.get('independent_review'),dict):
                reviews=[records['independent_review']]
            ctx.require(reviews,'Independent review receipts required')
            review_records=[api.record(receipt['ref']) for receipt in reviews]
            qualification_records=[receipt_records['author_execution'],*review_records,
                                   receipt_records['chatgpt_inspection'],ci,required[0]]
            verify_event_chronology(ctx, qualification_records,
                                    receipt_records['owner_authorization'].get('created_at'))
            binding=integration.get('readiness_index',{})
            index_ref=binding.get('normalization_ref') or binding.get('index_ref')
            loaded=load_readiness_index(ctx, index_ref,api.record,number)
            ctx.require(loaded['index_ref']==binding.get('index_ref') and
                    loaded['index_sha256']==binding.get('index_sha256') and
                    loaded['original_ref']==binding.get('original_ref') and
                    loaded['original_sha256']==binding.get('original_sha256') and
                    loaded['normalization_ref']==binding.get('normalization_ref') and
                    loaded['normalization_sha256']==binding.get('normalization_sha256'),
                    'Readiness index provider binding changed')
            original_index=loaded['original_record']
            verify_event_chronology(ctx, [*qualification_records,receipt_records['owner_authorization']],
                                    original_index.get('created_at'))
            receipts=[*qualification_records,receipt_records['owner_authorization'],original_index]
            verify_event_chronology(ctx, receipts,merged_at)
            if loaded['normalization_record'] is not None:
                ctx.require(_evidence_timestamp(ctx, loaded['normalization_record'].get('created_at'))>=
                        _evidence_timestamp(ctx, merged_at),
                        'Readiness normalization predates the actual merge')
        logs=api.job_log(required[0]['id'])
        for label,key in (('PR HEAD','reviewed_revision'),('Tested integration revision','tested_revision'),('Tested base revision','base_revision')):
            value=integration.get(key)
            ctx.require(isinstance(value,str) and ctx.SHA.fullmatch(value),f'Missing {key}')
            ctx.require(label+': '+value in logs,'CI synthetic merge identity not established')
        ctx.require(root is not None,'Committed CI applicability source required')
        manifest=json.loads(ctx.git(root,'show',integration['integrated_revision']+':skills/distribution.json'))
        workflow=ctx.git(root,'show',integration['integrated_revision']+':.github/workflows/ci.yml').decode()
        verify_ci_suites(ctx, logs,manifest.get('schema_version'),steps,workflow)
        verify_membership(ctx, api,integration)

def verify_premerge_integrations(ctx, api,evidence,root):
    """Verify PR evidence and successful candidate CI without claiming a merge."""
    for integration in evidence.get('integrations',[]):
        number=integration.get('pull_request')
        ctx.require(type(number) is int and number>0,'Pull request reference required')
        pr=api.record(ctx.BASE+f'/pulls/{number}')
        ctx.require(pr.get('base',{}).get('ref')=='main' and
                pr.get('base',{}).get('repo',{}).get('full_name',ctx.REPOSITORY)==ctx.REPOSITORY,
                'Candidate pull request must target this repository main')
        ctx.require(pr.get('head',{}).get('repo',{}).get('full_name',ctx.REPOSITORY)==ctx.REPOSITORY and
                pr.get('head',{}).get('sha')==integration.get('reviewed_revision'),
                'Candidate pull request head identity mismatch')
        ctx.require(not pr.get('merged_at'),'Use post-merge verification for an integrated pull request')
        ctx.require(pr.get('base',{}).get('sha',integration.get('base_revision'))==
                integration.get('base_revision'),'Candidate pull request base revision mismatch')
        ci_entry=integration.get('records',{}).get('ci',{})
        ci=api.record(ci_entry.get('ref'))
        ctx.require(ctx.digest(ctx.canonical(ci))==ci_entry.get('sha256') and
                ci.get('repository',{}).get('full_name')==ctx.REPOSITORY and
                ci.get('event')=='pull_request' and ci.get('status')=='completed' and
                ci.get('conclusion')=='success' and
                ci.get('head_sha')==integration.get('reviewed_revision') and
                ci.get('run_attempt')==ci_entry.get('run_attempt') and ci.get('completed_at'),
                'Successful candidate CI provider record required')
        verify_ci_pull_request(ctx, ci,number,integration.get('reviewed_revision'),
                               integration.get('base_revision'))
        jobs=api.ci_jobs(ci['id'],ci_entry['run_attempt'])
        required=[job for job in jobs if job.get('name')=='Validate committed PR integration diff']
        ctx.require(len(required)==1 and required[0].get('status')=='completed' and
                required[0].get('conclusion')=='success' and required[0].get('completed_at'),
                'Required completed candidate CI job unavailable')
        steps=required[0].get('steps',[])
        ctx.require(steps and all(step.get('conclusion')=='success' for step in steps),
                'Candidate CI contains failed or skipped steps')
        logs=api.job_log(required[0]['id'])
        tested=integration.get('tested_revision')
        for label,value in (('PR HEAD',integration['reviewed_revision']),
                            ('Tested integration revision',tested),
                            ('Tested base revision',integration['base_revision'])):
            ctx.require(isinstance(value,str) and ctx.SHA.fullmatch(value) and
                    label+': '+value in logs,'Candidate CI identity missing: '+label)
        ctx.revision(root,integration['reviewed_revision'])
        manifest=json.loads(ctx.git(root,'show',integration['reviewed_revision']+':skills/distribution.json'))
        workflow=ctx.git(root,'show',integration['reviewed_revision']+':.github/workflows/ci.yml').decode()
        verify_ci_suites(ctx, logs,manifest.get('schema_version'),steps,workflow)
        records=integration.get('records',{})
        reviews=records.get('independent_reviews',[])
        if not reviews and isinstance(records.get('independent_review'),dict):
            reviews=[records['independent_review']]
        owner_entry=records.get('owner_authorization',{})
        ctx.require(owner_entry.get('ref'),'Pre-merge owner authorization receipt required')
        qualifications=[api.record(records['author_execution']['ref'])]
        qualifications.extend(api.record(entry['ref']) for entry in reviews)
        qualifications.append(api.record(records['chatgpt_inspection']['ref']))
        qualifications.extend([ci,required[0]])
        owner_record=api.record(owner_entry['ref'])
        verify_event_chronology(ctx, qualifications,owner_record.get('created_at'))
        binding=integration.get('readiness_index',{})
        index_ref=binding.get('normalization_ref') or binding.get('index_ref')
        loaded=load_readiness_index(ctx, index_ref,api.record,number)
        ctx.require(loaded['index_ref']==binding.get('index_ref') and
                loaded['index_sha256']==binding.get('index_sha256') and
                loaded['original_ref']==binding.get('original_ref') and
                loaded['original_sha256']==binding.get('original_sha256') and
                loaded['normalization_ref']==binding.get('normalization_ref') and
                loaded['normalization_sha256']==binding.get('normalization_sha256'),
                'Readiness index provider binding changed')
        verify_event_chronology(ctx, [*qualifications,owner_record],
                                loaded['original_record'].get('created_at'))
