import copy
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from guardgap.app import create_app
from guardgap.demo import make_demo
from guardgap.engine import assess, compare
from guardgap.models import Bundle
from guardgap.collectors.gcp import normalize
from guardgap.collectors.terraform import normalize as terraform
from guardgap.collectors.source import scan
from guardgap.collectors.junit import collect as junit

@pytest.fixture
def client(tmp_path):
    app=create_app(f"sqlite:///{tmp_path/'test.db'}",admin_password="a-unique-test-password",demo_enabled=True,secure_cookie=False)
    with TestClient(app) as c:
        yield c

def login(c):
    r=c.post('/api/login',json={'password':'a-unique-test-password'})
    assert r.status_code==200
    return {'X-GuardGap-CSRF':r.json()['csrf']}

def live_bundle(variant='before',application='agent',environment='staging'):
    b=make_demo(variant)
    b.demo=False;b.application_id=application;b.environment=environment
    for r in b.resources: r.evidence.source='gcp_api' if r.layer=='deployed' else 'python_ast' if r.layer=='source' else 'junit'
    return b.model_dump(mode='json')

def test_before_after_regression_and_unknown():
    before=assess(make_demo('before'));after=assess(make_demo('after'))
    assert before['counts']=={'met':1,'gap':7,'unknown':1}
    assert after['counts']=={'met':9,'gap':0,'unknown':0}
    assert any(c['before']=='gap' and c['after']=='met' for c in compare(after,before))
    assert any(c['after']=='not_observed' for c in compare(assess(make_demo('partial')),after))

def test_stale_cannot_pass():
    b=make_demo('after')
    for r in b.resources: r.evidence.collected_at-=timedelta(days=2)
    result=assess(b)
    assert result['counts']['met']==0
    assert result['counts']['unknown']==9

def test_planned_never_confirms_deployment():
    b=make_demo('after')
    for r in b.resources:
        if r.layer=='deployed': r.layer='planned'
    assert all(f['status']=='unknown' for f in assess(b)['findings'])

def test_public_iam_disabled_and_inherited_roles():
    b=make_demo('after');r=next(x for x in b.resources if x.kind=='cloud_run')
    r.facts.invoker_iam_disabled=True
    assert next(f for f in assess(b)['findings'] if f['id']=='RUN-001')['status']=='gap'
    r.facts.invoker_iam_disabled=False;r.facts.iam_complete=False
    assert next(f for f in assess(b)['findings'] if f['id']=='RUN-001')['status']=='unknown'
    r.facts.iam_bindings=[{'role':'roles/run.invoker','members':['allAuthenticatedUsers']}]
    assert next(f for f in assess(b)['findings'] if f['id']=='RUN-001')['status']=='gap'

def test_test_result_requires_deployed_digest():
    b=make_demo('after')
    next(r for r in b.resources if r.kind=='authorization_test').facts.tested_image_digest='sha256:'+'f'*64
    assert next(f for f in assess(b)['findings'] if f['id']=='TEST-001')['status']=='unknown'

