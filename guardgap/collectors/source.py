"""Bounded static Python AST inventory. Does not execute or upload application code."""
import ast
import hashlib
import os
from pathlib import Path
from .common import resource

SKIP={".git",".venv","venv","node_modules","__pycache__","dist","build",".terraform","site-packages"}
AI_PREFIXES=("google.genai","vertexai","openai","anthropic","langchain","langgraph","crewai","google.adk")

def scan(repo, repository, at):
    root=Path(repo).resolve(); imports=set(); routes=set(); env=set(); warnings=[]; count=0; total=0; checksums=[]
    for directory,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in SKIP and not d.startswith(".") and not (Path(directory)/d).is_symlink())
        for name in sorted(files):
            if not name.endswith(".py"): continue
            p=Path(directory)/name
            if p.is_symlink() or p.stat().st_size>1_000_000: continue
            count+=1; total+=p.stat().st_size
            if count>2000 or total>20_000_000:
                warnings.append("Python scan stopped at the 2,000-file / 20 MB limit.")
                dirs[:]=[]; break
            data=p.read_bytes(); relative=str(p.relative_to(root)); checksums.append(relative+":"+hashlib.sha256(data).hexdigest())
            try: tree=ast.parse(data,filename=relative)
            except (SyntaxError,UnicodeDecodeError): warnings.append(f"Could not parse Python file: {relative}"); continue
            for node in ast.walk(tree):
                if isinstance(node,ast.Import): imports.update(n.name for n in node.names)
                if isinstance(node,ast.ImportFrom) and node.module:
                    imports.add(node.module)
                    imports.update(node.module+"."+a.name for a in node.names if a.name!="*")
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    for d in node.decorator_list:
                        if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in {"get","post","put","delete","patch","route"} and d.args and isinstance(d.args[0],ast.Constant) and isinstance(d.args[0].value,str):
                            routes.add(f"{d.func.attr.upper()} {d.args[0].value} ({relative}:{node.lineno})")
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {"getenv","get"} and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                    try: target=ast.unparse(node.func)
                    except Exception: target=""
                    if target in {"os.getenv","os.environ.get"}: env.add(node.args[0].value)
            if len(warnings)>90: break
        if count>2000 or total>20_000_000: break
    facts={"imports":sorted(imports)[:1000],"routes":sorted(routes)[:1000],"env_references":sorted(env)[:500],"ai_signals":sorted({prefix for prefix in AI_PREFIXES if any(i==prefix or i.startswith(prefix+".") for i in imports)})}
    rid="source:"+hashlib.sha256(repository.encode()).hexdigest()[:16]
    r=resource(rid,repository.rsplit("/",1)[-1],"python_component","source",facts,"python_ast",f"{repository}: {min(count,2000)} Python files",at)
    r.evidence.sha256=hashlib.sha256("\n".join(checksums).encode()).hexdigest()
    if not count: warnings.append("No Python source files were found. Other languages are not analyzed in v0.1.")
    return [r],warnings[:100]
