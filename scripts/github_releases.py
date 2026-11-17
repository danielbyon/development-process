"""GitHub CLI transport. Failed reads never become absent remote objects."""
from __future__ import annotations
import json
import hashlib
import os
import re
import subprocess
from pathlib import Path

class APIError(RuntimeError):
    """GitHub could not establish or change the requested state."""

class GitHubAPI:
    def __init__(self, repository='danielbyon/development-process'):
        if repository != 'danielbyon/development-process':
            raise APIError('Unexpected repository')
        self.repository = repository
        self.base = '/repos/' + repository
        self.historical_publication = False
        self.read_only = False
        self._read_only_token = None

    @classmethod
    def for_read_only_audit(cls, token):
        """Create a GET-only client bound to one explicitly selected token."""
        if not isinstance(token,str) or not token:
            raise APIError('Explicit read-only audit credential required')
        api=cls()
        api.read_only=True
        api._read_only_token=token
        return api

    def authorize_historical_publication(self):
        if self.read_only:
            raise APIError('read-only audit client cannot authorize publication')
        if os.environ.get('RELEASE_WORKFLOW_WRITE_AUTHORIZED')!='true' or not os.environ.get('RELEASE_WORKFLOW_WRITE_TOKEN'):
            raise APIError('Separate owner-authorized Workflows-write capability required')
        self.historical_publication=True

    def request(self, method, endpoint, data=None, raw=False):
        if self.read_only and method!='GET':
            raise APIError('read-only audit client refuses write requests')
        command = ['gh','api','--method',method,endpoint,'-H','X-GitHub-Api-Version: 2022-11-28']
        if raw: command += ['--allow-escape-sequences','-H','Accept: application/octet-stream']
        payload = None
        if data is not None:
            command += ['--input','-']; payload=json.dumps(data).encode()
        try:
            environment=os.environ.copy()
            if self.read_only:
                for key in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN'):
                    environment.pop(key,None)
                environment['GH_HOST']='github.com'
                environment['GH_TOKEN']=self._read_only_token
            if not self.read_only and method=='GET' and (endpoint.endswith('/immutable-releases') or '/rules/' in endpoint or '/rulesets' in endpoint or '/collaborators' in endpoint):
                token=environment.get('RELEASE_ADMIN_READ_TOKEN')
                if not token: raise APIError('Owner-provisioned Administration-read credential required')
                environment['GH_TOKEN']=token
            if method!='GET' and self.historical_publication:
                environment['GH_TOKEN']=environment['RELEASE_WORKFLOW_WRITE_TOKEN']
            result=subprocess.run(command,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,env=environment)
            return result.stdout if raw else json.loads(result.stdout or b'null')
        except (subprocess.CalledProcessError, ValueError) as error:
            raise APIError(f'{method} {endpoint} failed; reconcile remote state before retrying') from error

    def pages(self, endpoint):
        values=[]; page=1
        while True:
            batch=self.request('GET',endpoint+('&' if '?' in endpoint else '?')+f'per_page=100&page={page}')
            if isinstance(batch,dict) and 'jobs' in batch: batch=batch['jobs']
            if isinstance(batch,dict) and 'artifacts' in batch: batch=batch['artifacts']
            if not isinstance(batch,list): raise APIError('Expected paginated array')
            values.extend(batch)
            if len(batch)<100: return values
            page+=1

    def releases(self): return self.pages(self.base+'/releases')
    def tags(self): return self.pages(self.base+'/git/matching-refs/tags/')
    def release(self, release_id): return self.request('GET',self.base+f'/releases/{int(release_id)}')
    def original_context(self, run_id):
        import io
        import zipfile
        import hashlib
        artifacts=self.pages(self.base+f'/actions/runs/{int(run_id)}/artifacts')
        bundles=[a for a in artifacts if re.fullmatch(r'release-bundle-[1-9][0-9]*',a.get('name',''))]
        if not bundles: return None
        selected=min(bundles,key=lambda a:int(a['name'].rsplit('-',1)[1]))
        if selected.get('expired'): raise APIError('Original frozen bundle expired; preserve and block')
        payload=self.request('GET',self.base+f'/actions/artifacts/{selected["id"]}/zip',raw=True)
        if selected.get('digest')!='sha256:'+hashlib.sha256(payload).hexdigest():
            raise APIError('Original-run artifact digest unavailable or mismatched')
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or 'release-context.json' not in names:
                raise APIError('Original context missing or duplicated')
            context=json.loads(archive.read('release-context.json'))
            expected=context.get('qualified_artifacts',{})
            if set(names)!=set(expected)|{'release-context.json'}: raise APIError('Original bundle asset set mismatch')
            for name,sha in expected.items():
                if hashlib.sha256(archive.read(name)).hexdigest()!=sha: raise APIError('Original asset hash mismatch')
            return context

    def settings(self):
        rules=self.request('GET',self.base+'/rules/branches/main')
        source_ids={r.get('ruleset_id',r.get('rule_source_id')) for r in rules}
        source_ids.discard(None)
        return {'repository':self.request('GET',self.base),
                'immutability':self.request('GET',self.base+'/immutable-releases'),
                'rules':rules,
                'rulesets':[self.request('GET',self.base+f'/rulesets/{int(value)}') for value in source_ids],
                'collaborators':self.pages(self.base+'/collaborators?affiliation=all')}
    def ci_jobs(self, run_id, attempt):
        return self.pages(self.base+f'/actions/runs/{int(run_id)}/attempts/{int(attempt)}/jobs')
    def job_log(self, job_id):
        return self.request('GET',self.base+f'/actions/jobs/{int(job_id)}/logs',raw=True).decode('utf-8')
    def run(self, run_id): return self.request('GET',self.base+f'/actions/runs/{int(run_id)}')
    def record(self, reference):
        # References are repository-scoped API paths, never arbitrary URLs.
        if not isinstance(reference,str) or not (reference==self.base or reference.startswith(self.base+'/')) or '?' in reference or '..' in reference:
            raise APIError('Evidence reference must be a repository API path')
        return self.request('GET',reference)
    def create_draft(self, context, body):
        return self.request('POST',self.base+'/releases',{'tag_name':context['release_version'],
            'target_commitish':context['source_revision'],'name':context['release_version'],
            'body':body,'draft':True,'prerelease':False})
    def create_tag(self, tag, revision):
        return self.request('POST',self.base+'/git/refs',{'ref':'refs/tags/'+tag,'sha':revision})
    def publish(self, release_id):
        return self.request('PATCH',self.base+f'/releases/{int(release_id)}',{'draft':False})
    def upload(self, release_id, path):
        # Asset upload uses the release ID; never replace an existing asset.
        if self.read_only:
            raise APIError('read-only audit client refuses asset upload')
        from urllib.parse import quote
        endpoint='https://uploads.github.com'+self.base+f'/releases/{int(release_id)}/assets?name='+quote(path.name,safe='')
        try:
            subprocess.run(['gh','api','--method','POST',endpoint,'-H','Content-Type: application/octet-stream',
                            '--input',str(path)],check=True,capture_output=True,
                           env={**os.environ,**({'GH_TOKEN':os.environ['RELEASE_WORKFLOW_WRITE_TOKEN']} if self.historical_publication else {})})
        except subprocess.CalledProcessError as error: raise APIError('Upload failed; reconcile assets') from error
    def asset(self, asset):
        return self.request('GET',self.base+f'/releases/assets/{int(asset["id"])}',raw=True)
    def verify_qualification_attestation(self, directory, context):
        """Verify durable provenance signed by the pinned trusted workflow."""
        command=['gh','attestation','verify',str(Path(directory)/'release-manifest.json'),
                 '--repo',self.repository,'--signer-workflow',self.repository+'/.github/workflows/skill-release.yml',
                 '--signer-digest',context['builder_revision'],'--source-digest',context['builder_revision'],
                 '--source-ref','refs/heads/main','--deny-self-hosted-runners',
                 '--predicate-type','https://slsa.dev/provenance/v1','--format','json']
        try:
            result=subprocess.run(command,check=True,capture_output=True)
            results=json.loads(result.stdout)
            invocation_prefix='https://github.com/'+self.repository+'/actions/runs/'+str(context['run_id'])+'/attempts/'
            invocation_pattern=re.escape(invocation_prefix)+r'([1-9][0-9]*)'
            def valid_invocation(statement):
                invocation=statement.get('predicate',{}).get('runDetails',{}).get('metadata',{}).get('invocationId')
                match=re.fullmatch(invocation_pattern,invocation) if isinstance(invocation,str) else None
                return bool(match and int(match[1])>=context['qualification']['run_attempt'])
            manifest_digest=hashlib.sha256((Path(directory)/'release-manifest.json').read_bytes()).hexdigest()
            statements=[item.get('verificationResult',{}).get('statement',{}) for item in results]
            if not any(
                statement.get('predicateType')=='https://slsa.dev/provenance/v1'
                and statement.get('predicate',{}).get('runDetails',{}).get('builder',{}).get('id')=='https://github.com/'+self.repository+'/.github/workflows/skill-release.yml@refs/heads/main'
                and valid_invocation(statement)
                and statement.get('subject')==[{'name':'release-manifest.json','digest':{'sha256':manifest_digest}}]
                for statement in statements
            ):
                raise APIError('Qualification attestation invocation or subject mismatch')
        except (subprocess.CalledProcessError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
            raise APIError('Durable trusted-workflow qualification attestation unavailable or invalid') from error

    def verify_attestation(self, tag, directory):
        try:
            subprocess.run(['gh','release','verify',tag,'--repo',self.repository],check=True,capture_output=True)
            for path in sorted(Path(directory).iterdir()):
                if path.name=='release-context.json': continue
                subprocess.run(['gh','release','verify-asset',tag,str(path),'--repo',self.repository],check=True,capture_output=True)
        except subprocess.CalledProcessError as error: raise APIError('Release attestation verification unavailable or failed') from error