def test_schema_guards():
    b=live_bundle();b['resources'][0]['facts']['password']='oops'
    with pytest.raises(ValueError): Bundle.model_validate(b)
    b=live_bundle();b['resources'][1]['facts']['iam_bindings']=[{'role':'roles/run.invoker','members':True}]
    with pytest.raises(ValueError): Bundle.model_validate(b)
    b=live_bundle();b['resources'].append(b['resources'][0])
    with pytest.raises(ValueError): Bundle.model_validate(b)
    b=live_bundle();b['collected_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError): Bundle.model_validate(b)
    b=live_bundle();b['edges'][0]['target']='missing'
    with pytest.raises(ValueError): Bundle.model_validate(b)

def test_auth_csrf_and_headers(client):
    assert client.get('/api/applications').status_code==401
    assert client.post('/api/login',json={'password':'wrong'}).status_code==401
    headers=login(client)
    assert 'httponly' in client.cookies.jar._cookies['testserver.local']['/']['guardgap_session']._rest.keys().__str__().lower()
    assert client.post('/api/applications',json={'id':'agent','name':'Agent'}).status_code==403
    assert client.post('/api/applications',json={'id':'agent','name':'Agent'},headers=headers).status_code==200
    assert "frame-ancestors 'none'" in client.get('/').headers['content-security-policy']
    client.post('/api/logout',headers=headers)
    assert client.get('/api/applications').status_code==401

def test_end_to_end_collect_fix_reassess_revoke(client):
    h=login(client)
    client.post('/api/applications',json={'id':'agent','name':'Agent'},headers=h)
    token=client.post('/api/applications/agent/tokens',json={'environment':'staging'},headers=h).json()
    auth={'Authorization':'Bearer '+token['token']}
    before=live_bundle()
    r=client.post('/api/ingest',json=before,headers=auth)
    assert r.status_code==200,r.text
    assert client.post('/api/ingest',json=before,headers=auth).json()['duplicate']
    mismatch=copy.deepcopy(before);mismatch['environment']='production';mismatch['bundle_id']=str(uuid4())
    assert client.post('/api/ingest',json=mismatch,headers=auth).status_code==403
    same_id=copy.deepcopy(before);same_id['commit']='f'*40
    assert client.post('/api/ingest',json=same_id,headers=auth).status_code==409
    after=client.post('/api/ingest',json=live_bundle('after'),headers=auth).json()
    report=client.get('/api/reports/'+after['report_id']).json()
    assert report['report']['counts']['met']==9
    assert len(report['report']['changes'])==8
    repeat=client.post('/api/snapshots/'+after['snapshot_id']+'/assess',headers=h)
    assert repeat.status_code==200
    assert client.get('/api/reports/'+repeat.json()['report_id']).json()['report']['changes']==[]
    assert client.get('/api/applications/agent/tokens').json()[0].get('token') is None
    client.delete('/api/tokens/'+token['id'],headers=h)
    assert client.post('/api/ingest',json=live_bundle('after'),headers=auth).status_code==401
    assert len(client.get('/api/audit').json())>=5

def test_demo_separate_and_explicit(client):
    h=login(client)
    r=client.post('/api/demo',json={'variant':'before'},headers=h)
    assert r.status_code==200
    assert client.get('/api/reports/'+r.json()['report_id']).json()['report']['demo'] is True

def test_no_secret_values_in_normalization():
    raw={'project':'test-project','collected_at':datetime.now(timezone.utc).isoformat(),'project_policy':{'bindings':[]},'ancestor_policies':[],'ancestor_iam_complete':True,'cloud_run':[{'requested_name':'agent','service':{'metadata':{'name':'agent'},'spec':{'template':{'spec':{'serviceAccountName':'agent@test-project.iam.gserviceaccount.com','containers':[{'env':[{'name':'PASSWORD','value':'DO_NOT_UPLOAD'}]}]}}},'status':{'latestReadyRevisionName':'agent-1','latestCreatedRevisionName':'agent-1','conditions':[{'type':'Ready','status':'True'}]}},'revision':{'spec':{'serviceAccountName':'agent@test-project.iam.gserviceaccount.com','containers':[{'env':[{'name':'PASSWORD','value':'DO_NOT_UPLOAD'},{'name':'TOKEN','valueFrom':{'secretKeyRef':{'name':'token-secret'}}}]}]},'status':{'imageDigest':'image@sha256:'+'a'*64}},'iam_policy':{'bindings':[]}}],'sql_instances':[{'requested_name':'db','instance':{'name':'db','connectionName':'test:region:db','settings':{'ipConfiguration':{'ipv4Enabled':False,'sslMode':'ENCRYPTED_ONLY'}},'ipAddresses':[{'type':'PRIVATE','ipAddress':'10.0.0.2'}]}}],'buckets':[{'requested_name':'docs','bucket':{'name':'docs','iamConfiguration':{'publicAccessPrevention':'enforced','uniformBucketLevelAccess':{'enabled':True}}}}]}
    resources,_,_=normalize(raw)
    serialized=json.dumps([r.model_dump(mode='json') for r in resources])
    assert 'DO_NOT_UPLOAD' not in serialized
    assert 'token-secret' in serialized
    assert next(r for r in resources if r.kind=='cloud_run').facts.image_digest=='sha256:'+'a'*64
    assert next(r for r in resources if r.kind=='cloud_sql').facts.public_ip_present is False

def test_failed_collection_resources_are_unknown():
    raw={'project':'p','collected_at':datetime.now(timezone.utc).isoformat(),'cloud_run':[{'requested_name':'agent','service':None}],'sql_instances':[{'requested_name':'db','instance':None}],'buckets':[{'requested_name':'bucket','bucket':None}]}
    resources,_,_=normalize(raw)
    b=make_demo('after');b.resources=resources;b.edges=[]
    assert assess(b)['counts']['met']==0

def test_terraform_no_sensitive_passthrough():
    plan={'planned_values':{'root_module':{'resources':[{'address':'google_sql_database_instance.db','type':'google_sql_database_instance','values':{'name':'db','root_password':'TOP_SECRET','settings':[{'ip_configuration':[{'ipv4_enabled':False,'ssl_mode':'ENCRYPTED_ONLY'}]}]}}]}}}
    resources,_=terraform(plan,datetime.now(timezone.utc))
    assert 'TOP_SECRET' not in resources[0].model_dump_json()
    assert resources[0].layer=='planned'

def test_ast_no_execution_and_symlinks(tmp_path):
    (tmp_path/'app.py').write_text('import openai\nimport os\nos.system("echo DO_NOT_RUN")\nfrom fastapi import FastAPI\napp=FastAPI()\n@app.get("/records")\ndef records(): return os.getenv("DATABASE_HOST")\n')
    (tmp_path/'secret.py').symlink_to('/etc/passwd')
    resources,_=scan(tmp_path,'org/app',datetime.now(timezone.utc))
    assert resources[0].facts.ai_signals==['openai']
    assert resources[0].facts.env_references==['DATABASE_HOST']
    assert '/records' in resources[0].facts.routes[0]

def test_junit_skips_and_entities(tmp_path):
    p=tmp_path/'test.xml';p.write_text('<testsuite><testcase name="auth"><skipped/></testcase></testsuite>')
    assert junit(p,'auth','sha256:'+'a'*64,datetime.now(timezone.utc)).facts.test_passed is None
    p.write_text('<!DOCTYPE x [<!ENTITY a "secret">]><testsuite/>')
    with pytest.raises(ValueError): junit(p,'auth','x',datetime.now(timezone.utc))

def test_body_limit(client):
    assert client.post('/api/ingest',content=b'x'*5_000_001).status_code==413
