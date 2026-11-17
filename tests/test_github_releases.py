"""The GitHub adapter preserves remote failures and uses explicit API methods."""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import github_releases as github

class AdapterTests(unittest.TestCase):
    def test_api_failure_is_not_absence(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['gh'], stderr=b'Forbidden')):
            with self.assertRaises(github.APIError): github.GitHubAPI().request('GET', '/repos/x/y')
    def test_explicit_read_method(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([],0,b'{}',b'')) as run:
            github.GitHubAPI().request('GET','/user')
            self.assertIn('GET',run.call_args.args[0])
    def test_audit_uses_only_the_explicit_token(self):
        import os
        with patch.dict(os.environ,{'GH_TOKEN':'ambient-token','GITHUB_TOKEN':'other-token'}):
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{}',b'')) as run:
                api=github.GitHubAPI.for_read_only_audit('selected-token')
                api.request('GET','/user')
        self.assertEqual(run.call_args.kwargs['env']['GH_TOKEN'],'selected-token')
        self.assertNotIn('GITHUB_TOKEN',run.call_args.kwargs['env'])
    def test_audit_transport_refuses_every_write(self):
        api=github.GitHubAPI.for_read_only_audit('selected-token')
        with patch('subprocess.run') as run:
            with self.assertRaisesRegex(github.APIError,'read-only'):
                api.request('POST','/repos/danielbyon/development-process/releases',{})
        run.assert_not_called()
        with self.assertRaisesRegex(github.APIError,'read-only'):
            api.upload(1,Path('asset'))
    def test_binary_assets_request_octet_stream(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([],0,b'PK',b'')) as run:
            self.assertEqual(github.GitHubAPI().asset({'id':2}),b'PK')
            self.assertIn('Accept: application/octet-stream',run.call_args.args[0])
    def test_foreign_evidence_path_rejected(self):
        with self.assertRaises(github.APIError): github.GitHubAPI().record('https://attacker.test/report')
    def test_pagination_does_not_truncate_full_page(self):
        api=github.GitHubAPI()
        with patch.object(api,'request',side_effect=[[{}]*100,[{'id':101}]]) as request:
            self.assertEqual(len(api.pages('/example')),101)
            self.assertIn('page=2',request.call_args.args[1])
    def test_admin_token_scoped_to_settings(self):
        import os
        api=github.GitHubAPI()
        with patch.dict(os.environ,{'RELEASE_ADMIN_READ_TOKEN':'admin-secret'}):
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{}',b'')) as run:
                api.request('GET',api.base+'/immutable-releases')
                self.assertEqual(run.call_args.kwargs['env']['GH_TOKEN'],'admin-secret')
    def test_admin_token_not_used_for_publication(self):
        import os
        with patch.dict(os.environ,{'RELEASE_ADMIN_READ_TOKEN':'admin-secret','GH_TOKEN':'contents-token'}):
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{}',b'')) as run:
                github.GitHubAPI().request('POST','/repos/danielbyon/development-process/releases',{})
                self.assertEqual(run.call_args.kwargs['env']['GH_TOKEN'],'contents-token')
    def test_artifact_object_pagination(self):
        api=github.GitHubAPI()
        with patch.object(api,'request',return_value={'artifacts':[{'id':1}]}):
            self.assertEqual(api.pages('/artifacts'),[{'id':1}])
    def test_raw_logs_allow_escape_sequences(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([],0,b'log',b'')) as run:
            github.GitHubAPI().job_log(4)
            self.assertIn('--allow-escape-sequences',run.call_args.args[0])
    def test_historical_token_requires_separate_authorization(self):
        import os
        with patch.dict(os.environ,{'RELEASE_WORKFLOW_WRITE_TOKEN':'token','RELEASE_WORKFLOW_WRITE_AUTHORIZED':'false'}):
            with self.assertRaises(github.APIError): github.GitHubAPI().authorize_historical_publication()
    def test_original_context_verifies_artifact_archive_and_assets(self):
        import io,json,zipfile,hashlib
        context={'run_id':3,'qualified_artifacts':{'payload':hashlib.sha256(b'payload').hexdigest()}}
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('release-context.json',json.dumps(context));archive.writestr('payload',b'payload')
        payload=buffer.getvalue();api=github.GitHubAPI()
        artifact={'name':'release-bundle-1','id':4,'expired':False,'digest':'sha256:'+hashlib.sha256(payload).hexdigest()}
        with patch.object(api,'pages',return_value=[artifact]),patch.object(api,'request',return_value=payload):
            self.assertEqual(api.original_context(3),context)
        artifact['digest']='sha256:wrong'
        with patch.object(api,'pages',return_value=[artifact]),patch.object(api,'request',return_value=payload):
            with self.assertRaises(github.APIError):api.original_context(3)
    def test_expired_frozen_context_blocks_instead_of_renumbering(self):
        api=github.GitHubAPI()
        with patch.object(api,'pages',return_value=[{'name':'release-bundle-1','expired':True}]):
            with self.assertRaisesRegex(github.APIError,'expired'):api.original_context(3)

