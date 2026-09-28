"""Select one explicitly named negative authorization test; do not infer its meaning."""
from pathlib import Path
import xml.etree.ElementTree as ET
from .common import resource

def collect(path,test_name,tested_image_digest,at):
    data=Path(path).read_bytes()
    if len(data)>2_000_000 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("JUnit file too large or contains unsupported XML entities")
    root=ET.fromstring(data)
    matches=[t for t in root.iter("testcase") if t.get("name")==test_name or f"{t.get('classname','')}.{t.get('name','')}"==test_name]
    passed=None
    if len(matches)==1:
        t=matches[0]
        passed=None if t.find("skipped") is not None else t.find("failure") is None and t.find("error") is None
    r=resource("test:negative-authorization",test_name,"authorization_test","test",{"test_name":test_name,"test_passed":passed,"tested_image_digest":tested_image_digest},"junit",Path(path).name,at)
    import hashlib
    r.evidence.sha256=hashlib.sha256(data).hexdigest()
    return r
