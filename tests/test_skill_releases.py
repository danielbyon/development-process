"""Release decisions must fail closed before remote writes."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_release as release
from release_evidence import baseline, common, integrations, legacy, qualification, records
EVIDENCE_MODULES=(baseline,integrations,legacy,qualification,records)

def evidence_operation(name):
    for module in EVIDENCE_MODULES:
        if hasattr(module,name): return getattr(module,name)
    raise AttributeError(f'No evidence operation named {name}')

def evidence_call(name,*args,**kwargs):
    return evidence_operation(name)(*args,**kwargs)

def committed_transform_version(root, source_revision):
    import json
    import skill_distribution as package

    manifest = json.loads(release.git(
        root, 'show', f'{source_revision}:{package.MANIFEST_PATH.as_posix()}'))
    return package.release_transform_version(manifest)






class ReleaseTests(unittest.TestCase):
    def test_pacific_original_date_and_suffix(self):
        self.assertEqual(release.allocate_version('2026-11-16T01:00:00Z', ['2026.11.15', '2026.11.15.2']), '2026.11.15.3')
    def test_invalid_calendar_and_suffix(self):
        for tag in ['2026.02.30', '2026.11.15.1', '2026.11.15.0', 'v2026.11.15']:
            with self.assertRaises(release.ReleaseError): release.version_key(tag)
    def test_existing_pin_is_not_reselected(self):
        for pin in ('a' * 40, '2026.11.18'):
            with self.subTest(pin=pin):
                self.assertEqual(release.resolve_task(None, existing_pin=pin), {'task_pin': pin})
    def test_unpinned_task_requires_an_explicit_reference(self):
        class API:
            release_calls = 0
            def releases(self):
                self.release_calls += 1
                return []
        api = API()
        with self.assertRaisesRegex(release.ReleaseError, 'EXPLICIT_TASK_PIN_REQUIRED'):
            release.resolve_task(api)
        self.assertEqual(api.release_calls, 0)
    def test_skipped_qualification_blocks(self):
        result = unittest.TestResult(); result.testsRun=1; result.skipped=[('test','reason')]
        with self.assertRaises(release.ReleaseError): release.require_tests(result)
    def test_failed_and_empty_qualification_block(self):
        failed=unittest.TestResult();failed.testsRun=1;failed.failures=[('test','failure')]
        with self.assertRaises(release.ReleaseError): release.require_tests(failed)
        empty=unittest.TestResult()
        with self.assertRaises(release.ReleaseError): release.require_tests(empty)
    def test_successful_qualification_passes(self):
        result=unittest.TestResult();result.testsRun=1
        self.assertIsNone(release.require_tests(result))
    def test_all_nonpassing_result_categories_block_qualification(self):
        for category in ('failures','errors','skipped','expectedFailures','unexpectedSuccesses'):
            with self.subTest(category=category):
                result=unittest.TestResult();result.testsRun=1
                setattr(result,category,[('test','not successful')])
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
            evidence_call('verify_live_integrations',None,{'integrations':[{}]})

    def test_in_progress_ci_job_is_missing_evidence(self):
        from release_evidence.common import MissingEvidenceError
        from release_evidence.integrations import _required_ci_job
        class API:
            def ci_jobs(self,*args):
                return [{'name':'Validate committed PR integration diff',
                         'status':'in_progress','conclusion':None,'steps':[]}]
        with self.assertRaises(MissingEvidenceError):
            _required_ci_job(API(),{'id':1},1,completion_required=True,
                job_error='Required completed candidate CI job unavailable',
                steps_error='Candidate CI contains failed or skipped steps')

    def test_ambiguous_required_ci_jobs_are_failures_not_absence(self):
        from release_evidence.integrations import _required_ci_job
        job={'name':'Validate committed PR integration diff',
             'status':'completed','conclusion':'success','steps':[{'conclusion':'success'}]}
        class API:
            def ci_jobs(self,*args): return [job,dict(job)]
        with self.assertRaises(release.ReleaseError) as result:
            _required_ci_job(API(),{'id':1},1,completion_required=True,
                job_error='Required completed candidate CI job unavailable',
                steps_error='Candidate CI contains failed or skipped steps')

    def test_cancelled_ci_job_is_a_failure_not_missing_evidence(self):
        from release_evidence.integrations import _required_ci_job
        job={'name':'Validate committed PR integration diff','status':'cancelled',
             'conclusion':'cancelled','steps':[]}
        class API:
            def ci_jobs(self,*args): return [job]
        with self.assertRaisesRegex(release.ReleaseError,'did not complete') as result:
            _required_ci_job(API(),{'id':1},1,completion_required=True,
                job_error='Required completed candidate CI job unavailable',
                steps_error='Candidate CI contains failed or skipped steps')

    def test_ci_summary_success_without_jobs_does_not_pass(self):
        integration={'pull_request':1,'reviewed_revision':'a'*40,'integrated_revision':'b'*40,
                     'records':{'ci':{'ref':'ci','run_attempt':1}}}
        class API:
            def record(self,ref):
                if ref=='ci': return {'id':1,'repository':{'full_name':release.REPOSITORY},'event':'pull_request'}
                return {'merged':True,'base':{'ref':'main'},'head':{'sha':'a'*40},'merge_commit_sha':'b'*40}
            def ci_jobs(self,*args): return []
        with self.assertRaisesRegex(release.ReleaseError,'Required CI job'):
            evidence_call('verify_live_integrations',API(),{'integrations':[integration]})

class StateMachineTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.tmp=tempfile.TemporaryDirectory(); self.directory=Path(self.tmp.name)
        for n in range(8): (self.directory/str(n)).write_bytes(str(n).encode())
        self.context={'release_context_schema_version':1,'repository':release.REPOSITORY,
            'release_version':'2026.11.16','source_revision':'a'*40,'builder_revision':'a'*40,
            'owner_id':123,'run_id':7,'run_attempt':1,'validation_attempt':1,
            'created_at':'2026-11-16T01:00:00Z',
            'qualification':{'run_attempt':1,'suites':[{'suite':s,'tests':1} for s in release.SUITES]},
            'current_validation':{'run_attempt':1,'suites':[{'suite':s,'tests':1} for s in release.SUITES]},
            'qualified_artifacts':release.artifact_hashes(self.directory)}
        self.patches=[patch.object(release,'verify_dispatch_environment'),
            patch.object(release,'check_settings'),patch.object(release,'verify_bundle'),
            patch.object(release,'git',return_value=b'a'*40)]
        for p in self.patches: p.start()
        from unittest.mock import Mock
        self.api=Mock()
        self.api.releases.return_value=[];self.api.tags.return_value=[]
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()
    def body(self): return 'Release context: '+release.digest(release.canonical({k:v for k,v in self.context.items() if k not in ('qualified_artifacts','validation_attempt','current_validation')}))
    def stable_draft(self):
        return {'id':1,'tag_name':self.context['release_version'],
                'name':self.context['release_version'],'body':self.body(),
                'draft':True,'prerelease':False,
                'assets':[{'id':i+1,'name':name} for i,name in enumerate(sorted(self.context['qualified_artifacts']))]}
    def configure_stable_draft(self):
        draft=self.stable_draft()
        self.api.releases.return_value=[draft]
        self.api.asset.side_effect=lambda asset:(self.directory/asset['name']).read_bytes()
        self.api.tags.return_value=[{'ref':'refs/tags/'+self.context['release_version'],
            'object':{'sha':self.context['source_revision'],'type':'commit'}}]
        self.api.release.return_value=draft
        return draft
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
    def test_changed_final_draft_ownership_blocks_publication(self):
        self.configure_stable_draft()
        changed=self.stable_draft();changed['body']='foreign owner body'
        self.api.release.return_value=changed
        with self.assertRaisesRegex(release.ReleaseError,'ownership'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_final_draft_published_early_blocks_publication(self):
        self.configure_stable_draft()
        changed=self.stable_draft();changed['draft']=False
        self.api.release.return_value=changed
        with self.assertRaisesRegex(release.ReleaseError,'draft'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_changed_final_asset_bytes_block_publication(self):
        self.configure_stable_draft()
        calls=0
        def asset_bytes(asset):
            nonlocal calls
            calls+=1
            if calls==9: return b'changed after upload verification'
            return (self.directory/asset['name']).read_bytes()
        self.api.asset.side_effect=asset_bytes
        with self.assertRaisesRegex(release.ReleaseError,'asset bytes'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_changed_final_tag_target_blocks_publication(self):
        self.configure_stable_draft()
        valid={'ref':'refs/tags/'+self.context['release_version'],
               'object':{'sha':self.context['source_revision'],'type':'commit'}}
        changed={'ref':valid['ref'],'object':{'sha':'b'*40,'type':'commit'}}
        self.api.tags.side_effect=[[valid],[changed]]
        with self.assertRaisesRegex(release.ReleaseError,'Tag target'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_final_release_identity_and_asset_set_must_match(self):
        changes=(('tag_name','2026.11.17'),('name','unexpected release'),
                 ('prerelease',True),('assets','missing'),('assets','extra'))
        for field,value in changes:
            with self.subTest(field=field):
                self.api.reset_mock()
                self.configure_stable_draft()
                changed=self.stable_draft()
                if field=='assets':
                    if value=='missing': changed['assets']=changed['assets'][:-1]
                    else: changed['assets'].append({'id':99,'name':'unexpected.zip'})
                else: changed[field]=value
                self.api.release.return_value=changed
                with self.assertRaises(release.ReleaseError):
                    release.publish(Path('.'),self.api,self.context,self.directory)
                self.api.publish.assert_not_called()
    def test_missing_final_release_state_blocks_publication(self):
        self.configure_stable_draft()
        self.api.release.return_value=None
        with self.assertRaises(release.ReleaseError):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_final_release_id_must_match_fetched_draft(self):
        self.configure_stable_draft()
        changed=self.stable_draft();changed['id']=2
        self.api.release.return_value=changed
        with self.assertRaisesRegex(release.ReleaseError,'release ID'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.publish.assert_not_called()
    def test_stable_owned_draft_is_published_and_verified(self):
        from unittest.mock import patch
        draft=self.configure_stable_draft()
        published={**draft,'draft':False,'immutable':True}
        self.api.release.side_effect=[draft,published]
        self.api.settings.return_value={
            'repository':{'full_name':release.REPOSITORY,'default_branch':'main',
                          'owner':{'login':'danielbyon','id':self.context['owner_id']}},
            'immutability':{'enabled':True}}
        self.api.run.return_value={
            'id':self.context['run_id'],'event':'workflow_dispatch','head_branch':'main',
            'head_sha':self.context['source_revision'],
            'actor':{'id':self.context['owner_id']},
            'triggering_actor':{'id':self.context['owner_id']},
            'run_attempt':self.context['run_attempt'],'created_at':self.context['created_at'],
            'path':'.github/workflows/skill-release.yml'}
        self.api.verify_main_ancestry.return_value=self.context['source_revision']
        self.patches[1].stop()
        settings=patch.object(release,'check_settings',wraps=release.check_settings)
        settings.start();self.patches[1]=settings
        result=release.publish(Path('.'),self.api,self.context,self.directory)
        self.assertEqual(result,published)
        self.api.release.assert_any_call(1)
        self.api.publish.assert_called_once_with(1)
        self.assertEqual(self.api.settings.call_count,2)
        self.assertEqual(self.api.verify_main_ancestry.call_count,2)
        calls=[call[0] for call in self.api.mock_calls]
        publication=calls.index('publish')
        main_checks=[i for i,name in enumerate(calls) if name=='verify_main_ancestry']
        release_reads=[i for i,name in enumerate(calls) if name=='release']
        self.assertLess(release_reads[0],main_checks[-1])
        self.assertLess(main_checks[-1],publication)
        self.assertEqual(calls[publication-1],'verify_main_ancestry')
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
        with self.assertRaisesRegex(release.ReleaseError,'current-attempt validation'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called()
    def test_missing_current_attempt_validation_blocks_publication(self):
        del self.context['current_validation']
        with self.assertRaisesRegex(release.ReleaseError,'current-attempt validation'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.verify_qualification_attestation.assert_not_called()
        self.api.create_draft.assert_not_called()
    def test_stale_or_failed_current_attempt_validation_blocks_publication(self):
        from copy import deepcopy
        valid=self.context['current_validation']
        failures=(
            {**valid,'run_attempt':0},
            {**valid,'suites':[{'suite':s,'tests':0} for s in release.SUITES]},
        )
        for evidence in failures:
            with self.subTest(evidence=evidence):
                self.context['current_validation']=deepcopy(evidence)
                with self.assertRaisesRegex(release.ReleaseError,'current-attempt validation'):
                    release.publish(Path('.'),self.api,self.context,self.directory)
                self.api.verify_qualification_attestation.assert_not_called()
                self.api.create_draft.assert_not_called()
        self.context['current_validation']=valid
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
    def test_matching_partial_draft_uploads_only_missing_assets(self):
        from unittest.mock import patch
        existing={'name':'0','id':0}
        draft={'id':1,'tag_name':'2026.11.16','body':self.body(),
               'draft':True,'assets':[existing]}
        self.api.releases.return_value=[draft]
        self.api.asset.side_effect=lambda asset:(self.directory/asset['name']).read_bytes()
        self.api.release.return_value=draft
        with patch.object(release,'verify_remote',return_value=draft):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called()
        self.assertEqual(self.api.upload.call_count,7)
        self.assertEqual([call.args[1].name for call in self.api.upload.call_args_list],
                         [str(value) for value in range(1,8)])
        self.api.publish.assert_called_once_with(1)
    def test_successful_draft_upload_tag_publish_order(self):
        from unittest.mock import patch
        events=[]
        draft={'id':1,'tag_name':'2026.11.16','name':'2026.11.16',
               'body':self.body(),'draft':True,'prerelease':False,'assets':[]}
        self.api.verify_qualification_attestation.side_effect=lambda *args: events.append('attestation')
        self.api.create_draft.side_effect=lambda *args: events.append('draft') or draft
        self.api.upload.side_effect=lambda *args:events.append('upload')
        self.api.create_tag.side_effect=lambda *args:events.append('tag')
        self.api.publish.side_effect=lambda *args:events.append('publish')
        self.api.release.return_value=draft
        with patch.object(release,'verify_remote',return_value=draft):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.assertEqual(events,['attestation','draft']+['upload']*8+['tag','publish'])

    def test_main_membership_failure_before_first_mutation_blocks_release(self):
        from unittest.mock import patch
        self.patches[1].stop()
        settings=patch.object(release,'check_settings',side_effect=release.APIError('source removed from main'))
        settings.start();self.patches[1]=settings
        with self.assertRaisesRegex(release.APIError,'removed from main'):
            release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.create_draft.assert_not_called();self.api.publish.assert_not_called()

    def test_main_membership_is_rechecked_before_final_publication(self):
        from unittest.mock import patch
        draft={'id':1,'tag_name':'2026.11.16','name':'2026.11.16',
               'body':self.body(),'draft':True,'prerelease':False,'assets':[]}
        self.api.create_draft.return_value=draft
        self.api.release.return_value=draft
        self.patches[1].stop()
        settings=patch.object(release,'check_settings',side_effect=[None,None,None,
            release.APIError('source removed from main')])
        settings.start();self.patches[1]=settings
        with patch.object(release,'verify_remote',return_value=draft):
            with self.assertRaisesRegex(release.APIError,'removed from main'):
                release.publish(Path('.'),self.api,self.context,self.directory)
        self.api.release.assert_called_once_with(1)
        self.api.publish.assert_not_called()

class DispatchTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.api=Mock()
        self.context={'release_context_schema_version':1,'repository':release.REPOSITORY,
            'owner_id':123,
            'source_revision':'b'*40,'builder_revision':'b'*40,
            'run_id':4,'run_attempt':1,'created_at':'2026-11-16T01:00:00Z'}
        self.settings={'repository':{'full_name':release.REPOSITORY,'default_branch':'main','owner':{'login':'danielbyon','id':123}},
            'immutability':{'enabled':True}}
        self.run={'id':4,'event':'workflow_dispatch','head_branch':'main','head_sha':'b'*40,'actor':{'id':123},'triggering_actor':{'id':123},
            'run_attempt':1,'created_at':self.context['created_at'],'path':'.github/workflows/skill-release.yml'}
        self.api.settings.return_value=self.settings;self.api.run.return_value=self.run
        self.api.verify_main_ancestry.return_value='c'*40
    def test_valid_dispatch(self):
        self.assertEqual(release.check_settings(self.api,self.context),self.settings)
    def test_foreign_rerun_actor_blocks(self):
        self.run['triggering_actor']['id']=999
        with self.assertRaisesRegex(release.ReleaseError,'Owner-only'): release.check_settings(self.api,self.context)
    def test_immutability_disabled_blocks(self):
        self.settings['immutability']['enabled']=False
        with self.assertRaisesRegex(release.ReleaseError,'Immutable'): release.check_settings(self.api,self.context)
    def test_wrong_repository_or_default_branch_blocks(self):
        self.settings['repository']['full_name']='danielbyon/other'
        with self.assertRaisesRegex(release.ReleaseError,'Repository/default branch'):
            release.check_settings(self.api,self.context)
        self.settings['repository']['full_name']=release.REPOSITORY
        self.settings['repository']['default_branch']='trunk'
        with self.assertRaisesRegex(release.ReleaseError,'Repository/default branch'):
            release.check_settings(self.api,self.context)
    def test_non_dispatch_event_or_wrong_branch_blocks(self):
        self.run['event']='push'
        with self.assertRaisesRegex(release.ReleaseError,'Trusted main dispatch'):
            release.check_settings(self.api,self.context)
        self.run['event']='workflow_dispatch'
        self.run['head_branch']='feature'
        with self.assertRaisesRegex(release.ReleaseError,'Trusted main dispatch'):
            release.check_settings(self.api,self.context)
    def test_untrusted_workflow_blocks(self):
        self.run['path']='.github/workflows/ci.yml'
        with self.assertRaisesRegex(release.ReleaseError,'Unexpected dispatch'): release.check_settings(self.api,self.context)
    def test_workflow_run_path_must_be_the_main_release_workflow(self):
        self.run['path']='.github/workflows/skill-release.yml@refs/heads/attacker'
        with self.assertRaisesRegex(release.ReleaseError,'Unexpected dispatch'): release.check_settings(self.api,self.context)
    def test_wrong_workflow_run_id_blocks(self):
        self.run['id']=5
        with self.assertRaisesRegex(release.ReleaseError,'Trusted main dispatch'): release.check_settings(self.api,self.context)
    def test_wrong_run_head_blocks_even_when_source_tree_could_match(self):
        self.run['head_sha']='d'*40
        with self.assertRaisesRegex(release.ReleaseError,'source|builder|revision'):
            release.check_settings(self.api,self.context)
    def test_source_and_builder_must_be_the_same_dispatch_commit(self):
        self.context['source_revision']='a'*40
        with self.assertRaisesRegex(release.ReleaseError,'source|builder|revision'):
            release.check_settings(self.api,self.context)
    def test_commit_must_remain_in_authenticated_main_history(self):
        self.api.verify_main_ancestry.side_effect=release.APIError('source is not in main history')
        with self.assertRaisesRegex(release.APIError,'main history'):
            release.check_settings(self.api,self.context)
    def test_release_settings_do_not_require_development_governance_inventory(self):
        self.assertEqual(release.check_settings(self.api,self.context),self.settings)
        self.api.settings.assert_called_once()


class PreflightRetryTests(unittest.TestCase):
    def test_full_rerun_reuses_frozen_source_and_release_identity(self):
        from copy import deepcopy
        from unittest.mock import Mock, patch
        root=Path(__file__).resolve().parents[1]
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        policy=release.git(root,'log','--first-parent','-1','--format=%H',source,
                           '--','docs/PROCESS.md').decode().strip()
        transform_version=committed_transform_version(root,source)
        created='2026-11-17T09:00:00Z'
        original={'release_context_schema_version':1,'repository':release.REPOSITORY,
            'source_revision':source,'builder_revision':source,'policy_revision':policy,
            'owner_id':123,'run_id':41,'run_attempt':1,'validation_attempt':1,
            'created_at':created,'transform_version':transform_version,'supersedes':'',
            'correction_reason':'','release_version':'2026.11.17'}
        api=Mock()
        api.run.return_value={'id':41,'event':'workflow_dispatch','head_branch':'main',
            'head_sha':source,'actor':{'id':123},'triggering_actor':{'id':123},
            'run_attempt':2,'created_at':created,
            'path':'.github/workflows/skill-release.yml@refs/heads/main'}
        api.settings.return_value={'repository':{'full_name':release.REPOSITORY,
            'default_branch':'main','owner':{'login':'danielbyon','id':123}},
            'immutability':{'enabled':True}}
        api.original_context.return_value=deepcopy(original)
        environment={'GITHUB_REPOSITORY':release.REPOSITORY,'GITHUB_SHA':source,
            'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'41','GITHUB_RUN_ATTEMPT':'2',
            'GITHUB_ACTOR':'danielbyon','GITHUB_TRIGGERING_ACTOR':'danielbyon',
            'GITHUB_WORKFLOW_REF':release.REPOSITORY+
                '/.github/workflows/skill-release.yml@refs/heads/main'}
        with patch.dict(release.os.environ,environment,clear=True):
            context=release.preflight(root,api,41,2)
        self.assertEqual(context['source_revision'],source)
        self.assertEqual(context['builder_revision'],source)
        self.assertEqual(context['release_version'],'2026.11.17')
        self.assertEqual(context['run_attempt'],1)
        self.assertEqual(context['validation_attempt'],2)
        self.assertEqual(context['transform_version'],transform_version)
        api.releases.assert_not_called()
        api.tags.assert_not_called()

    def test_retry_without_original_context_blocks_existing_remote_state(self):
        from unittest.mock import Mock, patch
        root=Path(__file__).resolve().parents[1]
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        api=Mock()
        api.run.return_value={'id':41,'event':'workflow_dispatch','head_branch':'main',
            'head_sha':source,'actor':{'id':123},'triggering_actor':{'id':123},
            'run_attempt':2,'created_at':'2026-11-17T09:00:00Z',
            'path':'.github/workflows/skill-release.yml@refs/heads/main'}
        api.settings.return_value={'repository':{'full_name':release.REPOSITORY,
            'default_branch':'main','owner':{'login':'danielbyon','id':123}},
            'immutability':{'enabled':True}}
        api.original_context.return_value=None
        api.releases.return_value=[{'tag_name':'2026.11.17','draft':True}]
        api.tags.return_value=[{'ref':'refs/tags/2026.11.17'}]
        environment={'GITHUB_REPOSITORY':release.REPOSITORY,'GITHUB_SHA':source,
            'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'41','GITHUB_RUN_ATTEMPT':'2',
            'GITHUB_ACTOR':'danielbyon','GITHUB_TRIGGERING_ACTOR':'danielbyon',
            'GITHUB_WORKFLOW_REF':release.REPOSITORY+
                '/.github/workflows/skill-release.yml@refs/heads/main'}
        with patch.dict(release.os.environ,environment,clear=True):
            with self.assertRaisesRegex(release.ReleaseError,'(?i)retry.*context|context.*retry'):
                release.preflight(root,api,41,2)
        api.releases.assert_not_called()
        api.tags.assert_not_called()

    def test_retry_rejects_frozen_legacy_evidence_fields(self):
        from copy import deepcopy
        from unittest.mock import Mock, patch
        root=Path(__file__).resolve().parents[1]
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        policy=release.git(root,'log','--first-parent','-1','--format=%H',source,
                           '--','docs/PROCESS.md').decode().strip()
        transform_version=committed_transform_version(root,source)
        created='2026-11-17T09:00:00Z'
        original={'release_context_schema_version':1,'repository':release.REPOSITORY,
            'source_revision':source,'builder_revision':source,'policy_revision':policy,
            'owner_id':123,'run_id':41,'run_attempt':1,'validation_attempt':1,
            'created_at':created,'transform_version':transform_version,'supersedes':'',
            'correction_reason':'','release_version':'2026.11.17','evidence':{}}
        api=Mock()
        api.run.return_value={'id':41,'event':'workflow_dispatch','head_branch':'main',
            'head_sha':source,'actor':{'id':123},'triggering_actor':{'id':123},
            'run_attempt':2,'created_at':created,
            'path':'.github/workflows/skill-release.yml@refs/heads/main'}
        api.settings.return_value={'repository':{'full_name':release.REPOSITORY,
            'default_branch':'main','owner':{'login':'danielbyon','id':123}},
            'immutability':{'enabled':True}}
        api.original_context.return_value=deepcopy(original)
        environment={'GITHUB_REPOSITORY':release.REPOSITORY,'GITHUB_SHA':source,
            'GITHUB_REF':'refs/heads/main','GITHUB_RUN_ID':'41','GITHUB_RUN_ATTEMPT':'2',
            'GITHUB_ACTOR':'danielbyon','GITHUB_TRIGGERING_ACTOR':'danielbyon',
            'GITHUB_WORKFLOW_REF':release.REPOSITORY+
                '/.github/workflows/skill-release.yml@refs/heads/main'}
        with patch.dict(release.os.environ,environment,clear=True):
            with self.assertRaisesRegex(release.ReleaseError,'Legacy evidence fields'):
                release.preflight(root,api,41,2)

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
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        policy=release.git(root,'log','--first-parent','-1','--format=%H',source,
                           '--','docs/PROCESS.md').decode().strip()
        context={'release_context_schema_version':1,'repository':release.REPOSITORY,
            'release_version':'2026.11.16','source_revision':source,
            'builder_revision':source,'policy_revision':policy,'owner_id':123,
            'run_id':7,'run_attempt':1,'created_at':'2026-11-16T01:00:00Z',
            'transform_version':committed_transform_version(root,source)}
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
        original={'run_id':5,'run_attempt':1,'qualification':{'run_attempt':1},
                  'current_validation':{'run_attempt':1}}
        retried={**original,'validation_attempt':2,
                 'current_validation':{'run_attempt':2}}
        def identity(c):return release.digest(release.canonical({k:v for k,v in c.items() if k not in ('qualified_artifacts','validation_attempt','current_validation')}))
        self.assertEqual(identity(original),identity(retried))
    def test_reconstructed_but_unqualified_release_is_rejected(self):
        import json
        import tempfile
        import skill_distribution as packaging
        from unittest.mock import Mock
        root=Path(__file__).resolve().parents[1]
        source=release.git(root,'rev-parse','HEAD').decode().strip()
        policy=release.git(root,'log','--first-parent','-1','--format=%H',source,
                           '--','docs/PROCESS.md').decode().strip()
        context={'repository':release.REPOSITORY,'release_version':'2026.11.16',
            'source_revision':source,'builder_revision':source,
            'policy_revision':policy,'owner_id':123,
            'transform_version':committed_transform_version(root,source)}
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'bundle';packaging.build_release_packages(root,directory,context)
            assets=[{'name':p.name,'id':n} for n,p in enumerate(directory.iterdir())]
            payload={a['id']:(directory/a['name']).read_bytes() for a in assets}
            api=Mock();api.releases.return_value=[{'tag_name':context['release_version'],'assets':assets}]
            api.asset.side_effect=lambda a:payload[a['id']]
            api.record.return_value={'owner':{'id':123}}
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
        release.verify_historical_anchor(Path('.'),api,normalized)
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
                evidence_call('verify_coverage',root,evidence,result,admitted=True)
            evidence['integrations'][-1]['integrated_commits']=git('rev-list','--first-parent',base+'..'+result).split()[::-1]
            evidence_call('verify_coverage',root,evidence,result,admitted=True)
            evidence['integrations'].pop()
            with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
                evidence_call('verify_coverage',root,evidence,result,admitted=True)

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
        original={'id':10,'user':{'id':owner},'issue_url':release.BASE+f'/issues/{number}',
            'body':'<!-- release-readiness\n'+json.dumps({'schema_version':2,
                'repository':release.REPOSITORY,'pull_request':number,
                'evidence':original_evidence},sort_keys=True)+'\n-->',
            'created_at':'2026-11-16T18:00:00Z','updated_at':'2026-11-16T18:00:00Z'}
        normalized_evidence=copy.deepcopy(original_evidence)
        normalized_evidence['integrations'][0]['integrated_revision']='c'*40
        normalized_evidence['integrations'][0]['integrated_commits']=['c'*40]
        normalized={'id':11,'user':{'id':owner},'issue_url':release.BASE+f'/issues/{number}',
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
        authority=release.FrozenHistoricalEvidenceAuthority(api)
        snapshots=release.verify_frozen_release_evidence(f['evidence'],authority.record)
        evidence_call('verify_live_integrations',authority,f['evidence'],root)
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
            package_id = next(asset['id'] for asset in assets if asset['name'].endswith('.zip'))
            original_package = payload[package_id]
            payload[package_id] = b'corrupt package'
            with self.assertRaisesRegex(release.ReleaseError, 'RELEASE_VERIFICATION_FAILED'):
                release._verify_selected_release(root, api, context['release_version'])
            payload[package_id] = original_package
            manifest_id = next(asset['id'] for asset in assets
                               if asset['name'] == 'release-manifest.json')
            original_manifest = payload[manifest_id]
            for malformed_manifest in (b'{', b'[]', b'{"context": []}'):
                with self.subTest(manifest=malformed_manifest):
                    payload[manifest_id] = malformed_manifest
                    with self.assertRaisesRegex(
                        release.ReleaseError, 'RELEASE_VERIFICATION_FAILED: Malformed release manifest'
                    ):
                        release._verify_selected_release(root, api, context['release_version'])
            payload[manifest_id] = original_manifest
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

class SigningContextTests(unittest.TestCase):
    def test_signing_requires_exact_trusted_dispatch(self):
        from unittest.mock import patch
        suites=[{'suite':name,'tests':1} for name in release.SUITES]
        context={'release_context_schema_version':1,'repository':release.REPOSITORY,
                 'source_revision':'b'*40,'builder_revision':'b'*40,'owner_id':123,
                 'run_id':7,'run_attempt':2,'created_at':'2026-11-16T01:00:00Z',
                 'qualification':{'run_attempt':2,'suites':suites},
                 'current_validation':{'run_attempt':2,'suites':suites}}
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
        suites=[{'suite':name,'tests':1} for name in release.SUITES]
        context={'release_context_schema_version':1,'repository':release.REPOSITORY,
                 'source_revision':'b'*40,'builder_revision':'b'*40,'owner_id':123,
                 'run_id':7,'created_at':'2026-11-16T01:00:00Z',
                 'run_attempt':1,'qualification':{'run_attempt':1,'suites':suites},
                 'current_validation':{'run_attempt':3,'suites':suites},'validation_attempt':3}
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
        workflow=(root/'.github/workflows/ci.yml').read_text() if revision=='HEAD' else \
            release.git(root,'show',revision+':.github/workflows/ci.yml').decode()
        data=yaml.safe_load(workflow)
        job=next(j for j in data['jobs'].values() if j.get('name')=='Validate committed PR integration diff')
        suite_steps=[s for s in job['steps'] if 'unittest discover' in s.get('run','')]
        other_steps=[s for s in job['steps'] if 'unittest discover' not in s.get('run','')]
        steps=suite_steps+other_steps
        records=[{'name':s['name'],'status':'completed','conclusion':'success'} for s in steps]
        logs=''.join('##[group]Run '+s['run'].strip()+'\n##[endgroup]\ntest_example (tests.Contract) ... ok\ntest_other (tests.Contract) ... ok\nRan 2 tests in 0.01s\n\nOK\n' for s in suite_steps)
        return workflow,records,logs
    def test_python_safe_path_prevents_a_root_unittest_shadow(self):
        import os,subprocess,tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'unittest.py').write_text(
                "print('test_forged (tests.Contract) ... ok')\n"
                "print('Ran 1 test in 0.01s')\nprint('OK')\n")
            tests=root/'tests';tests.mkdir()
            (tests/'test_probe.py').write_text(
                'import unittest\nclass Probe(unittest.TestCase):\n'
                ' def test_real_runner(self): self.fail("real test executed")\n')
            command=[sys.executable,'-m','unittest','discover','-s','tests',
                     '-p','test_probe.py','-v']
            environment=os.environ.copy();environment.pop('PYTHONPATH',None)
            environment.pop('PYTHONSAFEPATH',None)
            forged=subprocess.run(command,cwd=root,env=environment,
                capture_output=True,text=True)
            self.assertEqual(forged.returncode,0)
            self.assertIn('test_forged',forged.stdout+forged.stderr)
            safe_environment=dict(environment,PYTHONSAFEPATH='1')
            actual=subprocess.run(command,cwd=root,env=safe_environment,
                capture_output=True,text=True)
            self.assertNotEqual(actual.returncode,0)
            self.assertNotIn('test_forged',actual.stdout+actual.stderr)
            self.assertIn('real test executed',actual.stdout+actual.stderr)
    def test_schema_v2_requires_python_safe_path_for_each_suite(self):
        import yaml
        workflow,steps,logs=self.fixture()
        data=yaml.safe_load(workflow)
        job=next(j for j in data['jobs'].values()
            if j.get('name')=='Validate committed PR integration diff')
        suite_steps=[s for s in job['steps'] if 'unittest discover' in s.get('run','')]
        for step in suite_steps:
            step['env']={'PYTHONSAFEPATH':'1'}
        safe_workflow=yaml.safe_dump(data,sort_keys=False)
        evidence_call('verify_ci_suites',logs,2,steps,safe_workflow)
        for step in suite_steps:
            step.pop('env')
        unsafe_workflow=yaml.safe_dump(data,sort_keys=False)
        with self.assertRaisesRegex(release.ReleaseError,'PYTHONSAFEPATH'):
            evidence_call('verify_ci_suites',logs,2,steps,unsafe_workflow)
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
            ('missing step',logs,steps[1:]),
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

class RuntimeResolutionTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock, patch

        self.api = Mock()
        self.api.releases.return_value = [
            {'tag_name': '2026.11.20', 'draft': False, 'prerelease': False}
        ]
        self.context = {"release_version": "2026.11.20"}
        self.verify_release = self.enterContext(
            patch.object(release, "verify_release", side_effect=AssertionError(
                "ordinary task resolution must not run the full release audit"
            ))
        )
        self.enterContext(patch.object(release, "GitHubAPI", return_value=self.api))

    def run_cli(self, *arguments):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = release.main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_explicit_release_audit_remains_available(self):
        import json

        self.verify_release.side_effect = None
        self.verify_release.return_value = self.context
        status, output, error = self.run_cli("verify-release")
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(json.loads(output), self.context)
        self.assertNotIn("task_pin", json.loads(output))
        self.assertEqual(self.verify_release.call_args.args[-1], "2026.11.20")

    def test_release_only_keeps_explicit_historical_tag(self):
        self.verify_release.side_effect = None
        self.verify_release.return_value = self.context
        status, _, error = self.run_cli("verify-release", "--tag", "2026.11.18.2")
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(self.verify_release.call_args.args[-1], "2026.11.18.2")

    def test_unpinned_task_admission_fails_without_release_discovery(self):
        with self.assertRaisesRegex(release.ReleaseError, "EXPLICIT_TASK_PIN_REQUIRED"):
            release.resolve_task(self.api)
        for name in (
            "releases", "release", "release_by_tag", "tags", "asset", "record",
            "request", "run", "run_attempt", "verify_attestation", "verify_qualification_attestation",
        ):
            getattr(self.api, name).assert_not_called()


class ExplicitNativeResolutionTests(unittest.TestCase):
    def setUp(self):
        import json
        from unittest.mock import Mock
        import skill_distribution as package

        self.tag = '2026.11.25'
        self.context = {
            'release_context_schema_version': 1,
            'repository': release.REPOSITORY,
            'release_version': self.tag,
            'source_revision': 'a' * 40,
            'policy_revision': 'b' * 40,
            'builder_revision': 'a' * 40,
            'owner_id': 123,
            'run_id': 77,
            'run_attempt': 1,
            'created_at': '2026-11-25T09:00:00Z',
            'transform_version': 2,
        }
        self.api = Mock()
        self.api.base = '/repos/' + release.REPOSITORY
        skill_names = tuple(package.SKILL_NAMES)
        self.payload_bytes = {
            'SKILL.md': b'delegation-executor instructions',
            'agents/openai.yaml': b'delegation-executor metadata',
        }
        self.payloads = {
            member: release.digest(content)
            for member, content in self.payload_bytes.items()
        }
        asset_bytes = {}
        asset_hashes = {}
        for skill in skill_names:
            members = {
                f'{skill}/SKILL.md': release.digest((skill + ' instructions').encode()),
                f'{skill}/agents/openai.yaml': release.digest((skill + ' metadata').encode()),
            }
            sidecar = {
                'schema_version': 2,
                'skill_name': skill,
                'release_version': self.tag,
                'source_revision': self.context['source_revision'],
                'policy_revision': self.context['policy_revision'],
                'builder_revision': self.context['builder_revision'],
                'transform_version': 2,
                'source_files': {
                    f'{skill}/SKILL.md': f'skills/{skill}/SKILL.md',
                    f'{skill}/agents/openai.yaml': f'skills/{skill}/agents/openai.yaml',
                },
                'payload_sha256': members,
                'archive_sha256': 'd' * 64,
            }
            sidecar_name = f'{skill}.provenance.json'
            sidecar_bytes = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            asset_bytes[sidecar_name] = sidecar_bytes
            asset_hashes[sidecar_name] = release.digest(sidecar_bytes)
            asset_hashes[f'{skill}.zip'] = 'd' * 64

        self.asset_bytes = asset_bytes
        self.asset_names = sorted([
            *(f'{skill}.zip' for skill in skill_names),
            *(f'{skill}.provenance.json' for skill in skill_names),
            'release-manifest.json', 'SHA256SUMS',
        ])
        manifest = {
            'schema_version': 2,
            'context': dict(self.context),
            'assets': self.asset_names,
            'asset_sha256': asset_hashes,
        }
        self.manifest = manifest
        self._write_manifest()
        self.release_detail = {
            'id': 20,
            'tag_name': self.tag,
            'name': self.tag,
            'body': 'Release context: ' + release.digest(
                release.canonical(release.frozen_release_context(self.context))
            ),
            'draft': False,
            'prerelease': False,
            'immutable': True,
            'assets': [],
        }
        self._refresh_release_assets()
        self.api.release_by_tag.return_value = self.release_detail
        self.api.tags.return_value = [{
            'ref': 'refs/tags/' + self.tag,
            'object': {'sha': self.context['source_revision'], 'type': 'commit'},
        }]
        self.api.asset.side_effect = lambda asset: self.asset_bytes[asset['name']]

    def _write_manifest(self):
        import json

        self.asset_bytes['release-manifest.json'] = (
            json.dumps(self.manifest, sort_keys=True, indent=2) + '\n'
        ).encode()

    def _refresh_release_assets(self):
        asset_digests = self.manifest['asset_sha256']
        manifest_digest = release.digest(self.asset_bytes['release-manifest.json'])
        digests = {
            'release-manifest.json': manifest_digest,
            **asset_digests,
            'SHA256SUMS': 'e' * 64,
        }
        self.release_detail['assets'] = [
            {
                'id': index + 1,
                'name': name,
                'digest': 'sha256:' + digests[name],
            }
            for index, name in enumerate(self.asset_names)
        ]

    def _set_tag(self, tag):
        import json

        self.tag = tag
        self.context['release_version'] = tag
        self.manifest['context']['release_version'] = tag
        for name, content in list(self.asset_bytes.items()):
            if not name.endswith('.provenance.json'):
                continue
            sidecar = json.loads(content)
            sidecar['release_version'] = tag
            encoded = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            self.asset_bytes[name] = encoded
            self.manifest['asset_sha256'][name] = release.digest(encoded)
        self._write_manifest()
        self.release_detail['tag_name'] = tag
        self.release_detail['name'] = tag
        self.release_detail['body'] = 'Release context: ' + release.digest(
            release.canonical(release.frozen_release_context(self.manifest['context']))
        )
        self.api.tags.return_value = [{
            'ref': 'refs/tags/' + tag,
            'object': {'sha': self.context['source_revision'], 'type': 'commit'},
        }]
        self._refresh_release_assets()

    def _install(self, directory, *, payload_bytes=None, marker=False):
        import json
        from pathlib import Path

        installed = self.payload_bytes if payload_bytes is None else payload_bytes
        for member, content in installed.items():
            path = Path(directory) / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if marker:
            metadata = {
                'schema_version': 1,
                'skill_name': 'delegation-executor',
                'policy_revision': self.context['policy_revision'],
                'source_revision': self.context['source_revision'],
                'archive_sha256': 'd' * 64,
                'payload_sha256': {member: release.digest(data) for member, data in installed.items()},
            }
            (Path(directory) / '.skill-distribution.json').write_text(json.dumps(metadata))

    def _resolve(self, directory, **options):
        return release.resolve_task(
            self.api,
            task_pin=self.tag,
            source_revision=self.context['source_revision'],
            policy_revision=self.context['policy_revision'],
            builder_revision=self.context['builder_revision'],
            skill='delegation-executor',
            installed_path=directory,
            **options,
        )

    def _run_cli(self, *arguments):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(release, 'GitHubAPI', return_value=self.api), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            status = release.main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def _assert_no_qualification_calls(self):
        for name in ('releases', 'release', 'run', 'run_attempt', 'record',
                     'request', 'verify_attestation', 'verify_qualification_attestation'):
            getattr(self.api, name).assert_not_called()

    def test_native_success_uses_only_the_selected_calver_and_authenticated_assets(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            result = self._resolve(directory)

        self.assertEqual(result['task_pin'], self.tag)
        self.assertTrue(result['local_installation_verified'])
        self.assertEqual(result['provenance']['source_revision'], self.context['source_revision'])
        self.assertEqual(
            result['provenance']['verified_payload_identities']['delegation-executor'],
            self.payloads,
        )
        self.api.release_by_tag.assert_called_once_with(self.tag)
        self.assertEqual(
            [call.args[0]['name'] for call in self.api.asset.call_args_list],
            ['release-manifest.json', 'delegation-executor.provenance.json'],
        )
        self.api.tags.assert_called_once()
        self._assert_no_qualification_calls()

    def test_exact_installation_rejects_well_formed_wrong_marker_identity(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory, marker=True)
            marker_path = Path(directory) / '.skill-distribution.json'
            original = json.loads(marker_path.read_text())
            self.assertTrue(self._resolve(directory)['local_installation_verified'])
            wrong_values = {
                'source_revision': 'f' * 40,
                'policy_revision': 'e' * 40,
                'archive_sha256': 'c' * 64,
            }
            for key, value in wrong_values.items():
                marker = {**original, key: value}
                marker_path.write_text(json.dumps(marker))
                with self.subTest(key=key), self.assertRaisesRegex(
                    release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'
                ):
                    self._resolve(directory)

    def test_sequenced_calver_uses_exact_release_by_tag_endpoint(self):
        import tempfile

        tag = self.tag + '.2'
        self._set_tag(tag)
        self.api.request.return_value = self.release_detail
        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            result = self._resolve(directory)
        self.assertEqual(result['task_pin'], tag)
        self.api.request.assert_called_once_with(
            'GET', self.api.base + '/releases/tags/' + tag
        )
        self.api.release_by_tag.assert_not_called()

    def test_existing_pin_is_exact_passthrough_and_rejects_native_options(self):
        import json
        from unittest.mock import patch

        pin = 'c' * 40
        with patch.object(release, '_verify_local_installation') as inspect:
            self.assertEqual(release.resolve_task(self.api, existing_pin=pin), {'task_pin': pin})
            inspect.assert_not_called()
        self._assert_no_qualification_calls()
        self.api.release_by_tag.assert_not_called()
        status, output, error = self._run_cli('resolve-task', '--existing-pin', pin)
        self.assertEqual((status, error), (0, ''))
        self.assertEqual(json.loads(output), {'task_pin': pin})
        with self.assertRaisesRegex(release.ReleaseError, 'EXISTING_PIN_INCOMPATIBLE_OPTIONS'):
            release.resolve_task(self.api, existing_pin=pin, skill='delegation-executor')
        status, output, error = self._run_cli(
            'resolve-task', '--existing-pin', pin, '--task-pin', self.tag
        )
        self.assertEqual(status, 1)
        self.assertEqual(output, '')
        self.assertIn('EXISTING_PIN_INCOMPATIBLE_OPTIONS', error)
        self.api.release_by_tag.assert_not_called()

    def test_cli_accepts_explicit_native_identity(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            status, output, error = self._run_cli(
                'resolve-task', '--task-pin', self.tag,
                '--source-revision', self.context['source_revision'],
                '--policy-revision', self.context['policy_revision'],
                '--builder-revision', self.context['builder_revision'],
                '--skill', 'delegation-executor', '--installed-path', directory,
            )
        self.assertEqual((status, error), (0, ''))
        self.assertEqual(json.loads(output)['task_pin'], self.tag)

    def test_cli_rejects_incomplete_native_options_before_remote_calls(self):
        status, output, error = self._run_cli(
            'resolve-task', '--skill', 'delegation-executor'
        )
        self.assertEqual(status, 1)
        self.assertEqual(output, '')
        self.assertIn('NATIVE_VERIFICATION_ARGUMENTS_REQUIRED', error)
        self.api.release_by_tag.assert_not_called()
        self.api.tags.assert_not_called()
        self.api.asset.assert_not_called()

    def test_cli_does_not_accept_caller_supplied_payload_hashes(self):
        import io
        from unittest.mock import patch

        with patch.object(release, 'GitHubAPI', return_value=self.api) as api_factory, \
                patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                release.main([
                    'resolve-task', '--task-pin', self.tag,
                    '--installed-payload', 'a' * 64,
                ])
        api_factory.assert_not_called()
        self.api.release_by_tag.assert_not_called()

    def test_native_arguments_are_validated_before_remote_calls(self):
        import tempfile

        cases = (
            ({'task_pin': self.tag}, 'NATIVE_VERIFICATION_ARGUMENTS_REQUIRED'),
            ({'task_pin': self.tag, 'source_revision': 'bad'}, 'INVALID_RECORDED_IDENTITY'),
            ({'task_pin': self.tag, 'skill': 'development-review'}, 'NATIVE_VERIFICATION_ARGUMENTS_REQUIRED'),
            ({'task_pin': self.tag, 'source_revision': self.context['source_revision'],
              'policy_revision': self.context['policy_revision'],
              'builder_revision': self.context['builder_revision'],
              'skill': 'development-review', 'installed_path': '.'},
             'NATIVE_VERIFICATION_SKILL_UNSUPPORTED'),
            ({'task_pin': self.tag, 'source_revision': self.context['source_revision'],
              'policy_revision': self.context['policy_revision'],
              'builder_revision': self.context['builder_revision'],
              'skill': 'delegation-executor'},
             'NATIVE_VERIFICATION_ARGUMENTS_REQUIRED'),
            ({'task_pin': '2026.02.30'}, 'INVALID_CALVER_TASK_PIN'),
        )
        for options, expected in cases:
            with self.subTest(options=options), self.assertRaisesRegex(release.ReleaseError, expected):
                release.resolve_task(self.api, **options)
            self.api.release_by_tag.assert_not_called()
            self.api.tags.assert_not_called()
            self.api.asset.assert_not_called()
            self.api.request.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(release.ReleaseError, 'INVALID_COMPATIBILITY_EVIDENCE'):
                release.resolve_task(
                    self.api,
                    task_pin=self.tag,
                    source_revision=self.context['source_revision'],
                    policy_revision=self.context['policy_revision'],
                    builder_revision=self.context['builder_revision'],
                    skill='delegation-executor',
                    installed_path=directory,
                    compatibility={'ref': 'comment', 'sha256': 'invalid'},
                )
        self.api.release_by_tag.assert_not_called()
        self.api.request.assert_not_called()

    def test_release_calver_immutability_and_tag_target_are_required(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            self.release_detail['tag_name'] = '2026.11.24'
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)
            self.release_detail['tag_name'] = self.tag
            self.release_detail['immutable'] = False
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)
            self.release_detail['immutable'] = True
            self.api.tags.return_value[0]['object']['sha'] = 'f' * 40
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)
        self.api.release_by_tag.assert_called_with(self.tag)

    def test_downloaded_manifest_and_sidecar_must_match_github_asset_digests(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            original = self.asset_bytes['release-manifest.json']
            self.asset_bytes['release-manifest.json'] = original + b' '
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)
            self.asset_bytes['release-manifest.json'] = original
            self.asset_bytes['delegation-executor.provenance.json'] += b' '
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_manifest_must_bind_the_executor_sidecar_and_recorded_identity(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            self.manifest['asset_sha256']['delegation-executor.provenance.json'] = '0' * 64
            self._write_manifest()
            self._refresh_release_assets()
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

            self.manifest['asset_sha256']['delegation-executor.provenance.json'] = release.digest(
                self.asset_bytes['delegation-executor.provenance.json']
            )
            self.manifest['context']['policy_revision'] = 'f' * 40
            self._write_manifest()
            self._refresh_release_assets()
            self.release_detail['body'] = 'Release context: ' + release.digest(
                release.canonical(release.frozen_release_context(self.manifest['context']))
            )
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_executor_sidecar_identity_must_match_the_manifest_context(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            name = 'delegation-executor.provenance.json'
            sidecar = json.loads(self.asset_bytes[name])
            sidecar['source_revision'] = 'f' * 40
            sidecar_bytes = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            self.asset_bytes[name] = sidecar_bytes
            self.manifest['asset_sha256'][name] = release.digest(sidecar_bytes)
            self._write_manifest()
            self._refresh_release_assets()
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_pinned_manifest_rejects_attempt_local_context_fields(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            self.manifest['context']['validation_attempt'] = 2
            self._write_manifest()
            self._refresh_release_assets()
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_executor_sidecar_transform_must_match_the_manifest(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            name = 'delegation-executor.provenance.json'
            sidecar = json.loads(self.asset_bytes[name])
            sidecar['transform_version'] = 1
            sidecar_bytes = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            self.asset_bytes[name] = sidecar_bytes
            self.manifest['asset_sha256'][name] = release.digest(sidecar_bytes)
            self._write_manifest()
            self._refresh_release_assets()
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_executor_sidecar_transform_version_must_be_an_integer(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            self.context['transform_version'] = 1
            self.manifest['context']['transform_version'] = 1
            self.release_detail['body'] = 'Release context: ' + release.digest(
                release.canonical(release.frozen_release_context(self.manifest['context']))
            )
            name = 'delegation-executor.provenance.json'
            sidecar = json.loads(self.asset_bytes[name])
            sidecar['transform_version'] = True
            sidecar_bytes = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            self.asset_bytes[name] = sidecar_bytes
            self.manifest['asset_sha256'][name] = release.digest(sidecar_bytes)
            self._write_manifest()
            self._refresh_release_assets()

            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

    def test_missing_executor_payload_hashes_are_unavailable(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            name = 'delegation-executor.provenance.json'
            sidecar = json.loads(self.asset_bytes[name])
            del sidecar['payload_sha256']
            sidecar_bytes = (json.dumps(sidecar, sort_keys=True, indent=2) + '\n').encode()
            self.asset_bytes[name] = sidecar_bytes
            self.manifest['asset_sha256'][name] = release.digest(sidecar_bytes)
            self._write_manifest()
            self._refresh_release_assets()
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_UNAVAILABLE'):
                self._resolve(directory)

    def test_missing_sidecar_digest_is_unavailable(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            sidecar = next(
                asset for asset in self.release_detail['assets']
                if asset['name'] == 'delegation-executor.provenance.json'
            )
            sidecar['digest'] = None
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_UNAVAILABLE'):
                self._resolve(directory)
            self._refresh_release_assets()
            self.release_detail['assets'] = [
                asset for asset in self.release_detail['assets']
                if asset['name'] != 'delegation-executor.provenance.json'
            ]
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_UNAVAILABLE'):
                self._resolve(directory)

    def test_changed_payload_needs_authenticated_compatibility_evidence(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            changed = {**self.payload_bytes, 'SKILL.md': b'older instructions'}
            self._install(directory, payload_bytes=changed, marker=True)
            marker_path = Path(directory) / '.skill-distribution.json'
            marker = json.loads(marker_path.read_text())
            marker.update(
                source_revision='c' * 40,
                policy_revision='d' * 40,
                archive_sha256='e' * 64,
            )
            marker_path.write_text(json.dumps(marker))
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory)

            inspected = {member: release.digest(content) for member, content in changed.items()}
            report = {
                'gate': 'compatibility',
                'skill': 'delegation-executor',
                'revision': self.context['source_revision'],
                'policy_revision': self.context['policy_revision'],
                'installed_payload': release.digest(release.canonical(inspected)),
                'installed_source': 'f' * 40,
                'differences': 'older executor instructions',
                'validation': 'compatibility checks passed',
                'execution_id': 'inspection',
                'verdict': 'pass',
            }
            record = {
                'user': {'id': self.context['owner_id']},
                'body': '<!-- release-evidence\n' + json.dumps(report) + '\n-->',
            }
            self.api.record.return_value = record
            evidence = {'ref': 'issue-comment', 'sha256': release.digest(release.canonical(record))}
            with self.assertRaisesRegex(release.ReleaseError, 'LOCAL_INSTALLATION_MISMATCH'):
                self._resolve(directory, compatibility=evidence)

            report['installed_source'] = marker['source_revision']
            record['body'] = '<!-- release-evidence\n' + json.dumps(report) + '\n-->'
            evidence['sha256'] = release.digest(release.canonical(record))
            result = self._resolve(directory, compatibility=evidence)
            self.assertTrue(result['local_installation_verified'])
            self.assertEqual(report['revision'], self.context['source_revision'])
            self.assertEqual(report['policy_revision'], self.context['policy_revision'])

    def test_historical_sha_pin_uses_manual_fallback_without_release_lookup(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self._install(directory)
            with self.assertRaisesRegex(
                release.ReleaseError,
                'LOCAL_INSTALLATION_UNAVAILABLE.*manual execution',
            ):
                release.resolve_task(
                    self.api,
                    task_pin='c' * 40,
                    source_revision=self.context['source_revision'],
                    policy_revision=self.context['policy_revision'],
                    builder_revision=self.context['builder_revision'],
                    skill='delegation-executor',
                    installed_path=directory,
                    compatibility={'ref': 'comment', 'sha256': 'c' * 64},
                )
        self.api.release_by_tag.assert_not_called()
        self.api.tags.assert_not_called()
        self.api.asset.assert_not_called()
        self.api.record.assert_not_called()


class InstalledSkillTests(unittest.TestCase):
    def test_inspected_skill_bytes_and_compatibility(self):
        import json
        import tempfile
        from unittest.mock import Mock

        skill = "delegation-executor"
        expected = {
            "SKILL.md": release.digest(b"current"),
            "agents/openai.yaml": release.digest(b"agent"),
        }
        context = {
            "source_revision": "a" * 40,
            "policy_revision": "b" * 40,
            "owner_id": 123,
        }
        api = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "agents").mkdir()
            (path / "SKILL.md").write_bytes(b"current")
            (path / "agents/openai.yaml").write_bytes(b"agent")
            release._verify_local_installation(api, context, skill, expected, path, None)

            (path / "SKILL.md").unlink()
            with self.assertRaisesRegex(release.ReleaseError, "Installed Skill file missing"):
                release._verify_local_installation(api, context, skill, expected, path, None)
            (path / "SKILL.md").write_bytes(b"older")
            with self.assertRaisesRegex(release.ReleaseError, "compatibility unverified"):
                release._verify_local_installation(api, context, skill, expected, path, None)

            inspected = {**expected, "SKILL.md": release.digest(b"older")}
            report = {
                "gate": "compatibility",
                "skill": skill,
                "revision": context["source_revision"],
                "policy_revision": context["policy_revision"],
                "installed_payload": release.digest(release.canonical(inspected)),
                "installed_source": "c" * 40,
                "differences": "inspected older instructions",
                "validation": "applicable checks passed",
                "execution_id": "inspection",
                "verdict": "pass",
            }
            record = {
                "user": {"id": context["owner_id"]},
                "body": "<!-- release-evidence\n" + json.dumps(report) + "\n-->",
            }
            api.record.return_value = record
            compatibility = {
                "ref": "record",
                "sha256": release.digest(release.canonical(record)),
            }
            release._verify_local_installation(api, context, skill, expected, path, compatibility)

            report["skill"] = "development-review"
            record["body"] = "<!-- release-evidence\n" + json.dumps(report) + "\n-->"
            compatibility["sha256"] = release.digest(release.canonical(record))
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, path, compatibility)

            record["body"] = "<!-- release-evidence\n[]\n-->"
            compatibility["sha256"] = release.digest(release.canonical(record))
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, path, compatibility)


class ManagedInstallationTests(unittest.TestCase):
    def test_real_installer_metadata_binds_payload_and_skill(self):
        import copy
        import json
        import tempfile
        import skill_distribution as package

        root = Path(__file__).resolve().parents[1]
        revision = release.git(root, "rev-parse", "HEAD").decode().strip()
        policy = release.git(
            root, "log", "--first-parent", "-1", "--format=%H", revision,
            "--", "docs/PROCESS.md",
        ).decode().strip()
        transform_version = committed_transform_version(root, revision)
        context = {
            "release_version": "2026.11.16",
            "source_revision": revision,
            "policy_revision": policy,
            "owner_id": 123,
            "transform_version": transform_version,
        }
        api = type("API", (), {"record": lambda self, ref: None})()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bundle = base / "bundle"
            stage = base / "stage"
            stage.mkdir()
            package.build_release_packages(root, bundle, {
                "release_version": "2026.11.16",
                "source_revision": revision,
                "policy_revision": policy,
                "builder_revision": revision,
                "transform_version": transform_version,
            })
            package.initialize_staging_root(root, stage)
            package.stage_release_packages(root, bundle, stage, {
                "release_version": "2026.11.16",
                "source_revision": revision,
                "policy_revision": policy,
                "builder_revision": revision,
                "transform_version": transform_version,
            })
            skill = "delegation-executor"
            installed = stage / ".agents/skills" / skill
            marker = installed / ".skill-distribution.json"
            original = marker.read_text()
            metadata = json.loads(original)
            expected = metadata["payload_sha256"]
            archive_sha256 = release.digest((bundle / "delegation-executor.zip").read_bytes())
            release._verify_local_installation(
                api, context, skill, expected, installed, None,
                archive_sha256=archive_sha256,
            )

            for key, value in (
                ("skill_name", "development-review"),
                ("schema_version", 2),
                ("source_revision", "invalid"),
                ("policy_revision", "invalid"),
                ("archive_sha256", "invalid"),
                ("payload_sha256", {"../outside": "a" * 64}),
            ):
                changed = copy.deepcopy(metadata)
                changed[key] = value
                marker.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                    release._verify_local_installation(api, context, skill, expected, installed, None)

            marker.write_text("not JSON")
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, installed, None)
            marker.write_text(original)
            payload = installed / "SKILL.md"
            original_payload = payload.read_bytes()
            payload.write_bytes(b"drift")
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, installed, None)
            payload.write_bytes(original_payload)
            (installed / "unrelated").write_text("extra")
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, installed, None)
            (installed / "unrelated").unlink()
            marker.unlink()
            marker.symlink_to(bundle / "release-manifest.json")
            with self.assertRaises(release.ReleaseError):
                release._verify_local_installation(api, context, skill, expected, installed, None)


class CLIEntrypointTests(unittest.TestCase):
    def test_obsolete_receipt_and_baseline_commands_are_not_exposed(self):
        import io
        from unittest.mock import patch
        output=io.StringIO()
        with patch('sys.stdout',output), self.assertRaises(SystemExit) as result:
            release.main(['--help'])
        self.assertEqual(result.exception.code,0)
        for command in ('audit','capture-execution','owner-receipt',
                        'prepare-index','admit-baseline'):
            with self.subTest(command=command):
                self.assertNotIn(command,output.getvalue())
        for command in ('preflight','qualify','verify-bundle','publish',
                        'verify-release','resolve-task'):
            self.assertIn(command,output.getvalue())

    def test_resolve_task_help_describes_the_native_contract(self):
        import io
        from unittest.mock import patch

        output = io.StringIO()
        with patch('sys.stdout', output), self.assertRaises(SystemExit) as result:
            release.main(['resolve-task', '--help'])
        self.assertEqual(result.exception.code, 0)
        for option in ('--existing-pin', '--task-pin', '--source-revision',
                       '--policy-revision', '--builder-revision', '--installed-path'):
            self.assertIn(option, output.getvalue())
