"""Explicit synthetic evidence used only for the guided local walkthrough."""
from uuid import uuid4
from .models import Bundle, Edge
from .collectors.common import resource, now

def make_demo(variant="before"):
    at=now(); fixed=variant=="after"; partial=variant=="partial"
    image="sha256:"+("b" if fixed else "a")*64
    service_account="support-agent@guardgap-demo.iam.gserviceaccount.com" if fixed else "123456-compute@developer.gserviceaccount.com"
    roles=[] if fixed else [{"role":"roles/editor","members":["serviceAccount:"+service_account]}]
    public=[] if fixed else [{"role":"roles/run.invoker","members":["allUsers"]}]
    def r(id,name,kind,layer,facts): return resource(id,name,kind,layer,facts,"fixture","synthetic:"+id,at)
    resources=[
        r("source:agent","support-agent","python_component","source",{"imports":["fastapi","google.genai"],"routes":["POST /customers/{customer_id}/records"],"ai_signals":["google.genai"]}),
        r("run:agent","Agent API","cloud_run","deployed",{"service_account":service_account,"invoker_iam_disabled":False,"iam_bindings":public,"iam_complete":not partial,"ready":True,"revision":"agent-00002" if fixed else "agent-00001","image_digest":image,"sql_connections":["guardgap-demo:us-central1:customers"]}),
        r("iam:project","Runtime permissions","project_iam","deployed",{"iam_bindings":roles,"iam_complete":not partial}),
        r("sql:customers","Customer database","cloud_sql","deployed",{"public_ip_enabled":not fixed,"public_ip_present":not fixed,"ssl_mode":"ENCRYPTED_ONLY" if fixed else "ALLOW_UNENCRYPTED_AND_ENCRYPTED","connection_name":"guardgap-demo:us-central1:customers"}),
        r("bucket:documents","Customer documents","gcs_bucket","deployed",{"public_access_prevention":"enforced" if fixed else "inherited","uniform_bucket_access":fixed}),
        r("test:negative-authorization","Cross-customer update denied","authorization_test","test",{"test_name":"test_cross_customer_denied","test_passed":fixed,"tested_image_digest":image}),
    ]
    if partial:
        resources=[x for x in resources if x.kind in {"python_component","cloud_run","project_iam"}]
        resources[1].facts.image_digest=None
    ids={x.id for x in resources}
    edges=[Edge(source=a,target=b,relationship=c,confidence="evidenced",reason=d) for a,b,c,d in [
        ("source:agent","run:agent","built and deployed","Fixture CI digest mapping"),
        ("run:agent","iam:project","runtime identity","Fixture service account and policy"),
        ("run:agent","sql:customers","database attachment","Fixture exact connectionName match"),
        ("test:negative-authorization","run:agent","tested image","Fixture matching image digest"),
    ] if a in ids and b in ids]
    return Bundle(bundle_id=uuid4(),application_id="support-assistant-demo",environment="demo",repository="example/support-agent",commit=("b" if fixed else "a")*40,collected_at=at,expected_image_digest=image,deployment_status="succeeded",demo=True,resources=resources,edges=edges,warnings=["Synthetic walkthrough. These observations were not collected from a real GCP project."])
