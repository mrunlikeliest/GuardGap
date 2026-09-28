import hashlib
import json
from datetime import datetime, timezone
from ..models import Resource, Evidence, Facts

def now(): return datetime.now(timezone.utc)

def resource(id, name, kind, layer, facts, source, locator, at=None):
    # Hash only normalized facts. Never send raw configuration or secret-bearing snapshots.
    facts = Facts.model_validate(facts)
    checksum = hashlib.sha256(json.dumps(facts.model_dump(mode="json"),sort_keys=True).encode()).hexdigest()
    return Resource(id=id,name=name,kind=kind,layer=layer,facts=facts,evidence=Evidence(source=source,locator=locator,sha256=checksum,collected_at=at or now()))

def bindings(policy):
    if not isinstance(policy,dict): return []
    return [{"role":b.get("role",""),"members":b.get("members",[]),"conditional":bool(b.get("condition"))} for b in policy.get("bindings",[]) if isinstance(b,dict)]

def sha_digest(value):
    import re
    match = re.search(r"sha256:[a-f0-9]{64}$",value or "")
    return match.group(0) if match else None
