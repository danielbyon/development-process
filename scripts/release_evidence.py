"""Evidence provenance, chronology, admission and coverage validation."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

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

_BASELINE_ADMISSION_SEAL=object()
_BASELINE_QUALIFICATION_SEAL=object()

def _readiness_payload(ctx, reference,record,owner_id,pull_request):
    match=re.fullmatch(re.escape(ctx.BASE)+r'/issues/comments/([1-9][0-9]*)',reference or '')
    ctx.require(match is not None and record.get('id')==int(match[1]),
            'Readiness index provider record identity mismatch')
    ctx.require(record.get('user',{}).get('id')==owner_id,
            'Readiness index must be owner-authenticated')
    marker='<!-- release-readiness\n';body=record.get('body','')
    ctx.require(body.count(marker)==1 and '\n-->' in body,
            'Inspectable release-readiness index required')
    try: payload=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
    except (ValueError,IndexError) as error:
        raise ctx.ReleaseError('Malformed release-readiness index') from error
    ctx.require(payload.get('schema_version')==2 and payload.get('repository')==ctx.REPOSITORY and
            payload.get('pull_request')==pull_request,
            'Readiness index schema, repository or pull request mismatch')
    evidence=payload.get('evidence')
    ctx.require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'Readiness index evidence payload missing')
    return payload,evidence

def _readiness_before_merge(ctx, evidence):
    """Compare premerge and normalized payloads after allowed merge fields."""
    import copy
    comparable=copy.deepcopy(evidence)
    for integration in comparable.get('integrations',[]):
        integration.pop('integrated_revision',None)
        integration.pop('integrated_commits',None)
    return ctx.canonical(comparable)

def load_readiness_index(ctx, reference,fetch,pull_request):
    """Load an original readiness index or authenticate its safe normalization.

    The original owner-authored provider comment remains immutable evidence.
    A later owner-authored index may add the actual merge SHA and commit
    membership only, and must bind the exact original provider record digest.
    """
    repository=fetch(ctx.BASE)
    owner_id=repository.get('owner',{}).get('id')
    ctx.require(repository.get('full_name')==ctx.REPOSITORY and owner_id is not None,
            'Readiness index repository owner unavailable')
    record=fetch(reference)
    payload,evidence=_readiness_payload(ctx, reference,record,owner_id,pull_request)
    normalization=payload.get('normalizes')
    if normalization is None:
        for integration in evidence.get('integrations',[]):
            ctx.require('integrated_revision' not in integration and
                    'integrated_commits' not in integration,
                    'Premerge readiness index contains post-merge identity')
        original_record=record;original_reference=reference
    else:
        ctx.require(isinstance(normalization,dict) and
                set(normalization)=={'ref','sha256'},
                'Readiness normalization origin reference malformed')
        original_reference=normalization['ref']
        original_record=fetch(original_reference)
        ctx.require(ctx.digest(ctx.canonical(original_record))==normalization['sha256'],
                'Original readiness record digest mismatch')
        original_payload,original_evidence=_readiness_payload(ctx,
            original_reference,original_record,owner_id,pull_request)
        ctx.require(original_payload.get('normalizes') is None,
                'Readiness normalization chain is not allowed')
        for integration in original_evidence.get('integrations',[]):
            ctx.require('integrated_revision' not in integration and
                    'integrated_commits' not in integration,
                    'Original readiness index already contains merge identity')
        ctx.require(_readiness_before_merge(ctx, evidence)==_readiness_before_merge(ctx, original_evidence),
                'Readiness normalization changed premerge evidence')
        originals={item.get('pull_request'):item for item in original_evidence.get('integrations',[])}
        normalized={item.get('pull_request'):item for item in evidence.get('integrations',[])}
        ctx.require(len(originals)==len(original_evidence.get('integrations',[])) and
                len(normalized)==len(evidence.get('integrations',[])) and
                originals.keys()==normalized.keys(),
                'Readiness normalization integration identities changed')
        for number,item in normalized.items():
            before=originals[number]
            ctx.require(item.get('integrated_revision') is not None and
                    ctx.SHA.fullmatch(item.get('integrated_revision','')) and
                    isinstance(item.get('integrated_commits'),list) and
                    item['integrated_commits'] and
                    item['integrated_commits'][-1]==item['integrated_revision'] and
                    'integrated_revision' not in before and 'integrated_commits' not in before,
                    'Readiness normalization merge identity is incomplete')
    return {'evidence':evidence,'original_record':original_record,
            'original_ref':original_reference,
            'original_sha256':ctx.digest(ctx.canonical(original_record)),
            'index_record':record,'index_ref':reference,
            'index_sha256':ctx.digest(ctx.canonical(record)),
            'normalization_record':record if normalization is not None else None,
            'normalization_ref':reference if normalization is not None else None,
            'normalization_sha256':ctx.digest(ctx.canonical(record)) if normalization is not None else None}

def readiness_index_binding(ctx, loaded):
    return {'index_ref':loaded['index_ref'],'index_sha256':loaded['index_sha256'],
            'original_ref':loaded['original_ref'],'original_sha256':loaded['original_sha256'],
            'normalization_ref':loaded['normalization_ref'],
            'normalization_sha256':loaded['normalization_sha256']}

def capture_execution(ctx, root,gate,system,command,report,reviewed_range,transcript=None):
    """Capture an owner-attested execution transcript in a controller receipt."""
    ctx.require(gate in ('author_execution','independent_review','chatgpt_inspection',
                     'baseline_review'), 'Unsupported captured execution gate')
    ctx.require(system in ('local_cubic','separate_codex','chatgpt'),
            'Unsupported captured execution system')
    ctx.require(isinstance(report,dict) and isinstance(report.get('summary'),str) and
            report['summary'],'Structured execution report summary required')
    ctx.require(isinstance(reviewed_range,dict),'Reviewed revision range required')
    started=ctx.utc_now()
    if transcript is not None:
        ctx.require(gate=='chatgpt_inspection' and system=='chatgpt' and
                isinstance(transcript,str) and transcript,
                'Transcript import is reserved for direct ChatGPT inspection')
        command=['chatgpt','inspection-transcript'];stdout=transcript;stderr='';exit_code=0
    else:
        ctx.require(isinstance(command,list) and command and
                all(isinstance(value,str) and value for value in command),
                'Captured command required')
        result=subprocess.run(command,cwd=root,capture_output=True,text=True,check=False)
        stdout=result.stdout;stderr=result.stderr;exit_code=result.returncode
    finished=ctx.utc_now()
    ctx.require(report['summary'] in stdout+stderr,
            'Report summary must appear in the captured execution transcript')
    if gate=='independent_review':
        step=report.get('review_step')
        ctx.require(isinstance(step,dict),'Structured independent review step required')
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
        ctx.require(names,'ChatGPT source and test inspection coverage required')
        ctx.require(all(name in stdout+stderr for name in names),
                'ChatGPT transcript does not name every inspected file')
        file_hashes={name:ctx.digest(ctx.git(root,'show',reviewed_revision+':'+name)) for name in names}
        if report.get('file_sha256'):
            ctx.require(report['file_sha256']==file_hashes,
                    'ChatGPT inspection file digest differs from the reviewed commit')
        report['file_sha256']=file_hashes
    execution={'system':system,'origin_status':'owner_attested','command':command,
        'exit_code':exit_code,'started_at':started,'finished_at':finished,
        'stdout':stdout,'stderr':stderr,'stdout_sha256':ctx.digest(stdout.encode()),
        'stderr_sha256':ctx.digest(stderr.encode()),'reviewed_range':expected}
    execution['execution_id']=ctx.digest(ctx.canonical(execution))
    report=dict(report,execution_id=execution['execution_id'],
                verdict='pass' if exit_code==0 else 'fail')
    event={'schema_version':2,'repository':ctx.REPOSITORY,'gate':gate,
           'revision':reviewed_range.get('head_revision') or
                      reviewed_range.get('baseline_revision'),
           'execution':execution,'report':report,
           'report_sha256':ctx.digest(ctx.canonical(report))}
    body='<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->'
    return {'event':event,'body':body,'exit_code':exit_code}

def build_owner_receipt(ctx, gate,revision_id):
    ctx.require(gate in ('owner_authorization','baseline_admission'),
            'Unsupported owner authorization receipt')
    ctx.require(ctx.SHA.fullmatch(revision_id or ''),'Full owner-authorized revision required')
    action='merge' if gate=='owner_authorization' else 'admit-baseline'
    report={'action':action,'verdict':'approve'}
    event={'schema_version':2,'repository':ctx.REPOSITORY,'gate':gate,
           'revision':revision_id,'report':report,
           'report_sha256':ctx.digest(ctx.canonical(report))}
    return '<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->'

def _bind_provider_entry(ctx, entry,api,owner_id,*,owner_comment):
    ctx.require(isinstance(entry,dict) and isinstance(entry.get('ref'),str),
            'Provider receipt reference required')
    record=api.record(entry['ref'])
    if owner_comment:
        ctx.require(record.get('user',{}).get('id')==owner_id,
                'Execution receipt must be posted by the repository owner')
    else:
        ctx.require(record.get('repository',{}).get('full_name')==ctx.REPOSITORY,
                'CI record belongs to a different repository')
    value=ctx.digest(ctx.canonical(record))
    ctx.require(not entry.get('sha256') or entry['sha256']==value,
            'Supplied provider record digest is stale')
    entry['sha256']=value
    return record

def prepare_readiness_index(ctx, evidence,pull_request,api,*,normalizes_reference=None):
    """Bind posted receipts to current GitHub records and render an index body."""
    import copy
    evidence=copy.deepcopy(evidence)
    evidence.pop('readiness_index',None)
    for integration in evidence.get('integrations',[]):
        integration.pop('readiness_index',None)
    ctx.require(type(pull_request) is int and pull_request>0,'Pull request number required')
    user=api.request('GET','/user')
    ctx.require(user.get('login')=='danielbyon',
            'Read-only index credential must authenticate as danielbyon')
    repository=api.record(ctx.BASE)
    owner_id=repository.get('owner',{}).get('id')
    ctx.require(repository.get('full_name')==ctx.REPOSITORY and
            repository.get('owner',{}).get('login')=='danielbyon' and owner_id is not None,
            'Readiness index repository owner mismatch')
    ctx.require(isinstance(evidence,dict) and evidence.get('schema_version')==2 and
            evidence.get('owner_id')==owner_id,
            'Schema v2 owner-authenticated evidence required')
    origin=evidence.get('origin',{}).get('kind')
    if origin=='ordinary':
        integrations=evidence.get('integrations')
        ctx.require(isinstance(integrations,list) and len(integrations)==1 and
                integrations[0].get('pull_request')==pull_request,
                'Ordinary readiness index must cover exactly its pull request')
        integration=integrations[0];records=integration.get('records',{})
        author=_bind_provider_entry(ctx, records.get('author_execution'),api,owner_id,owner_comment=True)
        review_entries=records.get('independent_reviews')
        if review_entries is None and isinstance(records.get('independent_review'),dict):
            review_entries=[records['independent_review']]
        ctx.require(isinstance(review_entries,list) and review_entries,
                'Independent review receipt references required')
        reviews=[_bind_provider_entry(ctx, entry,api,owner_id,owner_comment=True)
                 for entry in review_entries]
        chat=_bind_provider_entry(ctx, records.get('chatgpt_inspection'),api,owner_id,owner_comment=True)
        owner=_bind_provider_entry(ctx, records.get('owner_authorization'),api,owner_id,owner_comment=True)
        ci_entry=records.get('ci');ci=_bind_provider_entry(ctx, ci_entry,api,owner_id,owner_comment=False)
        ctx.require(ci.get('run_attempt')==ci_entry.get('run_attempt') and
                ci.get('head_sha')==integration.get('reviewed_revision'),
                'CI attempt or reviewed head differs from the evidence index')
        verify_ci_pull_request(ctx, ci,pull_request,integration.get('reviewed_revision'),
                               integration.get('base_revision'))
        ctx.require(integration.get('reviewed_revision') and integration.get('base_revision'),
                'Ordinary integration revisions required')
        if normalizes_reference:
            loaded=load_readiness_index(ctx, normalizes_reference,api.record,pull_request)
            ctx.require(loaded['normalization_record'] is None,
                    'A normalization cannot normalize another normalization')
            pr=api.record(ctx.BASE+f'/pulls/{pull_request}')
            ctx.require(pr.get('merged_at'),'Post-merge normalization requires actual merge metadata')
            verify_event_chronology(ctx, [loaded['original_record']],pr['merged_at'])
            ctx.require(_readiness_before_merge(ctx, evidence)==
                    _readiness_before_merge(ctx, loaded['evidence']),
                    'Readiness normalization changed premerge evidence')
            normalization={'ref':loaded['original_ref'],
                           'sha256':loaded['original_sha256']}
        else:
            ctx.require(all('integrated_revision' not in item and
                        'integrated_commits' not in item for item in integrations),
                    'Premerge readiness index cannot claim a merge identity')
            normalization=None
    elif origin=='prospective_baseline':
        ctx.require(evidence.get('integrations')==[] and
                evidence.get('baseline_admission',{}).get('correction_pull_request')==pull_request,
                'Prospective baseline index must identify its corrected merge PR')
        admission=evidence['baseline_admission']
        _bind_provider_entry(ctx, admission.get('full_review'),api,owner_id,owner_comment=True)
        _bind_provider_entry(ctx, admission.get('chatgpt_inspection'),api,owner_id,owner_comment=True)
        ci_entry=admission.get('ci');ci=_bind_provider_entry(ctx, ci_entry,api,owner_id,owner_comment=False)
        _bind_provider_entry(ctx, admission.get('owner_admission'),api,owner_id,owner_comment=True)
        ctx.require(ci.get('head_sha')==admission.get('reviewed_revision') and
                ci.get('run_attempt')==ci_entry.get('run_attempt'),
                'Baseline CI identity differs from its correction PR')
        verify_ci_pull_request(ctx, ci,pull_request,admission.get('reviewed_revision'),
                               ci_entry.get('tested_base_revision'))
        normalization=None
    else:
        raise ctx.ReleaseError('Unsupported readiness index origin')
    wrapper={'schema_version':2,'repository':ctx.REPOSITORY,
             'pull_request':pull_request,'evidence':evidence}
    if normalization is not None: wrapper['normalizes']=normalization
    body='<!-- release-readiness\n'+json.dumps(wrapper,sort_keys=True)+'\n-->'
    return body

def _evidence_timestamp(ctx, value):
    ctx.require(isinstance(value,str) and value,'Provider timestamp required')
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as error:
        raise ctx.ReleaseError('Invalid provider timestamp') from error
    ctx.require(parsed.tzinfo is not None,'Provider timestamp must include a timezone')
    return parsed.astimezone(timezone.utc)

def verify_event_chronology(ctx, provider_records,cutoff):
    """Require immutable provider records to predate a trusted cutoff."""
    cutoff=_evidence_timestamp(ctx, cutoff)
    ctx.require(isinstance(provider_records,list) and provider_records,'Provider records required')
    for record in provider_records:
        ctx.require(isinstance(record,dict),'Provider record required')
        created_value=record.get('created_at') or record.get('started_at')
        updated_value=record.get('updated_at') or record.get('completed_at')
        created=_evidence_timestamp(ctx, created_value)
        updated=_evidence_timestamp(ctx, updated_value)
        ctx.require(created<cutoff,'Evidence created at or after the integration')
        ctx.require(updated<cutoff,'Evidence record updated after the integration')
        if record.get('completed_at'):
            ctx.require(_evidence_timestamp(ctx, record['completed_at'])<cutoff,
                    'CI completed after the integration')
    return True

def verify_ci_pull_request(ctx, ci_record,pull_request,head_revision,base_revision):
    """Bind a successful Actions run to the exact PR, head and tested base."""
    relationships=ci_record.get('pull_requests')
    ctx.require(isinstance(relationships,list),'CI pull request identity unavailable')
    matches=[item for item in relationships if item.get('number')==pull_request]
    ctx.require(len(matches)==1,'CI run does not identify the exact pull request')
    relation=matches[0]
    ctx.require(relation.get('head',{}).get('sha')==head_revision and
            relation.get('base',{}).get('ref')=='main' and
            relation.get('base',{}).get('sha')==base_revision,
            'CI pull request head or base identity mismatch')
    return True

def verify_execution_receipt(ctx, event,gate,reviewed_range):
    """Bind a claimed execution to captured command output and its review range.

    The owner-authenticated receipt records an attestation about local output;
    the derived identity prevents an unattached arbitrary execution label from
    being substituted for that captured content.
    """
    ctx.require(isinstance(event,dict) and event.get('schema_version')==2,
            'Evidence schema v2 receipt required')
    ctx.require(event.get('repository')==ctx.REPOSITORY and event.get('gate')==gate,
            'Evidence receipt repository/gate mismatch')
    execution=event.get('execution'); report=event.get('report')
    ctx.require(isinstance(execution,dict) and isinstance(report,dict),
            'Captured execution and structured report required')
    ctx.require(execution.get('origin_status')=='owner_attested',
            'Execution origin must be explicitly owner-attested')
    ctx.require(execution.get('system') in ('local_cubic','separate_codex','chatgpt'),
            'Unsupported execution system')
    command=execution.get('command')
    ctx.require(isinstance(command,list) and command and all(isinstance(x,str) and x for x in command),
            'Captured execution command required')
    ctx.require(type(execution.get('exit_code')) is int and execution['exit_code']==0,
            'Captured execution did not succeed')
    stdout=execution.get('stdout'); stderr=execution.get('stderr')
    ctx.require(isinstance(stdout,str) and isinstance(stderr,str) and (stdout or stderr),
            'Captured execution output required')
    ctx.require(execution.get('stdout_sha256')==ctx.digest(stdout.encode()),
            'Captured execution output digest mismatch')
    if 'stderr_sha256' in execution:
        ctx.require(execution.get('stderr_sha256')==ctx.digest(stderr.encode()),
                'Captured error output digest mismatch')
    start=_evidence_timestamp(ctx, execution.get('started_at'))
    finish=_evidence_timestamp(ctx, execution.get('finished_at'))
    ctx.require(start<=finish,'Execution timestamps are reversed')
    identity={key:value for key,value in execution.items() if key!='execution_id'}
    execution_id=ctx.digest(ctx.canonical(identity))
    ctx.require(execution.get('execution_id')==execution_id,
            'Captured execution identity mismatch')
    ctx.require(execution.get('reviewed_range')==reviewed_range,
            'Execution reviewed range mismatch')
    ctx.require(report.get('execution_id')==execution_id and report.get('verdict')=='pass',
            'Execution report identity/verdict mismatch')
    ctx.require(isinstance(report.get('summary'),str) and report['summary'] and
            report['summary'] in stdout+stderr,
            'Execution report is not bound to captured output')
    ctx.require(event.get('report_sha256')==ctx.digest(ctx.canonical(report)),
            'Execution report digest mismatch')
    return event

def verify_review_chain(ctx, chain,base_revision,final_revision,*,final_diff_sha256=None):
    """Verify a full review followed by contiguous, resolved correction deltas."""
    ctx.require(isinstance(chain,list) and chain,'Full-diff review chain required')
    ctx.require(ctx.SHA.fullmatch(base_revision or '') and ctx.SHA.fullmatch(final_revision or ''),
            'Review chain revisions required')
    head=base_revision; unresolved={}
    for index,step in enumerate(chain):
        ctx.require(isinstance(step,dict),'Review chain step required')
        expected='full-diff' if index==0 else 'correction-delta'
        ctx.require(step.get('coverage')==expected and step.get('base_revision')==head,
                'Review correction chain is not contiguous')
        next_head=step.get('head_revision')
        if next_head is None:
            ctx.require(index==len(chain)-1 and step.get('uncommitted_candidate') is True and
                    re.fullmatch(r'[0-9a-f]{64}',step.get('diff_sha256','')) and
                    step.get('diff_sha256')==final_diff_sha256,
                    'Uncommitted review candidate content hash does not match the final diff')
            next_head=final_revision
        else:
            ctx.require(ctx.SHA.fullmatch(next_head or '') and next_head!=head,
                    'Review chain head revision required')
        findings=step.get('findings'); dispositions=step.get('dispositions')
        ctx.require(isinstance(findings,list) and isinstance(dispositions,list),
                'Review findings and dispositions must be preserved')
        disposed=set()
        for disposition in dispositions:
            ctx.require(isinstance(disposition,dict),'Review finding disposition required')
            finding_id=disposition.get('finding_id')
            ctx.require(finding_id in unresolved and finding_id not in disposed,
                    'Review disposition refers to an unknown finding')
            ctx.require(disposition.get('decision') in ('fixed','accepted') and
                    isinstance(disposition.get('evidence'),str) and disposition['evidence'],
                    'Review finding disposition is incomplete')
            ctx.require(unresolved[finding_id].get('severity') not in ('P0','P1','P2') or
                    disposition.get('decision')=='fixed',
                    'Material review finding must be fixed before admission')
            unresolved.pop(finding_id); disposed.add(finding_id)
        seen=set()
        for finding in findings:
            ctx.require(isinstance(finding,dict),'Review finding must be structured')
            finding_id=finding.get('id')
            ctx.require(isinstance(finding_id,str) and finding_id and finding_id not in seen and
                    finding_id not in unresolved,'Review finding identity is missing or repeated')
            ctx.require(finding.get('severity') in ('P0','P1','P2','P3') and
                    isinstance(finding.get('summary'),str) and finding['summary'],
                    'Review finding details are incomplete')
            unresolved[finding_id]=finding
            seen.add(finding_id)
        head=next_head
    ctx.require(head==final_revision,'Review chain does not cover the final candidate')
    ctx.require(not unresolved,'Review chain contains an unresolved finding')
    return True

def verify_review_dispositions(ctx, report):
    """Require every full-baseline finding to have an evidence-backed disposition."""
    findings=report.get('findings');dispositions=report.get('dispositions')
    ctx.require(isinstance(findings,list) and isinstance(dispositions,list),
            'Baseline review findings and dispositions must be preserved')
    unresolved={}
    for finding in findings:
        ctx.require(isinstance(finding,dict),'Baseline review finding must be structured')
        identity=finding.get('id')
        ctx.require(isinstance(identity,str) and identity and identity not in unresolved and
                finding.get('severity') in ('P0','P1','P2','P3') and
                isinstance(finding.get('summary'),str) and finding['summary'],
                'Baseline review finding identity or severity is invalid')
        unresolved[identity]=finding
    disposed=set()
    for disposition in dispositions:
        ctx.require(isinstance(disposition,dict),'Baseline finding disposition must be structured')
        identity=disposition.get('finding_id')
        ctx.require(identity in unresolved and identity not in disposed and
                disposition.get('decision') in ('fixed','accepted') and
                isinstance(disposition.get('evidence'),str) and disposition['evidence'],
                'Baseline finding disposition is incomplete or contradictory')
        finding=unresolved[identity]
        ctx.require(finding['severity'] not in ('P0','P1','P2') or
                disposition['decision']=='fixed',
                'Material baseline review finding must be fixed')
        disposed.add(identity)
    ctx.require(disposed==unresolved.keys(),
            'Baseline review contains an unresolved finding')
    return True

def _receipt_event(ctx, record,entry,owner_id,gate):
    ctx.require(isinstance(entry,dict) and entry.get('ref') and entry.get('sha256'),
            f'Missing {gate} provider receipt')
    ctx.require(isinstance(record,dict) and ctx.digest(ctx.canonical(record))==entry['sha256'],
            f'Stale {gate} provider receipt')
    ctx.require(record.get('user',{}).get('id')==owner_id,
            f'{gate} receipt must be owner-authenticated')
    match=re.fullmatch(re.escape(ctx.BASE)+r'/issues/comments/([1-9][0-9]*)',entry['ref'])
    ctx.require(match is not None and record.get('id')==int(match[1]),
            f'{gate} provider record identity mismatch')
    body=record.get('body',''); marker='<!-- release-evidence-v2\n'
    ctx.require(marker in body and '\n-->' in body,
            f'Inspectable schema v2 {gate} receipt required')
    try:
        event=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
    except (ValueError,IndexError) as error:
        raise ctx.ReleaseError(f'Malformed schema v2 {gate} receipt') from error
    ctx.require(event.get('schema_version')==2 and event.get('repository')==ctx.REPOSITORY and
            event.get('gate')==gate,'Provider receipt schema/repository/gate mismatch')
    ctx.require(event.get('report_sha256')==ctx.digest(ctx.canonical(event.get('report'))),
            f'{gate} report content digest mismatch')
    return event

def verify_receipt_time(ctx, record,event):
    ctx.require(_evidence_timestamp(ctx, record.get('created_at'))>=
            _evidence_timestamp(ctx, event.get('execution',{}).get('finished_at')),
            'Provider receipt predates its originating execution')

def _verify_execution_after(ctx, event,cutoff,description):
    execution=event.get('execution',{})
    started=_evidence_timestamp(ctx,execution.get('started_at'))
    finished=_evidence_timestamp(ctx,execution.get('finished_at'))
    ctx.require(started>cutoff and finished>cutoff,
            f'{description} execution must start and finish after the corrected merge')

def verify_inspection_files(ctx, root,revision_id,report,base_revision=None):
    inspected=[]
    for key in ('source_files','test_files'):
        names=report.get(key)
        ctx.require(isinstance(names,list) and names and all(isinstance(name,str) for name in names) and
                len(names)==len(set(names)),
                'ChatGPT source and test inspection coverage required')
        for name in names:
            path=Path(name)
            ctx.require(name and not path.is_absolute() and '..' not in path.parts and '\\' not in name,
                    'Unsafe ChatGPT inspection file path')
            if key=='test_files': ctx.require(path.parts[0]=='tests','ChatGPT test file must be under tests/')
            ctx.git(root,'cat-file','-e',revision_id+':'+name)
            inspected.append(name)
    expected_hashes={name:ctx.digest(ctx.git(root,'show',revision_id+':'+name)) for name in inspected}
    ctx.require(report.get('file_sha256')==expected_hashes,
            'ChatGPT inspection file content digests are missing or incorrect')
    if base_revision:
        changed=set(ctx.git(root,'diff','--name-only',base_revision,revision_id).decode().split())
        tracked=set(ctx.git(root,'ls-tree','-r','--name-only',revision_id).decode().split())
        changed &= tracked
        required_source={name for name in changed if name.startswith('scripts/') and name.endswith('.py')}
        required_tests={name for name in changed if name.startswith('tests/') and name.endswith('.py')}
        ctx.require(required_source<=set(report['source_files']) and
                required_tests<=set(report['test_files']),
                'ChatGPT inspection omits changed source or test files')

def verify_evidence(ctx, evidence,source,root=None,*,dispatch_run_id=None):
    """Authenticate ordinary evidence or a fully admitted prospective root."""
    ctx.require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'New qualification requires evidence schema v2')
    ctx.require(root is not None,'Git checkout required to bind reviewed diff and inspected files')
    if callable(source):
        fetch=source;api=getattr(source,'__self__',None)
    else:
        api=source if hasattr(source,'record') else None
        fetch=api.record if api is not None else source
    origin=evidence.get('origin',{})
    if origin.get('kind')=='prospective_baseline':
        ctx.require(api is not None and hasattr(api,'run') and dispatch_run_id is not None,
                'Prospective evidence requires an authenticated API and original dispatch identity')
        return verify_baseline_admission(ctx, root,api,evidence,
            origin.get('source_revision'),origin.get('builder_revision'),dispatch_run_id)
    repository=fetch(ctx.BASE)
    owner_id=repository.get('owner',{}).get('id')
    ctx.require(repository.get('full_name')==ctx.REPOSITORY and owner_id==evidence.get('owner_id'),
            'Evidence owner differs repository owner')
    ctx.require(origin.get('kind')=='ordinary','Ordinary integration evidence origin required')
    baseline=evidence.get('baseline_revision')
    ctx.require(isinstance(baseline,str) and ctx.SHA.fullmatch(baseline),'Evidence baseline revision required')
    integrations=evidence.get('integrations')
    ctx.require(isinstance(integrations,list),'Integration evidence list required')
    snapshots=[]
    for integration in integrations:
        ctx.require(isinstance(integration,dict),'Integration evidence object required')
        target=integration.get('reviewed_revision'); base=integration.get('base_revision')
        ctx.require(isinstance(target,str) and ctx.SHA.fullmatch(target) and
                isinstance(base,str) and ctx.SHA.fullmatch(base),'Reviewed integration range required')
        records=integration.get('records',{})
        ctx.require(isinstance(records,dict),'Integration provider receipts required')
        index_binding=integration.get('readiness_index')
        ctx.require(isinstance(index_binding,dict),'Authenticated readiness index binding required')
        index_ref=index_binding.get('normalization_ref') or index_binding.get('index_ref')
        loaded=load_readiness_index(ctx, index_ref,fetch,integration.get('pull_request'))
        ctx.require(loaded['index_ref']==index_binding.get('index_ref') and
                loaded['index_sha256']==index_binding.get('index_sha256') and
                loaded['original_ref']==index_binding.get('original_ref') and
                loaded['original_sha256']==index_binding.get('original_sha256') and
                loaded['normalization_ref']==index_binding.get('normalization_ref') and
                loaded['normalization_sha256']==index_binding.get('normalization_sha256'),
                'Readiness index provider binding changed')
        embedded=[item for item in loaded['evidence'].get('integrations',[])
                  if item.get('pull_request')==integration.get('pull_request')]
        ctx.require(len(embedded)==1,'Readiness index does not identify this integration once')
        import copy
        claim=copy.deepcopy(integration);claim.pop('readiness_index')
        ctx.require(ctx.canonical(embedded[0])==ctx.canonical(claim),
                'Readiness index evidence differs from the qualified integration')
        snapshots.append({'gate':'readiness_index','ref':loaded['original_ref'],
                          'sha256':loaded['original_sha256'],'record':loaded['original_record']})
        if loaded['normalization_record'] is not None:
            snapshots.append({'gate':'readiness_normalization','ref':loaded['normalization_ref'],
                              'sha256':loaded['normalization_sha256'],
                              'record':loaded['normalization_record']})
        expected={'base_revision':base,'head_revision':target}
        author_record=fetch(records.get('author_execution',{}).get('ref'))
        author_event=_receipt_event(ctx, author_record,records['author_execution'],owner_id,'author_execution')
        author_event=verify_execution_receipt(ctx, author_event,'author_execution',expected)
        verify_receipt_time(ctx, author_record,author_event)
        ctx.require(author_event['report'].get('role')=='author','Originating author execution required')
        author_id=author_event['execution']['execution_id']
        snapshots.append({'gate':'author_execution','ref':records['author_execution']['ref'],
                          'sha256':records['author_execution']['sha256'],'record':author_record})
        review_entries=records.get('independent_reviews')
        if review_entries is None and isinstance(records.get('independent_review'),dict):
            review_entries=[records['independent_review']]
        ctx.require(isinstance(review_entries,list) and review_entries,'Independent review receipts required')
        chain=[];review_ids=set();review_records=[]
        for entry in review_entries:
            actual=fetch(entry.get('ref'))
            event=_receipt_event(ctx, actual,entry,owner_id,'independent_review')
            step=event.get('report',{}).get('review_step')
            ctx.require(isinstance(step,dict),'Structured review step required')
            execution_range={'base_revision':step.get('base_revision'),
                             'head_revision':step.get('head_revision')}
            if step.get('uncommitted_candidate') is True:
                execution_range['diff_sha256']=step.get('diff_sha256')
            event=verify_execution_receipt(ctx, event,'independent_review',execution_range)
            verify_receipt_time(ctx, actual,event)
            ctx.require(event['execution'].get('system') in ('local_cubic','separate_codex'),
                    'Independent review must come from a non-authoring review execution')
            ctx.require(event['execution']['execution_id']!=author_id,
                    'Originating author cannot independently review')
            ctx.require(event['execution']['execution_id'] not in review_ids,
                    'Review execution identity reused')
            review_ids.add(event['execution']['execution_id'])
            chain.append(step);review_records.append(actual)
            snapshots.append({'gate':'independent_review','ref':entry['ref'],
                              'sha256':entry['sha256'],'record':actual})
        preceding_records=[author_record,*review_records[:-1]]
        for preceding,current in zip(preceding_records,review_records):
            verify_event_chronology(ctx, [preceding],current.get('created_at'))
        uncommitted=chain[-1] if chain[-1].get('head_revision') is None else None
        final_diff=(ctx.digest(ctx.git(root,'diff','--binary',uncommitted['base_revision'],target))
                    if uncommitted else None)
        verify_review_chain(ctx, chain,base,target,final_diff_sha256=final_diff)
        for step in chain:
            diff_head=step.get('head_revision') or target
            actual_diff=ctx.digest(ctx.git(root,'diff','--binary',step['base_revision'],diff_head))
            ctx.require(step.get('diff_sha256')==actual_diff,
                    'Review chain diff bytes differ from the authenticated Git range')
        chat_entry=records.get('chatgpt_inspection',{})
        chat_record=fetch(chat_entry.get('ref'))
        chat_event=_receipt_event(ctx, chat_record,chat_entry,owner_id,'chatgpt_inspection')
        chat_event=verify_execution_receipt(ctx, chat_event,'chatgpt_inspection',expected)
        verify_receipt_time(ctx, chat_record,chat_event)
        ctx.require(chat_event['execution'].get('system')=='chatgpt',
                'Direct ChatGPT inspection execution required')
        report=chat_event['report']
        ctx.require(isinstance(report.get('source_files'),list) and report['source_files'] and
                isinstance(report.get('test_files'),list) and report['test_files'],
                'ChatGPT source and test inspection coverage required')
        verify_inspection_files(ctx, root,target,report,base_revision=base)
        ctx.require(all(name in chat_event['execution'].get('stdout','')+
                    chat_event['execution'].get('stderr','')
                    for name in report['source_files']+report['test_files']),
                'ChatGPT transcript omits inspected source or test files')
        snapshots.append({'gate':'chatgpt_inspection','ref':chat_entry['ref'],
                          'sha256':chat_entry['sha256'],'record':chat_record})
        owner_entry=records.get('owner_authorization',{})
        owner_record=fetch(owner_entry.get('ref'))
        owner_event=_receipt_event(ctx, owner_record,owner_entry,owner_id,'owner_authorization')
        owner_report=owner_event.get('report',{})
        ctx.require(owner_event.get('revision')==target and owner_report.get('action')=='merge' and
                owner_report.get('verdict')=='approve','Pre-merge owner authorization required')
        snapshots.append({'gate':'owner_authorization','ref':owner_entry['ref'],
                          'sha256':owner_entry['sha256'],'record':owner_record})
        ci_entry=records.get('ci',{})
        ci_record=fetch(ci_entry.get('ref'))
        ctx.require(isinstance(ci_record,dict) and ctx.digest(ctx.canonical(ci_record))==ci_entry.get('sha256'),
                'Stale CI provider record')
        ctx.require(ci_record.get('repository',{}).get('full_name')==ctx.REPOSITORY and
                ci_record.get('event')=='pull_request' and ci_record.get('status')=='completed' and
                ci_record.get('conclusion')=='success' and ci_record.get('head_sha')==target and
                ci_record.get('run_attempt')==ci_entry.get('run_attempt') and ci_record.get('completed_at'),
                'Successful CI must test the reviewed candidate')
        verify_ci_pull_request(ctx, ci_record,integration.get('pull_request'),target,base)
        snapshots.append({'gate':'ci','ref':ci_entry['ref'],'sha256':ci_entry['sha256'],
                          'record':ci_record})
    ctx.require(snapshots,'No admitted ordinary integration evidence')
    return snapshots

class BaselineQualification(list):
    """Authenticated pre-dispatch baseline evidence; it cannot authorize release coverage."""
    def __init__(self,snapshots,baseline,source,builder,evidence_digest):
        super().__init__(snapshots)
        self.baseline=baseline;self.source=source;self.builder=builder
        self.evidence_digest=evidence_digest
        self._seal=_BASELINE_QUALIFICATION_SEAL

class VerifiedBaselineAdmission(list):
    """In-process result of the complete prospective admission verifier."""
    def __init__(self,snapshots,baseline,source,builder,dispatch_run_id,evidence_digest):
        super().__init__(snapshots)
        self.baseline=baseline;self.source=source;self.builder=builder
        self.dispatch_run_id=dispatch_run_id;self.evidence_digest=evidence_digest
        self._seal=_BASELINE_ADMISSION_SEAL

def verify_coverage(ctx, root,evidence,target,*,admitted=False,baseline_admission=None):
    """Require exact baseline identity and complete first-parent integration coverage."""
    baseline=ctx.revision(root,evidence.get('baseline_revision'))
    target=ctx.revision(root,target)
    if evidence.get('schema_version')==1:
        ctx.require(admitted and (baseline==ctx.BOOTSTRAP_BASELINE or evidence.get('anchor_release') or
                              evidence.get('baseline_admission')),
                'Frozen schema v1 baseline admission missing')
        ctx.git(root,'merge-base','--is-ancestor',baseline,target)
        required=set(ctx.git(root,'rev-list','--first-parent',baseline+'..'+target).decode().split())
        covered=set()
        for integration in evidence.get('integrations',[]):
            result=ctx.revision(root,integration.get('integrated_revision'))
            reviewed=ctx.revision(root,integration.get('reviewed_revision'))
            tested=ctx.revision(root,integration.get('tested_revision'))
            ctx.require(ctx.git(root,'rev-parse',result+'^{tree}')==ctx.git(root,'rev-parse',tested+'^{tree}'),
                    'Frozen integration tree differs from tested tree')
            parents=ctx.git(root,'show','-s','--format=%P',tested).decode().split()
            ctx.require(reviewed in parents or ctx.git(root,'rev-parse',reviewed+'^{tree}')==
                    ctx.git(root,'rev-parse',tested+'^{tree}'),
                    'Frozen reviewed candidate relationship unverified')
            members=integration.get('integrated_commits',[result])
            ctx.require(isinstance(members,list) and members and len(set(members))==len(members)
                    and members[-1]==result,'Invalid frozen integration membership')
            expected=ctx.git(root,'rev-list','--first-parent','--max-count='+str(len(members)),result).decode().split()[::-1]
            ctx.require(members==expected,'Frozen integration membership is not contiguous')
            covered.update(members)
        ctx.require(required<=covered,'Uncovered main integrations in frozen evidence')
        return
    origin=evidence.get('origin',{})
    integrations=evidence.get('integrations',[])
    ctx.require(isinstance(integrations,list),'Integration evidence list required')
    if origin.get('kind')=='prospective_baseline':
        proof=baseline_admission
        ctx.require(isinstance(proof,VerifiedBaselineAdmission) and
                proof._seal is _BASELINE_ADMISSION_SEAL and
                proof.baseline==baseline and proof.source==baseline and
                proof.builder==baseline and proof.dispatch_run_id is not None and
                proof.evidence_digest==ctx.digest(ctx.canonical(evidence)) and
                evidence.get('baseline_admission'),
                'Prospective baseline admission must be independently verified')
        ctx.require(target==baseline,'Prospective baseline target must exactly match its admitted revision')
        ctx.require(not integrations,'Prospective baseline requires zero ordinary integrations')
        return
    ctx.require(origin.get('kind')=='ordinary','Trusted evidence origin required')
    ctx.require(admitted or evidence.get('anchor_release'),
            'Ordinary evidence requires a verified immutable baseline')
    ctx.git(root,'merge-base','--is-ancestor',baseline,target)
    required=set(ctx.git(root,'rev-list','--first-parent',baseline+'..'+target).decode().split())
    covered=set()
    for integration in integrations:
        result=ctx.revision(root,integration.get('integrated_revision'))
        ctx.revision(root,integration.get('reviewed_revision'))
        tested=ctx.revision(root,integration.get('tested_revision'))
        ctx.require(ctx.git(root,'rev-parse',result+'^{tree}')==ctx.git(root,'rev-parse',tested+'^{tree}'),
                'Integration tree differs from tested tree')
        members=integration.get('integrated_commits',[result])
        ctx.require(isinstance(members,list) and members and len(set(members))==len(members)
                and members[-1]==result,'Invalid integrated commit membership')
        expected=ctx.git(root,'rev-list','--first-parent','--max-count='+str(len(members)),result).decode().split()[::-1]
        ctx.require(members==expected,'Integration membership is not a contiguous first-parent range')
        covered.update(members)
    ctx.require(required<=covered,'Uncovered main integrations')

def verify_pending_baseline_coverage(ctx, root,evidence,qualification,target,main_revision):
    """Verify exact baseline coverage before any release dispatch exists."""
    baseline=ctx.revision(root,evidence.get('baseline_revision'))
    target=ctx.revision(root,target);main_revision=ctx.revision(root,main_revision)
    origin=evidence.get('origin',{})
    ctx.require(isinstance(qualification,BaselineQualification) and
            qualification._seal is _BASELINE_QUALIFICATION_SEAL and
            qualification.baseline==baseline and qualification.source==baseline and
            qualification.builder==baseline and
            qualification.evidence_digest==ctx.digest(ctx.canonical(evidence)),
            'Pending baseline coverage requires authenticated qualification evidence')
    ctx.require(origin.get('kind')=='prospective_baseline' and
            origin.get('source_revision')==baseline and
            origin.get('builder_revision')==baseline,
            'Prospective source and builder must equal the exact baseline')
    ctx.require(target==baseline and main_revision==baseline,
            'Main coverage must remain exactly at the admitted baseline before dispatch')
    ctx.require(evidence.get('integrations')==[],
            'Prospective baseline requires zero ordinary integrations')

def _baseline_manifest_sha256(ctx, root,baseline):
    return ctx.digest(ctx.git(root,'ls-tree','-r','--full-tree','-z',baseline))

def verify_baseline_admission(ctx, root,api,evidence,source,builder,dispatch_run_id):
    """Verify baseline qualification and, when supplied, original dispatch order."""
    ctx.require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'Prospective baseline requires schema v2 evidence')
    origin=evidence.get('origin',{})
    ctx.require(origin.get('kind')=='prospective_baseline',
            'Prospective baseline evidence origin required')
    baseline=ctx.revision(root,evidence.get('baseline_revision'))
    ctx.require(ctx.revision(root,source)==baseline and ctx.revision(root,builder)==baseline,
            'First-release source and builder must equal the corrected merge revision')
    ctx.require(origin.get('baseline_revision')==baseline and origin.get('source_revision')==baseline and
            origin.get('builder_revision')==baseline,
            'Prospective source/builder identities do not match the admitted baseline')
    ctx.require(evidence.get('integrations')==[],
            'Prospective baseline requires zero ordinary integrations')
    repo=api.record(ctx.BASE)
    owner_id=repo.get('owner',{}).get('id')
    ctx.require(repo.get('full_name')==ctx.REPOSITORY and owner_id==evidence.get('owner_id'),
            'Prospective baseline repository owner mismatch')
    tree=ctx.git(root,'rev-parse',baseline+'^{tree}').decode().strip()
    manifest=_baseline_manifest_sha256(ctx, root,baseline)
    policy=ctx.git(root,'log','--first-parent','-1','--format=%H',baseline,'--','docs/PROCESS.md').decode().strip()
    policy_bytes=ctx.git(root,'show',baseline+':docs/PROCESS.md')
    ctx.require(policy and ctx.git(root,'show',policy+':docs/PROCESS.md')==policy_bytes,
            'Prospective policy identity cannot be derived from the baseline')
    ctx.require(origin.get('policy_revision')==policy and
            origin.get('policy_sha256')==ctx.digest(policy_bytes),
            'Prospective policy identity differs from the baseline policy')
    admission=evidence.get('baseline_admission',{})
    ctx.require(isinstance(admission,dict),'Baseline qualification and owner admission required')
    pr_number=admission.get('correction_pull_request')
    ctx.require(type(pr_number) is int and pr_number>0,'Corrected merge pull request required')
    pr=api.record(ctx.BASE+f'/pulls/{pr_number}')
    ctx.require(pr.get('number')==pr_number and
            pr.get('base',{}).get('repo',{}).get('full_name')==ctx.REPOSITORY and
            pr.get('head',{}).get('repo',{}).get('full_name')==ctx.REPOSITORY and
            pr.get('merged') is True and pr.get('base',{}).get('ref')=='main' and
            pr.get('merge_commit_sha')==baseline and
            pr.get('head',{}).get('sha')==admission.get('reviewed_revision'),
            'Prospective baseline is not the exact corrected main integration')
    merged_at=pr.get('merged_at')
    ctx.require(merged_at,'Corrected merge provider timestamp required')
    merge_time=_evidence_timestamp(ctx,merged_at)
    review_entry=admission.get('full_review',{})
    review_record=api.record(review_entry.get('ref'))
    review_event=_receipt_event(ctx, review_record,review_entry,owner_id,'baseline_review')
    review_range={'baseline_revision':baseline,'tree_sha':tree}
    review_event=verify_execution_receipt(ctx, review_event,'baseline_review',review_range)
    _verify_execution_after(ctx,review_event,merge_time,'Full-baseline review')
    verify_receipt_time(ctx, review_record,review_event)
    review_report=review_event['report']
    ctx.require(review_event['execution'].get('system') in ('local_cubic','separate_codex'),
            'Full-baseline review requires a non-authoring review execution')
    ctx.require(review_event.get('revision')==baseline and
            review_report.get('coverage')=='full-baseline' and
            review_report.get('reviewed_revision')==baseline and
            review_report.get('tree_sha')==tree and
            review_report.get('manifest_sha256')==manifest,
            'Independent full-baseline review does not cover the exact tree')
    verify_review_dispositions(ctx, review_report)
    ctx.require(_evidence_timestamp(ctx, review_record.get('created_at'))>
            _evidence_timestamp(ctx, merged_at),'Full-baseline review must inspect the corrected merge')
    chat_entry=admission.get('chatgpt_inspection',{})
    chat_record=api.record(chat_entry.get('ref'))
    chat_event=_receipt_event(ctx, chat_record,chat_entry,owner_id,'chatgpt_inspection')
    chat_event=verify_execution_receipt(ctx, chat_event,'chatgpt_inspection',review_range)
    _verify_execution_after(ctx,chat_event,merge_time,'ChatGPT inspection')
    verify_receipt_time(ctx, chat_record,chat_event)
    ctx.require(review_event['execution'].get('execution_id')!=
            chat_event['execution'].get('execution_id'),
            'Full-baseline review and ChatGPT inspection must be separate executions')
    chat_report=chat_event['report']
    ctx.require(chat_event['execution'].get('system')=='chatgpt' and
            chat_event.get('revision')==baseline and
            chat_report.get('coverage')=='full-baseline' and
            chat_report.get('reviewed_revision')==baseline and
            chat_report.get('tree_sha')==tree and chat_report.get('manifest_sha256')==manifest and
            isinstance(chat_report.get('source_files'),list) and chat_report['source_files'] and
            isinstance(chat_report.get('test_files'),list) and chat_report['test_files'],
            'ChatGPT inspection does not cover the exact full baseline')
    verify_inspection_files(ctx, root,baseline,chat_report)
    ctx.require(all(name in chat_event['execution'].get('stdout','')+
                chat_event['execution'].get('stderr','')
                for name in chat_report['source_files']+chat_report['test_files']),
            'ChatGPT baseline transcript omits inspected source or test files')
    ctx.require(_evidence_timestamp(ctx, chat_record.get('created_at'))>
            _evidence_timestamp(ctx, merged_at),'ChatGPT must inspect the corrected merge')
    ci_entry=admission.get('ci',{})
    ci_record=api.record(ci_entry.get('ref'))
    ctx.require(ctx.digest(ctx.canonical(ci_record))==ci_entry.get('sha256'),
            'Baseline CI provider record changed')
    ctx.require(ci_record.get('repository',{}).get('full_name')==ctx.REPOSITORY and
            ci_record.get('event')=='pull_request' and ci_record.get('status')=='completed' and
            ci_record.get('conclusion')=='success' and
            ci_record.get('head_sha')==pr.get('head',{}).get('sha') and
            ci_record.get('run_attempt')==ci_entry.get('run_attempt') and
            ci_record.get('completed_at'),
            'Successful correction PR CI bound to the baseline is required')
    tested=ctx.revision(root,ci_entry.get('tested_revision'))
    ctx.require(ctx.git(root,'rev-parse',tested+'^{tree}').decode().strip()==tree,
            'Baseline CI tested tree differs from the exact admitted source')
    parents=ctx.git(root,'show','-s','--format=%P',baseline).decode().split()
    ctx.require(parents and ci_entry.get('tested_base_revision')==parents[0],
            'Baseline CI tested base differs from corrected integration base')
    verify_ci_pull_request(ctx, ci_record,pr_number,pr.get('head',{}).get('sha'),parents[0])
    jobs=api.ci_jobs(ci_record['id'],ci_entry['run_attempt'])
    required=[job for job in jobs if job.get('name')=='Validate committed PR integration diff']
    ctx.require(len(required)==1 and required[0].get('conclusion')=='success' and
            required[0].get('status')=='completed' and required[0].get('completed_at'),
            'Required completed baseline CI job unavailable')
    steps=required[0].get('steps',[])
    ctx.require(steps and all(step.get('conclusion')=='success' for step in steps),
            'Baseline CI contains failed or skipped steps')
    logs=api.job_log(required[0]['id'])
    for label,value in (('PR HEAD',pr['head']['sha']),
                        ('Tested integration revision',tested),
                        ('Tested base revision',parents[0])):
        ctx.require(label+': '+value in logs,'Baseline CI identity missing: '+label)
    manifest_file=json.loads(ctx.git(root,'show',baseline+':skills/distribution.json'))
    workflow=ctx.git(root,'show',baseline+':.github/workflows/ci.yml').decode()
    verify_ci_suites(ctx, logs,manifest_file.get('schema_version'),steps,workflow)
    owner_entry=admission.get('owner_admission',{})
    owner_record=api.record(owner_entry.get('ref'))
    owner_event=_receipt_event(ctx, owner_record,owner_entry,owner_id,'baseline_admission')
    owner_report=owner_event.get('report',{})
    ctx.require(owner_event.get('revision')==baseline and
            owner_report.get('action')=='admit-baseline' and
            owner_report.get('verdict')=='approve',
            'Explicit owner baseline admission required')
    qualification_records=[review_record,chat_record,ci_record,required[0]]
    verify_event_chronology(ctx, qualification_records,owner_record.get('created_at'))
    binding=evidence.get('readiness_index')
    ctx.require(isinstance(binding,dict),'Prospective baseline readiness index binding required')
    index_ref=binding.get('normalization_ref') or binding.get('index_ref')
    loaded=load_readiness_index(ctx, index_ref,api.record,pr_number)
    ctx.require(loaded['normalization_record'] is None and
            readiness_index_binding(ctx, loaded)==binding,
            'Prospective baseline readiness index provider binding changed')
    import copy
    indexed_evidence=copy.deepcopy(loaded['evidence'])
    admitted_evidence=copy.deepcopy(evidence);admitted_evidence.pop('readiness_index')
    ctx.require(ctx.canonical(indexed_evidence)==ctx.canonical(admitted_evidence),
            'Prospective baseline index differs from admitted evidence')
    verify_event_chronology(ctx, [*qualification_records,owner_record],
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
        {'gate':'corrected_merge','ref':ctx.BASE+f'/pulls/{pr_number}',
         'sha256':ctx.digest(ctx.canonical(pr)),'record':pr},
        {'gate':'ci_job','ref':str(required[0]['id']),
         'sha256':ctx.digest(ctx.canonical(required[0])),'record':required[0]},
        {'gate':'ci_log','ref':str(required[0]['id']),'sha256':ctx.digest(logs.encode()),'record':logs},
    ])
    evidence_hash=ctx.digest(ctx.canonical(evidence))
    if dispatch_run_id is None:
        return BaselineQualification(snapshots,baseline,source,builder,evidence_hash)
    dispatch=api.run(int(dispatch_run_id))
    ctx.require(type(dispatch.get('id')) is int and dispatch['id']==int(dispatch_run_id) and
            dispatch.get('event')=='workflow_dispatch' and
            dispatch.get('head_sha')==baseline and
            dispatch.get('head_branch')=='main' and
            dispatch.get('actor',{}).get('id')==owner_id and
            dispatch.get('triggering_actor',{}).get('id')==owner_id and
            dispatch.get('path','').split('@')[0]=='.github/workflows/skill-release.yml',
            'Original first-release dispatch is not bound to the admitted baseline')
    ctx.require(_evidence_timestamp(ctx, owner_record.get('updated_at'))<
            _evidence_timestamp(ctx, dispatch.get('created_at')),
            'Owner baseline admission must precede the original release dispatch')
    verify_event_chronology(ctx, [loaded['original_record']],dispatch.get('created_at'))
    snapshots.append({'gate':'release_dispatch','ref':str(dispatch_run_id),
                      'sha256':ctx.digest(ctx.canonical(dispatch)),'record':dispatch})
    return VerifiedBaselineAdmission(snapshots,baseline,source,builder,int(dispatch_run_id),
                                     evidence_hash)

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

def verify_ci_suites(ctx, logs,schema,steps,workflow):
    """Bind each suite result to its committed command and successful CI step."""
    ctx.require(schema in (1,2),'Unsupported CI source schema')
    contract=yaml.safe_load(workflow)
    jobs=[j for j in contract.get('jobs',{}).values()
          if j.get('name')=='Validate committed PR integration diff']
    ctx.require(len(jobs)==1 and not any(k in jobs[0] for k in ('if','continue-on-error','strategy')),
            'Conditional or ambiguous mandatory CI job')
    expected=list(ctx.SUITES if schema==2 else ctx.SUITES[:4])
    workflow_steps=jobs[0].get('steps',[])
    if schema==1 and any('test_issue5_workflow.py' in x.get('run','') for x in workflow_steps):
        expected[0]='test_issue5_workflow.py'
    text=re.sub(r'^\d{4}-\d\d-\d\dT\S+ ', '', logs, flags=re.M)
    groups=list(re.finditer(r'^##\[group\]Run (.+)\n',text,re.M))
    for suite in expected:
        command='python3 -m unittest discover -s tests -p '+suite+' -v'
        matches=[x for x in workflow_steps if x.get('run','').strip()==command]
        ctx.require(len(matches)==1,'Missing or altered mandatory suite command: '+suite)
        step=matches[0]
        ctx.require(not any(k in step for k in ('if','continue-on-error','working-directory','env')),
                'Conditional or altered suite execution: '+suite)
        actual=[x for x in steps if x.get('name')==step.get('name')]
        ctx.require(len(actual)==1 and actual[0].get('conclusion')=='success',
                'Mandatory suite step not successful: '+suite)
        executed=[(i,g) for i,g in enumerate(groups) if shlex.split(g.group(1))==shlex.split(command)]
        ctx.require(len(executed)==1,'Missing or repeated suite command execution: '+suite)
        i,group=executed[0]
        section=text[group.end():groups[i+1].start() if i+1<len(groups) else len(text)]
        ctx.require('##[endgroup]\n' in section,'Suite command boundary absent')
        output=section.split('##[endgroup]\n',1)[1]
        summaries=re.findall(r'^Ran ([0-9]+) tests? in [^\n]+$',output,re.M)
        result_output=re.split(r'^-{5,}$|^Ran [0-9]+ tests?',output,maxsplit=1,flags=re.M)[0]
        labels=list(re.finditer(r'^test\S+ \(.+\)',result_output,re.M))
        statuses=[]
        for index,label in enumerate(labels):
            result=result_output[label.end():labels[index+1].start() if index+1<len(labels) else len(result_output)]
            statuses.append(bool(re.search(r'(?:^|\n|\.\.\. )ok\s*$',result)))
        ctx.require(len(summaries)==1 and int(summaries[0])>0 and
                len(labels)==int(summaries[0]) and all(statuses) and
                len(re.findall(r'^OK$',output,re.M))==1 and
                not re.search(r'^FAILED(?: |$)|^OK \(',output,re.M),
                'Mandatory suite execution failed, skipped or absent: '+suite)

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

def _audit_error_status(ctx, error):
    message=str(error).lower()
    if any(word in message for word in ('missing','required','unavailable','absent')):
        return 'MISSING_EVIDENCE'
    return 'FAIL'

def audit_pull_request(ctx, root,api,number):
    """Report evidence and pending runtime gates using only provider GETs."""
    result={'repository':ctx.REPOSITORY,'pull_request':number,'gates':{
        'account':'NOT_RUN','repository_identity':'NOT_RUN','pull_request_identity':'NOT_RUN',
        'evidence_receipts':'NOT_RUN','candidate_ci':'NOT_RUN','merge':'NOT_RUN',
        'integrated_revision':'NOT_RUN','git_coverage':'NOT_RUN',
        'baseline_admission':'NOT_RUN','release_dispatch':'NOT_RUN',
        'release_runtime':'NOT_RUN','publication':'NOT_RUN'},'details':{}}
    current_gate='account'
    try:
        user=api.request('GET','/user')
        ctx.require(user.get('login')=='danielbyon','Explicit audit credential must authenticate as danielbyon')
        result['gates']['account']='PASS'
        current_gate='repository_identity'
        repository=api.record(ctx.BASE)
        ctx.require(repository.get('full_name')==ctx.REPOSITORY and
                repository.get('owner',{}).get('login')=='danielbyon',
                'GitHub repository identity mismatch')
        result['gates']['repository_identity']='PASS'
        current_gate='pull_request_identity'
        pr=api.record(ctx.BASE+f'/pulls/{int(number)}')
        ctx.require(pr.get('number')==int(number) and pr.get('base',{}).get('ref')=='main' and
                pr.get('base',{}).get('repo',{}).get('full_name',ctx.REPOSITORY)==ctx.REPOSITORY,
                'Pull request identity or target mismatch')
        result['gates']['pull_request_identity']='PASS'
        current_gate='evidence_receipts'
        comments=api.pages(ctx.BASE+f'/issues/{int(number)}/comments')
        marker='<!-- release-readiness\n'; candidates=[]
        for comment in comments:
            if marker not in comment.get('body',''): continue
            reference=ctx.BASE+f'/issues/comments/{comment.get("id")}'
            loaded=load_readiness_index(ctx, reference,api.record,int(number))
            candidates.append(loaded)
        normalized=[item for item in candidates if item['normalization_record'] is not None]
        originals=[item for item in candidates if item['normalization_record'] is None]
        pending_baselines=[]
        if pr.get('merged_at'):
            pending_baselines=[item for item in originals
                if item['evidence'].get('origin',{}).get('kind')=='prospective_baseline']
            if len(normalized)==1 and not pending_baselines:
                loaded=normalized[0]
            else:
                ctx.require(not normalized and len(originals)==1 and len(pending_baselines)==1,
                        'Missing or contradictory release-readiness normalization or baseline index')
                loaded=pending_baselines[0]
        else:
            ctx.require(len(originals)==1 and not normalized,
                    'Missing or contradictory pre-merge release-readiness index')
            loaded=originals[0]
        evidence=loaded['evidence']
        if evidence.get('origin',{}).get('kind')=='prospective_baseline':
            ctx.require(pr.get('merged_at'),'Prospective baseline admission requires the corrected merge')
            evidence['readiness_index']=readiness_index_binding(ctx, loaded)
            current_gate='baseline_admission'
            baseline=evidence.get('baseline_revision')
            qualification=verify_baseline_admission(ctx, root,api,evidence,
                evidence.get('origin',{}).get('source_revision'),
                evidence.get('origin',{}).get('builder_revision'),None)
            result['gates']['evidence_receipts']='PASS'
            result['gates']['merge']='PASS'
            if pr.get('merge_commit_sha')==baseline:
                result['gates']['integrated_revision']='PASS'
            else:
                result['gates']['integrated_revision']='FAIL'
                result['details']['integrated_revision']=(
                    'Corrected PR merge SHA differs from the exact prospective baseline')
            result['gates']['candidate_ci']='PASS'
            result['gates']['baseline_admission']='PASS'
            current_gate='git_coverage'
            try:
                main_ref=api.record(ctx.BASE+'/git/ref/heads/main')
                main_revision=main_ref.get('object',{}).get('sha')
                ctx.require(main_revision,'Current main revision unavailable')
                verify_pending_baseline_coverage(ctx, root,evidence,qualification,baseline,main_revision)
                result['gates']['git_coverage']='PASS'
            except (ctx.ReleaseError,ctx.APIError,OSError,ValueError,KeyError,TypeError) as error:
                result['gates']['git_coverage']=_audit_error_status(ctx, error)
                result['details']['git_coverage']=str(error)
            result['details'].update(evidence_digest=ctx.digest(ctx.canonical(qualification)),
                baseline_revision=baseline,merged_at=pr.get('merged_at'))
            current_gate='baseline_admission'
        else:
            matched=[entry for entry in evidence.get('integrations',[])
                     if entry.get('pull_request')==int(number)]
            ctx.require(len(matched)==1,'Release evidence does not identify this pull request exactly once')
            integration=matched[0]
            integration['readiness_index']=readiness_index_binding(ctx, loaded)
            # The persisted index predates the merge; the derived local binding is
            # attached only after its provider record has been authenticated.
            snapshots=verify_evidence(ctx, evidence,api.record,root)
            ctx.require(pr.get('head',{}).get('sha')==integration.get('reviewed_revision'),
                    'Pull request head differs from reviewed evidence')
            result['gates']['evidence_receipts']='PASS'
            if pr.get('merged_at'):
                current_gate='merge'
                result['gates']['merge']='PASS'
                current_gate='integrated_revision'
                if integration.get('integrated_revision')==pr.get('merge_commit_sha'):
                    result['gates']['integrated_revision']='PASS'
                    try:
                        current_gate='candidate_ci'
                        verify_live_integrations(ctx, api,{'schema_version':2,'integrations':[integration]},root)
                        result['gates']['candidate_ci']='PASS'
                        if evidence.get('anchor_release'):
                            current_gate='git_coverage'
                            verify_coverage(ctx, root,evidence,integration['integrated_revision'],admitted=True)
                            result['gates']['git_coverage']='PASS'
                    except (ctx.ReleaseError,ctx.APIError,OSError,ValueError,KeyError,TypeError) as error:
                        result['gates'][current_gate]=_audit_error_status(ctx, error)
                        result['details'][current_gate]=str(error)
                else:
                    result['gates']['integrated_revision']='FAIL'
                    result['details']['integrated_revision']='Normalized evidence does not name the provider merge SHA'
            else:
                current_gate='candidate_ci'
                verify_premerge_integrations(ctx, api,{'integrations':[integration]},root)
                result['gates']['candidate_ci']='PASS'
            result['details'].update(evidence_digest=ctx.digest(ctx.canonical(snapshots)),
                                     reviewed_revision=integration.get('reviewed_revision'),
                                     merged_at=pr.get('merged_at'))
    except (ctx.ReleaseError,ctx.APIError,OSError,ValueError,KeyError,TypeError) as error:
        if result['gates'][current_gate]=='NOT_RUN':
            result['gates'][current_gate]=_audit_error_status(ctx, error)
        result['details'][current_gate]=str(error)
    result['gates']['release_dispatch']='NOT_RUN'
    result['gates']['release_runtime']='NOT_RUN'
    result['gates']['publication']='NOT_RUN'
    return result

def discover_evidence(ctx, root,api,source,builder):
    """Build current evidence from authenticated readiness indexes and Git.

    The initial release must use a separately admitted prospective baseline.
    Later releases cover each first-parent integration after an immutable anchor.
    """
    source=ctx.revision(root,source);builder=ctx.revision(root,builder)
    repo=api.request('GET',ctx.BASE)
    ctx.require(repo.get('full_name')==ctx.REPOSITORY and repo.get('owner',{}).get('id') is not None,
            'Repository identity unavailable during evidence discovery')
    owner_id=repo['owner']['id']
    anchor=ctx.select_anchor(root,api,source,builder)

    def readiness_for(pr_number,*,normalized):
        comments=api.pages(ctx.BASE+f'/issues/{pr_number}/comments')
        found=[];marker='<!-- release-readiness\n'
        for comment in comments:
            if marker not in comment.get('body',''): continue
            reference=ctx.BASE+f'/issues/comments/{comment.get("id")}'
            loaded=load_readiness_index(ctx, reference,api.record,pr_number)
            if (loaded['normalization_record'] is not None)==normalized:
                found.append(loaded)
        ctx.require(len(found)==1,
                'Missing or contradictory '+('normalized' if normalized else 'original')+
                f' readiness index for PR {pr_number}')
        return found[0]

    if anchor is None:
        ctx.require(source==builder,
                'First release requires source and builder to equal the prospective baseline')
        prs=api.pages(ctx.BASE+f'/commits/{source}/pulls')
        matches=[pr for pr in prs if pr.get('merge_commit_sha')==source and
                 pr.get('base',{}).get('ref')=='main' and pr.get('merged') is True]
        ctx.require(len(matches)==1,'Prospective baseline must be the exact corrected main merge')
        pr=matches[0];loaded=readiness_for(pr['number'],normalized=False)
        evidence=loaded['evidence']
        ctx.require(evidence.get('origin',{}).get('kind')=='prospective_baseline' and
                evidence.get('baseline_revision')==source and evidence.get('integrations')==[] and
                evidence.get('owner_id')==owner_id and
                evidence.get('origin',{}).get('source_revision')==source and
                evidence.get('origin',{}).get('builder_revision')==builder,
                'Prospective baseline readiness index identity mismatch')
        ctx.require(evidence.get('baseline_admission',{}).get('correction_pull_request')==pr['number'],
                'Prospective baseline admission references a different correction PR')
        evidence['readiness_index']=readiness_index_binding(ctx, loaded)
        return evidence

    baseline,tag=anchor
    try:
        ctx.git(root,'merge-base','--is-ancestor',baseline,source)
        ctx.git(root,'merge-base','--is-ancestor',baseline,builder)
    except ctx.ReleaseError as error:
        raise ctx.ReleaseError('Source and builder must descend from a verified immutable release') from error
    revisions=ctx.git(root,'rev-list','--first-parent',baseline+'..'+builder).decode().split()
    revision_set=set(revisions);prs_by_merge={}
    for commit in revisions:
        for pr in api.pages(ctx.BASE+f'/commits/{commit}/pulls'):
            merge=pr.get('merge_commit_sha')
            if (pr.get('base',{}).get('ref')=='main' and pr.get('merged') is True and
                    merge in revision_set):
                previous=prs_by_merge.get(merge)
                ctx.require(previous is None or previous.get('number')==pr.get('number'),
                        'Main integration maps to contradictory pull requests')
                prs_by_merge[merge]=pr
    integrations=[];covered=set()
    for commit in reversed(revisions):
        pr=prs_by_merge.get(commit)
        if pr is None: continue
        loaded=readiness_for(pr['number'],normalized=True)
        indexed=loaded['evidence']
        ctx.require(indexed.get('origin',{}).get('kind')=='ordinary' and
                indexed.get('baseline_revision')==baseline and indexed.get('owner_id')==owner_id,
                'Ordinary readiness index anchor or owner mismatch')
        matches=[item for item in indexed.get('integrations',[])
                 if item.get('pull_request')==pr['number'] and
                 item.get('integrated_revision')==commit]
        ctx.require(len(matches)==1,'Normalized readiness index does not identify exact merge')
        integration=matches[0]
        integration['readiness_index']=readiness_index_binding(ctx, loaded)
        members=integration.get('integrated_commits',[])
        verify_membership(ctx, api,integration)
        ctx.require(members and members[-1]==commit and not (set(members)&covered),
                'Overlapping or unavailable PR first-parent membership')
        covered.update(members);integrations.append(integration)
    ctx.require(set(revisions)<=covered,'Unmapped first-parent main integration')
    result={'schema_version':2,'owner_id':owner_id,
            'origin':{'kind':'ordinary'},'baseline_revision':baseline,
            'integrations':integrations,'anchor_release':tag}
    return result

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
