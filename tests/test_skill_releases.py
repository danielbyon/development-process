"""Release decisions must fail closed before remote writes."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_release as release

class ReleaseTests(unittest.TestCase):
    def test_pacific_original_date_and_suffix(self):
        self.assertEqual(release.allocate_version('2026-11-16T01:00:00Z', ['2026.11.15', '2026.11.15.2']), '2026.11.15.3')
    def test_invalid_calendar_and_suffix(self):
        for tag in ['2026.02.30', '2026.11.15.1', '2026.11.15.0', 'v2026.11.15']:
            with self.assertRaises(release.ReleaseError): release.version_key(tag)
    def test_boolean_is_not_review_evidence(self):
        with self.assertRaises(release.ReleaseError):
            release.verify_evidence({'independent_review': True}, lambda ref: {})
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
        self.assertEqual(len(release.verify_evidence(f['evidence'], records.__getitem__)),4)
    def test_tampered_record_blocks(self):
        f=self.fixture(); first=next(iter(f['records'].values())); first['body']='summary only'
        with self.assertRaises(release.ReleaseError): release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_self_review_blocks_even_with_recomputed_hash(self):
        f=self.fixture(); i=f['evidence']['integrations'][0]; i['author_execution_id']='review-execution'
        with self.assertRaises(release.ReleaseError): release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_wrong_inspection_candidate_blocks(self):
        f=self.fixture(); entry=f['evidence']['integrations'][0]['records']['chatgpt_inspection']
        actual=f['records'][entry['ref']]; actual['body']=actual['body'].replace('a'*40,'b'*40)
        entry['sha256']=release.digest(release.canonical(actual))
        with self.assertRaises(release.ReleaseError): release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_failed_ci_blocks_even_with_matching_digest(self):
        f=self.fixture(); entry=f['evidence']['integrations'][0]['records']['ci']
        actual=f['records'][entry['ref']]; actual['conclusion']='failure';entry['sha256']=release.digest(release.canonical(actual))
        with self.assertRaises(release.ReleaseError): release.verify_evidence(f['evidence'],f['records'].__getitem__)

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
        with self.assertRaises(release.ReleaseError):release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_missing_execution_export_blocks(self):
        f=self.fixture();entry=f['evidence']['integrations'][0]['records']['independent_review'];entry['execution']['sha256']='0'*64
        with self.assertRaisesRegex(release.ReleaseError,'Execution provenance'):
            release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_ci_head_can_differ_from_tested_merge(self):
        f=self.fixture();f['evidence']['integrations'][0]['tested_revision']='b'*40
        self.assertEqual(len(release.verify_evidence(f['evidence'],f['records'].__getitem__)),4)
    def test_owner_is_bound_to_repository_not_export(self):
        f=self.fixture();f['evidence']['owner_id']=999
        with self.assertRaisesRegex(release.ReleaseError,'repository owner'):
            release.verify_evidence(f['evidence'],f['records'].__getitem__)
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
        self.assertEqual(len(release.verify_evidence(evidence,f['records'].__getitem__)),4)
    def test_foreign_export_author_blocks(self):
        f,ref=self.legacy();f['records'][ref]['user']['id']=999
        with self.assertRaises(release.ReleaseError):release.load_evidence_export(ref,f['records'].__getitem__)
    def test_unverified_normalization_blocks(self):
        f,_=self.legacy()
        with self.assertRaises(release.ReleaseError):release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_normalized_claim_must_exist_in_execution(self):
        f,ref=self.legacy()
        evidence=release.load_evidence_export(ref,f['records'].__getitem__)
        evidence['integrations'][0]['records']['chatgpt_inspection']['normalized_report']['source_files']=['invented.py']
        with self.assertRaises(release.ReleaseError):release.verify_evidence(evidence,f['records'].__getitem__)

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
        self.assertEqual(release.verify_evidence(f['evidence'],f['records'].__getitem__),[])

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
            evidence={'baseline_revision':base,'baseline_admission':{'ref':'admitted'},'integrations':[
                {'integrated_revision':base,'reviewed_revision':base,'tested_revision':base},
                {'base_revision':base,'integrated_revision':result,'reviewed_revision':result,'tested_revision':result}]}
            with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):
                release.verify_coverage(root,evidence,result)
            evidence['integrations'][-1]['integrated_commits']=git('rev-list','--first-parent',base+'..'+result).split()[::-1]
            release.verify_coverage(root,evidence,result)
            evidence['integrations'].pop()
            with self.assertRaisesRegex(release.ReleaseError,'Uncovered'):release.verify_coverage(root,evidence,result)

class DiscoveryTests(unittest.TestCase):
    def test_discovery_reuses_verified_anchor_without_bootstrap_ancestry(self):
        from unittest.mock import Mock,patch
        api=Mock();api.request.return_value={'owner':{'id':123}}
        with patch.object(release,'select_anchor',return_value=('a'*40,'2026.11.15')),patch.object(release,'git',return_value=b''):
            evidence=release.discover_evidence(Path('.'),api,'b'*40,'c'*40)
        self.assertEqual(evidence['baseline_revision'],'a'*40)
        self.assertEqual(evidence['anchor_release'],'2026.11.15')
        self.assertEqual(evidence['integrations'],[])
    def test_prebaseline_without_anchor_requests_evidenced_export(self):
        from unittest.mock import Mock,patch
        with patch.object(release,'select_anchor',return_value=None),patch.object(release,'git',side_effect=release.ReleaseError('not ancestor')):
            with self.assertRaisesRegex(release.ReleaseError,'earlier baseline export'):
                release.discover_evidence(Path('.'),Mock(),'a'*40,'b'*40)
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
        self.assertEqual(len(release.verify_evidence(release.load_evidence_export(ref,f['records'].__getitem__),f['records'].__getitem__)),4)

class ExactExecutionTests(unittest.TestCase):
    fixture=EvidenceTests.fixture
    def test_reviewer_export_cannot_double_as_author(self):
        f=self.fixture();integration=f['evidence']['integrations'][0]
        integration['author_execution']=dict(integration['records']['independent_review']['execution'])
        integration['author_execution_id']='review'
        with self.assertRaises(release.ReleaseError):release.verify_evidence(f['evidence'],f['records'].__getitem__)
    def test_review_range_mismatch_rejected(self):
        import json
        f=self.fixture();entry=f['evidence']['integrations'][0]['records']['independent_review']['execution']
        record=f['records'][entry['ref']];envelope=json.loads(record['body'])
        envelope['reviewed_range']['base_revision']='c'*40;record['body']=json.dumps(envelope)
        entry['sha256']=release.digest(release.canonical(record))
        with self.assertRaises(release.ReleaseError):release.verify_evidence(f['evidence'],f['records'].__getitem__)

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
        api.ci_jobs.return_value=[{'id':5,'name':'Validate committed PR integration diff','conclusion':'success','steps':[{'conclusion':'success'}]}]
        api.job_log.return_value='\n'.join(['PR HEAD: '+revision,'Tested integration revision: '+revision,'Tested base revision: '+revision,*release.SUITES[:4],*['Ran 1 test']*4])
        api.pages.side_effect=lambda path: ([{'sha':revision}] if path.endswith('/commits') else [{'number':27,'merged_at':'date','base':{'ref':'main'},'merge_commit_sha':revision}])
        authority=release.EvidenceAuthority(api)
        snapshots=release.verify_evidence(f['evidence'],authority.record)
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
        with self.assertRaises(release.ReleaseError):release.verify_membership(api,integration)
    def test_schema_two_requires_all_six_ci_suites(self):
        logs='\n'.join([*release.SUITES[:4],*['Ran 1 test']*4])
        with self.assertRaises(release.ReleaseError):release.verify_ci_suites(logs,2)
        logs+='\n'+'\n'.join([*release.SUITES[4:],*['Ran 1 test']*2])
        release.verify_ci_suites(logs,2)
    def test_legacy_ci_has_explicit_four_suite_applicability(self):
        logs='\n'.join(['test_issue5_workflow.py',*release.SUITES[1:4],*['Ran 1 test']*4])
        release.verify_ci_suites(logs,1)
        with self.assertRaises(release.ReleaseError):release.verify_ci_suites(logs,3)

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
            pr={'number':9,'merge_commit_sha':result,'merged_at':'date','base':{'ref':'main'}}
            index={'integrated_revision':result,'reviewed_revision':result,'tested_revision':result,'base_revision':base}
            def pages(path):
                if path.endswith('/pulls/9/commits'):return [{'sha':'original-first'},{'sha':'original-second'}]
                if path.endswith('/issues/9/comments'):return [{'body':'<!-- release-readiness\n'+json.dumps(index)+'\n-->'}]
                if any('/commits/'+commit+'/pulls' in path for commit in (first,result)):return [pr]
                return []
            api=Mock();api.pages.side_effect=pages;api.request.return_value={'owner':{'id':123}}
            with patch.object(release,'select_anchor',return_value=(base,'2026.11.15')):
                evidence=release.discover_evidence(root,api,result,result)
            self.assertEqual(len(evidence['integrations']),1)
            self.assertEqual(evidence['integrations'][0]['integrated_commits'],[first,result])
            release.verify_coverage(root,evidence,result)


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
