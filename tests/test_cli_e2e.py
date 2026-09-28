"""Exercise CLI -> HTTP ingestion -> real report history in one network namespace."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]

def cloud_snapshot(fixed):
    identity='agent@demo-project.iam.gserviceaccount.com' if fixed else '123456-compute@developer.gserviceaccount.com'
    digest='sha256:'+('b' if fixed else 'a')*64
    return {'project':'demo-project','collected_at':datetime.now(timezone.utc).isoformat(),
        'project_policy':{'bindings':[] if fixed else [{'role':'roles/editor','members':['serviceAccount:'+identity]}]},'ancestor_policies':[],'ancestor_iam_complete':True,
        'cloud_run':[{'requested_name':'agent','service':{'metadata':{'name':'agent','annotations':{}},'status':{'latestReadyRevisionName':'agent-1','latestCreatedRevisionName':'agent-1','conditions':[{'type':'Ready','status':'True'}]}},'revision':{'metadata':{'annotations':{'run.googleapis.com/cloudsql-instances':'demo-project:us-central1:customers'}},'spec':{'serviceAccountName':identity,'containers':[]},'status':{'imageDigest':'image@'+digest}},'iam_policy':{'bindings':[] if fixed else [{'role':'roles/run.invoker','members':['allUsers']}]}}],
        'sql_instances':[{'requested_name':'customers','instance':{'name':'customers','connectionName':'demo-project:us-central1:customers','settings':{'ipConfiguration':{'ipv4Enabled':not fixed,'sslMode':'ENCRYPTED_ONLY' if fixed else 'ALLOW_UNENCRYPTED_AND_ENCRYPTED'}},'ipAddresses':[{'type':'PRIVATE'}] if fixed else [{'type':'PRIMARY'}]}}],
        'buckets':[{'requested_name':'documents','bucket':{'name':'documents','iamConfiguration':{'publicAccessPrevention':'enforced' if fixed else 'inherited','uniformBucketLevelAccess':{'enabled':fixed}}}}],
        'warnings':[]}

def test_cli_to_webapp_with_live_reassessment(tmp_path):
    env=os.environ.copy()
    env.update(GUARDGAP_ADMIN_PASSWORD='long-example-password',GUARDGAP_SECURE_COOKIE='false',GUARDGAP_DEMO='false',DATABASE_URL=f'sqlite:///{tmp_path}/guardgap.db')
    port='18291'
    server=subprocess.Popen([sys.executable,'-m','uvicorn','guardgap.app:create_app','--factory','--host','127.0.0.1','--port',port],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        base='http://127.0.0.1:'+port
        with httpx.Client(base_url=base,trust_env=False,timeout=2) as client:
            for _ in range(80):
                try:
                    if client.get('/healthz').status_code==200: break
                except httpx.TransportError: pass
                time.sleep(.05)
            else: raise AssertionError('GuardGap service failed to start: '+server.stderr.read()[-500:])
            assert client.get('/static/app.js').status_code==200
            login=client.post('/api/login',json={'password':'long-example-password'})
            assert login.status_code==200
            h={'X-GuardGap-CSRF':login.json()['csrf']}
            assert client.post('/api/applications',headers=h,json={'id':'agent','name':'Agent'}).status_code==200
            token=client.post('/api/applications/agent/tokens',headers=h,json={'environment':'staging'}).json()['token']
            env.update(GUARDGAP_TOKEN=token)
            reports=[]
            for fixed in (False,True):
                snapshot=tmp_path/f'{fixed}.json';snapshot.write_text(json.dumps(cloud_snapshot(fixed)))
                junit=tmp_path/f'{fixed}.xml'
                junit.write_text('<testsuite><testcase name="test_cross_customer_denied">'+('' if fixed else '<failure message="cross-customer update accepted"/>')+'</testcase></testsuite>')
                digest='sha256:'+('b' if fixed else 'a')*64
                output=tmp_path/f'{fixed}-bundle.json'
                command=[sys.executable,'-m','guardgap','collect','--application','agent','--environment','staging','--repo','examples/support-agent','--repository','org/agent','--commit',('b' if fixed else 'a')*40,'--gcp-snapshot',str(snapshot),'--image-digest',digest,'--deployment-status','succeeded','--junit',str(junit),'--test-name','test_cross_customer_denied','--tested-image-digest',digest,'--output',str(output),'--url',base]
                result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=45)
                assert result.returncode==0,result.stderr
                assert 'SUPPORT_TOKENS_JSON' not in output.read_text()
                uploaded=json.loads(result.stdout)
                reports.append(client.get('/api/reports/'+uploaded['report_id']).json()['report'])
            assert reports[0]['counts']['gap']>=6
            assert reports[1]['counts']=={'met':9,'gap':0,'unknown':0}
            assert any(x['before']=='gap' and x['after']=='met' for x in reports[1]['changes'])
    finally:
        server.terminate()
        try: server.communicate(timeout=5)
        except subprocess.TimeoutExpired: server.kill();server.communicate()
