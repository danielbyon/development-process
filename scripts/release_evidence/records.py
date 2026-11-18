"""Read-only verification for historical readiness, chronology, and CI records."""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml

from .common import (
    BASE, CI_REQUIRED_JOB_NAME, CI_REVISION_CHECK_STEP_NAME, CI_WORKFLOW_ID,
    CI_WORKFLOW_NAME, CI_WORKFLOW_PATH, JSON, MissingEvidenceError,
    REPOSITORY, SHA, SUITES, ReleaseError,
    _EvidenceAPI, canonical, digest, git, require, require_present,
)

def _readiness_payload(reference,record,owner_id,pull_request):
    match=re.fullmatch(re.escape(BASE)+r'/issues/comments/([1-9][0-9]*)',reference or '')
    require(match is not None and record.get('id')==int(match[1]),
            'Readiness index provider record identity mismatch')
    require(record.get('user',{}).get('id')==owner_id,
            'Readiness index must be owner-authenticated')
    _require_pull_request_comment(record,pull_request,'Readiness index')
    marker='<!-- release-readiness\n';body=record.get('body','')
    if marker not in body:
        raise MissingEvidenceError('Readiness index payload is missing')
    require(body.count(marker)==1 and '\n-->' in body,
            'Inspectable release-readiness index required')
    try: payload=json.loads(body.split(marker,1)[1].split('\n-->',1)[0])
    except (ValueError,IndexError) as error:
        raise ReleaseError('Malformed release-readiness index') from error
    require(payload.get('schema_version')==2 and payload.get('repository')==REPOSITORY and
            payload.get('pull_request')==pull_request,
            'Readiness index schema, repository or pull request mismatch')
    evidence=payload.get('evidence')
    require_present(evidence,'Readiness index evidence payload is missing')
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

def _evidence_timestamp(value):
    if value is None or value=='':
        raise MissingEvidenceError('Provider timestamp is missing')
    require(isinstance(value,str),'Provider timestamp is malformed')
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
    require(isinstance(provider_records,list),'Provider records are malformed')
    if not provider_records:
        raise MissingEvidenceError('Provider records are missing')
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
    require(isinstance(relationships,list),'CI pull request relationships are malformed')
    if not relationships:
        raise MissingEvidenceError('CI pull request identity is missing')
    matches=[item for item in relationships if item.get('number')==pull_request]
    require(len(matches)==1,'CI run does not identify the exact pull request')
    relation=matches[0]
    require(relation.get('head',{}).get('sha')==head_revision and
            relation.get('base',{}).get('ref')=='main' and
            relation.get('base',{}).get('sha')==base_revision,
            'CI pull request head or base identity mismatch')
    return True

def verify_ci_workflow_identity(ci_record: JSON) -> bool:
    """Require the provider run to come from this repository's CI workflow."""
    require(type(ci_record.get('workflow_id')) is int and
            ci_record.get('workflow_id')==CI_WORKFLOW_ID and
            ci_record.get('path')==CI_WORKFLOW_PATH and
            ci_record.get('name')==CI_WORKFLOW_NAME and
            ci_record.get('event')=='pull_request',
            'CI run is not from the required CI workflow')
    return True

def verify_ci_job_identity(ci_record: JSON, job: JSON, attempt: int,
                           steps: Sequence[JSON]) -> bool:
    """Bind the required job and its revision check to one provider run attempt."""
    run_id=ci_record.get('id')
    require(type(run_id) is int and run_id>0 and type(attempt) is int and attempt>0 and
            type(job.get('run_id')) is int and job.get('run_id')==run_id and
            type(job.get('run_attempt')) is int and job.get('run_attempt')==attempt,
            'CI job run identity mismatch')
    require(isinstance(steps,list) and all(isinstance(step,dict) for step in steps),
            'Required CI job steps are unavailable')
    required=[step for step in steps
              if step.get('name')==CI_REVISION_CHECK_STEP_NAME]
    require(len(required)==1,'Required CI revision-check step is missing or ambiguous')
    step=required[0]
    require(step.get('status')=='completed' and step.get('conclusion')=='success' and
            step.get('outcome','success')=='success',
            'Required CI revision-check step did not complete successfully')
    return True

