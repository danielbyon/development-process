"""Tests for prospective baseline admission and read-only audits."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_release as release
import release_evidence as evidence
from release_evidence_tests import EvidenceV2Tests, OrdinaryChronologyIntegrationTests, evidence_operation

def evidence_call(name,*args,**kwargs):
    if name=='discover_evidence':
        kwargs.setdefault('select_anchor',release.select_anchor)
    return evidence_operation(name)(*args,**kwargs)

class ProspectiveBaselineTests(unittest.TestCase):
    def qualified_fixture(self,chat_source_files=None,chat_test_files=None):
        import json,tempfile,subprocess
        from unittest.mock import Mock
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        def git(*args):
            return subprocess.check_output(['git','-C',temporary.name,*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','Release Evidence Test');git('config','user.email','release-evidence@example.invalid')
        (root/'docs').mkdir();(root/'skills').mkdir();(root/'.github/workflows').mkdir(parents=True)
        (root/'scripts').mkdir();(root/'tests').mkdir()
        (root/'docs/PROCESS.md').write_text('Pinned process policy for baseline qualification.\n')
        (root/'skills/distribution.json').write_text('{"schema_version":2}\n')
        (root/'scripts/skill_release.py').write_text('# baseline source\n')
        (root/'scripts/release_evidence.py').write_text('# baseline evidence source\n')
        (root/'tests/test_skill_releases.py').write_text('# baseline tests\n')
        (root/'tests/release_evidence_tests.py').write_text('# baseline evidence tests\n')
        (root/'tests/prospective_baseline_tests.py').write_text('# baseline prospective tests\n')
        suites=list(release.SUITES)
        steps=[{'name':suite,'run':'python3 -m unittest discover -s tests -p '+suite+' -v'} for suite in suites]
        workflow={'jobs':{'integration':{'name':'Validate committed PR integration diff','steps':steps}}}
        import yaml
        (root/'.github/workflows/ci.yml').write_text(yaml.safe_dump(workflow,sort_keys=False))
        git('add','.');git('commit','-qm','base before correction');base=git('rev-parse','HEAD')
        (root/'scripts/skill_release.py').write_text('# reviewed ordinary integration source\n')
        (root/'tests/test_skill_releases.py').write_text('# reviewed ordinary integration tests\n')
        git('add','.');git('commit','-qm','ordinary integration before correction');base=git('rev-parse','HEAD')
        (root/'docs/PROCESS.md').write_text('Corrected policy source for the prospective release baseline.\n')
        (root/'scripts/skill_release.py').write_text('# corrected release controller source\n')
        (root/'scripts/release_evidence.py').unlink()
        evidence_package=root/'scripts/release_evidence';evidence_package.mkdir()
        evidence_modules=('__init__','audit','baseline','common','discovery',
                          'integrations','legacy','qualification','records')
        for module in evidence_modules:
            (evidence_package/f'{module}.py').write_text('# corrected evidence package source\n')
        (root/'tests/test_skill_releases.py').write_text('# corrected release controller tests\n')
        (root/'tests/release_evidence_tests.py').write_text('# corrected release evidence tests\n')
        (root/'tests/prospective_baseline_tests.py').write_text('# corrected prospective baseline tests\n')
        git('add','.');git('commit','-qm','corrected release evidence process');baseline=git('rev-parse','HEAD')
        tree=git('rev-parse',baseline+'^{tree}')
        manifest=release.digest(release.git(root,'ls-tree','-r','--full-tree','-z',baseline))
        policy=git('log','--first-parent','-1','--format=%H',baseline,'--','docs/PROCESS.md')
        policy_digest=release.digest(release.git(root,'show',baseline+':docs/PROCESS.md'))
        owner=123; records={release.BASE:{'full_name':release.REPOSITORY,
            'owner':{'id':owner,'login':'danielbyon'}}};counter=0
        records[release.BASE+'/git/ref/heads/main']={
            'ref':'refs/heads/main','object':{'type':'commit','sha':baseline}}
        def make_receipt(gate,report,system,reviewed_range,created_at,revision):
            nonlocal counter
            counter+=1
            summary=report['summary']
            execution={'system':system,'origin_status':'owner_attested',
                'command':[system,'inspect',baseline], 'exit_code':0,
                'started_at':created_at,'finished_at':created_at,
                'stdout':summary,'stderr':'','stdout_sha256':release.digest(summary.encode()),
                'reviewed_range':reviewed_range}
            execution['execution_id']=release.digest(release.canonical(execution))
            report.update(execution_id=execution['execution_id'],verdict='pass')
            event={'schema_version':2,'repository':release.REPOSITORY,'gate':gate,
                   'revision':revision,'execution':execution,'report':report,
                   'report_sha256':release.digest(release.canonical(report))}
            ref=release.BASE+'/issues/comments/'+str(counter)
            record={'id':counter,'user':{'id':owner},
                'issue_url':release.BASE+'/issues/32',
                'body':'<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->',
                'created_at':created_at,'updated_at':created_at}
            records[ref]=record
            return {'ref':ref,'sha256':release.digest(release.canonical(record))}
        review_report={'coverage':'full-baseline','reviewed_revision':baseline,'tree_sha':tree,
                       'manifest_sha256':manifest,'findings':[],'dispositions':[],
                       'summary':'Reviewed every tracked file in the corrected baseline.'}
        review=make_receipt('baseline_review',review_report,'local_cubic',
            {'baseline_revision':baseline,'tree_sha':tree},'2026-11-16T20:05:00Z',baseline)
        source_files=chat_source_files or sorted([
            'scripts/skill_release.py',
            *[f'scripts/release_evidence/{module}.py' for module in evidence_modules]])
        test_files=chat_test_files or sorted([
            'tests/test_skill_releases.py','tests/release_evidence_tests.py',
            'tests/prospective_baseline_tests.py'])
        inspected_files=source_files+test_files
        chat_report={'coverage':'full-baseline','reviewed_revision':baseline,'tree_sha':tree,
                     'manifest_sha256':manifest,'source_files':source_files,
                     'test_files':test_files,
                     'file_sha256':{name:release.digest(release.git(
                         root,'show',baseline+':'+name)) for name in inspected_files},
                     'summary':'Inspected the baseline source and tests: '+' '.join(inspected_files)}
        chat=make_receipt('chatgpt_inspection',chat_report,'chatgpt',
            {'baseline_revision':baseline,'tree_sha':tree},'2026-11-16T20:06:00Z',baseline)
        ci_ref=release.BASE+'/actions/runs/101'
        ci={'id':101,'repository':{'full_name':release.REPOSITORY},'event':'pull_request',
            'head_sha':baseline,'status':'completed','conclusion':'success','run_attempt':1,
            'pull_requests':[{'number':32,'head':{'sha':baseline},
                'base':{'sha':base,'ref':'main'}}],
            'created_at':'2026-11-16T19:00:00Z','updated_at':'2026-11-16T20:07:00Z',
            'completed_at':'2026-11-16T20:07:00Z'}
        records[ci_ref]=ci
        ci_entry={'ref':ci_ref,'sha256':release.digest(release.canonical(ci)),
                  'run_attempt':1,'tested_revision':baseline,'tested_base_revision':base}
        owner_ref=release.BASE+'/issues/comments/'+str(counter+1)
        owner_report={'action':'admit-baseline','verdict':'approve'}
        owner_event={'schema_version':2,'repository':release.REPOSITORY,
                     'gate':'baseline_admission','revision':baseline,'report':owner_report,
                     'report_sha256':release.digest(release.canonical(owner_report))}
        owner_record={'id':counter+1,'user':{'id':owner},
            'issue_url':release.BASE+'/issues/32',
            'body':'<!-- release-evidence-v2\n'+json.dumps(owner_event,sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T20:08:00Z','updated_at':'2026-11-16T20:08:00Z'}
        records[owner_ref]=owner_record
        owner_entry={'ref':owner_ref,'sha256':release.digest(release.canonical(owner_record))}
        evidence={'schema_version':2,'owner_id':owner,'origin':{
            'kind':'prospective_baseline','baseline_revision':baseline,
            'source_revision':baseline,'builder_revision':baseline,
            'policy_revision':policy,'policy_sha256':policy_digest},
            'baseline_revision':baseline,'integrations':[],
            'baseline_admission':{'correction_pull_request':32,'reviewed_revision':baseline,
                'full_review':review,'chatgpt_inspection':chat,'ci':ci_entry,
                'owner_admission':owner_entry}}
        index_ref=release.BASE+'/issues/comments/'+str(counter+2)
        index_record={'id':counter+2,'user':{'id':owner},
            'issue_url':release.BASE+'/issues/32',
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':32,
                'evidence':evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T20:09:00Z','updated_at':'2026-11-16T20:09:00Z'}
        records[index_ref]=index_record
        evidence['readiness_index']={'index_ref':index_ref,
            'index_sha256':release.digest(release.canonical(index_record)),
            'original_ref':index_ref,'original_sha256':release.digest(release.canonical(index_record)),
            'normalization_ref':None,'normalization_sha256':None}
        pr_ref=release.BASE+'/pulls/32'
        pr={'number':32,'merged':True,'merged_at':'2026-11-16T20:00:00Z',
            'base':{'ref':'main','repo':{'full_name':release.REPOSITORY}},
            'head':{'sha':baseline,'repo':{'full_name':release.REPOSITORY}},
            'merge_commit_sha':baseline}
        records[pr_ref]=pr
        job={'id':201,'name':'Validate committed PR integration diff','status':'completed',
             'conclusion':'success','started_at':'2026-11-16T19:10:00Z',
             'completed_at':'2026-11-16T20:07:00Z',
             'steps':[{'name':step['name'],'conclusion':'success'} for step in steps]}
        logs=[]
        for suite in suites:
            command='python3 -m unittest discover -s tests -p '+suite+' -v'
            logs.append('##[group]Run '+command+'\n##[endgroup]\ntest_valid (tests.test_baseline.Baseline) ... ok\nRan 1 test in 0.001s\nOK\n')
        job_log='PR HEAD: '+baseline+'\nTested integration revision: '+baseline+'\nTested base revision: '+base+'\n'+''.join(logs)
        dispatch={'id':900,'event':'workflow_dispatch','head_sha':baseline,'head_branch':'main',
                  'actor':{'id':owner},'triggering_actor':{'id':owner},
                  'path':'.github/workflows/skill-release.yml@refs/heads/main',
                  'created_at':'2026-11-16T20:10:00Z'}
        class API:
            def record(self,ref):return records[ref] if ref in records else {'full_name':release.REPOSITORY,'owner':{'id':owner}}
            def request(self,method,endpoint):
                return {'login':'danielbyon'} if endpoint=='/user' else records[release.BASE]
            def pages(self,endpoint):
                if endpoint==release.BASE+f'/commits/{baseline}/pulls':return [pr]
                if endpoint==release.BASE+'/issues/32/comments':return [index_record]
                return []
            def ci_jobs(self,run_id,attempt):return [job]
            def job_log(self,job_id):return job_log
            def run(self,run_id):return dispatch
        api=API()
        api.records=records
        return root,api,evidence,base,baseline,dispatch,owner_record

    def rewrite_readiness_index(self,api,evidence):
        import json
        index_ref=evidence['readiness_index']['original_ref']
        index_record=api.records[index_ref]
        marker='<!-- release-readiness\n'
        payload=json.loads(index_record['body'].split(marker,1)[1].split('\n-->',1)[0])
        payload['evidence']={key:value for key,value in evidence.items()
                             if key!='readiness_index'}
        index_record['body']=marker+json.dumps(payload,sort_keys=True)+'\n-->'
        index_digest=release.digest(release.canonical(index_record))
        evidence['readiness_index']['index_sha256']=index_digest
        evidence['readiness_index']['original_sha256']=index_digest

    def history(self):
        import tempfile
        directory=Path(tempfile.mkdtemp())
        def run(*args):
            return release.git(directory,*args).decode().strip()
        run('init','-q')
        run('config','user.name','Release Evidence Test')
        run('config','user.email','release-evidence@example.invalid')
        (directory/'tracked.txt').write_text('baseline\n')
        run('add','tracked.txt');run('commit','-qm','baseline')
        baseline=run('rev-parse','HEAD')
        run('commit','--allow-empty','-qm','same-tree descendant')
        descendant=run('rev-parse','HEAD')
        return directory,baseline,descendant

    def test_admitted_prospective_root_has_zero_integrations_but_no_descendants(self):
        import subprocess
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        proof=evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)
        coverage=evidence_call('verify_coverage',root,evidence,baseline,
            baseline_admission=proof)
        self.assertEqual(coverage['origin'],'prospective_baseline')
        self.assertEqual(coverage['baseline_revision'],baseline)
        self.assertEqual(coverage['target_revision'],baseline)
        self.assertEqual(coverage['integrations'],[])
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm','same tree descendant'],check=True)
        descendant=release.git(root,'rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            evidence_call('verify_coverage',root,evidence,descendant,baseline_admission=proof)

    def test_boolean_cannot_substitute_for_verified_baseline_admission(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        with self.assertRaisesRegex(release.ReleaseError,'independently verified'):
            evidence_call('verify_coverage',root,evidence,baseline,admitted=True)

    def test_full_baseline_admission_uses_authenticated_records_and_real_git_history(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        snapshots=evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)
        self.assertEqual({item['gate'] for item in snapshots},
            {'baseline_review','chatgpt_inspection','ci','baseline_admission',
             'readiness_index','corrected_merge','ci_job','ci_log','release_dispatch',
             'baseline_main_ref'})
        coverage=evidence_call('verify_coverage',root,evidence,baseline,
            baseline_admission=snapshots)
        self.assertEqual(coverage['origin'],'prospective_baseline')
        self.assertEqual(coverage['baseline_revision'],baseline)
        self.assertEqual(coverage['target_revision'],baseline)
        self.assertEqual(coverage['integrations'],[])

    def test_baseline_review_execution_must_run_after_the_corrected_merge(self):
        import json
        cases=(('full_review','Full-baseline review'),
               ('chatgpt_inspection','ChatGPT inspection'))
        for field,label in cases:
            with self.subTest(gate=field):
                root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
                entry=evidence['baseline_admission'][field]
                record=api.records[entry['ref']]
                marker='<!-- release-evidence-v2\n'
                event=json.loads(record['body'].split(marker,1)[1].split('\n-->',1)[0])
                execution=event['execution']
                execution['started_at']='2026-11-16T19:50:00Z'
                execution['finished_at']='2026-11-16T19:55:00Z'
                execution['execution_id']=release.digest(release.canonical(
                    {key:value for key,value in execution.items() if key!='execution_id'}))
                event['report']['execution_id']=execution['execution_id']
                event['report_sha256']=release.digest(release.canonical(event['report']))
                record['body']=marker+json.dumps(event,sort_keys=True)+'\n-->'
                entry['sha256']=release.digest(release.canonical(record))

                self.rewrite_readiness_index(api,evidence)

                with self.assertRaisesRegex(release.ReleaseError,
                        label+' execution must start and finish after the corrected merge'):
                    evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)

    def test_baseline_review_and_chatgpt_receipts_must_belong_to_the_correction_pr(self):
        cases=(('full_review','baseline_review'),
               ('chatgpt_inspection','chatgpt_inspection'))
        for field,gate in cases:
            with self.subTest(gate=gate):
                root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
                entry=evidence['baseline_admission'][field]
                record=api.records[entry['ref']]
                record['issue_url']=release.BASE+'/issues/31'
                entry['sha256']=release.digest(release.canonical(record))
                self.rewrite_readiness_index(api,evidence)
                with self.assertRaisesRegex(release.ReleaseError,
                        gate+' provider record belongs to a different pull request'):
                    evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)

    def test_ordinary_chronology_and_prospective_admission_share_real_git_history(self):
        root,baseline_api,baseline_evidence,ordinary_head,baseline,dispatch,owner_record=(
            self.qualified_fixture())
        ordinary_base=release.git(root,'rev-parse',ordinary_head+'^').decode().strip()
        ordinary_case=EvidenceV2Tests()
        ordinary_fixture=ordinary_case.ordinary_fixture(root,ordinary_base,ordinary_head,
            pull_request=31,comment_offset=100)
        ordinary_integration=OrdinaryChronologyIntegrationTests().qualified_fixture(ordinary_fixture)
        ordinary_root,ordinary_api,ordinary_evidence,ordinary_records,job,pr=ordinary_integration
        self.assertEqual(ordinary_root,root)
        class CombinedAPI:
            def record(self,reference):
                try:return ordinary_api.record(reference)
                except KeyError:return baseline_api.record(reference)
            def pages(self,reference):return ordinary_api.pages(reference)
            def ci_jobs(self,run_id,attempt):
                if int(run_id)==7:return ordinary_api.ci_jobs(run_id,attempt)
                return baseline_api.ci_jobs(run_id,attempt)
            def job_log(self,job_id):
                if int(job_id)==81:return ordinary_api.job_log(job_id)
                return baseline_api.job_log(job_id)
            def run(self,run_id):return baseline_api.run(run_id)
        api=CombinedAPI()
        ordinary_snapshots=evidence_call('verify_evidence',ordinary_evidence,api.record,root)
        evidence_call('verify_live_integrations',api,ordinary_evidence,root)
        evidence_call('verify_coverage',root,ordinary_evidence,ordinary_head,admitted=True)
        baseline_proof=evidence_call('verify_baseline_admission',root,api,baseline_evidence,
            baseline,baseline,900)
        evidence_call('verify_coverage',root,baseline_evidence,baseline,
            baseline_admission=baseline_proof)
        self.assertEqual(pr['number'],31)
        self.assertEqual(ordinary_evidence['integrations'][0]['integrated_revision'],ordinary_head)
        self.assertIn('readiness_normalization',{item['gate'] for item in ordinary_snapshots})
        self.assertEqual(baseline_evidence['integrations'],[])
        self.assertIn('baseline_admission',{item['gate'] for item in baseline_proof})

    def test_explicit_baseline_admission_accepts_zero_integration_root(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        proof=evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)
        self.assertEqual(proof,evidence_call('verify_baseline_admission',
            root,api,evidence,baseline,baseline,900))
        with self.assertRaisesRegex(release.ReleaseError,'Ordinary integration evidence origin'):
            evidence_call('verify_evidence',evidence,api.record,root)

    def test_baseline_chatgpt_inspection_must_cover_every_changed_source_and_test(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture(
            chat_source_files=['scripts/skill_release.py'],
            chat_test_files=['tests/test_skill_releases.py'])
        with self.assertRaisesRegex(release.ReleaseError,
                'ChatGPT inspection omits changed source or test files'):
            evidence_call('verify_baseline_admission',root,api,evidence,
                          baseline,baseline,900)

    def test_baseline_index_preparation_binds_review_ci_and_owner_admission(self):
        import json
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        body=evidence_call('prepare_readiness_index',evidence,32,api)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['evidence']['origin']['kind'],'prospective_baseline')
        self.assertEqual(wrapper['evidence']['integrations'],[])
        self.assertNotIn('readiness_index',wrapper['evidence'])

    def test_discovery_selects_only_the_exact_prospective_baseline_origin(self):
        from unittest.mock import patch
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        with patch.object(release,'select_anchor',return_value=None):
            discovered=evidence_call('discover_evidence',root,api,baseline,baseline)
        self.assertEqual(discovered['origin']['kind'],'prospective_baseline')
        self.assertEqual(discovered['baseline_revision'],baseline)
        self.assertEqual(discovered['integrations'],[])
        proof=evidence_call('verify_baseline_admission',root,api,discovered,baseline,baseline,900)
        coverage=evidence_call('verify_coverage',root,discovered,baseline,
            baseline_admission=proof)
        self.assertEqual(coverage['origin'],'prospective_baseline')
        self.assertEqual(coverage['baseline_revision'],baseline)
        self.assertEqual(coverage['target_revision'],baseline)
        self.assertEqual(coverage['integrations'],[])

    def test_admission_after_original_dispatch_is_rejected(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        dispatch['created_at']='2026-11-16T20:07:30Z'
        dispatch['run_attempt']=2
        with self.assertRaisesRegex(release.ReleaseError,'precede the original release dispatch'):
            evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)

    def test_dispatch_requires_main_to_remain_at_the_admitted_baseline(self):
        import subprocess
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm',
                        'ordinary integration after baseline'],check=True)
        current_main=release.git(root,'rev-parse','HEAD').decode().strip()
        api.records[release.BASE+'/git/ref/heads/main']={
            'ref':'refs/heads/main','object':{'type':'commit','sha':current_main}}
        with self.assertRaisesRegex(release.ReleaseError,
                'Main must remain exactly at the admitted baseline through original release dispatch'):
            evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)

    def test_frozen_main_ref_snapshot_keeps_immutable_admission_verifiable(self):
        import copy,subprocess
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        live=release.EvidenceAuthority(api)
        evidence_call('verify_baseline_admission',root,live,evidence,baseline,baseline,900)
        frozen=release.EvidenceAuthority(data=copy.deepcopy(live.data))
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm',
                        'ordinary integration after release activation'],check=True)
        current_main=release.git(root,'rev-parse','HEAD').decode().strip()
        api.records[release.BASE+'/git/ref/heads/main']={
            'ref':'refs/heads/main','object':{'type':'commit','sha':current_main}}
        proof=evidence_call('verify_baseline_admission',root,frozen,evidence,baseline,baseline,900)
        main_snapshot=next(item for item in proof if item['gate']=='baseline_main_ref')
        self.assertEqual(main_snapshot['record']['object']['sha'],baseline)

    def test_tree_equivalent_descendant_cannot_replace_baseline_identity(self):
        import subprocess
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm','same tree later commit'],check=True)
        descendant=release.git(root,'rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(release.ReleaseError,'source and builder'):
            evidence_call('verify_baseline_admission',root,api,evidence,descendant,descendant,900)
        proof=evidence_call('verify_baseline_admission',root,api,evidence,baseline,baseline,900)
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            evidence_call('verify_coverage',root,evidence,base,baseline_admission=proof)
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            evidence_call('verify_coverage',root,evidence,descendant,baseline_admission=proof)
        ordinary={'schema_version':2,'origin':{'kind':'ordinary'},
            'baseline_revision':baseline,'anchor_release':'2026.11.16','integrations':[]}
        with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
            evidence_call('verify_coverage',root,ordinary,descendant,admitted=True)


class AuditTests(unittest.TestCase):
    def test_audit_status_does_not_use_error_wording(self):
        status=evidence_operation('_audit_error_status')(
            release.ReleaseError('Missing provider record'))
        self.assertEqual(status,'FAIL')

    def test_audit_status_uses_typed_missing_evidence(self):
        from release_evidence.common import MissingEvidenceError
        status=evidence_operation('_audit_error_status')(
            MissingEvidenceError('Provider returned no readiness index'))
        self.assertEqual(status,'MISSING_EVIDENCE')

    def test_presence_check_does_not_treat_false_as_absent(self):
        from release_evidence.common import require_present
        self.assertIs(require_present(False,'Provider reported an invalid value'),False)

    def test_merged_ordinary_pr_without_release_anchor_runs_git_coverage(self):
        root,api,evidence,records,job,pr=(
            OrdinaryChronologyIntegrationTests().qualified_fixture())
        binding=evidence['integrations'][0]['readiness_index']
        provider_pages=api.pages.side_effect
        def pages(reference):
            if reference==release.BASE+'/issues/5/comments':
                return [records[binding['original_ref']],
                        records[binding['normalization_ref']]]
            return provider_pages(reference)
        api.pages.side_effect=pages
        api.request.return_value={'login':'danielbyon'}

        result=evidence_call('audit_pull_request',root,api,5)

        self.assertEqual(result['gates']['git_coverage'],'FAIL')
        self.assertIn('Uncovered main integrations',
                      result['details']['git_coverage'])

    def test_open_pull_request_audit_marks_merge_and_release_gates_not_run(self):
        import json,yaml
        from unittest.mock import Mock
        evidence,records,_,root=EvidenceV2Tests().ordinary_fixture()
        integration=evidence['integrations'][0]
        integration['tested_revision']=integration['reviewed_revision']
        base=integration['base_revision'];head=integration['reviewed_revision']
        pr_ref=release.BASE+'/pulls/5'
        records[pr_ref]={'number':5,'merged':False,'base':{'ref':'main',
            'sha':base,'repo':{'full_name':release.REPOSITORY}},
            'head':{'sha':head,'repo':{'full_name':release.REPOSITORY}}}
        workflow=yaml.safe_load(release.git(root,'show',head+':.github/workflows/ci.yml').decode())
        workflow_steps=next(job['steps'] for job in workflow['jobs'].values()
            if job.get('name')=='Validate committed PR integration diff')
        steps=[{'name':step['name'],'conclusion':'success'} for step in workflow_steps]
        job={'id':700,'name':'Validate committed PR integration diff','status':'completed',
             'conclusion':'success','started_at':'2026-11-16T18:01:00Z',
             'completed_at':'2026-11-16T18:03:00Z','steps':steps}
        logs=[]
        for step in workflow_steps:
            if 'run' in step:
                logs.append('##[group]Run '+step['run']+'\n##[endgroup]\n'
                            'test_valid (tests.test_candidate.Candidate) ... ok\nRan 1 test in 0.001s\nOK\n')
        ci=records[integration['records']['ci']['ref']]
        ci['head_sha']=head
        integration['records']['ci']['sha256']=release.digest(release.canonical(ci))
        job_log='PR HEAD: '+head+'\nTested integration revision: '+head+'\nTested base revision: '+base+'\n'+''.join(logs)
        comments=[records[evidence['integrations'][0]['readiness_index']['index_ref']]]
        records[release.BASE+'/pulls/5']={'number':5,'merged':False,
            'base':{'ref':'main','sha':base,'repo':{'full_name':release.REPOSITORY}},
            'head':{'sha':head,'repo':{'full_name':release.REPOSITORY}}}
        class API:
            def __init__(self):self.methods=[]
            def request(self,method,endpoint):
                self.methods.append((method,endpoint));return {'login':'danielbyon'}
            def record(self,ref):return records[ref]
            def pages(self,ref):return comments
            def ci_jobs(self,run_id,attempt):return [job]
            def job_log(self,job_id):return job_log
        api=API()
        result=evidence_call('audit_pull_request',root,api,5)
        self.assertEqual(result['gates']['candidate_ci'],'PASS',result['details'])
        self.assertEqual(result['gates']['merge'],'NOT_RUN')
        self.assertEqual(result['gates']['integrated_revision'],'NOT_RUN')
        self.assertEqual(result['gates']['release_dispatch'],'NOT_RUN')
        self.assertEqual(result['gates']['release_runtime'],'NOT_RUN')
        self.assertEqual(result['gates']['publication'],'NOT_RUN')
        self.assertTrue(all(method=='GET' for method,_ in api.methods))

    def test_audit_rejects_a_provider_record_for_a_different_pr_number(self):
        evidence,records,_,root=EvidenceV2Tests().ordinary_fixture()
        class API:
            def request(self,method,endpoint):return {'login':'danielbyon'}
            def record(self,ref):
                if ref==release.BASE:return records[ref]
                if ref==release.BASE+'/pulls/5':
                    return {'number':6,'base':{'ref':'main','repo':{'full_name':release.REPOSITORY}}}
                return records[ref]
            def pages(self,ref):
                return [records[evidence['integrations'][0]['readiness_index']['index_ref']]]
        result=evidence_call('audit_pull_request',root,API(),5)
        self.assertEqual(result['gates']['pull_request_identity'],'FAIL')
        self.assertEqual(result['gates']['release_dispatch'],'NOT_RUN')

    def test_audit_qualifies_prospective_baseline_before_dispatch(self):
        baseline_case=ProspectiveBaselineTests()
        self.addCleanup(baseline_case.doCleanups)
        root,source_api,evidence,base,baseline,dispatch,owner_record=(
            baseline_case.qualified_fixture())
        index_record=source_api.pages(release.BASE+'/issues/32/comments')[0]
        class API:
            def __init__(self):self.methods=[]
            def request(self,method,endpoint):
                self.methods.append((method,endpoint))
                if endpoint=='/user':return {'login':'danielbyon'}
                return source_api.request(method,endpoint)
            def record(self,ref):
                self.methods.append(('GET',ref))
                if ref==release.BASE+'/git/ref/heads/main':
                    return {'ref':'refs/heads/main','object':{'sha':baseline}}
                return source_api.record(ref)
            def pages(self,ref):
                self.methods.append(('GET',ref))
                return [index_record] if ref==release.BASE+'/issues/32/comments' else source_api.pages(ref)
            def ci_jobs(self,run_id,attempt):
                self.methods.append(('GET','ci_jobs'))
                return source_api.ci_jobs(run_id,attempt)
            def job_log(self,job_id):
                self.methods.append(('GET','job_log'))
                return source_api.job_log(job_id)
        api=API()
        result=evidence_call('audit_pull_request',root,api,32)
        for gate in ('account','repository_identity','pull_request_identity',
                     'evidence_receipts','candidate_ci','merge','integrated_revision',
                     'git_coverage','baseline_admission'):
            self.assertEqual(result['gates'][gate],'PASS',(gate,result['details']))
        for gate in ('release_dispatch','release_runtime','publication'):
            self.assertEqual(result['gates'][gate],'NOT_RUN')
        self.assertTrue(all(method=='GET' for method,_ in api.methods))

    def test_audit_fails_baseline_coverage_after_a_later_main_integration(self):
        import subprocess
        baseline_case=ProspectiveBaselineTests()
        self.addCleanup(baseline_case.doCleanups)
        root,source_api,evidence,base,baseline,dispatch,owner_record=(
            baseline_case.qualified_fixture())
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm',
                        'later main integration'],check=True)
        current_main=release.git(root,'rev-parse','HEAD').decode().strip()
        index_record=source_api.pages(release.BASE+'/issues/32/comments')[0]
        class API:
            def request(self,method,endpoint):
                return {'login':'danielbyon'} if endpoint=='/user' else source_api.request(method,endpoint)
            def record(self,ref):
                if ref==release.BASE+'/git/ref/heads/main':
                    return {'ref':'refs/heads/main','object':{'sha':current_main}}
                return source_api.record(ref)
            def pages(self,ref):
                return [index_record] if ref==release.BASE+'/issues/32/comments' else source_api.pages(ref)
            def ci_jobs(self,run_id,attempt):return source_api.ci_jobs(run_id,attempt)
            def job_log(self,job_id):return source_api.job_log(job_id)
        result=evidence_call('audit_pull_request',root,API(),32)
        self.assertEqual(result['gates']['baseline_admission'],'PASS',result['details'])
        self.assertEqual(result['gates']['git_coverage'],'FAIL')
        self.assertEqual(result['gates']['release_dispatch'],'NOT_RUN')
