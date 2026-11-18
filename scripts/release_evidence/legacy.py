"""Compatibility verification for evidence frozen in existing releases."""

from __future__ import annotations

import json

from .common import (
    BASE, REPOSITORY, SHA, ReleaseError, canonical, digest, require,
)

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

def _verify_frozen_release_evidence_v1(evidence,fetch):
    """Resolve record references and require exact content and candidate binding.

    Exported reports are accepted only through an authenticated repository record
    containing the report, execution identity and reviewed revision. Booleans and
    summaries without those records cannot satisfy a gate.
    """
    require(isinstance(evidence,dict) and evidence.get('schema_version')==1,'Frozen schema v1 evidence required')
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

def verify_frozen_release_evidence(evidence,fetch):
    """Verify schema-v1 evidence embedded in an already-signed release only."""
    require(isinstance(evidence,dict) and evidence.get('schema_version')==1,
            'Frozen schema v1 evidence required')
    return _verify_frozen_release_evidence_v1(evidence,fetch)
