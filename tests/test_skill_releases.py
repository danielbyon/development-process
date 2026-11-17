"""Release decisions must fail closed before remote writes."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_release as release
import release_evidence as evidence

def evidence_call(name,*args,**kwargs):
    return getattr(evidence,name)(release._evidence_context(),*args,**kwargs)

class EvidenceModuleBoundaryTests(unittest.TestCase):
    def test_controller_exposes_only_evidence_service_operations(self):
        operations={
            'audit_pull_request','build_owner_receipt','capture_execution',
            'discover_evidence','prepare_readiness_index',
            'verify_baseline_admission','verify_coverage','verify_evidence',
            'verify_live_integrations','verify_pending_baseline_coverage',
            'verify_premerge_integrations'}
        self.assertIsInstance(release._EVIDENCE,evidence.EvidenceService)
        self.assertEqual(set(evidence.__all__),{
            'EvidenceContext','EvidenceService','BaselineQualification',
            'VerifiedBaselineAdmission'})
        for operation in operations:
            with self.subTest(operation=operation):
                controller_operation=getattr(release,operation)
                service_operation=getattr(release._EVIDENCE,operation)
                self.assertIs(controller_operation.__self__,release._EVIDENCE)
                self.assertIs(controller_operation.__func__,service_operation.__func__)
        for implementation_detail in (
                'verify_review_chain','verify_review_dispositions',
                'verify_event_chronology','verify_ci_pull_request',
                'verify_execution_receipt','load_readiness_index',
                'readiness_index_binding','verify_ci_suites'):
            with self.subTest(implementation_detail=implementation_detail):
                self.assertFalse(hasattr(release,implementation_detail))

class EvidenceV2Tests(unittest.TestCase):
    def ordinary_fixture(self,root=None,base=None,head=None,pull_request=5,comment_offset=0):
        import json
        root=Path(__file__).resolve().parents[1] if root is None else Path(root)
        owner=123
        head=head or release.git(root,'rev-parse','HEAD').decode().strip()
        base=base or release.git(root,'rev-parse',head+'^').decode().strip()
        records={release.BASE:{
            'full_name':release.REPOSITORY,'owner':{'id':owner,'login':'danielbyon'}}};counter=comment_offset
        def post(gate,report,system,reviewed_range,created_at,transcript=None):
            nonlocal counter
            from unittest.mock import patch
            times={
                '2026-11-16T18:01:00Z':('2026-11-16T18:00:00Z','2026-11-16T18:00:30Z'),
                '2026-11-16T18:02:00Z':('2026-11-16T18:01:30Z','2026-11-16T18:01:45Z'),
                '2026-11-16T18:03:00Z':('2026-11-16T18:02:30Z','2026-11-16T18:02:45Z')}
            summary=report['summary']
            command=[sys.executable,'-c','import sys; print(sys.argv[1])',summary]
            with patch.object(release,'_utc_now',side_effect=times[created_at]):
                result=release.capture_execution(root,gate,system,command,report,
                    reviewed_range,transcript)
            counter+=1
            ref=release.BASE+'/issues/comments/'+str(counter)
            record={'id':counter,'user':{'id':owner},
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
            'body':'<!-- release-evidence-v2\n'+json.dumps(owner_event,sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:04:00Z','updated_at':'2026-11-16T18:04:00Z'}
        records[owner_ref]=owner_record
        owner_entry={'ref':owner_ref,'sha256':release.digest(release.canonical(owner_record))}
        ci_ref=release.BASE+'/actions/runs/7'
        ci={'id':7,'repository':{'full_name':release.REPOSITORY},'event':'pull_request',
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
            'reviewed_revision':head,'tested_revision':head,'records':integration_records}]}
        index_evidence={'schema_version':2,'owner_id':owner,'origin':{'kind':'ordinary'},
            'baseline_revision':base,'integrations':[dict(evidence['integrations'][0])]}
        index_ref=release.BASE+'/issues/comments/'+str(counter+2)
        index_record={'id':counter+2,'user':{'id':owner},
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

    def test_schema_v1_is_not_accepted_for_new_qualification(self):
        legacy=EvidenceTests().fixture()['evidence']
        with self.assertRaisesRegex(release.ReleaseError,'schema v2'):
            release.verify_evidence(legacy,lambda ref: {})

    def test_schema_v1_remains_available_only_for_frozen_release_verification(self):
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
        self.assertEqual(len(release.verify_evidence(evidence,records.__getitem__,root)),6)

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
            release.verify_evidence(evidence,records.__getitem__,root)

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

class ProspectiveBaselineTests(unittest.TestCase):
    def qualified_fixture(self):
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
        (root/'tests/test_skill_releases.py').write_text('# baseline tests\n')
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
        git('add','.');git('commit','-qm','corrected release evidence process');baseline=git('rev-parse','HEAD')
        tree=git('rev-parse',baseline+'^{tree}')
        manifest=release.digest(release.git(root,'ls-tree','-r','--full-tree','-z',baseline))
        policy=git('log','--first-parent','-1','--format=%H',baseline,'--','docs/PROCESS.md')
        policy_digest=release.digest(release.git(root,'show',baseline+':docs/PROCESS.md'))
        owner=123; records={release.BASE:{'full_name':release.REPOSITORY,
            'owner':{'id':owner,'login':'danielbyon'}}};counter=0
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
                'body':'<!-- release-evidence-v2\n'+json.dumps(event,sort_keys=True)+'\n-->',
                'created_at':created_at,'updated_at':created_at}
            records[ref]=record
            return {'ref':ref,'sha256':release.digest(release.canonical(record))}
        review_report={'coverage':'full-baseline','reviewed_revision':baseline,'tree_sha':tree,
                       'manifest_sha256':manifest,'findings':[],'dispositions':[],
                       'summary':'Reviewed every tracked file in the corrected baseline.'}
        review=make_receipt('baseline_review',review_report,'local_cubic',
            {'baseline_revision':baseline,'tree_sha':tree},'2026-11-16T20:05:00Z',baseline)
        chat_report={'coverage':'full-baseline','reviewed_revision':baseline,'tree_sha':tree,
                     'manifest_sha256':manifest,'source_files':['scripts/skill_release.py'],
                     'test_files':['tests/test_skill_releases.py'],
                     'file_sha256':{
                         'scripts/skill_release.py':release.digest(release.git(root,'show',baseline+':scripts/skill_release.py')),
                         'tests/test_skill_releases.py':release.digest(release.git(root,'show',baseline+':tests/test_skill_releases.py'))},
                     'summary':'Inspected the baseline source and release tests: scripts/skill_release.py tests/test_skill_releases.py'}
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
        proof=release.verify_baseline_admission(root,api,evidence,baseline,baseline,900)
        self.assertIsNone(release.verify_coverage(root,evidence,baseline,
            baseline_admission=proof))
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm','same tree descendant'],check=True)
        descendant=release.git(root,'rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            release.verify_coverage(root,evidence,descendant,baseline_admission=proof)

    def test_boolean_cannot_substitute_for_verified_baseline_admission(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        with self.assertRaisesRegex(release.ReleaseError,'independently verified'):
            release.verify_coverage(root,evidence,baseline,admitted=True)

    def test_full_baseline_admission_uses_authenticated_records_and_real_git_history(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        snapshots=release.verify_baseline_admission(root,api,evidence,baseline,baseline,900)
        self.assertEqual({item['gate'] for item in snapshots},
            {'baseline_review','chatgpt_inspection','ci','baseline_admission',
             'readiness_index','corrected_merge','ci_job','ci_log','release_dispatch'})
        self.assertIsNone(release.verify_coverage(root,evidence,baseline,
            baseline_admission=snapshots))

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

                index_ref=evidence['readiness_index']['original_ref']
                index_record=api.records[index_ref]
                index_marker='<!-- release-readiness\n'
                index=json.loads(index_record['body'].split(index_marker,1)[1].split('\n-->',1)[0])
                index['evidence']={key:value for key,value in evidence.items()
                                   if key!='readiness_index'}
                index_record['body']=index_marker+json.dumps(index,sort_keys=True)+'\n-->'
                index_digest=release.digest(release.canonical(index_record))
                evidence['readiness_index']['index_sha256']=index_digest
                evidence['readiness_index']['original_sha256']=index_digest

                with self.assertRaisesRegex(release.ReleaseError,
                        label+' execution must start and finish after the corrected merge'):
                    release.verify_baseline_admission(root,api,evidence,baseline,baseline,900)

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
        ordinary_snapshots=release.verify_evidence(ordinary_evidence,api.record,root)
        release.verify_live_integrations(api,ordinary_evidence,root)
        release.verify_coverage(root,ordinary_evidence,ordinary_head,admitted=True)
        baseline_proof=release.verify_baseline_admission(root,api,baseline_evidence,
            baseline,baseline,900)
        release.verify_coverage(root,baseline_evidence,baseline,
            baseline_admission=baseline_proof)
        self.assertEqual(pr['number'],31)
        self.assertEqual(ordinary_evidence['integrations'][0]['integrated_revision'],ordinary_head)
        self.assertIn('readiness_normalization',{item['gate'] for item in ordinary_snapshots})
        self.assertEqual(baseline_evidence['integrations'],[])
        self.assertIn('baseline_admission',{item['gate'] for item in baseline_proof})

    def test_verify_evidence_accepts_verified_zero_integration_baseline(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        proof=release.verify_evidence(evidence,api,root,dispatch_run_id=900)
        self.assertEqual(proof,release.verify_baseline_admission(
            root,api,evidence,baseline,baseline,900))
        with self.assertRaisesRegex(release.ReleaseError,'dispatch identity'):
            release.verify_evidence(evidence,api.record,root)

    def test_baseline_index_preparation_binds_review_ci_and_owner_admission(self):
        import json
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        body=release.prepare_readiness_index(evidence,32,api)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['evidence']['origin']['kind'],'prospective_baseline')
        self.assertEqual(wrapper['evidence']['integrations'],[])
        self.assertNotIn('readiness_index',wrapper['evidence'])

    def test_discovery_selects_only_the_exact_prospective_baseline_origin(self):
        from unittest.mock import patch
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        with patch.object(release,'select_anchor',return_value=None):
            discovered=release.discover_evidence(root,api,baseline,baseline)
        self.assertEqual(discovered['origin']['kind'],'prospective_baseline')
        self.assertEqual(discovered['baseline_revision'],baseline)
        self.assertEqual(discovered['integrations'],[])
        proof=release.verify_baseline_admission(root,api,discovered,baseline,baseline,900)
        self.assertIsNone(release.verify_coverage(root,discovered,baseline,
            baseline_admission=proof))

    def test_admission_after_original_dispatch_is_rejected(self):
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        dispatch['created_at']='2026-11-16T20:07:30Z'
        dispatch['run_attempt']=2
        with self.assertRaisesRegex(release.ReleaseError,'precede the original release dispatch'):
            release.verify_baseline_admission(root,api,evidence,baseline,baseline,900)

    def test_tree_equivalent_descendant_cannot_replace_baseline_identity(self):
        import subprocess
        root,api,evidence,base,baseline,dispatch,owner_record=self.qualified_fixture()
        subprocess.run(['git','-C',str(root),'commit','--allow-empty','-qm','same tree later commit'],check=True)
        descendant=release.git(root,'rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(release.ReleaseError,'source and builder'):
            release.verify_baseline_admission(root,api,evidence,descendant,descendant,900)
        proof=release.verify_baseline_admission(root,api,evidence,baseline,baseline,900)
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            release.verify_coverage(root,evidence,base,baseline_admission=proof)
        with self.assertRaisesRegex(release.ReleaseError,'exactly match'):
            release.verify_coverage(root,evidence,descendant,baseline_admission=proof)
        ordinary={'schema_version':2,'origin':{'kind':'ordinary'},
            'baseline_revision':baseline,'anchor_release':'2026.11.16','integrations':[]}
        with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
            release.verify_coverage(root,ordinary,descendant,admitted=True)

class AuditTests(unittest.TestCase):
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
        result=release.audit_pull_request(root,api,5)
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
        result=release.audit_pull_request(root,API(),5)
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
        result=release.audit_pull_request(root,api,32)
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
        result=release.audit_pull_request(root,API(),32)
        self.assertEqual(result['gates']['baseline_admission'],'PASS',result['details'])
        self.assertEqual(result['gates']['git_coverage'],'FAIL')
        self.assertEqual(result['gates']['release_dispatch'],'NOT_RUN')

class CaptureTests(unittest.TestCase):
    def test_execution_capture_derives_identity_from_real_command_output(self):
        import json,subprocess
        root=Path(__file__).resolve().parents[1]
        head=release.git(root,'rev-parse','HEAD').decode().strip()
        base=release.git(root,'rev-parse',head+'^').decode().strip()
        result=release.capture_execution(root,'author_execution','separate_codex',
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
        result=release.capture_execution(root,'chatgpt_inspection','chatgpt',[],report,
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
        evidence,records,_,_=EvidenceV2Tests().ordinary_fixture()
        api=Mock();api.request.return_value={'login':'danielbyon'}
        api.record.side_effect=records.__getitem__
        body=release.prepare_readiness_index(evidence,5,api)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['schema_version'],2)
        self.assertNotIn('normalizes',wrapper)
        self.assertNotIn('readiness_index',wrapper['evidence']['integrations'][0])
        self.assertEqual(wrapper['evidence']['integrations'][0]['records']['ci']['sha256'],
            release.digest(release.canonical(records[wrapper['evidence']['integrations'][0]['records']['ci']['ref']])))

    def test_postmerge_index_preparation_only_adds_actual_merge_identity(self):
        import json
        from unittest.mock import Mock
        evidence,records,_,_=EvidenceV2Tests().ordinary_fixture()
        integration=evidence['integrations'][0];head=integration['reviewed_revision']
        index_ref=integration['readiness_index']['original_ref']
        integration['integrated_revision']=head;integration['integrated_commits']=[head]
        records[release.BASE+'/pulls/5']={'number':5,'merged':True,
            'merged_at':'2026-11-16T18:10:00Z'}
        api=Mock();api.request.return_value={'login':'danielbyon'}
        api.record.side_effect=records.__getitem__
        body=release.prepare_readiness_index(evidence,5,api,normalizes_reference=index_ref)
        wrapper=json.loads(body.split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(wrapper['normalizes']['ref'],index_ref)
        self.assertEqual(wrapper['evidence']['integrations'][0]['integrated_revision'],head)
        self.assertNotIn('readiness_index',wrapper['evidence']['integrations'][0])

    def test_owner_receipt_names_the_distinct_authorized_action(self):
        import json
        body=release.build_owner_receipt('baseline_admission','a'*40)
        event=json.loads(body.split('<!-- release-evidence-v2\n',1)[1].split('\n-->',1)[0])
        self.assertEqual(event['report'],{'action':'admit-baseline','verdict':'approve'})

class OrdinaryChronologyIntegrationTests(unittest.TestCase):
    def qualified_fixture(self,fixture=None):
        import copy,json
        from unittest.mock import Mock
        evidence,records,_,root=(fixture or EvidenceV2Tests().ordinary_fixture())
        integration=evidence['integrations'][0]
        pull_request=integration['pull_request']
        head=integration['reviewed_revision']
        integration.update(integrated_revision=head,integrated_commits=[head])
        binding=integration['readiness_index']
        original=records[binding['original_ref']]
        payload=json.loads(original['body'].split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        normalized_evidence=copy.deepcopy(payload['evidence'])
        normalized_evidence['integrations'][0].update(
            integrated_revision=head,integrated_commits=[head])
        normalized_id=original['id']+1
        normalized_ref=release.BASE+'/issues/comments/'+str(normalized_id)
        normalized={'id':normalized_id,'user':{'id':123},
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
        job={'id':81,'name':'Validate committed PR integration diff','status':'completed',
             'conclusion':'success','started_at':'2026-11-16T18:01:00Z',
             'completed_at':'2026-11-16T18:03:00Z','steps':steps}
        ci_entry=integration['records']['ci'];ci=records[ci_entry['ref']]
        log='PR HEAD: '+head+'\nTested integration revision: '+head+'\nTested base revision: '+integration['base_revision']+'\n'+logs
        api=Mock()
        def record(ref):return records[ref]
        def pages(ref):
            if ref.endswith(f'/pulls/{pull_request}/commits'):return [{'sha':head}]
            if ref==release.BASE+'/commits/'+head+'/pulls':return [pr]
            return []
        api.record.side_effect=record;api.pages.side_effect=pages
        api.ci_jobs.return_value=[job];api.job_log.return_value=log
        loaded=evidence_call('load_readiness_index',normalized_ref,api.record,pull_request)
        integration['readiness_index']=evidence_call('readiness_index_binding',loaded)
        return root,api,evidence,records,job,pr

    def test_authenticated_receipts_normalization_ci_and_actual_merge_chronology(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        snapshots=release.verify_evidence(evidence,api.record,root)
        self.assertTrue(any(item['gate']=='readiness_normalization' for item in snapshots))
        release.verify_live_integrations(api,evidence,root)

    def test_original_index_edit_after_merge_invalidates_normalization(self):
        import json
        root,api,evidence,records,job,pr=self.qualified_fixture()
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
            release.verify_live_integrations(api,evidence,root)

    def test_ci_completion_after_merge_is_rejected(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        job['completed_at']='2026-11-16T18:12:00Z'
        with self.assertRaisesRegex(release.ReleaseError,'updated after|after the integration'):
            release.verify_live_integrations(api,evidence,root)

    def test_missing_merge_timestamp_and_wrong_pr_identity_are_rejected(self):
        root,api,evidence,records,job,pr=self.qualified_fixture()
        pr.pop('merged_at')
        with self.assertRaisesRegex(release.ReleaseError,'merge timestamp'):
            release.verify_live_integrations(api,evidence,root)
        pr['merged_at']='2026-11-16T18:10:00Z';pr['number']=6
        with self.assertRaisesRegex(release.ReleaseError,'number identity'):
            release.verify_live_integrations(api,evidence,root)

class ReleaseTests(unittest.TestCase):
    def test_pacific_original_date_and_suffix(self):
        self.assertEqual(release.allocate_version('2026-11-16T01:00:00Z', ['2026.11.15', '2026.11.15.2']), '2026.11.15.3')
    def test_invalid_calendar_and_suffix(self):
        for tag in ['2026.02.30', '2026.11.15.1', '2026.11.15.0', 'v2026.11.15']:
            with self.assertRaises(release.ReleaseError): release.version_key(tag)
    def test_boolean_is_not_review_evidence(self):
        with self.assertRaises(release.ReleaseError):
            release.verify_frozen_release_evidence({'independent_review': True}, lambda ref: {})
    def test_existing_pin_is_not_reselected(self):
        self.assertEqual(release.resolve_task(None, existing_pin='a'*40), {'task_pin':'a'*40})
    def test_no_release_blocks(self):
        class API:
            def releases(self): return []
        with self.assertRaisesRegex(release.ReleaseError, 'NO_IMMUTABLE_RELEASE'):
            release.resolve_task(API())
    def test_skipped_qualification_blocks(self):
        result = unittest.TestResult(); result.testsRun=1; result.skipped=[('test','reason')]
        with self.assertRaises(release.ReleaseError): release.require_tests(result)

class EvidenceTests(unittest.TestCase):
    def fixture(self):
        import json
        return json.loads((Path(__file__).parent/'fixtures/release_evidence.json').read_text())
    def test_authenticated_reports_are_bound_to_candidate(self):
        f=self.fixture()
        records=f['records']
        self.assertEqual(len(release.verify_frozen_release_evidence(f['evidence'], records.__getitem__)),4)
    def test_tampered_record_blocks(self):
        f=self.fixture(); first=next(iter(f['records'].values())); first['body']='summary only'
        with self.assertRaises(release.ReleaseError): release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_self_review_blocks_even_with_recomputed_hash(self):
        f=self.fixture(); i=f['evidence']['integrations'][0]; i['author_execution_id']='review-execution'
        with self.assertRaises(release.ReleaseError): release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_wrong_inspection_candidate_blocks(self):
        f=self.fixture(); entry=f['evidence']['integrations'][0]['records']['chatgpt_inspection']
        actual=f['records'][entry['ref']]; actual['body']=actual['body'].replace('a'*40,'b'*40)
        entry['sha256']=release.digest(release.canonical(actual))
        with self.assertRaises(release.ReleaseError): release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_failed_ci_blocks_even_with_matching_digest(self):
        f=self.fixture(); entry=f['evidence']['integrations'][0]['records']['ci']
        actual=f['records'][entry['ref']]; actual['conclusion']='failure';entry['sha256']=release.digest(release.canonical(actual))
        with self.assertRaises(release.ReleaseError): release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)

class PublicationTests(unittest.TestCase):
    def test_duplicate_remote_assets_block(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(8): (Path(tmp)/str(n)).write_bytes(b'x')
            class API:
                def tags(self): return []
            with self.assertRaises(release.ReleaseError):
                release.verify_remote(API(),{'tag_name':'2026.11.16','name':'2026.11.16','prerelease':False,'assets':[]},
                    {'release_version':'2026.11.16','source_revision':'a'*40},tmp,False)
    def test_asset_directory_rejects_symlinks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(7): (Path(tmp)/str(n)).write_bytes(b'x')
            (Path(tmp)/'link').symlink_to(Path(tmp)/'0')
            with self.assertRaises(release.ReleaseError): release.artifact_hashes(tmp)

class LiveEvidenceTests(unittest.TestCase):
    def test_missing_pr_cannot_be_admitted_from_reports(self):
        with self.assertRaisesRegex(release.ReleaseError,'Merged PR reference'):
            release.verify_live_integrations(None,{'integrations':[{}]})
    def test_ci_summary_success_without_jobs_does_not_pass(self):
        integration={'pull_request':1,'reviewed_revision':'a'*40,'integrated_revision':'b'*40,
                     'records':{'ci':{'ref':'ci','run_attempt':1}}}
        class API:
            def record(self,ref):
                if ref=='ci': return {'id':1,'repository':{'full_name':release.REPOSITORY},'event':'pull_request'}
                return {'merged':True,'base':{'ref':'main'},'head':{'sha':'a'*40},'merge_commit_sha':'b'*40}
            def ci_jobs(self,*args): return []
        with self.assertRaisesRegex(release.ReleaseError,'Required CI job'):
            release.verify_live_integrations(API(),{'integrations':[integration]})

class StateMachineTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.tmp=tempfile.TemporaryDirectory(); self.directory=Path(self.tmp.name)
        for n in range(8): (self.directory/str(n)).write_bytes(str(n).encode())
        self.context={'release_version':'2026.11.16','source_revision':'a'*40,'builder_revision':'b'*40,
            'run_attempt':1,'evidence':{},'evidence_snapshots':[],
            'qualification':{'run_attempt':1,'suites':[{'suite':s,'tests':1} for s in release.SUITES]},
            'qualified_artifacts':release.artifact_hashes(self.directory)}
        self.patches=[patch.object(release,'check_settings'),patch.object(release,'verify_evidence',return_value=[]),
            patch.object(release,'verify_live_integrations'),patch.object(release,'admit_anchor'),patch.object(release,'verify_coverage'),
            patch.object(release,'verify_bundle')]
        for p in self.patches: p.start()
        from unittest.mock import Mock
        self.api=Mock()
        self.api.releases.return_value=[];self.api.tags.return_value=[]
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()
    def body(self): return 'Release context: '+release.digest(release.canonical({k:v for k,v in self.context.items() if k!='qualified_artifacts'}))
    def test_orphan_tag_is_preserved_without_mutation(self):
        self.api.tags.return_value=[{'ref':'refs/tags/2026.11.16'}]
        with self.assertRaisesRegex(release.ReleaseError,'Orphaned tag'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called();self.api.create_tag.assert_not_called()
    def test_unknown_draft_is_preserved(self):
        self.api.releases.return_value=[{'tag_name':'2026.11.16','body':'foreign','draft':True}]
        with self.assertRaisesRegex(release.ReleaseError,'ownership'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.upload.assert_not_called();self.api.publish.assert_not_called()
    def test_modified_qualified_bytes_prevent_draft(self):
        (self.directory/'0').write_bytes(b'modified')
        with self.assertRaisesRegex(release.ReleaseError,'artifact mismatch'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called()
    def test_attestation_failures_prevent_every_release_mutation(self):
        for failure in ('missing permissions','invalid signature','wrong workflow','modified manifest','missing attestation','service unavailable'):
            with self.subTest(failure=failure):
                self.api.verify_qualification_attestation.side_effect=release.APIError(failure)
                with self.assertRaises(release.APIError):
                    release.publish(Path('.'),self.api,self.context,self.directory)
                for name in ('create_draft','upload','create_tag','publish'):
                    getattr(self.api,name).assert_not_called()

    def test_wrong_attempt_prevents_draft(self):
        self.context['qualification']['run_attempt']=0
        with self.assertRaisesRegex(release.ReleaseError,'Fresh qualification'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called()
    def test_published_release_only_verifies(self):
        from unittest.mock import patch
        published={'tag_name':'2026.11.16','body':self.body(),'draft':False}
        self.api.releases.return_value=[published]
        with patch.object(release,'verify_remote',return_value=published):
            self.assertEqual(release.publish(Path('.'),self.api,self.context,self.directory),published)
        self.api.publish.assert_not_called();self.api.upload.assert_not_called()
    def test_conflicting_asset_never_overwritten(self):
        self.api.releases.return_value=[{'tag_name':'2026.11.16','body':self.body(),'draft':True,'assets':[{'name':'0'}]}]
        self.api.asset.return_value=b'conflict'
        with self.assertRaisesRegex(release.ReleaseError,'Conflicting draft asset'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.upload.assert_not_called();self.api.publish.assert_not_called()
    def test_successful_draft_upload_tag_publish_order(self):
        from unittest.mock import patch
        events=[]
        draft={'id':1,'tag_name':'2026.11.16','draft':True,'assets':[]}
        self.api.verify_qualification_attestation.side_effect=lambda *args: events.append('attestation')
        self.api.create_draft.side_effect=lambda *args: events.append('draft') or draft
        self.api.upload.side_effect=lambda *args:events.append('upload')
        self.api.create_tag.side_effect=lambda *args:events.append('tag')
        self.api.publish.side_effect=lambda *args:events.append('publish')
        self.api.release.return_value=draft
        with patch.object(release,'verify_remote',return_value=draft):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.assertEqual(events,['attestation','draft']+['upload']*8+['tag','publish'])

class DispatchTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.api=Mock()
        self.context={'owner_id':123,'builder_revision':'b'*40,'run_id':4,'run_attempt':1,'created_at':'2026-11-16T01:00:00Z'}
        self.settings={'repository':{'full_name':release.REPOSITORY,'default_branch':'main','owner':{'login':'danielbyon','id':123}},
            'immutability':{'enabled':True},'rules':[{'type':name} for name in ('pull_request','non_fast_forward','deletion')]+[
                {'type':'required_status_checks','parameters':{'required_status_checks':[{'context':'Validate committed PR integration diff','integration_id':15368}]}}]}
        self.run={'event':'workflow_dispatch','head_branch':'main','head_sha':'b'*40,'actor':{'id':123},'triggering_actor':{'id':123},
            'run_attempt':1,'created_at':self.context['created_at'],'path':'.github/workflows/skill-release.yml'}
        self.settings['rulesets']=[{'enforcement':'active','bypass_actors':[]}]
        self.settings['collaborators']=[{'id':123,'permissions':{'admin':True}}]
        self.api.settings.return_value=self.settings;self.api.run.return_value=self.run
    def test_valid_dispatch(self):
        self.assertEqual(release.check_settings(self.api,self.context),self.settings)
    def test_foreign_rerun_actor_blocks(self):
        self.run['triggering_actor']['id']=999
        with self.assertRaisesRegex(release.ReleaseError,'Owner-only'): release.check_settings(self.api,self.context)
    def test_immutability_disabled_blocks(self):
        self.settings['immutability']['enabled']=False
        with self.assertRaisesRegex(release.ReleaseError,'Immutable'): release.check_settings(self.api,self.context)
    def test_untrusted_workflow_blocks(self):
        self.run['path']='.github/workflows/ci.yml'
        with self.assertRaisesRegex(release.ReleaseError,'Unexpected dispatch'): release.check_settings(self.api,self.context)
    def test_missing_main_protection_blocks(self):
        self.settings['rules']=[]
        with self.assertRaisesRegex(release.ReleaseError,'Main protections'): release.check_settings(self.api,self.context)

class RemoteVerificationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import Mock
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.assets=[]
        for n in range(8):
            (self.directory/str(n)).write_bytes(str(n).encode());self.assets.append({'name':str(n),'id':n})
        self.api=Mock();self.api.asset.side_effect=lambda a:str(a['id']).encode()
        self.api.tags.return_value=[{'ref':'refs/tags/2026.11.16','object':{'type':'commit','sha':'a'*40}}]
        self.context={'release_version':'2026.11.16','source_revision':'a'*40}
        self.remote={'tag_name':'2026.11.16','name':'2026.11.16','prerelease':False,'draft':False,'immutable':True,'assets':self.assets}
    def tearDown(self): self.tmp.cleanup()
    def test_valid_release_checks_attestation(self):
        release.verify_remote(self.api,self.remote,self.context,self.directory,True)
        self.api.verify_attestation.assert_called_once()
    def test_mutable_release_rejected(self):
        self.remote['immutable']=False
        with self.assertRaisesRegex(release.ReleaseError,'not immutable'):
            release.verify_remote(self.api,self.remote,self.context,self.directory,True)
    def test_annotated_tag_not_silently_accepted(self):
        self.api.tags.return_value[0]['object']['type']='tag'
        with self.assertRaisesRegex(release.ReleaseError,'Tag target'):
            release.verify_remote(self.api,self.remote,self.context,self.directory,True)
    def test_asset_replacement_detected(self):
        self.api.asset.return_value=b'bad';self.api.asset.side_effect=None
        with self.assertRaisesRegex(release.ReleaseError,'asset bytes'):
            release.verify_remote(self.api,self.remote,self.context,self.directory,True)
    def test_title_change_is_rechecked(self):
        self.remote['name']='changed'
        with self.assertRaisesRegex(release.ReleaseError,'identity'):
            release.verify_remote(self.api,self.remote,self.context,self.directory,True)

class PackagingIntegrationTests(unittest.TestCase):
    def test_transport_context_is_excluded_and_frozen_context_preserved(self):
        import tempfile
        import json
        import skill_distribution as packaging
        root=Path(__file__).resolve().parents[1]
        context={'repository':release.REPOSITORY,'release_version':'2026.11.16',
            'source_revision':release.BOOTSTRAP_BASELINE,'builder_revision':release.BOOTSTRAP_BASELINE,
            'policy_revision':'e2afa055d1126763c69f0e0392d25b86bab98014','transform_version':1}
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'bundle'
            packaging.build_release_packages(root,directory,context)
            transport={**context,'qualified_artifacts':release.artifact_hashes(directory)}
            (directory/'release-context.json').write_text(json.dumps(transport))
            release.verify_bundle(root,directory,transport)
            self.assertEqual(len(release.artifact_hashes(directory)),8)
            (directory/'SHA256SUMS').write_text('altered')
            with self.assertRaisesRegex(release.ReleaseError,'artifact mismatch'):
                release.verify_bundle(root,directory,transport)

class AdversarialProvenanceTests(unittest.TestCase):
    def fixture(self):
        import json
        return json.loads((Path(__file__).parent/'fixtures/release_evidence.json').read_text())
    def test_reviewer_cannot_choose_its_own_trust_identity(self):
        f=self.fixture();integration=f['evidence']['integrations'][0]
        integration.pop('author_execution_id')
        entry=integration['records']['independent_review'];record=f['records'][entry['ref']]
        record['user']['id']=999999;entry['author_id']=999999;entry['sha256']=release.digest(release.canonical(record))
        with self.assertRaises(release.ReleaseError):release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_missing_execution_export_blocks(self):
        f=self.fixture();entry=f['evidence']['integrations'][0]['records']['independent_review'];entry['execution']['sha256']='0'*64
        with self.assertRaisesRegex(release.ReleaseError,'Execution provenance'):
            release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_ci_head_can_differ_from_tested_merge(self):
        f=self.fixture();f['evidence']['integrations'][0]['tested_revision']='b'*40
        self.assertEqual(len(release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)),4)
    def test_owner_is_bound_to_repository_not_export(self):
        f=self.fixture();f['evidence']['owner_id']=999
        with self.assertRaisesRegex(release.ReleaseError,'repository owner'):
            release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_frozen_ownership_excludes_fresh_attempt(self):
        original={'run_id':5,'run_attempt':1,'qualification':{'run_attempt':1}}
        retried={**original,'validation_attempt':2}
        def identity(c):return release.digest(release.canonical({k:v for k,v in c.items() if k not in ('qualified_artifacts','validation_attempt')}))
        self.assertEqual(identity(original),identity(retried))
    def test_reconstructed_but_unqualified_release_is_rejected(self):
        import tempfile
        import skill_distribution as packaging
        from unittest.mock import Mock
        root=Path(__file__).resolve().parents[1]
        context={'repository':release.REPOSITORY,'release_version':'2026.11.16',
            'source_revision':release.BOOTSTRAP_BASELINE,'builder_revision':release.BOOTSTRAP_BASELINE,
            'policy_revision':'e2afa055d1126763c69f0e0392d25b86bab98014','transform_version':1}
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'bundle';packaging.build_release_packages(root,directory,context)
            assets=[{'name':p.name,'id':n} for n,p in enumerate(directory.iterdir())]
            payload={a['id']:(directory/a['name']).read_bytes() for a in assets}
            api=Mock();api.releases.return_value=[{'tag_name':context['release_version'],'assets':assets}]
            api.asset.side_effect=lambda a:payload[a['id']]
            with self.assertRaisesRegex(release.ReleaseError,'Qualification evidence'):
                release.verify_release(root,api,context['release_version'])

class BuildProcessTests(unittest.TestCase):
    def test_independent_builds_match_source_bound_bytes(self):
        import tempfile
        root=Path(__file__).resolve().parents[1]
        context={'repository':release.REPOSITORY,'release_version':'2026.11.16',
            'source_revision':release.BOOTSTRAP_BASELINE,'builder_revision':release.BOOTSTRAP_BASELINE,
            'policy_revision':'e2afa055d1126763c69f0e0392d25b86bab98014','transform_version':1}
        with tempfile.TemporaryDirectory() as tmp:
            first=Path(tmp)/'first';second=Path(tmp)/'second'
            release.independent_build(root,first,context);release.independent_build(root,second,context)
            self.assertEqual(release.artifact_hashes(first),release.artifact_hashes(second))

class LegacyNormalizationTests(unittest.TestCase):
    fixture=EvidenceTests.fixture
    def legacy(self):
        import json
        f=self.fixture()
        for gate,entry in f['evidence']['integrations'][0]['records'].items():
            if gate=='ci': continue
            record=f['records'][entry['ref']]
            report=json.loads(record['body'].split('<!-- release-evidence\n')[1].split('\n-->')[0])
            entry['normalized_report']=report
            record['body']=report['report']
            entry['sha256']=release.digest(release.canonical(record))
            transcript=f['records'][entry['execution']['ref']]
            envelope=json.loads(transcript['body'])
            envelope['transcript']+='\n'+json.dumps(report,sort_keys=True)
            transcript['body']=json.dumps(envelope,sort_keys=True)
            entry['execution']['sha256']=release.digest(release.canonical(transcript))
        ref=release.BASE+'/issues/comments/99'
        f['records'][ref]={'user':{'id':123},'body':json.dumps({'repository':release.REPOSITORY,'evidence':f['evidence']})}
        return f,ref
    def test_legacy_reports_need_no_new_original_markers(self):
        f,ref=self.legacy()
        evidence=release.load_evidence_export(ref,f['records'].__getitem__)
        self.assertEqual(len(release.verify_frozen_release_evidence(evidence,f['records'].__getitem__)),4)
    def test_foreign_export_author_blocks(self):
        f,ref=self.legacy();f['records'][ref]['user']['id']=999
        with self.assertRaises(release.ReleaseError):release.load_evidence_export(ref,f['records'].__getitem__)
    def test_unverified_normalization_blocks(self):
        f,_=self.legacy()
        with self.assertRaises(release.ReleaseError):release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_normalized_claim_must_exist_in_execution(self):
        f,ref=self.legacy()
        evidence=release.load_evidence_export(ref,f['records'].__getitem__)
        evidence['integrations'][0]['records']['chatgpt_inspection']['normalized_report']['source_files']=['invented.py']
        with self.assertRaises(release.ReleaseError):release.verify_frozen_release_evidence(evidence,f['records'].__getitem__)

class AnchorSelectionTests(unittest.TestCase):
    def test_selects_nearest_applicable_verified_source_not_newest_tag(self):
        from unittest.mock import Mock,patch
        api=Mock();api.releases.return_value=[{'tag_name':v,'draft':False,'prerelease':False} for v in ('2026.11.16','2026.11.17')]
        def history(root,*args):
            if args[0]=='rev-list': return b'x\ny\n' if args[-1].startswith('a') else b'x\n'
            return b''
        with patch.object(release,'git',side_effect=history),patch.object(release,'verify_release',side_effect=[{'source_revision':'a'*40},{'source_revision':'b'*40}]):
            self.assertEqual(release.select_anchor(Path('.'),api,'c'*40,'d'*40),('b'*40,'2026.11.16'))
    def test_nonancestor_release_is_not_anchor(self):
        from unittest.mock import Mock,patch
        api=Mock();api.releases.return_value=[{'tag_name':'2026.11.16','draft':False,'prerelease':False}]
        with patch.object(release,'git',side_effect=release.ReleaseError('not ancestor')),patch.object(release,'verify_release',return_value={'source_revision':'a'*40}):
            self.assertEqual(release.select_anchor(Path('.'),api,'c'*40,'d'*40),None)

class HistoricalAdmissionTests(unittest.TestCase):
    fixture=EvidenceTests.fixture
    legacy=LegacyNormalizationTests.legacy
    def test_legacy_baseline_admission_uses_original_report(self):
        import json
        from unittest.mock import Mock
        f,ref=self.legacy()
        admission_ref=release.BASE+'/issues/comments/100'
        report={'revision':'a'*40,'action':'admit-baseline','report':'Reviewed original baseline qualification.', 'execution_id':'baseline-execution'}
        original={'user':{'id':123},'body':'baseline-execution at '+'a'*40+'\n'+report['report']}
        f['records'][admission_ref]=original
        evidence=json.loads(f['records'][ref]['body'])['evidence']
        evidence['baseline_admission']={'ref':admission_ref,'sha256':release.digest(release.canonical(original)), 'normalized_report':report}
        f['records'][ref]['body']=json.dumps({'repository':release.REPOSITORY,'evidence':evidence})
        normalized=release.load_evidence_export(ref,f['records'].__getitem__)
        api=Mock();api.record.side_effect=f['records'].__getitem__
        release.admit_anchor(Path('.'),api,normalized)
    def test_no_uncovered_integrations_can_reuse_verified_anchor(self):
        f=self.fixture();f['evidence']['integrations']=[];f['evidence']['anchor_release']='2026.11.15'
        self.assertEqual(release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__),[])

class ReleaseRecursionTests(unittest.TestCase):
    def test_anchor_cycle_blocks_without_infinite_recursion(self):
        from unittest.mock import patch
        with patch.object(release,'_verify_release',side_effect=lambda *args: release.verify_release(*args)):
            with self.assertRaisesRegex(release.ReleaseError,'Cyclic'):
                release.verify_release(Path('.'),None,'2026.11.16')

class HistoryCoverageTests(unittest.TestCase):
    def test_rebased_range_covers_each_integrated_commit(self):
        import tempfile,subprocess
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def git(*args):return subprocess.check_output(['git','-C',temporary,*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.name','Test');git('config','user.email','test@example.invalid')
            (root/'file').write_text('base');git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            (root/'file').write_text('first');git('commit','-am','first')
            (root/'file').write_text('final');git('commit','-am','final');result=git('rev-parse','HEAD')
            evidence={'schema_version':1,'baseline_revision':base,'baseline_admission':{'ref':'admitted'},'integrations':[
                {'integrated_revision':base,'reviewed_revision':base,'tested_revision':base},
                {'base_revision':base,'integrated_revision':result,'reviewed_revision':result,'tested_revision':result}]}
            with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
                release.verify_coverage(root,evidence,result,admitted=True)
            evidence['integrations'][-1]['integrated_commits']=git('rev-list','--first-parent',base+'..'+result).split()[::-1]
            release.verify_coverage(root,evidence,result,admitted=True)
            evidence['integrations'].pop()
            with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
                release.verify_coverage(root,evidence,result,admitted=True)

class DiscoveryTests(unittest.TestCase):
    def test_discovery_reuses_verified_anchor_without_bootstrap_ancestry(self):
        from unittest.mock import Mock,patch
        api=Mock();api.request.return_value={'full_name':release.REPOSITORY,'owner':{'id':123}}
        revisions={'a'*40,'b'*40,'c'*40}
        def git(root,*args):
            if args[0]=='rev-parse' and args[1].endswith('^{commit}'):
                value=args[1][:-len('^{commit}')]
                return (value+'\n').encode() if value in revisions else b''
            return b''
        with patch.object(release,'select_anchor',return_value=('a'*40,'2026.11.15')),patch.object(release,'git',side_effect=git):
            evidence=release.discover_evidence(Path('.'),api,'b'*40,'c'*40)
        self.assertEqual(evidence['schema_version'],2)
        self.assertEqual(evidence['baseline_revision'],'a'*40)
        self.assertEqual(evidence['anchor_release'],'2026.11.15')
        self.assertEqual(evidence['integrations'],[])
    def test_first_release_refuses_different_source_and_builder_without_anchor(self):
        from unittest.mock import Mock,patch
        root=Path(__file__).resolve().parents[1]
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        builder=release.git(root,'rev-parse','HEAD^').decode().strip()
        api=Mock();api.request.return_value={'full_name':release.REPOSITORY,'owner':{'id':123}}
        with patch.object(release,'select_anchor',return_value=None):
            with self.assertRaisesRegex(release.ReleaseError,'source and builder'):
                release.discover_evidence(root,api,source,builder)
    def test_failed_release_verification_is_not_silently_skipped(self):
        from unittest.mock import Mock,patch
        api=Mock();api.releases.return_value=[{'tag_name':'2026.11.16','draft':False,'prerelease':False}]
        with patch.object(release,'verify_release',side_effect=release.APIError('expired evidence')):
            with self.assertRaisesRegex(release.APIError,'expired evidence'):
                release.select_anchor(Path('.'),api,'a'*40,'b'*40)

class NormalizationBoundaryTests(unittest.TestCase):
    fixture=EvidenceTests.fixture
    legacy=LegacyNormalizationTests.legacy
    def test_nonowner_original_review_can_be_verified_by_owner_export(self):
        import json
        f,ref=self.legacy()
        evidence=json.loads(f['records'][ref]['body'])['evidence']
        entry=evidence['integrations'][0]['records']['independent_review']
        f['records'][entry['ref']]['user']['id']=999
        entry['author_id']=999;entry['sha256']=release.digest(release.canonical(f['records'][entry['ref']]))
        f['records'][ref]['body']=json.dumps({'repository':release.REPOSITORY,'evidence':evidence})
        self.assertEqual(len(release.verify_frozen_release_evidence(release.load_evidence_export(ref,f['records'].__getitem__),f['records'].__getitem__)),4)

class ReadinessNormalizationTests(unittest.TestCase):
    def fixture(self):
        import copy,json
        owner=123;number=32
        original_evidence={'schema_version':2,'owner_id':owner,
            'origin':{'kind':'ordinary'},'baseline_revision':'a'*40,
            'integrations':[{'pull_request':number,'base_revision':'a'*40,
                'reviewed_revision':'b'*40,'records':{'author_execution':{'ref':'author','sha256':'1'*64}}}]}
        original={'id':10,'user':{'id':owner},
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':number,
                'evidence':original_evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:00:00Z','updated_at':'2026-11-16T18:00:00Z'}
        normalized_evidence=copy.deepcopy(original_evidence)
        normalized_evidence['integrations'][0]['integrated_revision']='c'*40
        normalized_evidence['integrations'][0]['integrated_commits']=['c'*40]
        normalized={'id':11,'user':{'id':owner},
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':number,
                'normalizes':{'ref':release.BASE+'/issues/comments/10',
                    'sha256':release.digest(release.canonical(original))},
                'evidence':normalized_evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T20:00:00Z','updated_at':'2026-11-16T20:00:00Z'}
        records={release.BASE+'/issues/comments/10':original,
                 release.BASE+'/issues/comments/11':normalized,
                 release.BASE:{'full_name':release.REPOSITORY,'owner':{'id':owner}}}
        return records,normalized_evidence

    def test_late_normalization_binds_unchanged_premerge_index(self):
        records,expected=self.fixture()
        loaded=evidence_call('load_readiness_index',release.BASE+'/issues/comments/11',
            records.__getitem__,32)
        self.assertEqual(loaded['evidence'],expected)
        self.assertEqual(loaded['original_record']['id'],10)
        self.assertEqual(loaded['normalization_record']['id'],11)

    def test_normalization_cannot_change_reviewed_evidence(self):
        import json
        records,_=self.fixture();record=records[release.BASE+'/issues/comments/11']
        wrapper=json.loads(record['body'].split('<!-- release-readiness\n',1)[1].split('\n-->',1)[0])
        wrapper['evidence']['integrations'][0]['reviewed_revision']='d'*40
        record['body']='<!-- release-readiness\n'+json.dumps(wrapper,sort_keys=True)+'\n-->'
        with self.assertRaisesRegex(release.ReleaseError,'normalization changed'):
            evidence_call('load_readiness_index',release.BASE+'/issues/comments/11',
                records.__getitem__,32)

    def test_normalization_rejects_mutated_original_provider_record(self):
        records,_=self.fixture()
        records[release.BASE+'/issues/comments/10']['updated_at']='2026-11-16T20:01:00Z'
        with self.assertRaisesRegex(release.ReleaseError,'Original readiness record'):
            evidence_call('load_readiness_index',release.BASE+'/issues/comments/11',
                records.__getitem__,32)

class ExactExecutionTests(unittest.TestCase):
    fixture=EvidenceTests.fixture
    def test_reviewer_export_cannot_double_as_author(self):
        f=self.fixture();integration=f['evidence']['integrations'][0]
        integration['author_execution']=dict(integration['records']['independent_review']['execution'])
        integration['author_execution_id']='review'
        with self.assertRaises(release.ReleaseError):release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)
    def test_review_range_mismatch_rejected(self):
        import json
        f=self.fixture();entry=f['evidence']['integrations'][0]['records']['independent_review']['execution']
        record=f['records'][entry['ref']];envelope=json.loads(record['body'])
        envelope['reviewed_range']['base_revision']='c'*40;record['body']=json.dumps(envelope)
        entry['sha256']=release.digest(release.canonical(record))
        with self.assertRaises(release.ReleaseError):release.verify_frozen_release_evidence(f['evidence'],f['records'].__getitem__)

class DurableResolutionTests(unittest.TestCase):
    def test_verified_release_survives_missing_actions_artifacts_and_logs(self):
        import json,tempfile
        from unittest.mock import Mock
        import skill_distribution as packaging
        root=Path(__file__).resolve().parents[1]
        revision=release.BOOTSTRAP_BASELINE
        f=EvidenceTests.fixture(self)
        f=json.loads(json.dumps(f).replace('a'*40,revision).replace('b'*40,revision))
        integration=f['evidence']['integrations'][0];integration['pull_request']=27
        ci=f['records'][integration['records']['ci']['ref']]
        ci.update(id=4,repository={'full_name':release.REPOSITORY},event='pull_request')
        for entry in [integration['author_execution']]+list(integration['records'].values())+[e['execution'] for e in integration['records'].values() if 'execution' in e]:
            entry['sha256']=release.digest(release.canonical(f['records'][entry['ref']]))
        f['records'][release.BASE+'/pulls/27']={'merged':True,'base':{'ref':'main'},'head':{'sha':revision},'merge_commit_sha':revision}
        api=Mock();api.record.side_effect=f['records'].__getitem__
        _,steps,logs=SuiteExecutionTests.fixture(revision)
        api.ci_jobs.return_value=[{'id':5,'name':'Validate committed PR integration diff','conclusion':'success','steps':steps}]
        api.job_log.return_value='\n'.join(['PR HEAD: '+revision,'Tested integration revision: '+revision,'Tested base revision: '+revision,logs])
        api.pages.side_effect=lambda path: ([{'sha':revision}] if path.endswith('/commits') else [{'number':27,'merged_at':'date','base':{'ref':'main'},'merge_commit_sha':revision}])
        authority=release.EvidenceAuthority(api)
        snapshots=release.verify_frozen_release_evidence(f['evidence'],authority.record)
        release.verify_live_integrations(authority,f['evidence'],root)
        context={'repository':release.REPOSITORY,'release_version':'2026.11.16','source_revision':revision,
            'builder_revision':revision,'policy_revision':'e2afa055d1126763c69f0e0392d25b86bab98014',
            'transform_version':1,'owner_id':123,'run_id':7,'evidence':f['evidence'],
            'evidence_snapshots':snapshots,'evidence_digest':release.digest(release.canonical(snapshots)),
            'authenticated_evidence':authority.data,
            'qualification':{'run_attempt':1,'suites':[{'suite':name,'tests':1} for name in release.SUITES]}}
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'bundle';packaging.build_release_packages(root,directory,context)
            payload={index:p.read_bytes() for index,p in enumerate(sorted(directory.iterdir()))}
            assets=[{'id':index,'name':p.name} for index,p in enumerate(sorted(directory.iterdir()))]
            remote={'tag_name':context['release_version'],'name':context['release_version'],'draft':False,'prerelease':False,'immutable':True,'assets':assets}
            api.releases.return_value=[remote];api.asset.side_effect=lambda asset:payload[asset['id']]
            api.tags.return_value=[{'ref':'refs/tags/'+context['release_version'],'object':{'sha':revision,'type':'commit'}}]
            api.original_context.side_effect=release.APIError('expired artifact')
            api.ci_jobs.side_effect=release.APIError('expired jobs');api.job_log.side_effect=release.APIError('expired logs')
            result=release.verify_release(root,api,context['release_version'])
            self.assertEqual(result['source_revision'],revision)
            api.original_context.assert_not_called();api.verify_qualification_attestation.assert_called_once()
            api.verify_attestation.assert_called_once()
            for key,value in [('immutable',False),('draft',True),('prerelease',True),('name','altered')]:
                original=remote[key];remote[key]=value
                with self.assertRaises(release.ReleaseError):
                    release.verify_release(root,api,context['release_version'])
                remote[key]=original
            api.verify_qualification_attestation.side_effect=release.APIError('unsigned qualification')
            with self.assertRaisesRegex(release.APIError,'unsigned qualification'):
                release.verify_release(root,api,context['release_version'])

class IntegrationMembershipTests(unittest.TestCase):
    def test_intervening_other_pr_cannot_be_absorbed(self):
        from unittest.mock import Mock
        api=Mock();integration={'pull_request':2,'integrated_revision':'c'*40,'integrated_commits':['b'*40,'c'*40]}
        def pages(path):
            if path.endswith('/commits'): return [{'sha':'x'},{'sha':'y'}]
            number=1 if '/commits/'+('b'*40) in path else 2
            return [{'number':number,'merged_at':'date','base':{'ref':'main'},'merge_commit_sha':('b' if number==1 else 'c')*40}]
        api.pages.side_effect=pages
        with self.assertRaises(release.ReleaseError):evidence_call('verify_membership',api,integration)

class RebaseDiscoveryTests(unittest.TestCase):
    def test_normal_dispatch_groups_all_rebased_commits(self):
        import json,subprocess,tempfile
        from unittest.mock import Mock,patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def git(*args):return subprocess.check_output(['git','-C',temporary,*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.name','Test');git('config','user.email','test@example.invalid')
            commits=[]
            for content in ('baseline','first rebased change','second rebased change'):
                (root/'file').write_text(content);git('add','.');git('commit','-m',content);commits.append(git('rev-parse','HEAD'))
            base,first,result=commits
            pr={'number':9,'merged':True,'merge_commit_sha':result,
                'merged_at':'2026-11-16T19:00:00Z','base':{'ref':'main'}}
            integration={'pull_request':9,'integrated_revision':result,
                'integrated_commits':[first,result],'reviewed_revision':result,
                'tested_revision':result,'base_revision':base,'records':{}}
            original_evidence={'schema_version':2,'owner_id':123,
                'origin':{'kind':'ordinary'},'baseline_revision':base,
                'integrations':[{'pull_request':9,'reviewed_revision':result,
                    'tested_revision':result,'base_revision':base,'records':{}}]}
            normalized_evidence={'schema_version':2,'owner_id':123,
                'origin':{'kind':'ordinary'},'baseline_revision':base,
                'integrations':[integration]}
            original={'id':90,'user':{'id':123},
                'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                    'repository':release.REPOSITORY,'pull_request':9,
                    'evidence':original_evidence},sort_keys=True)+'\n-->',
                'created_at':'2026-11-16T18:00:00Z','updated_at':'2026-11-16T18:00:00Z'}
            normalized={'id':91,'user':{'id':123},
                'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                    'repository':release.REPOSITORY,'pull_request':9,
                    'normalizes':{'ref':release.BASE+'/issues/comments/90',
                        'sha256':release.digest(release.canonical(original))},
                    'evidence':normalized_evidence},sort_keys=True)+'\n-->',
                'created_at':'2026-11-16T19:01:00Z','updated_at':'2026-11-16T19:01:00Z'}
            records={release.BASE:{'full_name':release.REPOSITORY,'owner':{'id':123}},
                release.BASE+'/issues/comments/90':original,
                release.BASE+'/issues/comments/91':normalized}
            def pages(path):
                if path.endswith('/pulls/9/commits'):return [{'sha':'original-first'},{'sha':'original-second'}]
                if path.endswith('/issues/9/comments'):return [original,normalized]
                if any('/commits/'+commit+'/pulls' in path for commit in (first,result)):return [pr]
                return []
            api=Mock();api.pages.side_effect=pages;api.record.side_effect=records.__getitem__
            api.request.return_value=records[release.BASE]
            with patch.object(release,'select_anchor',return_value=(base,'2026.11.15')):
                evidence=release.discover_evidence(root,api,result,result)
            self.assertEqual(len(evidence['integrations']),1)
            self.assertEqual(evidence['integrations'][0]['integrated_commits'],[first,result])
            release.verify_coverage(root,evidence,result,admitted=True)


class SigningContextTests(unittest.TestCase):
    def test_signing_requires_exact_trusted_dispatch(self):
        from unittest.mock import patch
        context={'repository':release.REPOSITORY,'builder_revision':'b'*40,'run_id':7,
                 'run_attempt':2,'qualification':{'run_attempt':2}}
        environment={'GITHUB_REPOSITORY':release.REPOSITORY,'GITHUB_SHA':'b'*40,
            'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'7','GITHUB_RUN_ATTEMPT':'2',
            'GITHUB_WORKFLOW_REF':release.REPOSITORY+'/.github/workflows/skill-release.yml@refs/heads/main'}
        with patch.dict(release.os.environ,environment,clear=True), patch.object(release,'git',return_value=('b'*40).encode()):
            release.verify_signing_context(Path('.'),context)
            for key in environment:
                with self.subTest(key=key), patch.dict(release.os.environ,{key:'wrong'}):
                    with self.assertRaises(release.ReleaseError):
                        release.verify_signing_context(Path('.'),context)
        with patch.dict(release.os.environ,{},clear=True):
            with self.assertRaises(release.ReleaseError):release.verify_signing_context(Path('.'),context)

    def test_rerun_signs_same_frozen_context_after_current_validation(self):
        from unittest.mock import patch
        import copy
        context={'repository':release.REPOSITORY,'builder_revision':'b'*40,'run_id':7,
                 'run_attempt':2,'qualification':{'run_attempt':2},'validation_attempt':3}
        frozen=copy.deepcopy(context)
        environment={'GITHUB_REPOSITORY':release.REPOSITORY,'GITHUB_SHA':'b'*40,
            'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'7','GITHUB_RUN_ATTEMPT':'3',
            'GITHUB_WORKFLOW_REF':release.REPOSITORY+'/.github/workflows/skill-release.yml@refs/heads/main'}
        with patch.dict(release.os.environ,environment,clear=True), patch.object(release,'git',return_value=('b'*40).encode()):
            release.verify_signing_context(Path('.'),context)
            self.assertEqual(context,frozen)
            for attempt in (1,2,4):
                with self.subTest(attempt=attempt), patch.dict(release.os.environ,{'GITHUB_RUN_ATTEMPT':str(attempt)}):
                    with self.assertRaises(release.ReleaseError):release.verify_signing_context(Path('.'),context)
            context['validation_attempt']=1
            with patch.dict(release.os.environ,{'GITHUB_RUN_ATTEMPT':'1'}):
                with self.assertRaises(release.ReleaseError):release.verify_signing_context(Path('.'),context)

class SuiteExecutionTests(unittest.TestCase):
    @staticmethod
    def fixture(revision='HEAD',root=None):
        import yaml
        root=Path(__file__).resolve().parents[1] if root is None else Path(root)
        workflow=release.git(root,'show',revision+':.github/workflows/ci.yml').decode()
        data=yaml.safe_load(workflow)
        job=next(j for j in data['jobs'].values() if j.get('name')=='Validate committed PR integration diff')
        steps=[s for s in job['steps'] if 'unittest discover' in s.get('run','')]
        records=[{'name':s['name'],'conclusion':'success'} for s in steps]
        logs=''.join('##[group]Run '+s['run'].strip()+'\n##[endgroup]\ntest_example (tests.Contract) ... ok\ntest_other (tests.Contract) ... ok\nRan 2 tests in 0.01s\n\nOK\n' for s in steps)
        return workflow,records,logs
    def test_committed_contract_accepts_six_and_historical_four(self):
        for revision,schema in [('HEAD',2),(release.BOOTSTRAP_BASELINE,1)]:
            workflow,steps,logs=self.fixture(revision)
            evidence_call('verify_ci_suites',logs,schema,steps,workflow)
    def test_unbound_or_unsuccessful_suite_execution_blocks(self):
        import copy
        workflow,steps,logs=self.fixture()
        groups=logs.split('##[group]')[1:]
        variants=[('repeated suite','##[group]'+groups[0]*6,steps),
                  ('filename mentions','\n'.join(release.SUITES)+'\n'+('Ran 2 tests\nOK\n'*6),steps),
                  ('missing step',logs,steps[:-1]),
                  ('aggregate only',logs.replace('Ran 2 tests in 0.01s','no execution')+'Ran 12 tests\nOK',steps),
                  ('skipped',logs.replace('OK','OK (skipped=1)',1),steps),
                  ('unrelated count',logs.replace('Ran 2 tests','Ran 20 tests',1),steps),
                  ('zero',logs.replace('Ran 2 tests','Ran 0 tests',1),steps),
                  ('failed',logs.replace('OK','FAILED (failures=1)',1),steps)]
        failed=copy.deepcopy(steps);failed[0]['conclusion']='failure'
        variants.append(('step failed',logs,failed))
        for label,text,records in variants:
            with self.subTest(label=label),self.assertRaises(release.ReleaseError):
                evidence_call('verify_ci_suites',text,2,records,workflow)
    def test_warning_interleaving_and_skip_words_are_successful_results(self):
        workflow,steps,logs=self.fixture()
        logs=logs.replace('test_example (tests.Contract) ... ok',
            "test_skipped_qualification_blocks (tests.Contract) ... /python/zipfile.py: UserWarning: Duplicate name: 'Skill.md'\n  return self._open_to_write(zinfo)\nok")
        evidence_call('verify_ci_suites',logs,2,steps,workflow)
    def test_diagnostic_does_not_hide_skipped_or_failed_status(self):
        workflow,steps,logs=self.fixture()
        for status in ["skipped 'unavailable'",'FAIL','ERROR','expected failure','unexpected success']:
            changed=logs.replace('test_example (tests.Contract) ... ok',
                'test_example (tests.Contract) ... warning: diagnostic\n'+status,1)
            with self.subTest(status=status),self.assertRaises(release.ReleaseError):
                evidence_call('verify_ci_suites',changed,2,steps,workflow)
    def test_workflow_command_drift_blocks(self):
        workflow,steps,logs=self.fixture()
        for changed in [workflow.replace('-p test_skill_distribution.py','-p unrelated.py'),
                        workflow.replace('run: python3 -m unittest discover -s tests -p test_skill_distribution.py -v',
                                         'if: false\n        run: python3 -m unittest discover -s tests -p test_skill_distribution.py -v')]:
            with self.assertRaises(release.ReleaseError):evidence_call('verify_ci_suites',logs,2,steps,changed)

class InstalledSkillTests(unittest.TestCase):
    def test_inspected_skill_bytes_and_compatibility(self):
        import tempfile,json
        from unittest.mock import Mock,patch
        names=['development-orchestrator','development-review']
        hashes={'SKILL.md':release.digest(b'current'),'agents/openai.yaml':release.digest(b'agent')}
        context={'verified_payload_identities':{names[0]:hashes,names[1]:{'SKILL.md':release.digest(b'other')}},
                 'source_revision':'a'*40,'policy_revision':'b'*40,'owner_id':123}
        api=Mock();api.releases.return_value=[{'tag_name':'2026.11.16','draft':False,'prerelease':False}]
        with tempfile.TemporaryDirectory() as temporary,patch.object(release,'verify_release',return_value=context):
            path=Path(temporary);(path/'agents').mkdir();(path/'SKILL.md').write_bytes(b'current');(path/'agents/openai.yaml').write_bytes(b'agent')
            self.assertEqual(release.resolve_task(api,root=path,skill=names[0],installed_path=path)['task_pin'],'2026.11.16')
            with patch.object(release,'GitHubAPI',return_value=api),patch('sys.stdout'):
                self.assertEqual(release.main(['resolve-task','--root',str(path),'--skill',names[0],'--installed-path',str(path)]),0)
            with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=path,skill=names[1],installed_path=path)
            with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=path,installed_payload=release.digest(release.canonical(hashes)))
            (path/'SKILL.md').unlink()
            with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=path,skill=names[0],installed_path=path)
            (path/'SKILL.md').write_bytes(b'older')
            inspected={**hashes,'SKILL.md':release.digest(b'older')}
            report={'gate':'compatibility','skill':names[0],'revision':'a'*40,'policy_revision':'b'*40,
                    'installed_payload':release.digest(release.canonical(inspected)),'installed_source':'c'*40,
                    'differences':'inspected older instructions','validation':'applicable checks passed','execution_id':'inspection','verdict':'pass'}
            record={'user':{'id':123},'body':'<!-- release-evidence\n'+json.dumps(report)+'\n-->'}
            api.record.return_value=record
            compatibility={'ref':'record','sha256':release.digest(release.canonical(record))}
            self.assertEqual(release.resolve_task(api,root=path,skill=names[0],installed_path=path,compatibility=compatibility)['task_pin'],'2026.11.16')
            report['skill']=names[1];record['body']='<!-- release-evidence\n'+json.dumps(report)+'\n-->'
            compatibility['sha256']=release.digest(release.canonical(record))
            with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=path,skill=names[0],installed_path=path,compatibility=compatibility)

class ManagedInstallationTests(unittest.TestCase):
    def test_real_installer_metadata_binds_payload_and_skill(self):
        import tempfile,json,copy
        from unittest.mock import Mock,patch
        import skill_distribution as package
        root=Path(__file__).resolve().parents[1]
        revision=release.git(root,'rev-parse','HEAD').decode().strip()
        policy=release.git(root,'log','--first-parent','-1','--format=%H',revision,'--','docs/PROCESS.md').decode().strip()
        context={'release_version':'2026.11.16','source_revision':revision,'policy_revision':policy,'builder_revision':revision}
        api=Mock();api.releases.return_value=[{'tag_name':'2026.11.16','draft':False,'prerelease':False}]
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);bundle=base/'bundle';stage=base/'stage';stage.mkdir()
            package.build_release_packages(root,bundle,context)
            package.initialize_staging_root(root,stage)
            package.stage_release_packages(root,bundle,stage,context)
            name='development-orchestrator';installed=stage/'.agents/skills'/name
            marker=installed/'.skill-distribution.json';original=marker.read_text();metadata=json.loads(original)
            verified={**context,'verified_payload_identities':{name:metadata['payload_sha256']}}
            with patch.object(release,'verify_release',return_value=verified):
                self.assertEqual(release.resolve_task(api,root=root,skill=name,installed_path=installed)['task_pin'],'2026.11.16')
                for key,value in [('skill_name','development-review'),('schema_version',2),('source_revision','invalid'),('policy_revision','invalid'),('archive_sha256','invalid'),('payload_sha256',{'../outside':'a'*64})]:
                    changed=copy.deepcopy(metadata);changed[key]=value;marker.write_text(json.dumps(changed))
                    with self.subTest(key=key),self.assertRaises(release.ReleaseError):
                        release.resolve_task(api,root=root,skill=name,installed_path=installed)
                marker.write_text('not JSON')
                with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=root,skill=name,installed_path=installed)
                marker.write_text(original)
                payload=installed/'SKILL.md';original_payload=payload.read_bytes();payload.write_bytes(b'drift')
                with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=root,skill=name,installed_path=installed)
                payload.write_bytes(original_payload)
                marker.write_text(original);(installed/'unrelated').write_text('extra')
                with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=root,skill=name,installed_path=installed)
                (installed/'unrelated').unlink();marker.unlink();marker.symlink_to(bundle/'release-manifest.json')
                with self.assertRaises(release.ReleaseError):release.resolve_task(api,root=root,skill=name,installed_path=installed)
