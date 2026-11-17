"""Admission checks for a prospective first-release baseline."""

from __future__ import annotations

import json

from .common import (
    BASE, JSON, MissingEvidenceError, REPOSITORY, SHA, ReleaseError,
    _EvidenceAPI, canonical, digest, git, require, require_present, revision,
)
from .records import (
    _evidence_timestamp, load_readiness_index, readiness_index_binding,
    verify_ci_job_identity, verify_ci_test_commit, verify_ci_suites,
    verify_event_chronology,
)
from .qualification import (
    BaselineQualification, VerifiedBaselineAdmission, load_receipt_event,
    verify_execution_after, verify_execution_receipt, verify_inspection_files,
    verify_receipt_time, verify_review_dispositions,
)

def _baseline_manifest_sha256(root,baseline):
    return digest(git(root,'ls-tree','-r','--full-tree','-z',baseline))

def verify_baseline_admission(
        root: RepositoryPath, api: _EvidenceAPI,
        evidence: JSON, source: str, builder: str,
        dispatch_run_id: int) -> VerifiedBaselineAdmission:
    """Verify baseline qualification and bind dispatch to the exact main ref."""
    require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'Prospective baseline requires schema v2 evidence')
    origin=evidence.get('origin',{})
    require(origin.get('kind')=='prospective_baseline',
            'Prospective baseline evidence origin required')
    baseline=revision(root,evidence.get('baseline_revision'))
    require(revision(root,source)==baseline and revision(root,builder)==baseline,
            'First-release source and builder must equal the corrected merge revision')
    require(origin.get('baseline_revision')==baseline and origin.get('source_revision')==baseline and
            origin.get('builder_revision')==baseline,
            'Prospective source/builder identities do not match the admitted baseline')
    require(evidence.get('integrations')==[],
            'Prospective baseline requires zero ordinary integrations')
    repo=api.record(BASE)
    owner_id=repo.get('owner',{}).get('id')
    require(repo.get('full_name')==REPOSITORY and owner_id==evidence.get('owner_id'),
            'Prospective baseline repository owner mismatch')
    tree=git(root,'rev-parse',baseline+'^{tree}').decode().strip()
    manifest=_baseline_manifest_sha256(root,baseline)
    policy=git(root,'log','--first-parent','-1','--format=%H',baseline,'--','docs/PROCESS.md').decode().strip()
    policy_bytes=git(root,'show',baseline+':docs/PROCESS.md')
    require(policy and git(root,'show',policy+':docs/PROCESS.md')==policy_bytes,
            'Prospective policy identity cannot be derived from the baseline')
    require(origin.get('policy_revision')==policy and
            origin.get('policy_sha256')==digest(policy_bytes),
            'Prospective policy identity differs from the baseline policy')
    admission=require_present(evidence.get('baseline_admission'),
                              'Baseline qualification and owner admission are missing')
    require(isinstance(admission,dict),'Baseline qualification and owner admission required')
    pr_number=require_present(admission.get('correction_pull_request'),
                              'Corrected merge pull request is missing')
    require(type(pr_number) is int and pr_number>0,'Corrected merge pull request required')
    pr=api.record(BASE+f'/pulls/{pr_number}')
    require(pr.get('number')==pr_number and
            pr.get('base',{}).get('repo',{}).get('full_name')==REPOSITORY and
            pr.get('head',{}).get('repo',{}).get('full_name')==REPOSITORY and
            pr.get('merged') is True and pr.get('base',{}).get('ref')=='main' and
            pr.get('merge_commit_sha')==baseline and
            pr.get('head',{}).get('sha')==admission.get('reviewed_revision'),
            'Prospective baseline is not the exact corrected main integration')
    merged_at=pr.get('merged_at')
    require_present(merged_at,'Corrected merge provider timestamp is missing')
    merge_time=_evidence_timestamp(merged_at)
    parents=git(root,'show','-s','--format=%P',baseline).decode().split()
    require(parents,'Corrected baseline parent revision required')
    review_entry=admission.get('full_review')
    review_record,review_event=load_receipt_event(
        api.record,review_entry,owner_id,'baseline_review',pr_number)
    review_range={'baseline_revision':baseline,'tree_sha':tree}
    review_event=verify_execution_receipt(review_event,'baseline_review',review_range)
    verify_execution_after(review_event,merge_time,'Full-baseline review')
    verify_receipt_time(review_record,review_event)
    review_report=review_event['report']
    require(review_event['execution'].get('system') in ('local_cubic','separate_codex'),
            'Full-baseline review requires a non-authoring review execution')
    require(review_event.get('revision')==baseline and
            review_report.get('coverage')=='full-baseline' and
            review_report.get('reviewed_revision')==baseline and
            review_report.get('tree_sha')==tree and
            review_report.get('manifest_sha256')==manifest,
            'Independent full-baseline review does not cover the exact tree')
    verify_review_dispositions(review_report)
    require(_evidence_timestamp(review_record.get('created_at'))>
            _evidence_timestamp(merged_at),'Full-baseline review must inspect the corrected merge')
    chat_entry=admission.get('chatgpt_inspection')
    chat_record,chat_event=load_receipt_event(
        api.record,chat_entry,owner_id,'chatgpt_inspection',pr_number)
    chat_event=verify_execution_receipt(chat_event,'chatgpt_inspection',review_range)
    verify_execution_after(chat_event,merge_time,'ChatGPT inspection')
    verify_receipt_time(chat_record,chat_event)
    require(review_event['execution'].get('execution_id')!=
            chat_event['execution'].get('execution_id'),
            'Full-baseline review and ChatGPT inspection must be separate executions')
    chat_report=chat_event['report']
    require(chat_event['execution'].get('system')=='chatgpt' and
            chat_event.get('revision')==baseline and
            chat_report.get('coverage')=='full-baseline' and
            chat_report.get('reviewed_revision')==baseline and
            chat_report.get('tree_sha')==tree and chat_report.get('manifest_sha256')==manifest and
            isinstance(chat_report.get('source_files'),list) and chat_report['source_files'] and
            isinstance(chat_report.get('test_files'),list) and chat_report['test_files'],
            'ChatGPT inspection does not cover the exact full baseline')
    verify_inspection_files(root,baseline,chat_report,base_revision=parents[0])
    require(all(name in chat_event['execution'].get('stdout','')+
                chat_event['execution'].get('stderr','')
                for name in chat_report['source_files']+chat_report['test_files']),
            'ChatGPT baseline transcript omits inspected source or test files')
    require(_evidence_timestamp(chat_record.get('created_at'))>
            _evidence_timestamp(merged_at),'ChatGPT must inspect the corrected merge')
    ci_entry=require_present(admission.get('ci'),'Baseline CI provider receipt is missing')
    require(isinstance(ci_entry,dict),'Baseline CI provider receipt is malformed')
    require_present(ci_entry.get('ref'),'Baseline CI provider reference is missing')
    require_present(ci_entry.get('sha256'),'Baseline CI provider digest is missing')
    ci_record=api.record(ci_entry.get('ref'))
    require(digest(canonical(ci_record))==ci_entry.get('sha256'),
            'Baseline CI provider record changed')
    require(ci_record.get('repository',{}).get('full_name')==REPOSITORY and
            ci_record.get('event')=='pull_request' and ci_record.get('status')=='completed' and
            ci_record.get('conclusion')=='success' and
            ci_record.get('head_sha')==pr.get('head',{}).get('sha') and
            ci_record.get('run_attempt')==ci_entry.get('run_attempt') and
            ci_record.get('completed_at'),
            'Successful correction PR CI bound to the baseline is required')
    tested=ci_entry.get('tested_revision')
    require(parents and ci_entry.get('tested_base_revision')==parents[0],
            'Baseline CI tested base differs from corrected integration base')
    tested_record,test_strategy=verify_ci_test_commit(
        api.record,root,ci_record,pr_number,tested,pr.get('head',{}).get('sha'),
        parents[0],baseline)
    require(tested_record.get('tree',{}).get('sha')==tree,
            'Baseline CI tested tree differs from the exact admitted source')
    jobs=api.ci_jobs(ci_record['id'],ci_entry['run_attempt'])
    required=[job for job in jobs if job.get('name')=='Validate committed PR integration diff']
    if not required:
        raise MissingEvidenceError('Required completed baseline CI job is unavailable')
    require(len(required)==1,'Baseline CI job identity is ambiguous')
    require(required[0].get('conclusion')=='success',
            'Baseline CI job did not succeed')
    job_status=require_present(required[0].get('status'),
                               'Baseline CI job completion status is missing')
    if job_status in ('queued','in_progress'):
        raise MissingEvidenceError('Required completed baseline CI job is unavailable')
    require(job_status=='completed','Baseline CI job did not complete')
    require_present(required[0].get('completed_at'),
                    'Required completed baseline CI job completion time is missing')
    steps=required[0].get('steps',[])
    require(steps and all(step.get('conclusion')=='success' for step in steps),
            'Baseline CI contains failed or skipped steps')
    verify_ci_job_identity(ci_record,required[0],ci_entry['run_attempt'],steps)
    logs=api.job_log(required[0]['id'])
    for label,value in (('PR HEAD',pr['head']['sha']),
                        ('Tested integration revision',tested),
                        ('Tested base revision',parents[0])):
        require(label+': '+value in logs,'Baseline CI identity missing: '+label)
    manifest_file=json.loads(git(root,'show',baseline+':skills/distribution.json'))
    workflow=git(root,'show',baseline+':.github/workflows/ci.yml').decode()
    verify_ci_suites(logs,manifest_file.get('schema_version'),steps,workflow)
    owner_entry=admission.get('owner_admission')
    owner_record,owner_event=load_receipt_event(
        api.record,owner_entry,owner_id,'baseline_admission',pr_number)
    owner_report=owner_event.get('report',{})
    require(owner_event.get('revision')==baseline and
            owner_report.get('action')=='admit-baseline' and
            owner_report.get('verdict')=='approve',
            'Explicit owner baseline admission required')
    qualification_records=[review_record,chat_record,ci_record,required[0]]
    verify_event_chronology(qualification_records,owner_record.get('created_at'))
    binding=require_present(evidence.get('readiness_index'),
                            'Prospective baseline readiness index binding is missing')
    require(isinstance(binding,dict),'Prospective baseline readiness index binding required')
    index_ref=binding.get('normalization_ref') or binding.get('index_ref')
    require_present(index_ref,'Prospective baseline readiness index reference is missing')
    loaded=load_readiness_index(index_ref,api.record,pr_number)
    require(loaded['normalization_record'] is None and
            readiness_index_binding(loaded)==binding,
            'Prospective baseline readiness index provider binding changed')
    import copy
    indexed_evidence=copy.deepcopy(loaded['evidence'])
    admitted_evidence=copy.deepcopy(evidence);admitted_evidence.pop('readiness_index')
    require(canonical(indexed_evidence)==canonical(admitted_evidence),
            'Prospective baseline index differs from admitted evidence')
    verify_event_chronology([*qualification_records,owner_record],
                            loaded['original_record'].get('created_at'))
    snapshots=[]
    for gate,entry,record in (('baseline_review',review_entry,review_record),
                              ('chatgpt_inspection',chat_entry,chat_record),
                              ('ci',ci_entry,ci_record),
                              ('baseline_admission',owner_entry,owner_record)):
        snapshots.append({'gate':gate,'ref':entry['ref'],'sha256':entry['sha256'],
                          'record':record})
    snapshots.extend([
        {'gate':'readiness_index','ref':loaded['original_ref'],
         'sha256':loaded['original_sha256'],'record':loaded['original_record']},
        {'gate':'tested_commit','ref':BASE+'/commits/'+tested,
         'sha256':digest(canonical(tested_record)),'record':tested_record},
        {'gate':'corrected_merge','ref':BASE+f'/pulls/{pr_number}',
         'sha256':digest(canonical(pr)),'record':pr},
        {'gate':'ci_job','ref':str(required[0]['id']),
         'sha256':digest(canonical(required[0])),'record':required[0]},
        {'gate':'ci_log','ref':str(required[0]['id']),'sha256':digest(logs.encode()),'record':logs},
    ])
    evidence_hash=digest(canonical(evidence))
    tested_commit={'reviewed_revision':pr.get('head',{}).get('sha'),
                   'base_revision':parents[0],'tested_revision':tested,
                   'strategy':test_strategy,'record':tested_record}
    if dispatch_run_id is None:
        return BaselineQualification(snapshots,baseline,source,builder,evidence_hash,
                                     tested_commit)
    dispatch=api.run(int(dispatch_run_id))
    require(type(dispatch.get('id')) is int and dispatch['id']==int(dispatch_run_id) and
            dispatch.get('event')=='workflow_dispatch' and
            dispatch.get('head_sha')==baseline and
            dispatch.get('head_branch')=='main' and
            dispatch.get('actor',{}).get('id')==owner_id and
            dispatch.get('triggering_actor',{}).get('id')==owner_id and
            dispatch.get('path','').split('@')[0]=='.github/workflows/skill-release.yml',
            'Original first-release dispatch is not bound to the admitted baseline')
    require(_evidence_timestamp(owner_record.get('updated_at'))<
            _evidence_timestamp(dispatch.get('created_at')),
            'Owner baseline admission must precede the original release dispatch')
    verify_event_chronology([loaded['original_record']],dispatch.get('created_at'))
    snapshots.append({'gate':'release_dispatch','ref':str(dispatch_run_id),
                      'sha256':digest(canonical(dispatch)),'record':dispatch})
    main_ref_name=BASE+'/git/ref/heads/main'
    main_ref=api.record(main_ref_name)
    main_object=main_ref.get('object',{})
    require(main_ref.get('ref')=='refs/heads/main' and
            main_object.get('type')=='commit' and
            revision(root,main_object.get('sha'))==baseline,
            'Main must remain exactly at the admitted baseline through original release dispatch')
    snapshots.append({'gate':'baseline_main_ref','ref':main_ref_name,
                      'sha256':digest(canonical(main_ref)),
                      'record':main_ref})
    return VerifiedBaselineAdmission(snapshots,baseline,source,builder,int(dispatch_run_id),
                                     evidence_hash,tested_commit)
