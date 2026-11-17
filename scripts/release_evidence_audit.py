"""Report evidence readiness without changing release or GitHub state."""
from __future__ import annotations

from release_evidence_records import load_readiness_index, readiness_index_binding
from release_evidence_baseline import verify_baseline_admission
from release_evidence_qualification import verify_coverage, verify_evidence, verify_pending_baseline_coverage
from release_evidence_integrations import verify_live_integrations, verify_membership, verify_premerge_integrations

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
