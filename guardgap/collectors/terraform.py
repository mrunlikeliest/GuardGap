"""Reads saved terraform show -json output, never runs Terraform or copies values wholesale."""
from .common import resource

def normalize(plan,at):
    resources=[]; warnings=[]
    def modules(module):
        yield from module.get("resources",[])
        for child in module.get("child_modules",[]): yield from modules(child)
    root=plan.get("planned_values",{}).get("root_module",{})
    if not root: return [],["Terraform plan has no planned_values.root_module; saved plan JSON is required."]
    for r in modules(root):
        t=r.get("type"); v=r.get("values") or {}; facts={}; kind=None
        # Unknown plan values remain absent; never replace missing values with permissive defaults.
        if t=="google_sql_database_instance":
            kind="cloud_sql"; settings=(v.get("settings") or [{}])[0]; ip=(settings.get("ip_configuration") or [{}])[0]
            facts={"public_ip_enabled":ip.get("ipv4_enabled"),"ssl_mode":ip.get("ssl_mode"),"connection_name":v.get("connection_name")}
        elif t=="google_storage_bucket":
            kind="gcs_bucket"; facts={"public_access_prevention":v.get("public_access_prevention"),"uniform_bucket_access":v.get("uniform_bucket_level_access")}
        elif t=="google_cloud_run_v2_service":
            kind="cloud_run"; template=(v.get("template") or [{}])[0]
            facts={"service_account":template.get("service_account"),"invoker_iam_disabled":v.get("invoker_iam_disabled")}
        if kind:
            resources.append(resource("tf:"+r["address"],v.get("name") or r["address"],kind,"planned",facts,"terraform_plan",r["address"],at))
    if not resources: warnings.append("No supported GCP resource types found in this Terraform plan.")
    return resources,warnings
