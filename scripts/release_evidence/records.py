"""Provider-bound execution, readiness, chronology, and CI evidence records."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml

from .common import (
    BASE, JSON, REPOSITORY, SHA, SUITES, ReleaseError, _EvidenceAPI, _utc_now, canonical,
    digest, git, require,
)

def _readiness_payload(reference,record,owner_id,pull_request):
    match=re.fullmatch(re.escape(BASE)+r'/issues/comments/([1-9][0-9]*)',reference or '')
    require(match is not None and record.get('id')==int(match[1]),
            'Readiness index provider record identity mismatch')
    require(record.get('user',{}).get('id')==owner_id,
            'Readiness index must be owner-authenticated')
    _require_pull_request_comment(record,pull_request,'Readiness index')
    marker='<!-- release-readiness\n';body=record.get('body','')
    require(body.count(marker)==1 and '\n-->' in body,
            'Inspectable release-readiness index required')
    try: payload=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
    except (ValueError,IndexError) as error:
        raise ReleaseError('Malformed release-readiness index') from error
    require(payload.get('schema_version')==2 and payload.get('repository')==REPOSITORY and
            payload.get('pull_request')==pull_request,
            'Readiness index schema, repository or pull request mismatch')
    evidence=payload.get('evidence')
    require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'Readiness index evidence payload missing')
    return payload,evidence

def _require_pull_request_comment(record,pull_request,gate):
    require(type(pull_request) is int and pull_request>0 and
            record.get('issue_url')==BASE+f'/issues/{pull_request}',
            f'{gate} provider record belongs to a different pull request')

def _readiness_before_merge(evidence):
    """Compare premerge and normalized payloads after allowed merge fields."""
    import copy
    comparable=copy.deepcopy(evidence)
    for integration in comparable.get('integrations',[]):
        integration.pop('integrated_revision',None)
        integration.pop('integrated_commits',None)
    return canonical(comparable)

def load_readiness_index(reference,fetch,pull_request):
    """Load an original readiness index or authenticate its safe normalization.

    The original owner-authored provider comment remains immutable evidence.
    A later owner-authored index may add the actual merge SHA and commit
    membership only, and must bind the exact original provider record digest.
    """
    repository=fetch(BASE)
    owner_id=repository.get('owner',{}).get('id')
    require(repository.get('full_name')==REPOSITORY and owner_id is not None,
            'Readiness index repository owner unavailable')
    record=fetch(reference)
    payload,evidence=_readiness_payload(reference,record,owner_id,pull_request)
    normalization=payload.get('normalizes')
    if normalization is None:
        for integration in evidence.get('integrations',[]):
            require('integrated_revision' not in integration and
                    'integrated_commits' not in integration,
                    'Premerge readiness index contains post-merge identity')
        original_record=record;original_reference=reference
    else:
        require(isinstance(normalization,dict) and
                set(normalization)=={'ref','sha256'},
                'Readiness normalization origin reference malformed')
        original_reference=normalization['ref']
        original_record=fetch(original_reference)
        require(digest(canonical(original_record))==normalization['sha256'],
                'Original readiness record digest mismatch')
        original_payload,original_evidence=_readiness_payload(original_reference,original_record,owner_id,pull_request)
        require(original_payload.get('normalizes') is None,
                'Readiness normalization chain is not allowed')
        for integration in original_evidence.get('integrations',[]):
            require('integrated_revision' not in integration and
                    'integrated_commits' not in integration,
                    'Original readiness index already contains merge identity')
        require(_readiness_before_merge(evidence)==_readiness_before_merge(original_evidence),
                'Readiness normalization changed premerge evidence')
        originals={item.get('pull_request'):item for item in original_evidence.get('integrations',[])}
        normalized={item.get('pull_request'):item for item in evidence.get('integrations',[])}
        require(len(originals)==len(original_evidence.get('integrations',[])) and
                len(normalized)==len(evidence.get('integrations',[])) and
                originals.keys()==normalized.keys(),
                'Readiness normalization integration identities changed')
        for number,item in normalized.items():
            before=originals[number]
            require(item.get('integrated_revision') is not None and
                    SHA.fullmatch(item.get('integrated_revision','')) and
                    isinstance(item.get('integrated_commits'),list) and
                    item['integrated_commits'] and
                    item['integrated_commits'][-1]==item['integrated_revision'] and
                    'integrated_revision' not in before and 'integrated_commits' not in before,
                    'Readiness normalization merge identity is incomplete')
    return {'evidence':evidence,'original_record':original_record,
            'original_ref':original_reference,
            'original_sha256':digest(canonical(original_record)),
            'index_record':record,'index_ref':reference,
            'index_sha256':digest(canonical(record)),
            'normalization_record':record if normalization is not None else None,
            'normalization_ref':reference if normalization is not None else None,
            'normalization_sha256':digest(canonical(record)) if normalization is not None else None}

def readiness_index_binding(loaded):
    return {'index_ref':loaded['index_ref'],'index_sha256':loaded['index_sha256'],
            'original_ref':loaded['original_ref'],'original_sha256':loaded['original_sha256'],
            'normalization_ref':loaded['normalization_ref'],
            'normalization_sha256':loaded['normalization_sha256']}

def capture_execution(root: RepositoryPath, gate: str,
                      system: str, command: Sequence[str], report: JSON,
                      reviewed_range: JSON,
                      transcript: str | Path | None = None) -> JSON:
    """Capture an owner-attested execution transcript in a controller receipt."""
    require(gate in ('author_execution','independent_review','chatgpt_inspection',
                     'baseline_review'), 'Unsupported captured execution gate')
    require(system in ('local_cubic','separate_codex','chatgpt'),
            'Unsupported captured execution system')
    require(isinstance(report,dict) and isinstance(report.get('summary'),str) and
            report['summary'],'Structured execution report summary required')
    require(isinstance(reviewed_range,dict),'Reviewed revision range required')
    started=_utc_now()
    if transcript is not None:
        require(gate=='chatgpt_inspection' and system=='chatgpt' and
                isinstance(transcript,str) and transcript,
                'Transcript import is reserved for direct ChatGPT inspection')
        command=['chatgpt','inspection-transcript'];stdout=transcript;stderr='';exit_code=0
    else:
        require(isinstance(command,list) and command and
                all(isinstance(value,str) and value for value in command),
                'Captured command required')
        result=subprocess.run(command,cwd=root,capture_output=True,text=True,check=False)
        stdout=result.stdout;stderr=result.stderr;exit_code=result.returncode
    finished=_utc_now()
    require(report['summary'] in stdout+stderr,
            'Report summary must appear in the captured execution transcript')
    if gate=='independent_review':
        step=report.get('review_step')
        require(isinstance(step,dict),'Structured independent review step required')
        expected={'base_revision':step.get('base_revision'),
                  'head_revision':step.get('head_revision')}
        if step.get('uncommitted_candidate') is True:
            expected['diff_sha256']=step.get('diff_sha256')
    elif gate=='baseline_review':
        expected={'baseline_revision':reviewed_range.get('baseline_revision'),
                  'tree_sha':reviewed_range.get('tree_sha')}
    elif gate=='chatgpt_inspection' and 'baseline_revision' in reviewed_range:
        expected={'baseline_revision':reviewed_range.get('baseline_revision'),
                  'tree_sha':reviewed_range.get('tree_sha')}
    else:
        expected={'base_revision':reviewed_range.get('base_revision'),
                  'head_revision':reviewed_range.get('head_revision')}
    if gate=='chatgpt_inspection':
        reviewed_revision=expected.get('head_revision') or reviewed_range.get('baseline_revision')
        names=report.get('source_files',[])+report.get('test_files',[])
        require(names,'ChatGPT source and test inspection coverage required')
        require(all(name in stdout+stderr for name in names),
                'ChatGPT transcript does not name every inspected file')
        file_hashes={name:digest(git(root,'show',reviewed_revision+':'+name)) for name in names}
        if report.get('file_sha256'):
            require(report['file_sha256']==file_hashes,
                    'ChatGPT inspection file digest differs from the reviewed commit')
        report['file_sha256']=file_hashes
    execution={'system':system,'origin_status':'owner_attested','command':command,
        'exit_code':exit_code,'started_at':started,'finished_at':finished,
        'stdout':stdout,'stderr':stderr,'stdout_sha256':digest(stdout.encode()),
        'stderr_sha256':digest(stderr.encode()),'reviewed_range':expected}
    execution['execution_id']=digest(canonical(execution))
    report=dict(report,execution_id=execution['execution_id'],
                verdict='pass' if exit_code==0 else 'fail')
    event={'schema_version':2,'repository':REPOSITORY,'gate':gate,
           'revision':reviewed_range.get('head_revision') or
                      reviewed_range.get('baseline_revision'),
           'execution':execution,'report':report,
           'report_sha256':digest(canonical(report))}
    body='<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->'
    return {'event':event,'body':body,'exit_code':exit_code}

def build_owner_receipt(gate: str, revision_id: str) -> str:
    require(gate in ('owner_authorization','baseline_admission'),
            'Unsupported owner authorization receipt')
    require(SHA.fullmatch(revision_id or ''),'Full owner-authorized revision required')
    action='merge' if gate=='owner_authorization' else 'admit-baseline'
    report={'action':action,'verdict':'approve'}
    event={'schema_version':2,'repository':REPOSITORY,'gate':gate,
           'revision':revision_id,'report':report,
           'report_sha256':digest(canonical(report))}
    return '<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->'

def _bind_provider_entry(entry,api,owner_id,pull_request,*,owner_comment):
    require(isinstance(entry,dict) and isinstance(entry.get('ref'),str),
            'Provider receipt reference required')
    record=api.record(entry['ref'])
    if owner_comment:
        require(record.get('user',{}).get('id')==owner_id,
                'Execution receipt must be posted by the repository owner')
        _require_pull_request_comment(record,pull_request,'Evidence receipt')
    else:
        require(record.get('repository',{}).get('full_name')==REPOSITORY,
                'CI record belongs to a different repository')
    value=digest(canonical(record))
    require(not entry.get('sha256') or entry['sha256']==value,
            'Supplied provider record digest is stale')
    entry['sha256']=value
    return record

def prepare_readiness_index(evidence: JSON,
                            pull_request: int, api: _EvidenceAPI, *,
                            normalizes_reference: str | None = None) -> str:
    """Bind posted receipts to current GitHub records and render an index body."""
    import copy
    evidence=copy.deepcopy(evidence)
    evidence.pop('readiness_index',None)
    for integration in evidence.get('integrations',[]):
        integration.pop('readiness_index',None)
    require(type(pull_request) is int and pull_request>0,'Pull request number required')
    user=api.request('GET','/user')
    require(user.get('login')=='danielbyon',
            'Read-only index credential must authenticate as danielbyon')
    repository=api.record(BASE)
    owner_id=repository.get('owner',{}).get('id')
    require(repository.get('full_name')==REPOSITORY and
            repository.get('owner',{}).get('login')=='danielbyon' and owner_id is not None,
            'Readiness index repository owner mismatch')
    require(isinstance(evidence,dict) and evidence.get('schema_version')==2 and
            evidence.get('owner_id')==owner_id,
            'Schema v2 owner-authenticated evidence required')
    origin=evidence.get('origin',{}).get('kind')
    if origin=='ordinary':
        integrations=evidence.get('integrations')
        require(isinstance(integrations,list) and len(integrations)==1 and
                integrations[0].get('pull_request')==pull_request,
                'Ordinary readiness index must cover exactly its pull request')
        integration=integrations[0];records=integration.get('records',{})
        author=_bind_provider_entry(records.get('author_execution'),api,owner_id,
                                    pull_request,owner_comment=True)
        review_entries=records.get('independent_reviews')
        if review_entries is None and isinstance(records.get('independent_review'),dict):
            review_entries=[records['independent_review']]
        require(isinstance(review_entries,list) and review_entries,
                'Independent review receipt references required')
        reviews=[_bind_provider_entry(entry,api,owner_id,pull_request,owner_comment=True)
                 for entry in review_entries]
        chat=_bind_provider_entry(records.get('chatgpt_inspection'),api,owner_id,
                                  pull_request,owner_comment=True)
        owner=_bind_provider_entry(records.get('owner_authorization'),api,owner_id,
                                   pull_request,owner_comment=True)
        ci_entry=records.get('ci');ci=_bind_provider_entry(ci_entry,api,owner_id,
                                                           pull_request,owner_comment=False)
        require(ci.get('run_attempt')==ci_entry.get('run_attempt') and
                ci.get('head_sha')==integration.get('reviewed_revision'),
                'CI attempt or reviewed head differs from the evidence index')
        verify_ci_pull_request(ci,pull_request,integration.get('reviewed_revision'),
                               integration.get('base_revision'))
        require(integration.get('reviewed_revision') and integration.get('base_revision'),
                'Ordinary integration revisions required')
        if normalizes_reference:
            loaded=load_readiness_index(normalizes_reference,api.record,pull_request)
            require(loaded['normalization_record'] is None,
                    'A normalization cannot normalize another normalization')
            pr=api.record(BASE+f'/pulls/{pull_request}')
            require(pr.get('merged_at'),'Post-merge normalization requires actual merge metadata')
            verify_event_chronology([loaded['original_record']],pr['merged_at'])
            require(_readiness_before_merge(evidence)==
                    _readiness_before_merge(loaded['evidence']),
                    'Readiness normalization changed premerge evidence')
            normalization={'ref':loaded['original_ref'],
                           'sha256':loaded['original_sha256']}
        else:
            require(all('integrated_revision' not in item and
                        'integrated_commits' not in item for item in integrations),
                    'Premerge readiness index cannot claim a merge identity')
            normalization=None
    elif origin=='prospective_baseline':
        require(evidence.get('integrations')==[] and
                evidence.get('baseline_admission',{}).get('correction_pull_request')==pull_request,
                'Prospective baseline index must identify its corrected merge PR')
        admission=evidence['baseline_admission']
        _bind_provider_entry(admission.get('full_review'),api,owner_id,
                             pull_request,owner_comment=True)
        _bind_provider_entry(admission.get('chatgpt_inspection'),api,owner_id,
                             pull_request,owner_comment=True)
        ci_entry=admission.get('ci');ci=_bind_provider_entry(ci_entry,api,owner_id,
                                                            pull_request,owner_comment=False)
        _bind_provider_entry(admission.get('owner_admission'),api,owner_id,
                             pull_request,owner_comment=True)
        require(ci.get('head_sha')==admission.get('reviewed_revision') and
                ci.get('run_attempt')==ci_entry.get('run_attempt'),
                'Baseline CI identity differs from its correction PR')
        verify_ci_pull_request(ci,pull_request,admission.get('reviewed_revision'),
                               ci_entry.get('tested_base_revision'))
        normalization=None
    else:
        raise ReleaseError('Unsupported readiness index origin')
    wrapper={'schema_version':2,'repository':REPOSITORY,
             'pull_request':pull_request,'evidence':evidence}
    if normalization is not None: wrapper['normalizes']=normalization
    body='<!-- release-readiness\n'+json.dumps(wrapper,sort_keys=True)+'\n-->'
    return body

def _evidence_timestamp(value):
    require(isinstance(value,str) and value,'Provider timestamp required')
    if value.endswith('Z'):
        require(value.count('Z')==1,'Invalid provider timestamp')
        value=value[:-1]+'+00:00'
    else:
        require('Z' not in value,'Invalid provider timestamp')
    try:
        parsed=datetime.fromisoformat(value)
    except ValueError as error:
        raise ReleaseError('Invalid provider timestamp') from error
    require(parsed.tzinfo is not None,'Provider timestamp must include a timezone')
    return parsed.astimezone(timezone.utc)

def verify_event_chronology(provider_records,cutoff):
    """Require immutable provider records to predate a trusted cutoff."""
    cutoff=_evidence_timestamp(cutoff)
    require(isinstance(provider_records,list) and provider_records,'Provider records required')
    for record in provider_records:
        require(isinstance(record,dict),'Provider record required')
        created_value=record.get('created_at') or record.get('started_at')
        updated_value=record.get('updated_at') or record.get('completed_at')
        created=_evidence_timestamp(created_value)
        updated=_evidence_timestamp(updated_value)
        require(created<cutoff,'Evidence created at or after the integration')
        require(updated<cutoff,'Evidence record updated after the integration')
        if record.get('completed_at'):
            require(_evidence_timestamp(record['completed_at'])<cutoff,
                    'CI completed after the integration')
    return True

def verify_ci_pull_request(ci_record,pull_request,head_revision,base_revision):
    """Bind a successful Actions run to the exact PR, head and tested base."""
    relationships=ci_record.get('pull_requests')
    require(isinstance(relationships,list),'CI pull request identity unavailable')
    matches=[item for item in relationships if item.get('number')==pull_request]
    require(len(matches)==1,'CI run does not identify the exact pull request')
    relation=matches[0]
    require(relation.get('head',{}).get('sha')==head_revision and
            relation.get('base',{}).get('ref')=='main' and
            relation.get('base',{}).get('sha')==base_revision,
            'CI pull request head or base identity mismatch')
    return True

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
