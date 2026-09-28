import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4
from .models import Bundle, Edge
from .engine import assess

MAX_FILE=25_000_000

def read_json(path):
    p=Path(path)
    if p.stat().st_size>MAX_FILE: raise ValueError("Input JSON exceeds 25 MB")
    return json.loads(p.read_text())

def write_json(path,value):
    text=json.dumps(value,indent=2)+"\n"
    if path: Path(path).write_text(text)
    else: print(text)

def submit(bundle,url,token,allow_http=False):
    import httpx
    parsed=urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("Use a base URL without credentials, query, or fragment")
    if parsed.scheme!="https" and not (parsed.scheme=="http" and (parsed.hostname in {"localhost","127.0.0.1","::1"} or allow_http)):
        raise ValueError("Use HTTPS; --allow-http is available for an explicitly trusted private network")
    if not token: raise ValueError("Set GUARDGAP_TOKEN to the scoped collector token")
    with httpx.Client(timeout=60,follow_redirects=False,trust_env=parsed.hostname not in {"localhost","127.0.0.1","::1"}) as client:
        for attempt in range(3):
            try:
                headers={"Authorization":"Bearer "+token}
                if os.getenv("GUARDGAP_IDENTITY_TOKEN"):
                    headers["X-Serverless-Authorization"]="Bearer "+os.environ["GUARDGAP_IDENTITY_TOKEN"]
                r=client.post(url.rstrip("/")+"/api/ingest",headers=headers,json=bundle.model_dump(mode="json"))
            except httpx.TransportError:
                if attempt==2: raise ValueError("Could not connect to GuardGap; check URL, TLS and network reachability") from None
                time.sleep(attempt+1); continue
            if r.status_code in {429,502,503,504} and attempt<2:
                time.sleep(attempt+1); continue
            if r.status_code>=400:
                raise ValueError(f"GuardGap rejected evidence (HTTP {r.status_code}). Check schema, application/environment, and token. Server response: {r.text[:500]}")
            return r.json()

