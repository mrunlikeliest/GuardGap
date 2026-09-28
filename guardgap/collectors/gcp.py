"""Read selected GCP resources with the runner's existing gcloud identity.
No shell execution, recursive discovery, secret access, or cloud mutation.
"""
import json
import re
import subprocess
from .common import resource, bindings, sha_digest, now
from ..models import Edge

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,250}$")

def validate_name(value):
    if not SAFE_NAME.fullmatch(value): raise ValueError(f"Invalid GCP resource identifier: {value!r}")
    return value

def capture(project, region, run_services=(), sql_instances=(), buckets=()):
    project, region = validate_name(project), validate_name(region)
    warnings=[]
    def get(args, label):
        try:
            result=subprocess.run(["gcloud",*args,f"--project={project}","--format=json","--quiet"],capture_output=True,text=True,timeout=90,check=True)
            return json.loads(result.stdout)
        except (subprocess.SubprocessError,OSError,ValueError):
            # gcloud stderr can contain request details; do not forward it.
            warnings.append(f"Could not collect {label}; check read permissions, resource name, and gcloud authentication.")
            return None
    raw={"project":project,"collected_at":now().isoformat(),"cloud_run":[],"sql_instances":[],"buckets":[],"ancestor_policies":[]}
    raw["project_policy"]=get(["projects","get-iam-policy",project],"project IAM")
    ancestors=get(["projects","get-ancestors",project],"project ancestry")
    raw["ancestor_iam_complete"]=ancestors is not None and raw["project_policy"] is not None
    for item in ancestors or []:
        kind=str(item.get("type","")); identity=validate_name(str(item.get("id","")))
        if kind == "project": continue
        if kind not in {"folder","organization"}:
            raw["ancestor_iam_complete"]=False; continue
        command=["resource-manager","folders","get-iam-policy",identity] if kind == "folder" else ["organizations","get-iam-policy",identity]
        policy=get(command,f"{kind} IAM")
        if policy is None: raw["ancestor_iam_complete"]=False
        else: raw["ancestor_policies"].append(policy)
    for name in run_services:
        name=validate_name(name)
        service=get(["run","services","describe",name,f"--region={region}"],f"Cloud Run service {name}")
        if service is None:
            raw["cloud_run"].append({"requested_name":name,"service":None}); continue
        ready=service.get("status",{}).get("latestReadyRevisionName")
        revision=get(["run","revisions","describe",validate_name(ready),f"--region={region}"],f"revision {ready}") if ready else None
        policy=get(["run","services","get-iam-policy",name,f"--region={region}"],f"service IAM {name}")
        raw["cloud_run"].append({"requested_name":name,"service":service,"revision":revision,"iam_policy":policy})
    for name in sql_instances:
        name=validate_name(name)
        raw["sql_instances"].append({"requested_name":name,"instance":get(["sql","instances","describe",name],f"Cloud SQL {name}")})
    for name in buckets:
        name=validate_name(name.removeprefix("gs://"))
        raw["buckets"].append({"requested_name":name,"bucket":get(["storage","buckets","describe",f"gs://{name}","--raw"],f"bucket {name}")})
    raw["warnings"]=warnings
    return raw

def normalize(raw):
    from datetime import datetime
    project=raw["project"]
    # Offline raw snapshots MUST retain their capture timestamp. Never restamp imported evidence.
    at=datetime.fromisoformat(raw["collected_at"])
    resources,edges=[],[]
    ancestor_bindings=bindings(raw.get("project_policy"))
    for p in raw.get("ancestor_policies",[]): ancestor_bindings += bindings(p)
    complete=bool(raw.get("ancestor_iam_complete")) and raw.get("project_policy") is not None
    iam_id=f"gcp:{project}:iam"
    resources.append(resource(iam_id,project+" IAM","project_iam","deployed",{"iam_bindings":ancestor_bindings,"iam_complete":complete},"gcp_api",f"projects/{project}:getIamPolicy + ancestors",at))
    for item in raw.get("cloud_run",[]):
        service=item.get("service") or {}; revision=item.get("revision") or {}
        name=service.get("metadata",{}).get("name") or item["requested_name"]
        spec=service.get("spec",{}).get("template",{}).get("spec",{})
        # Use the ready revision for identity/connections where available; service-wide IAM remains on Service.
        runtime=revision.get("spec",{})
        annotations=service.get("metadata",{}).get("annotations",{})
        rev_annotations=revision.get("metadata",{}).get("annotations",{}) or service.get("spec",{}).get("template",{}).get("metadata",{}).get("annotations",{})
        status=service.get("status",{})
        ready=bool(status.get("latestReadyRevisionName")) and status.get("latestReadyRevisionName")==status.get("latestCreatedRevisionName") and any(c.get("type")=="Ready" and c.get("status") in {True,"True"} for c in status.get("conditions",[]))
        refs=[]
        for c in runtime.get("containers",[]):
            for e in c.get("env",[]):
                ref=e.get("valueFrom",{}).get("secretKeyRef",{})
                if ref.get("name"): refs.append(ref["name"])
        facts={"service_account":runtime.get("serviceAccountName"),"invoker_iam_disabled":str(annotations.get("run.googleapis.com/invoker-iam-disabled","false")).lower()=="true" if service else None,"iam_bindings":bindings(item.get("iam_policy"))+ancestor_bindings,"iam_complete":complete and item.get("iam_policy") is not None,"ready":ready if service else None,"revision":status.get("latestReadyRevisionName"),"image_digest":sha_digest(revision.get("status",{}).get("imageDigest")),"secret_references":refs,"sql_connections":[v for v in rev_annotations.get("run.googleapis.com/cloudsql-instances","").split(",") if v]}
        rid=f"gcp:{project}:run:{name}"
        resources.append(resource(rid,name,"cloud_run","deployed",facts,"gcp_api",f"run/{name}:service,readyRevision,iamPolicy",at))
        if facts["service_account"]:
            edges.append(Edge(source=rid,target=iam_id,relationship="runtime identity policies",confidence="evidenced",reason=facts["service_account"]))
    for item in raw.get("sql_instances",[]):
        instance=item.get("instance") or {}; name=instance.get("name") or item["requested_name"]
        ip=instance.get("settings",{}).get("ipConfiguration",{})
        facts={"public_ip_enabled":ip.get("ipv4Enabled"),"public_ip_present":any(x.get("type")=="PRIMARY" for x in instance.get("ipAddresses",[])) if "ipAddresses" in instance else None,"ssl_mode":ip.get("sslMode"),"connection_name":instance.get("connectionName")}
        rid=f"gcp:{project}:sql:{name}"
        resources.append(resource(rid,name,"cloud_sql","deployed",facts,"gcp_api",f"sql/instances/{name}",at))
        for r in resources:
            if r.kind=="cloud_run" and facts["connection_name"] and facts["connection_name"] in r.facts.sql_connections:
                edges.append(Edge(source=r.id,target=rid,relationship="Cloud SQL attachment",confidence="evidenced",reason="Exact connectionName matches the ready revision's Cloud SQL annotation; traffic is not observed."))
    for item in raw.get("buckets",[]):
        bucket=item.get("bucket") or {}; name=bucket.get("name") or item["requested_name"]
        iam=bucket.get("iamConfiguration",{})
        facts={"public_access_prevention":iam.get("publicAccessPrevention"),"uniform_bucket_access":iam.get("uniformBucketLevelAccess",{}).get("enabled")}
        resources.append(resource(f"gcp:{project}:bucket:{name}",name,"gcs_bucket","deployed",facts,"gcp_api",f"storage/buckets/{name}",at))
    return resources,edges,raw.get("warnings",[])
