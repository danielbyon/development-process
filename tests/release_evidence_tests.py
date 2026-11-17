"""Tests for evidence receipt capture, chronology, and ordinary integrations."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_release as release
import release_evidence as evidence
from release_evidence import audit, baseline, discovery, integrations, legacy, qualification, records
EVIDENCE_MODULES=(audit,baseline,discovery,integrations,legacy,qualification,records)
evidence_module=records

def evidence_operation(name):
    for module in EVIDENCE_MODULES:
        if hasattr(module,name): return getattr(module,name)
    raise AttributeError(f'No evidence operation named {name}')

def evidence_call(name,*args,**kwargs):
    if name=='discover_evidence':
        kwargs.setdefault('select_anchor',release.select_anchor)
    return evidence_operation(name)(*args,**kwargs)

def isolated_repository(test_case):
    import subprocess,tempfile
    temporary=tempfile.TemporaryDirectory(prefix='release-evidence-fixture-')
    test_case.addCleanup(temporary.cleanup)
    source=Path(__file__).resolve().parents[1]
    root=Path(temporary.name)/'repository'
    subprocess.run(['git','clone','--quiet','--shared',str(source),str(root)],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return root

class EvidenceModuleBoundaryTests(unittest.TestCase):
    def test_controller_uses_module_operations_without_reexporting_them(self):
        import inspect
        operations={
            'audit_pull_request','build_owner_receipt','capture_execution',
            'discover_evidence','prepare_readiness_index',
            'verify_baseline_admission','verify_coverage','verify_evidence',
            'verify_live_integrations','verify_pending_baseline_coverage',
            'verify_premerge_integrations'}
        self.assertFalse(hasattr(release,'_EVIDENCE_CONTEXT'))
        self.assertFalse(hasattr(evidence,'EvidenceContext'))
        self.assertFalse(hasattr(evidence,'EvidenceService'))
        owners={
            'audit_pull_request':audit,
            'build_owner_receipt':records,
            'capture_execution':records,
            'discover_evidence':discovery,
            'prepare_readiness_index':records,
            'verify_baseline_admission':baseline,
            'verify_coverage':qualification,
            'verify_evidence':qualification,
            'verify_live_integrations':integrations,
            'verify_pending_baseline_coverage':qualification,
            'verify_premerge_integrations':integrations,
        }
        for operation,module in owners.items():
            with self.subTest(operation=operation):
                implementation=getattr(module,operation)
                self.assertTrue(callable(implementation))
                self.assertEqual(inspect.getmodule(implementation).__name__,module.__name__)
                self.assertFalse(hasattr(evidence,operation))
                self.assertFalse(hasattr(release,operation))
        self.assertEqual(set(owners),operations)
        self.assertEqual(inspect.getmodule(release.verify_frozen_release_evidence).__name__,
                         'release_evidence.legacy')
        self.assertEqual(inspect.getmodule(release.load_evidence_export).__name__,
                         'release_evidence.legacy')
        self.assertFalse(hasattr(release,'execution_provenance'))
        self.assertFalse(hasattr(release,'_verify_frozen_release_evidence_v1'))
        for implementation_detail in (
                'verify_review_chain','verify_review_dispositions',
                'verify_event_chronology','verify_ci_pull_request',
                'verify_execution_receipt','load_readiness_index',
                'readiness_index_binding','verify_ci_suites'):
            with self.subTest(implementation_detail=implementation_detail):
                self.assertFalse(hasattr(release,implementation_detail))

    def test_module_operations_have_explicit_typed_signatures(self):
        import inspect
        operations=(
            'audit_pull_request','build_owner_receipt','capture_execution',
            'discover_evidence','prepare_readiness_index',
            'verify_baseline_admission','verify_coverage','verify_evidence',
            'verify_live_integrations','verify_pending_baseline_coverage',
            'verify_premerge_integrations')
        for name in operations:
            with self.subTest(operation=name):
                signature=inspect.signature(evidence_operation(name))
                parameters=list(signature.parameters.values())
                self.assertFalse(any(parameter.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD) for parameter in parameters))
                self.assertTrue(all(parameter.annotation is not inspect.Parameter.empty
                                    for parameter in parameters))
                self.assertIsNot(signature.return_annotation,inspect.Signature.empty)


class EvidenceV2Tests(unittest.TestCase):
    def ordinary_fixture(self,root=None,base=None,head=None,pull_request=5,comment_offset=0,
                         tested_parents=None):
        import json,os,subprocess
        root=isolated_repository(self) if root is None else Path(root)
        owner=123
        default_head=head is None
        head=head or release.git(root,'rev-parse','HEAD').decode().strip()
        default_base=release.git(root,'rev-parse',head+'^').decode().strip() if default_head else \
            release.git(root,'rev-parse',head+'^').decode().strip()
        base=base or default_base
        tree=release.git(root,'rev-parse',head+'^{tree}').decode().strip()
        if tested_parents=='unrelated':
            parents=[base]
        elif tested_parents=='wrong_order':
            parents=[head,base]
        else:
            parents=tested_parents or [base,head]
        env=os.environ.copy()
        env.update(GIT_AUTHOR_NAME='Release Evidence Test',
                   GIT_AUTHOR_EMAIL='release-evidence@example.invalid',
                   GIT_COMMITTER_NAME='Release Evidence Test',
                   GIT_COMMITTER_EMAIL='release-evidence@example.invalid',
                   GIT_AUTHOR_DATE='2026-11-16 17:45:00 +0000',
                   GIT_COMMITTER_DATE='2026-11-16 17:45:00 +0000')
        command=['git','-C',str(root),'commit-tree',tree]
        for parent in parents: command.extend(['-p',parent])
        command.extend(['-m','synthetic pull request test commit'])
        tested_revision=subprocess.check_output(command,env=env).decode().strip()
        tested_record={'sha':tested_revision,'tree':{'sha':tree},
            'parents':[{'sha':parent} for parent in parents]}
        records={release.BASE:{
            'full_name':release.REPOSITORY,'owner':{'id':owner,'login':'danielbyon'}}};counter=comment_offset
        records[release.BASE+'/commits/'+tested_revision]=tested_record
        def post(gate,report,system,reviewed_range,created_at,transcript=None):
            nonlocal counter
            from unittest.mock import patch
            times={
                '2026-11-16T18:01:00Z':('2026-11-16T18:00:00Z','2026-11-16T18:00:30Z'),
                '2026-11-16T18:02:00Z':('2026-11-16T18:01:30Z','2026-11-16T18:01:45Z'),
                '2026-11-16T18:03:00Z':('2026-11-16T18:02:30Z','2026-11-16T18:02:45Z')}
            summary=report['summary']
            command=[sys.executable,'-c','import sys; print(sys.argv[1])',summary]
            with patch.object(evidence_module,'_utc_now',side_effect=times[created_at]):
                result=evidence_call('capture_execution',root,gate,system,command,report,
                    reviewed_range,transcript)
            counter+=1
            ref=release.BASE+'/issues/comments/'+str(counter)
            record={'id':counter,'user':{'id':owner},
                'issue_url':release.BASE+f'/issues/{pull_request}',
                'body':result['body'],'created_at':created_at,'updated_at':created_at}
            records[ref]=record
            return {'ref':ref,'sha256':release.digest(release.canonical(record))},result['event']
        author,author_event=post('author_execution',
            {'role':'author','summary':'Ran the implementation command.'},'separate_codex',
            {'base_revision':base,'head_revision':head},'2026-11-16T18:01:00Z')
        step={'coverage':'full-diff','base_revision':base,'head_revision':head,
              'diff_sha256':release.digest(release.git(root,'diff','--binary',base,head)),
              'findings':[],'dispositions':[]}
        review,review_event=post('independent_review',{'review_step':step,
            'summary':'Reviewed the complete implementation diff.'},'local_cubic',
            {'base_revision':base,'head_revision':head},
            '2026-11-16T18:02:00Z')
        changed=release.git(root,'diff','--name-only',base,head).decode().split()
        tracked=set(release.git(root,'ls-tree','-r','--name-only',head).decode().split())
        changed=[name for name in changed if name in tracked]
        source_files=sorted(name for name in changed if name.startswith('scripts/') and name.endswith('.py'))
        test_files=sorted(name for name in changed if name.startswith('tests/') and name.endswith('.py'))
        file_sha256={name:release.digest(release.git(root,'show',head+':'+name))
                     for name in source_files+test_files}
        chat_summary='Inspected changed source and tests: '+' '.join(source_files+test_files)
        chat,chat_event=post('chatgpt_inspection',{'source_files':source_files,
            'test_files':test_files,'file_sha256':file_sha256,
            'summary':chat_summary},'chatgpt',
            {'base_revision':base,'head_revision':head},'2026-11-16T18:03:00Z',
            chat_summary+'\n'+'\n'.join(source_files+test_files))
        owner_report={'action':'merge','verdict':'approve'}
        owner_event={'schema_version':2,'repository':release.REPOSITORY,
            'gate':'owner_authorization','revision':head,'report':owner_report,
            'report_sha256':release.digest(release.canonical(owner_report))}
        owner_ref=release.BASE+'/issues/comments/'+str(counter+1)
        owner_record={'id':counter+1,'user':{'id':owner},
            'issue_url':release.BASE+f'/issues/{pull_request}',
            'body':'<!-- release-evidence-v2\n'+json.dumps(owner_event,sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:04:00Z','updated_at':'2026-11-16T18:04:00Z'}
        records[owner_ref]=owner_record
        owner_entry={'ref':owner_ref,'sha256':release.digest(release.canonical(owner_record))}
        ci_ref=release.BASE+'/actions/runs/7'
        ci={'id':7,'repository':{'full_name':release.REPOSITORY},'event':'pull_request',
            'workflow_id':413585893,'path':'.github/workflows/ci.yml','name':'CI',
            'status':'completed','conclusion':'success','head_sha':head,'run_attempt':1,
            'pull_requests':[{'number':pull_request,'head':{'sha':head},
                'base':{'sha':base,'ref':'main'}}],
            'created_at':'2026-11-16T17:50:00Z','updated_at':'2026-11-16T18:03:00Z',
            'completed_at':'2026-11-16T18:03:00Z'}
        records[ci_ref]=ci
        integration_records={'author_execution':author,
            'independent_reviews':[review],'chatgpt_inspection':chat,
            'owner_authorization':owner_entry,'ci':{'ref':ci_ref,
            'sha256':release.digest(release.canonical(ci)),'run_attempt':1}}
        evidence={'schema_version':2,'owner_id':owner,'origin':{'kind':'ordinary'},
            'baseline_revision':base,'integrations':[{'pull_request':pull_request,'base_revision':base,
            'reviewed_revision':head,'tested_revision':tested_revision,
            'records':integration_records}]}
        index_evidence={'schema_version':2,'owner_id':owner,'origin':{'kind':'ordinary'},
            'baseline_revision':base,'integrations':[dict(evidence['integrations'][0])]}
        index_ref=release.BASE+'/issues/comments/'+str(counter+2)
        index_record={'id':counter+2,'user':{'id':owner},
            'issue_url':release.BASE+f'/issues/{pull_request}',
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':pull_request,
                'evidence':index_evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:05:00Z','updated_at':'2026-11-16T18:05:00Z'}
        records[index_ref]=index_record
        evidence['integrations'][0]['readiness_index']={
            'index_ref':index_ref,'index_sha256':release.digest(release.canonical(index_record)),
            'original_ref':index_ref,'original_sha256':release.digest(release.canonical(index_record)),
            'normalization_ref':None,'normalization_sha256':None}
        return evidence,records,{'author':author_event,'review':review_event,'chat':chat_event},root

    def test_default_fixture_uses_an_isolated_repository(self):
        import os,subprocess,tempfile
        from unittest.mock import patch
        source=Path(__file__).resolve().parents[1]
        common_dir=Path(subprocess.check_output(
            ['git','-C',str(source),'rev-parse','--git-common-dir'],
            text=True).strip())
        if not common_dir.is_absolute():common_dir=source/common_dir
        with tempfile.TemporaryDirectory() as object_directory:
            environment={'GIT_OBJECT_DIRECTORY':object_directory,
                'GIT_ALTERNATE_OBJECT_DIRECTORIES':str(common_dir/'objects')}
            with patch.dict(os.environ,environment):
                _,_,_,fixture_root=self.ordinary_fixture()
        self.assertNotEqual(fixture_root.resolve(),source.resolve())

    def test_ordinary_ci_commit_verifies_synthetic_merge_parents(self):
        from release_evidence.records import verify_ci_test_commit
        evidence,records,_,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        ci=records[integration['records']['ci']['ref']]
        commit,strategy=verify_ci_test_commit(
            records.__getitem__,root,ci,integration['pull_request'],
            integration['tested_revision'],integration['reviewed_revision'],
            integration['base_revision'],integration['reviewed_revision'])
        self.assertEqual(strategy,'synthetic_merge')
        self.assertEqual([parent['sha'] for parent in commit['parents']],
                         [integration['base_revision'],integration['reviewed_revision']])

    def test_unrelated_test_commit_with_identical_tree_is_rejected(self):
        evidence,records,_,root=self.ordinary_fixture(tested_parents='unrelated')
        integration=evidence['integrations'][0]
        tested=integration['tested_revision']
        record=records[release.BASE+'/commits/'+tested]
        self.assertEqual(record['tree']['sha'],
                         release.git(root,'rev-parse',integration['reviewed_revision']+'^{tree}').decode().strip())
        with self.assertRaisesRegex(release.ReleaseError,'expected synthetic merge parents'):
            evidence_call('verify_evidence',evidence,records.__getitem__,root)

    def test_ci_commit_with_wrong_parents_is_rejected_even_when_labels_can_match(self):
        fixture=self.ordinary_fixture(tested_parents='wrong_order')
        root,api,evidence,records,job,pr=OrdinaryChronologyIntegrationTests().qualified_fixture(fixture)
        integration=evidence['integrations'][0]
        self.assertIn('Tested integration revision: '+integration['tested_revision'],
                      api.job_log.return_value)
        with self.assertRaisesRegex(release.ReleaseError,'expected synthetic merge parents'):
            evidence_call('verify_evidence',evidence,api.record,root)

    def test_ci_test_commit_rejects_incorrect_reviewed_head_or_base(self):
        from release_evidence.records import verify_ci_test_commit
        evidence,records,_,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        ci=records[integration['records']['ci']['ref']]
        args=(records.__getitem__,root,ci,integration['pull_request'],
              integration['tested_revision'])
        with self.assertRaisesRegex(release.ReleaseError,'CI run head differs'):
            verify_ci_test_commit(*args,'0'*40,integration['base_revision'],
                                  integration['reviewed_revision'])
        with self.assertRaisesRegex(release.ReleaseError,'head or base identity mismatch'):
            verify_ci_test_commit(*args,integration['reviewed_revision'],'0'*40,
                                  integration['reviewed_revision'])

    def test_ci_test_commit_requires_the_provider_identified_ci_workflow(self):
        from release_evidence.records import verify_ci_test_commit
        evidence,records,_,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        ci=records[integration['records']['ci']['ref']]
        ci.update(workflow_id=413585893,path='.github/workflows/ci.yml')
        arguments=(records.__getitem__,root,ci,integration['pull_request'],
            integration['tested_revision'],integration['reviewed_revision'],
            integration['base_revision'],integration['reviewed_revision'])
        for field,value in (('path','.github/workflows/other.yml'),
                            ('workflow_id',0),('name','Unrelated workflow'),
                            ('event','workflow_dispatch')):
            with self.subTest(field=field):
                ci[field]=value
                with self.assertRaisesRegex(release.ReleaseError,'required CI workflow'):
                    verify_ci_test_commit(*arguments)
                ci[field]={'workflow_id':413585893,'path':'.github/workflows/ci.yml',
                           'name':'CI','event':'pull_request'}[field]

    def test_ci_workflow_change_cannot_comment_out_checks_then_switch_before_tests(self):
        import subprocess,tempfile,yaml
        from release_evidence.records import verify_ci_test_commit
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git','-C',str(root),*args],
                stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Release Evidence Test')
        git('config','user.email','release-evidence@example.invalid')
        workflow_path=root/'.github/workflows/ci.yml';workflow_path.parent.mkdir(parents=True)
        workflow_path.write_text((Path(__file__).resolve().parents[1]/
            '.github/workflows/ci.yml').read_text())
        (root/'candidate.txt').write_text('base\n')
        git('add','.');git('commit','-qm','base workflow')
        base=git('rev-parse','HEAD')
        workflow=yaml.safe_load(workflow_path.read_text())
        job=next(job for job in workflow['jobs'].values()
            if job.get('name')=='Validate committed PR integration diff')
        steps=job['steps']
        check_index=next(index for index,step in enumerate(steps)
            if step.get('name')=='Verify revision and check committed diff')
        check=steps[check_index]
        check['run']='true\n'+'\n'.join(
            '# '+line.strip() for line in check['run'].splitlines() if line.strip())
        steps.insert(check_index+1,{'name':'Switch before test steps',
            'run':'git checkout '+base})
        workflow_path.write_text(yaml.safe_dump(workflow,sort_keys=False))
        (root/'candidate.txt').write_text('reviewed\n')
        git('add','.');git('commit','-qm','reviewed workflow change')
        head=git('rev-parse','HEAD')
        tree=git('rev-parse',head+'^{tree}')
        tested=subprocess.check_output(['git','-C',str(root),'commit-tree',tree,
            '-p',base,'-p',head,'-m','synthetic test merge']).decode().strip()
        tested_record={'sha':tested,'tree':{'sha':tree},
            'parents':[{'sha':base},{'sha':head}]}
        ci={'workflow_id':413585893,'path':'.github/workflows/ci.yml',
            'name':'CI','event':'pull_request',
            'head_sha':head,'pull_requests':[{'number':17,
                'head':{'sha':head},'base':{'ref':'main','sha':base}}]}
        with self.assertRaisesRegex(release.ReleaseError,'workflow differs from the PR base'):
            verify_ci_test_commit(lambda _:tested_record,root,ci,17,tested,head,base,head)

    def test_direct_head_ci_is_accepted_only_with_matching_workflow_and_git_ancestry(self):
        import subprocess,tempfile,yaml
        from release_evidence.records import verify_ci_test_commit
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git','-C',str(root),*args],
                                           stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Release Evidence Test')
        git('config','user.email','release-evidence@example.invalid')
        workflow=yaml.safe_load((Path(__file__).resolve().parents[1]/
                                 '.github/workflows/ci.yml').read_text())
        job=next(job for job in workflow['jobs'].values()
                 if job.get('name')=='Validate committed PR integration diff')
        checkout=next(step for step in job['steps']
                      if step.get('uses','').startswith('actions/checkout@') and
                      not step.get('with',{}).get('path'))
        checkout['with']['ref']='${{ github.event.pull_request.head.sha }}'
        check=next(step for step in job['steps']
                   if step.get('name')=='Verify revision and check committed diff')
        check['env']['EXPECTED_TEST_SHA']='${{ github.event.pull_request.head.sha }}'
        check['run']='set -euo pipefail\nactual_test_sha="$(git rev-parse HEAD)"\n'
        check['run']+='if [[ "$actual_test_sha" != "$EXPECTED_TEST_SHA" ]]; then exit 1; fi\n'
        check['run']+='git cat-file -e "$EXPECTED_TEST_SHA^{commit}"\n'
        check['run']+='git merge-base --is-ancestor "$EXPECTED_BASE_SHA" "$EXPECTED_TEST_SHA"\n'
        check['run']+='printf "PR HEAD: %s\\n" "$EXPECTED_HEAD_SHA"\n'
        check['run']+='printf "Tested integration revision: %s\\n" "$EXPECTED_TEST_SHA"\n'
        check['run']+='printf "Tested base revision: %s\\n" "$EXPECTED_BASE_SHA"'
        workflow_path=root/'.github/workflows/ci.yml';workflow_path.parent.mkdir(parents=True)
        workflow_path.write_text(yaml.safe_dump(workflow,sort_keys=False))
        (root/'source.txt').write_text('base\n');git('add','.');git('commit','-qm','base')
        base=git('rev-parse','HEAD')
        (root/'source.txt').write_text('reviewed\n');git('add','.');git('commit','-qm','reviewed head')
        head=git('rev-parse','HEAD')
        record={'sha':head,'tree':{'sha':git('rev-parse',head+'^{tree}')},
                'parents':[{'sha':base}]}
        ci={'workflow_id':413585893,'path':'.github/workflows/ci.yml','name':'CI',
            'event':'pull_request','head_sha':head,'pull_requests':[{'number':11,
            'head':{'sha':head},'base':{'ref':'main','sha':base}}]}
        self.assertEqual(verify_ci_test_commit(
            lambda ref:record,root,ci,11,head,head,base,head)[1],'direct_head')

    def test_ci_base_workflow_cannot_make_the_revision_check_optional(self):
        import subprocess,yaml
        from release_evidence.records import verify_ci_test_commit
        root=isolated_repository(self)
        def git(*args):
            return subprocess.check_output(['git','-C',str(root),*args],
                stderr=subprocess.DEVNULL).decode().strip()
        git('config','user.name','Release Evidence Test')
        git('config','user.email','release-evidence@example.invalid')
        workflow_path=root/'.github/workflows/ci.yml'
        workflow=yaml.safe_load(workflow_path.read_text())
        job=next(job for job in workflow['jobs'].values()
                 if job.get('name')=='Validate committed PR integration diff')
        check=next(step for step in job['steps']
                   if step.get('name')=='Verify revision and check committed diff')
        check['continue-on-error']=True
        workflow_path.write_text(yaml.safe_dump(workflow,sort_keys=False))
        git('add','.github/workflows/ci.yml');git('commit','-qm','optional revision check')
        base=git('rev-parse','HEAD')
        (root/'candidate.txt').write_text('reviewed candidate\n')
        git('add','candidate.txt');git('commit','-qm','reviewed candidate')
        head=git('rev-parse','HEAD')
        tree=git('rev-parse',head+'^{tree}')
        tested=subprocess.check_output(['git','-C',str(root),'commit-tree',tree,
            '-p',base,'-p',head,'-m','synthetic test merge']).decode().strip()
        tested_record={'sha':tested,'tree':{'sha':tree},
            'parents':[{'sha':base},{'sha':head}]}
        ci={'workflow_id':413585893,'path':'.github/workflows/ci.yml',
            'name':'CI','event':'pull_request','head_sha':head,
            'pull_requests':[{'number':18,'head':{'sha':head},
                'base':{'ref':'main','sha':base}}]}
        with self.assertRaisesRegex(release.ReleaseError,'revision check is optional'):
            verify_ci_test_commit(lambda _:tested_record,root,ci,18,tested,head,base,head)

    def test_readiness_index_comment_cannot_be_replayed_across_pull_requests(self):
        evidence,records,_,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        binding=integration['readiness_index']
        record=records[binding['index_ref']]
        record['issue_url']=release.BASE+'/issues/6'
        index_digest=release.digest(release.canonical(record))
        binding['index_sha256']=index_digest
        binding['original_sha256']=index_digest
        with self.assertRaisesRegex(release.ReleaseError,
                'Readiness index provider record belongs to a different pull request'):
            evidence_call('verify_evidence',evidence,records.__getitem__,root)

    def test_schema_v1_is_not_accepted_for_new_qualification(self):
        from test_skill_releases import EvidenceTests
        legacy=EvidenceTests().fixture()['evidence']
        with self.assertRaisesRegex(release.ReleaseError,'schema v2'):
            evidence_call('verify_evidence',legacy,lambda ref: {})

    def test_schema_v1_remains_available_only_for_frozen_release_verification(self):
        from test_skill_releases import EvidenceTests
        fixture=EvidenceTests().fixture()
        self.assertEqual(
            len(release.verify_frozen_release_evidence(
                fixture['evidence'],fixture['records'].__getitem__)),4)

    def test_execution_identity_is_derived_from_captured_output(self):
        event={
            'schema_version':2,'repository':release.REPOSITORY,'gate':'independent_review',
            'execution':{
                'system':'local_cubic','origin_status':'owner_attested',
                'execution_id':'arbitrary-execution-id',
                'command':['cubic','review','--base','a'*40,'--head','b'*40],
                'exit_code':0,'started_at':'2026-11-16T18:00:00Z',
                'finished_at':'2026-11-16T18:01:00Z',
                'stdout':'Full diff reviewed; no findings.','stderr':'',
                'stdout_sha256':release.digest(b'Full diff reviewed; no findings.'),
                'reviewed_range':{'base_revision':'a'*40,'head_revision':'b'*40},
            },
            'report':{'verdict':'pass','coverage':'full-diff'},
        }
        with self.assertRaisesRegex(release.ReleaseError,'execution identity'):
            evidence_call('verify_execution_receipt',event,'independent_review',
                {'base_revision':'a'*40,'head_revision':'b'*40})

    def test_dot_test_path_is_rejected_as_a_controlled_evidence_error(self):
        root=Path(__file__).resolve().parents[1]
        revision=release.git(root,'rev-parse','HEAD').decode().strip()
        report={'source_files':['scripts/skill_release.py'],'test_files':['.']}
        with self.assertRaisesRegex(release.ReleaseError,
                'Unsafe ChatGPT inspection file path'):
            evidence_call('verify_inspection_files',root,revision,report)

    def test_ci_run_must_name_the_exact_pull_request_and_base(self):
        ci={'pull_requests':[{'number':5,'head':{'sha':'b'*40},
            'base':{'sha':'a'*40,'ref':'main'}}]}
        self.assertTrue(evidence_call('verify_ci_pull_request',ci,5,'b'*40,'a'*40))
        with self.assertRaisesRegex(release.ReleaseError,'exact pull request'):
            evidence_call('verify_ci_pull_request',ci,6,'b'*40,'a'*40)
        with self.assertRaisesRegex(release.ReleaseError,'head or base'):
            evidence_call('verify_ci_pull_request',ci,5,'b'*40,'c'*40)

    def test_authenticates_ordinary_author_review_chatgpt_and_ci_receipts(self):
        evidence,records,_,root=self.ordinary_fixture()
        self.assertEqual(len(evidence_call('verify_evidence',evidence,records.__getitem__,root)),7)

    def test_ordinary_receipt_from_another_pr_cannot_qualify(self):
        import json
        evidence,records,_,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        entry=integration['records']['author_execution']
        record=records[entry['ref']]
        record['issue_url']=release.BASE+'/issues/99'
        entry['sha256']=release.digest(release.canonical(record))
        binding=integration['readiness_index']
        index_record=records[binding['index_ref']]
        marker='<!-- release-readiness\n'
        payload=json.loads(index_record['body'].split(marker,1)[1].split('\n-->',1)[0])
        payload['evidence']['integrations'][0]['records']['author_execution']['sha256']=entry['sha256']
        index_record['body']=marker+json.dumps(payload,sort_keys=True)+'\n-->'
        index_digest=release.digest(release.canonical(index_record))
        binding['index_sha256']=index_digest
        binding['original_sha256']=index_digest
        with self.assertRaisesRegex(release.ReleaseError,
                'author_execution provider record belongs to a different pull request'):
            evidence_call('verify_evidence',evidence,records.__getitem__,root)

    def test_reviewer_cannot_reuse_author_execution_after_rehashing_receipt(self):
        import json
        evidence,records,events,root=self.ordinary_fixture()
        integration=evidence['integrations'][0]
        entry=integration['records']['independent_reviews'][0]
        record=records[entry['ref']]
        event=json.loads(record['body'].split('<!-- release-evidence-v2\n',1)[1].split('\n-->',1)[0])
        event['execution']=events['author']['execution']
        event['report']['execution_id']=event['execution']['execution_id']
        event['report']['summary']=event['execution']['stdout']
        event['report_sha256']=release.digest(release.canonical(event['report']))
        record['body']='<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->'
        entry['sha256']=release.digest(release.canonical(record))
        binding=integration['readiness_index'];index_record=records[binding['index_ref']]
        payload=json.loads(index_record['body'].split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        payload['evidence']['integrations'][0]['records']['independent_reviews'][0]['sha256']=entry['sha256']
        index_record['body']='<!-- release-readiness\n'+json.dumps(payload,sort_keys=True)+'\n-->'
        binding['index_sha256']=release.digest(release.canonical(index_record))
        binding['original_sha256']=binding['index_sha256']
        with self.assertRaisesRegex(release.ReleaseError,'cannot independently review'):
            evidence_call('verify_evidence',evidence,records.__getitem__,root)

    def test_review_correction_chain_is_contiguous_and_preserves_findings(self):
        chain=[
            {'coverage':'full-diff','base_revision':'a'*40,'head_revision':'b'*40,
             'findings':[{'id':'R1','severity':'P1','summary':'unsafe path'}],
             'dispositions':[]},
            {'coverage':'correction-delta','base_revision':'b'*40,'head_revision':'c'*40,
             'findings':[],
             'dispositions':[{'finding_id':'R1','decision':'fixed','evidence':'changed path validation'}]},
        ]
        self.assertTrue(evidence_call('verify_review_chain',chain,'a'*40,'c'*40))
        gap=[dict(chain[1],base_revision='d'*40)]
        with self.assertRaisesRegex(release.ReleaseError,'contiguous'):
            evidence_call('verify_review_chain',[chain[0],*gap],'a'*40,'c'*40)
        omitted=[chain[0],dict(chain[1],dispositions=[])]
        with self.assertRaisesRegex(release.ReleaseError,'unresolved finding'):
            evidence_call('verify_review_chain',omitted,'a'*40,'c'*40)
        accepted=[chain[0],dict(chain[1],dispositions=[{
            'finding_id':'R1','decision':'accepted','evidence':'accepted risk'}])]
        with self.assertRaisesRegex(release.ReleaseError,'Material review finding'):
            evidence_call('verify_review_chain',accepted,'a'*40,'c'*40)
        with self.assertRaisesRegex(release.ReleaseError,'does not cover the final candidate'):
            evidence_call('verify_review_chain',chain[:1],'a'*40,'c'*40)

    def test_full_baseline_review_requires_evidence_backed_finding_dispositions(self):
        report={'findings':[{'id':'R3','severity':'P3','summary':'minor wording'}],
                'dispositions':[{'finding_id':'R3','decision':'accepted',
                                 'evidence':'documented as non-blocking'}]}
        self.assertTrue(evidence_call('verify_review_dispositions',report))
        unresolved={'findings':report['findings'],'dispositions':[]}
        with self.assertRaisesRegex(release.ReleaseError,'unresolved'):
            evidence_call('verify_review_dispositions',unresolved)
        material={'findings':[{'id':'R1','severity':'P2','summary':'unsafe behavior'}],
                  'dispositions':[{'finding_id':'R1','decision':'accepted',
                                   'evidence':'owner accepted'}]}
        with self.assertRaisesRegex(release.ReleaseError,'must be fixed'):
            evidence_call('verify_review_dispositions',material)

    def test_precommit_full_review_requires_exact_final_diff_digest(self):
        content='d'*64
        step={'coverage':'full-diff','base_revision':'a'*40,'head_revision':None,
              'uncommitted_candidate':True,'diff_sha256':content,
              'findings':[],'dispositions':[]}
        self.assertTrue(evidence_call('verify_review_chain',[step],'a'*40,'b'*40,
            final_diff_sha256=content))
        with self.assertRaisesRegex(release.ReleaseError,'content hash'):
            evidence_call('verify_review_chain',[step],'a'*40,'b'*40,
                final_diff_sha256='e'*64)

    def test_provider_record_modified_after_merge_is_not_premerge_evidence(self):
        record={'created_at':'2026-11-16T18:00:00Z','updated_at':'2026-11-16T18:03:00Z'}
        with self.assertRaisesRegex(release.ReleaseError,'updated after'):
            evidence_call('verify_event_chronology',[record],'2026-11-16T18:02:00Z')
        ci={'created_at':'2026-11-16T17:50:00Z','updated_at':'2026-11-16T18:01:00Z',
            'completed_at':'2026-11-16T18:03:00Z'}
        with self.assertRaisesRegex(release.ReleaseError,'CI completed after'):
            evidence_call('verify_event_chronology',[ci],'2026-11-16T18:02:00Z')
        self.assertTrue(evidence_call('verify_event_chronology',[
            {'created_at':'2026-11-16T18:00:00Z','updated_at':'2026-11-16T18:00:00Z'}
        ],'2026-11-16T18:02:00Z'))

    def test_malformed_utc_suffixes_are_rejected(self):
        for value in ('2026-11-16T18:00:00ZZ',
                      '2026-11-16T18:00:00Z+00:00'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(release.ReleaseError,
                        'Invalid provider timestamp'):
                    evidence_call('_evidence_timestamp',value)


class CaptureTests(unittest.TestCase):
    def test_execution_capture_derives_identity_from_real_command_output(self):
        import json,subprocess
        root=Path(__file__).resolve().parents[1]
        head=release.git(root,'rev-parse','HEAD').decode().strip()
        base=release.git(root,'rev-parse',head+'^').decode().strip()
        result=evidence_call('capture_execution',root,'author_execution','separate_codex',
            [sys.executable,'-c','print("Captured author command")'],
            {'role':'author','summary':'Captured author command'},
            {'base_revision':base,'head_revision':head})
        event=json.loads(result['body'].split('<!-- release-evidence-v2\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(event['execution']['exit_code'],0)
        self.assertEqual(result['exit_code'],0)
        evidence_call('verify_execution_receipt',event,'author_execution',
            {'base_revision':base,'head_revision':head})

    def test_baseline_chatgpt_capture_binds_the_baseline_tree(self):
        import json
        root=Path(__file__).resolve().parents[1]
        baseline=release.git(root,'rev-parse','HEAD').decode().strip()
        tree=release.git(root,'rev-parse',baseline+'^{tree}').decode().strip()
        source_files=['scripts/skill_release.py']
        test_files=['tests/test_skill_releases.py']
        names=source_files+test_files
        summary='Inspected the corrected baseline source and tests.'
        report={'coverage':'full-baseline','reviewed_revision':baseline,
            'tree_sha':tree,'source_files':source_files,'test_files':test_files,
            'summary':summary}
        transcript=summary+' '+' '.join(names)
        result=evidence_call('capture_execution',root,'chatgpt_inspection','chatgpt',[],report,
            {'baseline_revision':baseline,'tree_sha':tree},transcript)
        event=json.loads(result['body'].split('<!-- release-evidence-v2\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(event['revision'],baseline)
        self.assertEqual(event['execution']['reviewed_range'],
            {'baseline_revision':baseline,'tree_sha':tree})
        evidence_call('verify_execution_receipt',event,'chatgpt_inspection',
            {'baseline_revision':baseline,'tree_sha':tree})

    def test_premerge_index_preparation_binds_provider_records_without_self_reference(self):
        import json
        from unittest.mock import Mock
        evidence,records,_,_=EvidenceV2Tests().ordinary_fixture(
            root=isolated_repository(self))
        api=Mock();api.request.return_value={'login':'danielbyon'}
        api.record.side_effect=records.__getitem__
        body=evidence_call('prepare_readiness_index',evidence,5,api)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['schema_version'],2)
        self.assertNotIn('normalizes',wrapper)
        self.assertNotIn('readiness_index',wrapper['evidence']['integrations'][0])
        self.assertEqual(wrapper['evidence']['integrations'][0]['records']['ci']['sha256'],
            release.digest(release.canonical(records[wrapper['evidence']['integrations'][0]['records']['ci']['ref']])))

    def test_postmerge_index_preparation_only_adds_actual_merge_identity(self):
        import json
        from unittest.mock import Mock
        evidence,records,_,_=EvidenceV2Tests().ordinary_fixture(
            root=isolated_repository(self))
        integration=evidence['integrations'][0];head=integration['reviewed_revision']
        index_ref=integration['readiness_index']['original_ref']
        integration['integrated_revision']=head;integration['integrated_commits']=[head]
        records[release.BASE+'/pulls/5']={'number':5,'merged':True,
            'merged_at':'2026-11-16T18:10:00Z'}
        api=Mock();api.request.return_value={'login':'danielbyon'}
        api.record.side_effect=records.__getitem__
        body=evidence_call('prepare_readiness_index',evidence,5,api,normalizes_reference=index_ref)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['normalizes']['ref'],index_ref)
        self.assertEqual(wrapper['evidence']['integrations'][0]['integrated_revision'],head)
        self.assertNotIn('readiness_index',wrapper['evidence']['integrations'][0])

    def test_owner_receipt_names_the_distinct_authorized_action(self):
        import json
        body=evidence_call('build_owner_receipt','baseline_admission','a'*40)
        event=json.loads(body.split('<!-- release-evidence-v2\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(event['report'],{'action':'admit-baseline','verdict':'approve'})


class OrdinaryChronologyIntegrationTests(unittest.TestCase):
    def qualified_fixture(self,fixture=None,integrated_commits=None,original_commits=None):
        from test_skill_releases import SuiteExecutionTests
        import copy,json
        from unittest.mock import Mock
        evidence,records,_,root=(fixture or EvidenceV2Tests().ordinary_fixture(
            root=isolated_repository(self)))
        integration=evidence['integrations'][0]
        pull_request=integration['pull_request']
        head=integration['reviewed_revision']
        members=integrated_commits or [head]
        original_members=original_commits or members
        integration.update(integrated_revision=head,integrated_commits=members)
        binding=integration['readiness_index']
        original=records[binding['original_ref']]
        payload=json.loads(original['body'].split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        normalized_evidence=copy.deepcopy(payload['evidence'])
        normalized_evidence['integrations'][0].update(
            integrated_revision=head,integrated_commits=members)
        normalized_id=original['id']+1
        normalized_ref=release.BASE+'/issues/comments/'+str(normalized_id)
        normalized={'id':normalized_id,'user':{'id':123},
            'issue_url':release.BASE+f'/issues/{pull_request}',
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':pull_request,
                'normalizes':{'ref':binding['original_ref'],
                    'sha256':release.digest(release.canonical(original))},
                'evidence':normalized_evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:11:00Z','updated_at':'2026-11-16T18:11:00Z'}
        records[normalized_ref]=normalized
        pr={'number':pull_request,'merged':True,'merged_at':'2026-11-16T18:10:00Z',
            'base':{'ref':'main','repo':{'full_name':release.REPOSITORY}},
            'head':{'sha':head,'repo':{'full_name':release.REPOSITORY}},
            'merge_commit_sha':head}
        records[release.BASE+f'/pulls/{pull_request}']=pr
        workflow,steps,logs=SuiteExecutionTests.fixture(head,root)
        ci_entry=integration['records']['ci'];ci=records[ci_entry['ref']]
        job={'id':81,'run_id':ci['id'],'run_attempt':ci.get('run_attempt',1),
             'name':'Validate committed PR integration diff','status':'completed',
             'conclusion':'success','started_at':'2026-11-16T18:01:00Z',
             'completed_at':'2026-11-16T18:03:00Z','steps':steps}
        log='PR HEAD: '+head+'\nTested integration revision: '+integration['tested_revision']+'\nTested base revision: '+integration['base_revision']+'\n'+logs
        api=Mock()
        def record(ref):return records[ref]
        def pages(ref):
            if ref.endswith(f'/pulls/{pull_request}/commits'):
                return [{'sha':commit} for commit in original_members]
            if any(ref==release.BASE+'/commits/'+commit+'/pulls' for commit in members):
                return [pr]
            if ref==release.BASE+f'/issues/{pull_request}/comments':
                return [original,normalized]
            return []
        api.record.side_effect=record;api.pages.side_effect=pages
        api.ci_jobs.return_value=[job];api.job_log.return_value=log
        loaded=evidence_call('load_readiness_index',normalized_ref,api.record,pull_request)
        integration['readiness_index']=evidence_call('readiness_index_binding',loaded)
        return root,api,evidence,records,job,pr

    def test_authenticated_receipts_normalization_ci_and_actual_merge_chronology(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        snapshots=evidence_call('verify_evidence',evidence,api.record,root)
        self.assertTrue(any(item['gate']=='readiness_normalization' for item in snapshots))
        evidence_call('verify_live_integrations',api,evidence,root,
                      ordinary_evidence=snapshots)

    def test_ci_job_must_report_the_completed_revision_check_step(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        job['steps']=[step for step in job['steps']
            if step.get('name')!='Verify revision and check committed diff']
        with self.assertRaisesRegex(release.ReleaseError,'revision-check step'):
            evidence_call('verify_live_integrations',api,evidence,root,
                ordinary_evidence=verified)

    def test_ci_job_and_revision_step_are_bound_to_the_authenticated_attempt(self):
        for field,value in (('run_id',999),('run_attempt',2)):
            with self.subTest(field=field):
                root,api,evidence,records,job,pr=self.qualified_fixture()
                verified=evidence_call('verify_evidence',evidence,api.record,root)
                job[field]=value
                with self.assertRaisesRegex(release.ReleaseError,'CI job run identity mismatch'):
                    evidence_call('verify_live_integrations',api,evidence,root,
                                  ordinary_evidence=verified)
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        revision_step=next(step for step in job['steps']
            if step.get('name')=='Verify revision and check committed diff')
        revision_step['status']='in_progress'
        with self.assertRaisesRegex(release.ReleaseError,'revision-check step'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)
        revision_step['status']='completed'
        revision_step['outcome']='failure'
        with self.assertRaisesRegex(release.ReleaseError,'revision-check step'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)

    def test_misleading_ci_log_identity_labels_are_rejected(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        tested=evidence['integrations'][0]['tested_revision']
        api.job_log.return_value=api.job_log.return_value.replace(
            'Tested integration revision: '+tested,
            'Tested integration revision: '+'0'*40)
        with self.assertRaisesRegex(release.ReleaseError,'CI synthetic merge identity not established'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)

    def test_missing_v2_ci_status_is_classified_as_missing_evidence(self):
        from release_evidence.audit import _audit_error_status
        from release_evidence.common import MissingEvidenceError
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        job.pop('status')
        with self.assertRaises(MissingEvidenceError) as result:
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)
        self.assertEqual(_audit_error_status(result.exception),'MISSING_EVIDENCE')

    def test_ci_run_attempt_must_be_present_and_positive_in_both_records(self):
        import copy,json
        from release_evidence.audit import _audit_error_status
        cases=('both_missing','boolean_receipt_attempt')
        for case in cases:
            with self.subTest(case=case):
                fixture=EvidenceV2Tests().ordinary_fixture(root=isolated_repository(self))
                evidence,records,_,root=fixture
                entry=evidence['integrations'][0]['records']['ci']
                record=records[entry['ref']]
                if case=='both_missing':
                    entry.pop('run_attempt')
                    record.pop('run_attempt')
                else:
                    entry['run_attempt']=True
                entry['sha256']=release.digest(release.canonical(record))
                binding=evidence['integrations'][0]['readiness_index']
                index_record=records[binding['original_ref']]
                wrapper=json.loads(index_record['body'].split(
                    '<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
                wrapper['evidence']['integrations'][0]['records']['ci']=copy.deepcopy(entry)
                index_record['body']='<!-- release-readiness\n'+json.dumps(
                    wrapper,sort_keys=True)+'\n-->'
                binding['original_sha256']=release.digest(
                    release.canonical(index_record))
                binding['index_sha256']=binding['original_sha256']
                root,api,evidence,records,job,pr=self.qualified_fixture(fixture)
                with self.assertRaisesRegex(release.ReleaseError,'run attempt') as result:
                    evidence_call('verify_evidence',evidence,api.record,root)
                self.assertEqual(_audit_error_status(result.exception),'FAIL')

    def test_original_index_edit_after_merge_invalidates_normalization(self):
        import json
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        binding=evidence['integrations'][0]['readiness_index']
        original=records[binding['original_ref']]
        original['updated_at']='2026-11-16T18:12:00Z'
        normalized=records[binding['normalization_ref']]
        wrapper=json.loads(normalized['body'].split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        wrapper['normalizes']['sha256']=release.digest(release.canonical(original))
        normalized['body']='<!-- release-readiness\n'+json.dumps(wrapper,sort_keys=True)+'\n-->'
        loaded=evidence_call('load_readiness_index',binding['normalization_ref'],api.record,5)
        evidence['integrations'][0]['readiness_index']=evidence_call('readiness_index_binding',loaded)
        with self.assertRaisesRegex(release.ReleaseError,'updated after'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)

    def test_ci_completion_after_merge_is_rejected(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        job['completed_at']='2026-11-16T18:12:00Z'
        with self.assertRaisesRegex(release.ReleaseError,'updated after|after the integration'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)

    def test_missing_merge_timestamp_and_wrong_pr_identity_are_rejected(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        verified=evidence_call('verify_evidence',evidence,api.record,root)
        pr.pop('merged_at')
        with self.assertRaisesRegex(release.ReleaseError,'merge timestamp'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)
        pr['merged_at']='2026-11-16T18:10:00Z';pr['number']=6
        with self.assertRaisesRegex(release.ReleaseError,'number identity'):
            evidence_call('verify_live_integrations',api,evidence,root,
                          ordinary_evidence=verified)
