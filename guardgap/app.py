import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from .db import connect, Application, Token, Snapshot, Report, Session, Audit, LoginAttempt
from .models import Bundle, StrictModel
from .engine import assess, compare, CATALOG

STATIC = Path(__file__).parent / "static"

def digest(s): return hashlib.sha256(s.encode()).hexdigest()

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt:{salt}:{result}"

def password_matches(password, encoded):
    try:
        _, salt, _ = encoded.split(":")
        return hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError): return False

class Login(StrictModel):
    password: str = Field(min_length=1, max_length=1024)
class NewApplication(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    name: str = Field(min_length=1,max_length=120)
    description: str = Field(default="",max_length=2000)
class NewToken(StrictModel):
    environment: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    label: str = Field(default="CI collector",min_length=1,max_length=120)
class Demo(StrictModel):
    variant: str = Field(pattern=r"^(before|after|partial)$")


def create_app(database_url=None, admin_password=None, demo_enabled=None, secure_cookie=None):
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/guardgap.db")
    if database_url.startswith("sqlite:///"):
        Path(database_url[10:]).parent.mkdir(parents=True, exist_ok=True)
    sessions, engine = connect(database_url)
    encoded = os.getenv("GUARDGAP_ADMIN_PASSWORD_HASH", "")
    plain = admin_password or os.getenv("GUARDGAP_ADMIN_PASSWORD", "")
    if plain:
        if len(plain) < 12: raise RuntimeError("GUARDGAP_ADMIN_PASSWORD must contain at least 12 characters")
        encoded = password_hash(plain)
    if not encoded: raise RuntimeError("Set GUARDGAP_ADMIN_PASSWORD or GUARDGAP_ADMIN_PASSWORD_HASH. Run python scripts/bootstrap.py first.")
    demo_enabled = demo_enabled if demo_enabled is not None else os.getenv("GUARDGAP_DEMO", "false").lower() == "true"
    secure_cookie = secure_cookie if secure_cookie is not None else os.getenv("GUARDGAP_SECURE_COOKIE", "true").lower() == "true"
    max_age = int(os.getenv("GUARDGAP_MAX_EVIDENCE_HOURS", "24"))
    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()
    app = FastAPI(title="GuardGap", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.sessions = sessions

    @app.middleware("http")
    async def boundaries(request, call_next):
        # Reject oversized uploads even when Transfer-Encoding is chunked.
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks, total = [], 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > 5_000_000: return JSONResponse({"detail":"Maximum request size is 5 MB"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        return response

    def admin(request: Request):
        cookie = request.cookies.get("guardgap_session", "")
        with sessions() as db:
            s = db.get(Session, digest(cookie)) if cookie else None
            if not s or s.expires < time.time(): raise HTTPException(401,"Sign in required")
            if request.method not in {"GET","HEAD"} and not hmac.compare_digest(request.headers.get("x-guardgap-csrf", ""), s.csrf):
                raise HTTPException(403,"CSRF token required")
            return s.csrf

    def audit(db, action, **detail):
        db.add(Audit(id=str(uuid4()), action=action, detail=detail))

    def get_application(db, app_id):
        application = db.get(Application, app_id)
        if not application: raise HTTPException(404,"Application not found")
        return application

    def make_report(db, snapshot):
        previous_rows = db.scalars(select(Report).where(Report.application_id == snapshot.application_id, Report.environment == snapshot.environment).order_by(Report.created_at.desc()).limit(50)).all()
        # Never mix fixture history with real evidence or compare a late arrival against a newer snapshot.
        current = Bundle.model_validate(snapshot.payload)
        previous = None
        for row in previous_rows:
            prior = db.get(Snapshot,row.snapshot_id)
            if prior.payload.get("demo",False) == current.demo and prior.payload["repository"] == current.repository and Bundle.model_validate(prior.payload).collected_at <= current.collected_at:
                previous = row.payload; break
        result = assess(current, max_age_hours=max_age)
        result["changes"] = compare(result, previous)
        report = Report(id=str(uuid4()), snapshot_id=snapshot.id, application_id=snapshot.application_id, environment=snapshot.environment, payload=result)
        db.add(report); db.flush()
        return report

    def ingest(db, bundle, token_id=None):
        payload = bundle.model_dump(mode="json")
        content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        existing = db.get(Snapshot,str(bundle.bundle_id))
        if existing:
            if existing.content_hash != content_hash: raise HTTPException(409,"Bundle ID already used for different evidence")
            r = db.scalar(select(Report).where(Report.snapshot_id == existing.id).order_by(Report.created_at.desc()))
            return {"snapshot_id":existing.id,"report_id":r.id,"duplicate":True}
        snap = Snapshot(id=str(bundle.bundle_id), application_id=bundle.application_id, environment=bundle.environment, token_id=token_id, content_hash=content_hash, payload=payload)
        db.add(snap); db.flush()
        r = make_report(db,snap)
        audit(db,"evidence.ingested",application_id=bundle.application_id,environment=bundle.environment,snapshot_id=snap.id,token_id=token_id,demo=bundle.demo)
        try: db.commit()
        except IntegrityError:
            db.rollback(); raise HTTPException(409,"Concurrent bundle upload; retry this bundle")
        return {"snapshot_id":snap.id,"report_id":r.id,"duplicate":False}

    @app.get("/healthz")
    def health(): return {"status":"ok","version":"0.1.0"}

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = digest(request.client.host if request.client else "unknown")
        now = int(time.time())
        with sessions() as db:
            db.execute(delete(LoginAttempt).where(LoginAttempt.window < now-3600))
            attempt = db.get(LoginAttempt,ip)
            if attempt and now-attempt.window < 300 and attempt.attempts >= 10:
                raise HTTPException(429,"Too many attempts; try again in five minutes")
            if not password_matches(body.password,encoded):
                if not attempt:
                    db.add(LoginAttempt(key=ip,window=now,attempts=1))
                elif now-attempt.window >= 300:
                    attempt.window,attempt.attempts=now,1
                else: attempt.attempts += 1
                db.commit(); raise HTTPException(401,"Incorrect password")
            if attempt: db.delete(attempt)
            db.execute(delete(Session).where(Session.expires < now))
            session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.add(Session(digest=digest(session),csrf=csrf,expires=now+8*3600))
            audit(db,"admin.login"); db.commit()
            response.set_cookie("guardgap_session",session,httponly=True,secure=secure_cookie,samesite="strict",max_age=8*3600,path="/")
        return {"csrf":csrf}

    @app.get("/api/me")
    def me(csrf=Depends(admin)):
        return {"csrf":csrf,"demo_enabled":demo_enabled,"version":"0.1.0","max_evidence_hours":max_age}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, _=Depends(admin)):
        with sessions() as db:
            db.execute(delete(Session).where(Session.digest == digest(request.cookies.get("guardgap_session","")))); db.commit()
        response.delete_cookie("guardgap_session",path="/")
        return {"ok":True}

    @app.get("/api/schema",dependencies=[Depends(admin)])
    def schema(): return Bundle.model_json_schema()

    @app.get("/api/controls",dependencies=[Depends(admin)])
    def controls(): return CATALOG

    @app.get("/api/applications",dependencies=[Depends(admin)])
    def applications():
        with sessions() as db:
            return [{"id":a.id,"name":a.name,"description":a.description,"created_at":a.created_at} for a in db.scalars(select(Application).order_by(Application.created_at))]

    @app.post("/api/applications",dependencies=[Depends(admin)])
    def create_application(body: NewApplication):
        with sessions() as db:
            if db.get(Application,body.id): raise HTTPException(409,"Application ID already exists")
            db.add(Application(**body.model_dump())); audit(db,"application.created",application_id=body.id); db.commit()
        return body

    @app.get("/api/applications/{app_id}/tokens",dependencies=[Depends(admin)])
    def tokens(app_id: str):
        with sessions() as db:
            get_application(db,app_id)
            return [{"id":t.id,"label":t.label,"environment":t.environment,"revoked":bool(t.revoked),"created_at":t.created_at} for t in db.scalars(select(Token).where(Token.application_id==app_id))]

    @app.post("/api/applications/{app_id}/tokens",dependencies=[Depends(admin)])
    def create_token(app_id: str, body: NewToken):
        raw = "gg_" + secrets.token_urlsafe(36)
        with sessions() as db:
            get_application(db,app_id)
            t=Token(id=str(uuid4()),application_id=app_id,environment=body.environment,label=body.label,digest=digest(raw))
            db.add(t); audit(db,"token.created",application_id=app_id,environment=body.environment); db.commit()
        return {"id":t.id,"token":raw,"environment":body.environment}

    @app.delete("/api/tokens/{token_id}",dependencies=[Depends(admin)])
    def revoke(token_id:str):
        with sessions() as db:
            t=db.get(Token,token_id)
            if not t: raise HTTPException(404,"Token not found")
            t.revoked=1; audit(db,"token.revoked",token_id=token_id); db.commit()
        return {"ok":True}

    @app.post("/api/ingest")
    def upload(bundle: Bundle, request: Request):
        authorization=request.headers.get("authorization","")
        if not authorization.startswith("Bearer "): raise HTTPException(401,"Collector bearer token required")
        with sessions() as db:
            t=db.scalar(select(Token).where(Token.digest==digest(authorization[7:]),Token.revoked==0))
            if not t: raise HTTPException(401,"Invalid or revoked collector token")
            if t.application_id != bundle.application_id or t.environment != bundle.environment:
                raise HTTPException(403,"Token application/environment does not match evidence")
            if bundle.demo: raise HTTPException(400,"Demo evidence is only accepted through the explicit demo workflow")
            return ingest(db,bundle,t.id)

    @app.post("/api/import",dependencies=[Depends(admin)])
    def manual_import(bundle: Bundle):
        if bundle.demo and not demo_enabled: raise HTTPException(403,"Demo mode disabled")
        with sessions() as db:
            get_application(db,bundle.application_id)
            return ingest(db,bundle)

    @app.get("/api/applications/{app_id}/reports",dependencies=[Depends(admin)])
    def reports(app_id: str):
        with sessions() as db:
            get_application(db,app_id)
            rows=db.scalars(select(Report).where(Report.application_id==app_id).order_by(Report.created_at.desc()).limit(200)).all()
            return [{"id":r.id,"environment":r.environment,"created_at":r.created_at,"counts":r.payload["counts"],"demo":r.payload["demo"],"commit":db.get(Snapshot,r.snapshot_id).payload["commit"],"evidence_collected_at":db.get(Snapshot,r.snapshot_id).payload["collected_at"]} for r in rows]

    @app.get("/api/reports/{report_id}",dependencies=[Depends(admin)])
    def report(report_id:str):
        with sessions() as db:
            r=db.get(Report,report_id)
            if not r: raise HTTPException(404,"Report not found")
            s=db.get(Snapshot,r.snapshot_id)
            return {"id":r.id,"snapshot_id":s.id,"application_id":r.application_id,"environment":r.environment,"created_at":r.created_at,"report":r.payload,"bundle":s.payload}

    @app.post("/api/snapshots/{snapshot_id}/assess",dependencies=[Depends(admin)])
    def reassess(snapshot_id:str):
        with sessions() as db:
            s=db.get(Snapshot,snapshot_id)
            if not s: raise HTTPException(404,"Snapshot not found")
            r=make_report(db,s); audit(db,"snapshot.reassessed",snapshot_id=s.id); db.commit()
            return {"report_id":r.id}

    @app.post("/api/demo",dependencies=[Depends(admin)])
    def demo(body: Demo):
        if not demo_enabled: raise HTTPException(403,"Demo mode disabled")
        from .demo import make_demo
        with sessions() as db:
            if not db.get(Application,"support-assistant-demo"):
                db.add(Application(id="support-assistant-demo",name="Support assistant · demo",description="Synthetic fixture evidence. No cloud resources are created.")); db.flush()
            return ingest(db,make_demo(body.variant))

    @app.get("/api/audit",dependencies=[Depends(admin)])
    def audit_log():
        with sessions() as db:
            return [{"id":a.id,"at":a.created_at,"action":a.action,"detail":a.detail} for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200))]

    @app.get("/")
    def index(): return FileResponse(STATIC/"index.html")
    app.mount("/static",StaticFiles(directory=STATIC),name="static")
    return app