def _ci_workflow_for_safe_path_comparison(workflow_bytes,require_safe_path):
    """Compare workflows after removing their approved safe-path settings."""
    workflow=yaml.safe_load(workflow_bytes)
    require(isinstance(workflow,dict) and isinstance(workflow.get('jobs'),dict),
            'CI tested-commit workflow is malformed')
    jobs=[job for job in workflow['jobs'].values()
          if job.get('name')==CI_REQUIRED_JOB_NAME]
    require(len(jobs)==1,'CI tested-commit job is missing or ambiguous')
    steps=jobs[0].get('steps',[])
    require(isinstance(steps,list) and all(isinstance(step,dict) for step in steps),
            'CI tested-commit steps are malformed')
    expected={f'python3 -m unittest discover -s tests -p {suite} -v'
              for suite in SUITES}
    found=[]
    for step in steps:
        if step.get('run','').strip() not in expected:
            continue
        found.append(step['run'].strip())
        environment=step.get('env')
        if require_safe_path:
            require(environment=={'PYTHONSAFEPATH':'1'},
                    'CI suite steps must enable PYTHONSAFEPATH')
        else:
            require(environment in (None,{}, {'PYTHONSAFEPATH':'1'}),
                    'PR base CI suite environment is unsupported')
        step.pop('env',None)
    require(sorted(found)==sorted(expected),
            'CI workflow does not contain each required suite exactly once')
    return workflow

def _ci_test_strategy(root,workflow_revision,base_revision):
    workflow_bytes=git(root,'show',workflow_revision+':.github/workflows/ci.yml')
    base_workflow=git(root,'show',base_revision+':.github/workflows/ci.yml')
    workflow_for_comparison=_ci_workflow_for_safe_path_comparison(
        workflow_bytes,require_safe_path=True)
    base_for_comparison=_ci_workflow_for_safe_path_comparison(
        base_workflow,require_safe_path=False)
    require(workflow_for_comparison==base_for_comparison,
            'CI workflow differs from the PR base')
    workflow=yaml.safe_load(workflow_bytes.decode())
    require(isinstance(workflow,dict) and isinstance(workflow.get('jobs'),dict),
            'CI tested-commit workflow is malformed')
    jobs=[job for job in workflow['jobs'].values()
          if job.get('name')==CI_REQUIRED_JOB_NAME]
    require(len(jobs)==1 and not any(key in jobs[0]
            for key in ('if','continue-on-error','strategy')),
            'CI tested-commit job is conditional or ambiguous')
    steps=jobs[0].get('steps',[])
    require(isinstance(steps,list) and all(isinstance(step,dict) for step in steps),
            'CI tested-commit steps are malformed')
    checkouts=[step for step in steps
               if isinstance(step.get('uses'),str) and step['uses'].startswith('actions/checkout@')
               and not step.get('with',{}).get('path')]
    checks=[step for step in steps
            if step.get('name')==CI_REVISION_CHECK_STEP_NAME]
    require(len(checkouts)==1 and len(checks)==1,
            'CI tested-commit checkout or identity step is missing or ambiguous')
    checkout=checkouts[0]
    check=checks[0]
    require(steps.index(checkout)<steps.index(check) and
            checkout.get('with',{}).get('fetch-depth')==0 and
            not any(key in checkout for key in ('if','continue-on-error')) and
            not any(key in check for key in ('if','continue-on-error')) and
            check.get('shell')=='bash',
            'CI tested-commit checkout or revision check is optional or incomplete')
    checkout_ref=checkout.get('with',{}).get('ref')
    environment=check.get('env',{})
    require(environment.get('EXPECTED_BASE_SHA')=='${{ github.event.pull_request.base.sha }}' and
            environment.get('EXPECTED_HEAD_SHA')=='${{ github.event.pull_request.head.sha }}',
            'CI tested-commit workflow does not bind the PR head and base')
    run='\n'.join(line for line in check.get('run','').splitlines()
                   if line.strip() and not line.lstrip().startswith('#'))
    require('actual_test_sha="$(git rev-parse HEAD)"' in run and
            'if [[ "$actual_test_sha" != "$EXPECTED_TEST_SHA" ]]' in run,
            'CI does not verify the checked-out test revision')
    test_sha=environment.get('EXPECTED_TEST_SHA')
    if checkout_ref=='${{ github.sha }}' and test_sha=='${{ github.sha }}':
        require('git rev-list --parents -n 1 HEAD' in run and
                'git rev-parse HEAD^1' in run and 'git rev-parse HEAD^2' in run and
                'if [[ "$actual_base_sha" != "$EXPECTED_BASE_SHA" ]]' in run and
                'if [[ "$actual_head_sha" != "$EXPECTED_HEAD_SHA" ]]' in run,
                'Synthetic-merge CI does not verify both expected parents')
        return 'synthetic_merge'
    direct_head='${{ github.event.pull_request.head.sha }}'
    if checkout_ref==direct_head and test_sha==direct_head:
        require('git merge-base --is-ancestor "$EXPECTED_BASE_SHA" "$EXPECTED_TEST_SHA"' in run,
                'Direct-head CI does not verify base ancestry')
        return 'direct_head'
    raise ReleaseError('CI tested-commit checkout strategy is unsupported')