class QualificationAttestationTests(unittest.TestCase):
    def test_attestation_pins_builder_workflow_and_run(self):
        import json, tempfile, hashlib
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        directory=Path(temporary.name)
        (directory/'release-manifest.json').write_bytes(b'manifest')
        api=github.GitHubAPI()
        context={'builder_revision':'b'*40,'run_id':7,'qualification':{'run_attempt':2}}
        result=[{'verificationResult':{'statement':{'subject':[{'name':'release-manifest.json','digest':{'sha256':hashlib.sha256(b'manifest').hexdigest()}}], 'predicateType':'https://slsa.dev/provenance/v1',
            'predicate':{'runDetails':{'builder':{'id':'https://github.com/danielbyon/development-process/.github/workflows/skill-release.yml@refs/heads/main'},'metadata':{'invocationId':'https://github.com/danielbyon/development-process/actions/runs/7/attempts/2'}}}}}}]
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')) as run:
            api.verify_qualification_attestation(directory,context)
            command=run.call_args.args[0]
            self.assertIn('--signer-digest',command);self.assertIn('b'*40,command)
            self.assertIn('--deny-self-hosted-runners',command)
            for flag,value in {
                '--repo':'danielbyon/development-process',
                '--signer-workflow':'danielbyon/development-process/.github/workflows/skill-release.yml',
                '--signer-digest':'b'*40,'--source-digest':'b'*40,
                '--source-ref':'refs/heads/main','--predicate-type':'https://slsa.dev/provenance/v1',
            }.items():
                self.assertEqual(command[command.index(flag)+1],value)
        metadata=result[0]['verificationResult']['statement']['predicate']['runDetails']['metadata']
        for invocation,accepted in (
            ('https://github.com/danielbyon/development-process/actions/runs/7/attempts/3',True),
            ('https://github.com/danielbyon/development-process/actions/runs/8/attempts/3',False),
            ('https://github.com/danielbyon/development-process/actions/runs/7/attempts/1',False),
        ):
            metadata['invocationId']=invocation
            with self.subTest(invocation=invocation), patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')):
                if accepted: api.verify_qualification_attestation(directory,context)
                else:
                    with self.assertRaises(github.APIError):api.verify_qualification_attestation(directory,context)
        metadata['invocationId']='https://github.com/danielbyon/development-process/actions/runs/7/attempts/2'
        result[0]['verificationResult']['statement']['predicate']['runDetails']['builder']['id']='wrong'
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')):
            with self.assertRaises(github.APIError):api.verify_qualification_attestation(directory,context)
        result[0]['verificationResult']['statement']['predicate']['runDetails']['builder']['id']='https://github.com/danielbyon/development-process/.github/workflows/skill-release.yml@refs/heads/main'
        result[0]['verificationResult']['statement']['predicate']['runDetails']['metadata']['invocationId']='wrong'
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')):
            with self.assertRaises(github.APIError):api.verify_qualification_attestation(directory,context)

    def test_verification_failures_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            (directory/'release-manifest.json').write_bytes(b'manifest')
            context={'builder_revision':'b'*40,'run_id':7,'qualification':{'run_attempt':2}}
            for failure in ('missing permissions','invalid signature','wrong workflow','missing attestation','service unavailable'):
                with self.subTest(failure=failure), patch('subprocess.run',side_effect=subprocess.CalledProcessError(1,['gh'],stderr=failure.encode())):
                    with self.assertRaises(github.APIError):
                        github.GitHubAPI().verify_qualification_attestation(directory,context)

    def test_modified_manifest_is_rejected_even_with_successful_verifier_output(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); (directory/'release-manifest.json').write_bytes(b'modified')
            context={'builder_revision':'b'*40,'run_id':7,'qualification':{'run_attempt':2}}
            result=[{'verificationResult':{'statement':{'subject':[{'digest':{'sha256':'0'*64}}],
                'predicate':{'runDetails':{'builder':{'id':'https://github.com/danielbyon/development-process/.github/workflows/skill-release.yml@refs/heads/main'},'metadata':{'invocationId':'https://github.com/danielbyon/development-process/actions/runs/7/attempts/2'}}}}}}]
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')):
                with self.assertRaises(github.APIError):
                    github.GitHubAPI().verify_qualification_attestation(directory,context)
