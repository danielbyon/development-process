"""Read-only audit of release evidence and unrun qualification gates."""

from __future__ import annotations

from github_releases import APIError

from .common import (
    BASE, JSON, MissingEvidenceError, REPOSITORY, ReleaseError, _EvidenceAPI,
    canonical, digest, require,
)
from .baseline import verify_baseline_admission
from .integrations import verify_live_integrations, verify_premerge_integrations
from .qualification import (
    verify_coverage, verify_evidence, verify_pending_baseline_coverage,
)
from .records import load_readiness_index, readiness_index_binding

def _audit_error_status(error: Exception) -> str:
    return 'MISSING_EVIDENCE' if isinstance(error,MissingEvidenceError) else 'FAIL'

def audit_pull_request(root: RepositoryPath,
                       api: _EvidenceAPI, number: int) -> JSON:
    """Report evidence and pending runtime gates using only provider GETs."""
    result={'repository':REPOSITORY,'pull_request':number,'gates':{
        'account':'NOT_RUN','repository_identity':'NOT_RUN','pull_request_identity':'NOT_RUN',
        'evidence_receipts':'NOT_RUN','candidate_ci':'NOT_RUN','merge':'NOT_RUN',
        'integrated_revision':'NOT_RUN','git_coverage':'NOT_RUN',
        'baseline_admission':'NOT_RUN','release_dispatch':'NOT_RUN',
        'release_runtime':'NOT_RUN','publication':'NOT_RUN'},'details':{}}
    current_gate='account'
    try:
        user=api.request('GET','/user')
        require(user.get('login')=='danielbyon','Explicit audit credential must authenticate as danielbyon')
        result['gates']['account']='PASS'
        current_gate='repository_identity'
        repository=api.record(BASE)
        require(repository.get('full_name')==REPOSITORY and
                repository.get('owner',{}).get('login')=='danielbyon',
                'GitHub repository identity mismatch')
        result['gates']['repository_identity']='PASS'
        current_gate='pull_request_identity'
        pr=api.record(BASE+f'/pulls/{int(number)}')
        require(pr.get('number')==int(number) and pr.get('base',{}).get('ref')=='main' and
                pr.get('base',{}).get('repo',{}).get('full_name',REPOSITORY)==REPOSITORY,
                'Pull request identity or target mismatch')
        result['gates']['pull_request_identity']='PASS'
        current_gate='evidence_receipts'
        comments=api.pages(BASE+f'/issues/{int(number)}/comments')
        marker='<!-- release-readiness\n'; candidates=[]
        for comment in comments:
            if marker not in comment.get('body',''): continue
            reference=BASE+f'/issues/comments/{comment.get("id")}'
            loaded=load_readiness_index(reference,api.record,int(number))
            candidates.append(loaded)
        if not candidates:
            raise MissingEvidenceError('No release-readiness index was found')
        normalized=[item for item in candidates if item['normalization_record'] is not None]
        originals=[item for item in candidates if item['normalization_record'] is None]
        pending_baselines=[]
        if pr.get('merged_at'):
            pending_baselines=[item for item in originals
                if item['evidence'].get('origin',{}).get('kind')=='prospective_baseline']
            if len(normalized)==1 and not pending_baselines:
                loaded=normalized[0]
            elif not normalized and len(originals)==1 and not pending_baselines:
                raise MissingEvidenceError(
                    'Merged ordinary pull request has no normalized readiness index')
            else:
                require(not normalized and len(originals)==1 and len(pending_baselines)==1,
                        'Missing or contradictory release-readiness normalization or baseline index')
                loaded=pending_baselines[0]
        else:
            require(len(originals)==1 and not normalized,
                    'Missing or contradictory pre-merge release-readiness index')
            loaded=originals[0]
        evidence=loaded['evidence']
        if evidence.get('origin',{}).get('kind')=='prospective_baseline':
            if not pr.get('merged_at'):
                raise MissingEvidenceError(
                    'Prospective baseline admission requires the corrected merge')
            evidence['readiness_index']=readiness_index_binding(loaded)
            current_gate='baseline_admission'
            baseline=evidence.get('baseline_revision')
            qualification=verify_baseline_admission(root,api,evidence,
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
                main_ref=api.record(BASE+'/git/ref/heads/main')
                main_revision=main_ref.get('object',{}).get('sha')
                if not main_revision:
                    raise MissingEvidenceError('Current main revision is unavailable')
                verify_pending_baseline_coverage(root,evidence,qualification,baseline,main_revision)
                result['gates']['git_coverage']='PASS'
            except (ReleaseError,APIError,OSError,ValueError,KeyError,TypeError) as error:
                result['gates']['git_coverage']=_audit_error_status(error)
                result['details']['git_coverage']=str(error)
            result['details'].update(evidence_digest=digest(canonical(qualification)),
                baseline_revision=baseline,merged_at=pr.get('merged_at'))
            current_gate='baseline_admission'
        else:
            matched=[entry for entry in evidence.get('integrations',[])
                     if entry.get('pull_request')==int(number)]
            require(len(matched)==1,'Release evidence does not identify this pull request exactly once')
            integration=matched[0]
            integration['readiness_index']=readiness_index_binding(loaded)
            # The persisted index predates the merge; the derived local binding is
            # attached only after its provider record has been authenticated.
            snapshots=verify_evidence(evidence,api.record,root)
            require(pr.get('head',{}).get('sha')==integration.get('reviewed_revision'),
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
                        verify_live_integrations(
                            api,{'schema_version':2,'integrations':[integration]},root,
                            ordinary_evidence=snapshots)
                        result['gates']['candidate_ci']='PASS'
                        current_gate='git_coverage'
                        verify_coverage(root,evidence,integration['integrated_revision'],
                                        admitted=True,ordinary_evidence=snapshots)
                        result['gates']['git_coverage']='PASS'
                    except (ReleaseError,APIError,OSError,ValueError,KeyError,TypeError) as error:
                        result['gates'][current_gate]=_audit_error_status(error)
                        result['details'][current_gate]=str(error)
                else:
                    result['gates']['integrated_revision']='FAIL'
                    result['details']['integrated_revision']='Normalized evidence does not name the provider merge SHA'
            else:
                current_gate='candidate_ci'
                verify_premerge_integrations(
                    api,{'integrations':[integration]},root,ordinary_evidence=snapshots)
                result['gates']['candidate_ci']='PASS'
            result['details'].update(evidence_digest=digest(canonical(snapshots)),
                                     reviewed_revision=integration.get('reviewed_revision'),
                                     merged_at=pr.get('merged_at'))
    except (ReleaseError,APIError,OSError,ValueError,KeyError,TypeError) as error:
        if result['gates'][current_gate]=='NOT_RUN':
            result['gates'][current_gate]=_audit_error_status(error)
        result['details'][current_gate]=str(error)
    result['gates']['release_dispatch']='NOT_RUN'
    result['gates']['release_runtime']='NOT_RUN'
    result['gates']['publication']='NOT_RUN'
    return result