def collect(args):
    from .collectors import source, terraform, gcp, junit
    at=datetime.now(timezone.utc); resources=[]; edges=[]; warnings=[]
    repository=args.repository or os.getenv("GITHUB_REPOSITORY") or "local/application"
    commit=args.commit or os.getenv("GITHUB_SHA")
    if not commit:
        try: commit=subprocess.run(["git","-C",args.repo,"rev-parse","HEAD"],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
        except (OSError,subprocess.SubprocessError): raise ValueError("Supply --commit, GITHUB_SHA, or a Git checkout")
    src,w=source.scan(args.repo,repository,at); resources+=src; warnings+=w
    if args.terraform_plan:
        plan=read_json(args.terraform_plan)
        # Preserve saved plan time if present rather than treating an old plan as freshly produced.
        plan_at=datetime.fromisoformat(plan["timestamp"].replace("Z","+00:00")) if plan.get("timestamp") else datetime.fromtimestamp(Path(args.terraform_plan).stat().st_mtime,timezone.utc)
        rs,w=terraform.normalize(plan,plan_at); resources+=rs; warnings+=w
    if args.gcp_project:
        raw=gcp.capture(args.gcp_project,args.region,args.run_service,args.sql_instance,args.bucket)
        rs,es,w=gcp.normalize(raw); resources+=rs; edges+=es; warnings+=w
    elif args.gcp_snapshot:
        rs,es,w=gcp.normalize(read_json(args.gcp_snapshot)); resources+=rs; edges+=es; warnings+=w
    else: warnings.append("No cloud snapshot supplied. Source and planned configuration do not confirm deployed controls.")
    if args.junit:
        if not args.test_name or not args.tested_image_digest: raise ValueError("JUnit requires --test-name and --tested-image-digest")
        test_at=datetime.fromtimestamp(Path(args.junit).stat().st_mtime,timezone.utc)
        test=junit.collect(args.junit,args.test_name,args.tested_image_digest,test_at); resources.append(test)
        for r in resources:
            if r.kind=="cloud_run" and r.facts.image_digest==args.tested_image_digest:
                edges.append(Edge(source=test.id,target=r.id,relationship="test image match",confidence="evidenced",reason="JUnit supplied with the same image digest; the CI producer is trusted."))
    if args.image_digest:
        for r in resources:
            if r.kind=="cloud_run" and r.facts.image_digest==args.image_digest:
                edges.append(Edge(source=src[0].id,target=r.id,relationship="build digest match",confidence="evidenced",reason="Runner supplies this checkout's build digest; deployed revision matches. Independent provenance verification is not performed."))
    bundle=Bundle(bundle_id=uuid4(),application_id=args.application,environment=args.environment,repository=repository,commit=commit,collected_at=at,expected_image_digest=args.image_digest,deployment_status=args.deployment_status,resources=resources,edges=edges,warnings=warnings[:100])
    write_json(args.output,bundle.model_dump(mode="json"))
    print(f"Collected {len(resources)} resources; {len(warnings)} coverage notices. Evidence saved to {args.output}.",file=sys.stderr)
    if args.url: print(json.dumps(submit(bundle,args.url,os.getenv("GUARDGAP_TOKEN",""),args.allow_http)))

def markdown(report):
    lines=["# GuardGap assessment", "",f"Assessed: {report['assessed_at']}", "", report["scope_note"], "", "| Control | Resource | Status | Observation |", "| --- | --- | --- | --- |"]
    for f in report["findings"]:
        values=[f["id"],f["resource_name"],f["status"],f["message"]]
        lines.append("| "+" | ".join(v.replace("|","\\|").replace("\n"," ") for v in values)+" |")
    return "\n".join(lines)+"\n"

def sarif(report):
    rules={f["id"]:{"id":f["id"],"shortDescription":{"text":f["title"]},"help":{"text":f["fix"]}} for f in report["findings"]}
    return {"version":"2.1.0","$schema":"https://json.schemastore.org/sarif-2.1.0.json","runs":[{"tool":{"driver":{"name":"GuardGap","version":"0.1.0","rules":list(rules.values())}},"results":[{"ruleId":f["id"],"level":"error" if f["status"]=="gap" else "warning","message":{"text":f"{f['resource_name']}: {f['message']}"},"properties":{"status":f["status"],"resource_id":f["resource_id"],"layer":f["layer"]}} for f in report["findings"] if f["status"]!="met"]}]}

def main():
    p=argparse.ArgumentParser(description="GuardGap portable service and evidence collector")
    commands=p.add_subparsers(dest="command",required=True)
    serve=commands.add_parser("serve"); serve.add_argument("--host",default="127.0.0.1"); serve.add_argument("--port",type=int,default=int(os.getenv("PORT","8000")))
    c=commands.add_parser("collect",help="Collect normalized facts from code, Terraform and selected GCP resources")
    c.add_argument("--application",required=True); c.add_argument("--environment",required=True); c.add_argument("--repo",default="."); c.add_argument("--repository"); c.add_argument("--commit"); c.add_argument("--terraform-plan")
    group=c.add_mutually_exclusive_group(); group.add_argument("--gcp-project"); group.add_argument("--gcp-snapshot")
    c.add_argument("--region",default="us-central1"); c.add_argument("--run-service",action="append",default=[]); c.add_argument("--sql-instance",action="append",default=[]); c.add_argument("--bucket",action="append",default=[])
    c.add_argument("--image-digest"); c.add_argument("--deployment-status",choices=["succeeded","failed","unknown","not_deployed"],default="unknown")
    c.add_argument("--junit"); c.add_argument("--test-name"); c.add_argument("--tested-image-digest"); c.add_argument("--output",default="guardgap-evidence.json"); c.add_argument("--url",default=os.getenv("GUARDGAP_URL")); c.add_argument("--allow-http",action="store_true")
    s=commands.add_parser("submit"); s.add_argument("file"); s.add_argument("--url",default=os.getenv("GUARDGAP_URL"),required=not bool(os.getenv("GUARDGAP_URL"))); s.add_argument("--allow-http",action="store_true")
    check=commands.add_parser("check"); check.add_argument("file"); check.add_argument("--format",choices=["json","markdown","sarif"],default="json"); check.add_argument("--output"); check.add_argument("--fail-on",choices=["none","gap","gap-or-unknown"],default="none")
    schema=commands.add_parser("schema"); schema.add_argument("--output")
    demo=commands.add_parser("demo-evidence"); demo.add_argument("--variant",choices=["before","after","partial"],default="before"); demo.add_argument("--output",default="demo-evidence.json")
    args=p.parse_args()
    try:
        if args.command=="serve":
            import uvicorn
            uvicorn.run("guardgap.app:create_app",factory=True,host=args.host,port=args.port,proxy_headers=False)
        elif args.command=="collect": collect(args)
        elif args.command=="submit":
            print(json.dumps(submit(Bundle.model_validate(read_json(args.file)),args.url,os.getenv("GUARDGAP_TOKEN",""),args.allow_http)))
        elif args.command=="schema": write_json(args.output,Bundle.model_json_schema())
        elif args.command=="demo-evidence":
            from .demo import make_demo
            write_json(args.output,make_demo(args.variant).model_dump(mode="json"))
        elif args.command=="check":
            report=assess(Bundle.model_validate(read_json(args.file)))
            if args.format=="markdown":
                output=markdown(report)
                if args.output: Path(args.output).write_text(output)
                else: print(output)
            else: write_json(args.output,sarif(report) if args.format=="sarif" else report)
            if args.fail_on!="none" and (report["counts"]["gap"] or (args.fail_on=="gap-or-unknown" and (report["counts"]["unknown"] or not report["findings"]))): return 2
    except (ValueError,OSError,KeyError) as e:
        print(f"GuardGap: {e}",file=sys.stderr); return 1
    return 0

if __name__=="__main__": sys.exit(main())
