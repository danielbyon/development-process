"""Verify review chains, evidence chronology, and baseline admission."""
from __future__ import annotations

from pathlib import Path
import json
import re

from release_evidence_records import (
    _evidence_timestamp, _require_pull_request_comment, load_readiness_index,
    readiness_index_binding, verify_ci_pull_request, verify_ci_suites,
    verify_event_chronology)

_BASELINE_ADMISSION_SEAL=object()
_BASELINE_QUALIFICATION_SEAL=object()

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

def _receipt_event(ctx, record,entry,owner_id,gate,pull_request):
    ctx.require(isinstance(entry,dict) and entry.get('ref') and entry.get('sha256'),
            f'Missing {gate} provider receipt')
    ctx.require(isinstance(record,dict) and ctx.digest(ctx.canonical(record))==entry['sha256'],
            f'Stale {gate} provider receipt')
    ctx.require(record.get('user',{}).get('id')==owner_id,
            f'{gate} receipt must be owner-authenticated')
    _require_pull_request_comment(ctx,record,pull_request,gate)
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
            ctx.require(name and path.parts and not path.is_absolute() and
                    '..' not in path.parts and '\\' not in name,
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
    """Authenticate chronological evidence for ordinary integrations."""
    ctx.require(isinstance(evidence,dict) and evidence.get('schema_version')==2,
            'New qualification requires evidence schema v2')
    ctx.require(root is not None,'Git checkout required to bind reviewed diff and inspected files')
    if callable(source):
        fetch=source;api=getattr(source,'__self__',None)
    else:
        api=source if hasattr(source,'record') else None
        fetch=api.record if api is not None else source
    origin=evidence.get('origin',{})
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
        pull_request=integration.get('pull_request')
        ctx.require(type(pull_request) is int and pull_request>0,
                'Integration pull request identity required')
        target=integration.get('reviewed_revision'); base=integration.get('base_revision')
        ctx.require(isinstance(target,str) and ctx.SHA.fullmatch(target) and
                isinstance(base,str) and ctx.SHA.fullmatch(base),'Reviewed integration range required')
        records=integration.get('records',{})
        ctx.require(isinstance(records,dict),'Integration provider receipts required')
        index_binding=integration.get('readiness_index')
        ctx.require(isinstance(index_binding,dict),'Authenticated readiness index binding required')
        index_ref=index_binding.get('normalization_ref') or index_binding.get('index_ref')
        loaded=load_readiness_index(ctx, index_ref,fetch,pull_request)
        ctx.require(loaded['index_ref']==index_binding.get('index_ref') and
                loaded['index_sha256']==index_binding.get('index_sha256') and
                loaded['original_ref']==index_binding.get('original_ref') and
                loaded['original_sha256']==index_binding.get('original_sha256') and
                loaded['normalization_ref']==index_binding.get('normalization_ref') and
                loaded['normalization_sha256']==index_binding.get('normalization_sha256'),
                'Readiness index provider binding changed')
        embedded=[item for item in loaded['evidence'].get('integrations',[])
                  if item.get('pull_request')==pull_request]
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
        author_event=_receipt_event(ctx, author_record,records['author_execution'],owner_id,
                                    'author_execution',pull_request)
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
            event=_receipt_event(ctx, actual,entry,owner_id,'independent_review',pull_request)
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
        chat_event=_receipt_event(ctx, chat_record,chat_entry,owner_id,
                                  'chatgpt_inspection',pull_request)
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
        owner_event=_receipt_event(ctx, owner_record,owner_entry,owner_id,
                                   'owner_authorization',pull_request)
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