def ci_test_commit_tree_sha(record: JSON) -> str:
    """Read the tree identity from GitHub's repository-commit response."""
    commit=record.get('commit') if isinstance(record,dict) else None
    tree=commit.get('tree') if isinstance(commit,dict) else None
    tree_sha=tree.get('sha') if isinstance(tree,dict) else None
    require(isinstance(tree_sha,str) and SHA.fullmatch(tree_sha),
            'Provider CI-tested commit tree is malformed')
    return tree_sha

def verify_ci_test_commit(fetch: Callable[[str], Any], root: str | Path,
                          ci_record: JSON, pull_request: int,
                          tested_revision: str, reviewed_revision: str,
                          base_revision: str, workflow_revision: str) -> tuple[JSON, str]:
    """Bind CI's tested commit to the reviewed PR head and base using Git parents."""
    require(type(pull_request) is int and pull_request>0,
            'CI tested-commit pull request identity is invalid')
    for value in (tested_revision,reviewed_revision,base_revision,workflow_revision):
        require(isinstance(value,str) and SHA.fullmatch(value),
                'CI tested-commit revisions must be full immutable SHAs')
    require(ci_record.get('head_sha')==reviewed_revision,
            'CI run head differs from the reviewed PR head')
    verify_ci_pull_request(ci_record,pull_request,reviewed_revision,base_revision)
    verify_ci_workflow_identity(ci_record)
    strategy=_ci_test_strategy(root,workflow_revision,base_revision)
    record=fetch(BASE+'/commits/'+tested_revision)
    require(isinstance(record,dict) and record.get('sha')==tested_revision,
            'Provider commit identity differs from the CI-tested revision')
    tree=ci_test_commit_tree_sha(record)
    parents=record.get('parents')
    require(isinstance(parents,list) and all(isinstance(parent,dict) and
            isinstance(parent.get('sha'),str) and SHA.fullmatch(parent['sha'])
            for parent in parents),
            'Provider CI-tested commit parents are malformed')
    parent_shas=[parent['sha'] for parent in parents]
    if strategy=='synthetic_merge':
        require(parent_shas==[base_revision,reviewed_revision],
                'CI-tested commit does not have the expected synthetic merge parents')
    else:
        require(tested_revision==reviewed_revision,
                'Direct-head CI must test the exact reviewed PR head')
        local_parents=git(root,'show','-s','--format=%P',reviewed_revision).decode().split()
        require(parent_shas==local_parents,
                'Provider and local reviewed-head parents differ')
        try:
            git(root,'merge-base','--is-ancestor',base_revision,reviewed_revision)
        except ReleaseError as error:
            raise ReleaseError('Direct-head CI base is not an ancestor of the reviewed head') from error
    return record,strategy

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
        require(not any(k in step for k in ('if','continue-on-error','working-directory')),
                'Conditional or altered suite execution: '+suite)
        if schema==2:
            require(step.get('env')=={'PYTHONSAFEPATH':'1'},
                    'Mandatory suite execution must enable PYTHONSAFEPATH: '+suite)
        else:
            require('env' not in step,
                    'Historical suite execution has an unexpected environment: '+suite)
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
