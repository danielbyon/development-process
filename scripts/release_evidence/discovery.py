"""Read-only discovery and assembly of evidence for a release candidate."""

from __future__ import annotations

from typing import Callable

from .common import BASE, BOOTSTRAP_BASELINE, JSON, REPOSITORY, ReleaseError, _EvidenceAPI, git, require, revision
from .integrations import verify_membership
from .records import load_readiness_index, readiness_index_binding

def discover_evidence(
        root: RepositoryPath, api: _EvidenceAPI,
        source: str, builder: str,
        select_anchor: Callable[[RepositoryPath, _EvidenceAPI, str, str], JSON | None]
        ) -> JSON:
    """Build current evidence from authenticated readiness indexes and Git.

    The initial release must use a separately admitted prospective baseline.
    Later releases cover each first-parent integration after an immutable anchor.
    """
    source=revision(root,source);builder=revision(root,builder)
    repo=api.request('GET',BASE)
    require(repo.get('full_name')==REPOSITORY and repo.get('owner',{}).get('id') is not None,
            'Repository identity unavailable during evidence discovery')
    owner_id=repo['owner']['id']
    anchor=select_anchor(root,api,source,builder)

    def readiness_for(pr_number,*,normalized):
        comments=api.pages(BASE+f'/issues/{pr_number}/comments')
        found=[];marker='<!-- release-readiness\n'
        for comment in comments:
            if marker not in comment.get('body',''): continue
            reference=BASE+f'/issues/comments/{comment.get("id")}'
            loaded=load_readiness_index(reference,api.record,pr_number)
            if (loaded['normalization_record'] is not None)==normalized:
                found.append(loaded)
        require(len(found)==1,
                'Missing or contradictory '+('normalized' if normalized else 'original')+
                f' readiness index for PR {pr_number}')
        return found[0]

    if anchor is None:
        require(source==builder,
                'First release requires source and builder to equal the prospective baseline')
        prs=api.pages(BASE+f'/commits/{source}/pulls')
        matches=[pr for pr in prs if pr.get('merge_commit_sha')==source and
                 pr.get('base',{}).get('ref')=='main' and pr.get('merged') is True]
        require(len(matches)==1,'Prospective baseline must be the exact corrected main merge')
        pr=matches[0];loaded=readiness_for(pr['number'],normalized=False)
        evidence=loaded['evidence']
        require(evidence.get('origin',{}).get('kind')=='prospective_baseline' and
                evidence.get('baseline_revision')==source and evidence.get('integrations')==[] and
                evidence.get('owner_id')==owner_id and
                evidence.get('origin',{}).get('source_revision')==source and
                evidence.get('origin',{}).get('builder_revision')==builder,
                'Prospective baseline readiness index identity mismatch')
        require(evidence.get('baseline_admission',{}).get('correction_pull_request')==pr['number'],
                'Prospective baseline admission references a different correction PR')
        evidence['readiness_index']=readiness_index_binding(loaded)
        return evidence

    baseline,tag=anchor
    try:
        git(root,'merge-base','--is-ancestor',baseline,source)
        git(root,'merge-base','--is-ancestor',baseline,builder)
    except ReleaseError as error:
        raise ReleaseError('Source and builder must descend from a verified immutable release') from error
    revisions=git(root,'rev-list','--first-parent',baseline+'..'+builder).decode().split()
    revision_set=set(revisions);prs_by_merge={}
    for commit in revisions:
        for pr in api.pages(BASE+f'/commits/{commit}/pulls'):
            merge=pr.get('merge_commit_sha')
            if (pr.get('base',{}).get('ref')=='main' and pr.get('merged') is True and
                    merge in revision_set):
                previous=prs_by_merge.get(merge)
                require(previous is None or previous.get('number')==pr.get('number'),
                        'Main integration maps to contradictory pull requests')
                prs_by_merge[merge]=pr
    integrations=[];covered=set()
    for commit in reversed(revisions):
        pr=prs_by_merge.get(commit)
        if pr is None: continue
        loaded=readiness_for(pr['number'],normalized=True)
        indexed=loaded['evidence']
        require(indexed.get('origin',{}).get('kind')=='ordinary' and
                indexed.get('baseline_revision')==baseline and indexed.get('owner_id')==owner_id,
                'Ordinary readiness index anchor or owner mismatch')
        matches=[item for item in indexed.get('integrations',[])
                 if item.get('pull_request')==pr['number'] and
                 item.get('integrated_revision')==commit]
        require(len(matches)==1,'Normalized readiness index does not identify exact merge')
        integration=matches[0]
        integration['readiness_index']=readiness_index_binding(loaded)
        members=integration.get('integrated_commits',[])
        verify_membership(api,integration)
        require(members and members[-1]==commit and not (set(members)&covered),
                'Overlapping or unavailable PR first-parent membership')
        covered.update(members);integrations.append(integration)
    require(set(revisions)<=covered,'Unmapped first-parent main integration')
    result={'schema_version':2,'owner_id':owner_id,
            'origin':{'kind':'ordinary'},'baseline_revision':baseline,
            'integrations':integrations,'anchor_release':tag}
    return result
