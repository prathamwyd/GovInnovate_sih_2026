"""GovPilot API: a single-file Flask + PostgreSQL backend.

Run with: flask --app app run --debug
Required environment: DATABASE_URL, JWT_SECRET_KEY. See .env.example.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import jwt
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/govpilot"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
    ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", "admin123"),
    UPLOAD_FOLDER=os.getenv("UPLOAD_FOLDER", "uploads"),
    MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024,
)
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": cors_origins}}, supports_credentials=True)
db = SQLAlchemy(app)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(db.Model):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[Role] = relationship(back_populates="users")


class Challenge(db.Model):
    __tablename__ = "government_challenges"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="Draft")
    stage: Mapped[str] = mapped_column(String(40), default="Problem")
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, default="")
    baseline: Mapped[str] = mapped_column(Text, default="")
    desired_outcome: Mapped[str] = mapped_column(Text, default="")
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    kpis: Mapped[list] = mapped_column(JSON, default=list)
    pilot_requirements: Mapped[str] = mapped_column(Text, default="")
    estimated_budget: Mapped[str] = mapped_column(String(80), default="")
    pilot_duration_days: Mapped[int] = mapped_column(default=90)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Startup(db.Model):
    __tablename__ = "startup_proposals"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(120), nullable=False)
    proposal: Mapped[str] = mapped_column(Text, default="")
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    readiness: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Expert(db.Model):
    __tablename__ = "experts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    organisation: Mapped[str] = mapped_column(String(255), default="")
    specialisms: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)


class Evaluation(db.Model):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("government_challenges.id"), nullable=False)
    startup_id: Mapped[str] = mapped_column(ForeignKey("startup_proposals.id"), nullable=False)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("experts.id"))
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(String(80), default="Pending")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Pilot(db.Model):
    __tablename__ = "pilots"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: str(uuid.uuid4()))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("government_challenges.id"), nullable=False)
    startup_id: Mapped[str] = mapped_column(ForeignKey("startup_proposals.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="Active Pilot")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kpis: Mapped[list] = mapped_column(JSON, default=list)
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    feedback: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Score(db.Model):
    __tablename__ = "pilot_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[str] = mapped_column(ForeignKey("pilots.id"), nullable=False)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    overall_score: Mapped[int] = mapped_column(default=0)
    decision: Mapped[str] = mapped_column(String(100), default="Not Ready for Scale Review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Procurement(db.Model):
    __tablename__ = "procurement_workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[str] = mapped_column(ForeignKey("pilots.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="ACTION REQUIRED")
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    handoff_summary: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Notification(db.Model):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UploadedFile(db.Model):
    __tablename__ = "uploaded_evidence_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[str | None] = mapped_column(ForeignKey("pilots.id"))
    challenge_id: Mapped[str | None] = mapped_column(ForeignKey("government_challenges.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shortlist(db.Model):
    __tablename__ = "startup_shortlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("government_challenges.id"), nullable=False)
    startup_id: Mapped[str] = mapped_column(ForeignKey("startup_proposals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


MODELS = {"challenge": Challenge, "startup": Startup, "expert": Expert, "evaluation": Evaluation, "pilot": Pilot}

def jsonable(obj):
    if isinstance(obj, list): return [jsonable(x) for x in obj]
    if isinstance(obj, dict): return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, datetime): return obj.isoformat()
    if hasattr(obj, "__table__"):
        result = {c.name: jsonable(getattr(obj, c.name)) for c in obj.__table__.columns}
        if isinstance(obj, User) and obj.role:
            result["role"] = {"id": obj.role.id, "name": obj.role.name}
        return result
    return obj


def token_for(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "role": user.role.name, "exp": utcnow() + timedelta(hours=12)}, app.config["JWT_SECRET_KEY"], algorithm="HS256")


def auth(required_roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            raw = request.headers.get("Authorization", "")
            try:
                payload = jwt.decode(raw.removeprefix("Bearer "), app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
                user = db.session.get(User, int(payload["sub"]))
                if not user or not user.is_active or (required_roles and user.role.name not in required_roles): raise ValueError
                g.user = user
            except Exception:
                return jsonify(error="Authentication required"), 401
            return fn(*args, **kwargs)
        return wrapped
    return decorator


@app.get("/api/health")
def health(): return jsonify(status="ok", database="configured")


@app.post("/api/auth/register")
def register():
    body = request.get_json() or {}
    if not body.get("email") or not body.get("password") or not body.get("full_name"): return jsonify(error="email, password and full_name are required"), 400
    if User.query.filter_by(email=body["email"].lower()).first(): return jsonify(error="Email already registered"), 409
    role_name = "officer"
    role = Role.query.filter_by(name=role_name).first()
    if not role: return jsonify(error="Invalid role"), 400
    user = User(email=body["email"].lower(), full_name=body["full_name"], password_hash=generate_password_hash(body["password"]), role=role, last_login_at=utcnow())
    db.session.add(user); db.session.commit()
    return jsonify(user=jsonable(user), access_token=token_for(user)), 201


@app.post("/api/auth/login")
def login():
    body = request.get_json() or {}; user = User.query.filter_by(email=body.get("email", "").lower()).first()
    if not user or not check_password_hash(user.password_hash, body.get("password", "")): return jsonify(error="Invalid credentials"), 401
    user.last_login_at = utcnow(); db.session.commit()
    return jsonify(user=jsonable(user), access_token=token_for(user))


@app.get("/api/auth/me")
@auth()
def me(): return jsonify(user=jsonable(g.user))


@app.post("/api/admin/login")
def admin_login():
    body = request.get_json() or {}
    if body.get("password") != app.config["ADMIN_PASSWORD"]: return jsonify(error="Invalid admin password"), 401
    role = Role.query.filter_by(name="admin").first()
    user = User.query.filter_by(email="admin@govpilot.local").first()
    if not user:
        user = User(email="admin@govpilot.local", full_name="GovPilot Administrator", password_hash=generate_password_hash(app.config["ADMIN_PASSWORD"]), role=role)
        db.session.add(user); db.session.commit()
    user.last_login_at = utcnow(); db.session.commit()
    return jsonify(user=jsonable(user), access_token=token_for(user))


def crud_routes(name, model, roles=("admin", "officer", "evaluator", "startup")):
    endpoint = f"/api/{name}s"
    @app.get(endpoint, endpoint=f"{name}_collection")
    @auth()
    def collection(model=model): return jsonify(items=[jsonable(x) for x in model.query.order_by(model.created_at.desc() if hasattr(model, "created_at") else model.id.desc()).all()])
    @app.post(endpoint, endpoint=f"{name}_create")
    @auth(roles)
    def create(model=model):
        item = model(**(request.get_json() or {})); db.session.add(item); db.session.commit(); return jsonify(item=jsonable(item)), 201
    @app.get(endpoint + "/<string:item_id>", endpoint=f"{name}_get")
    @auth()
    def get_one(item_id, model=model):
        item = db.session.get(model, int(item_id) if model is Expert or model is Evaluation else item_id)
        return (jsonify(item=jsonable(item)) if item else (jsonify(error="Not found"), 404))
    @app.patch(endpoint + "/<string:item_id>", endpoint=f"{name}_update")
    @auth(roles)
    def update(item_id, model=model):
        item = db.session.get(model, int(item_id) if model is Expert or model is Evaluation else item_id)
        if not item: return jsonify(error="Not found"), 404
        for key, value in (request.get_json() or {}).items():
            if hasattr(item, key) and key not in {"id", "created_at"}: setattr(item, key, value)
        db.session.commit(); return jsonify(item=jsonable(item))
    @app.delete(endpoint + "/<string:item_id>", endpoint=f"{name}_delete")
    @auth(("admin",))
    def delete(item_id, model=model):
        item = db.session.get(model, int(item_id) if model is Expert or model is Evaluation else item_id)
        if not item: return jsonify(error="Not found"), 404
        db.session.delete(item); db.session.commit(); return "", 204

for _name, _model in MODELS.items(): crud_routes(_name, _model)


@app.get("/api/analytics")
@auth()
def analytics():
    return jsonify(challenges=Challenge.query.count(), startups=Startup.query.count(), pilots=Pilot.query.count(), evaluations=Evaluation.query.count(), active_pilots=Pilot.query.filter_by(status="Active Pilot").count(), average_score=db.session.query(func.avg(Score.overall_score)).scalar() or 0)


@app.get("/api/admin/users")
@auth(("admin",))
def admin_users():
    return jsonify(items=[jsonable(user) for user in User.query.order_by(User.created_at.desc()).all()])


@app.patch("/api/admin/users/<int:user_id>")
@auth(("admin",))
def update_admin_user(user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify(error="User not found"), 404
    body = request.get_json() or {}
    if "role" in body:
        role = Role.query.filter_by(name=body["role"]).first()
        if not role: return jsonify(error="Invalid role"), 400
        user.role = role
    if "is_active" in body: user.is_active = bool(body["is_active"])
    db.session.commit()
    return jsonify(item=jsonable(user))


@app.get("/api/notifications")
@auth()
def notifications():
    items = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.created_at.desc()).all()
    return jsonify(items=[jsonable(item) for item in items])


@app.patch("/api/notifications/<int:notification_id>")
@auth()
def mark_notification_read(notification_id):
    item = Notification.query.filter_by(id=notification_id, user_id=g.user.id).first()
    if not item: return jsonify(error="Not found"), 404
    item.read_at = (request.get_json() or {}).get("read_at") or utcnow(); db.session.commit()
    return jsonify(item=jsonable(item))


@app.get("/api/shortlists/<string:challenge_id>")
@auth()
def get_shortlist(challenge_id):
    return jsonify(startup_ids=[x.startup_id for x in Shortlist.query.filter_by(user_id=g.user.id, challenge_id=challenge_id).all()])


@app.put("/api/shortlists/<string:challenge_id>/<string:startup_id>")
@auth(("admin", "officer", "startup"))
def put_shortlist(challenge_id, startup_id):
    if not db.session.get(Challenge, challenge_id) or not db.session.get(Startup, startup_id): return jsonify(error="Challenge or startup not found"), 404
    if not Shortlist.query.filter_by(user_id=g.user.id, challenge_id=challenge_id, startup_id=startup_id).first():
        db.session.add(Shortlist(user_id=g.user.id, challenge_id=challenge_id, startup_id=startup_id)); db.session.commit()
    return jsonify(status="shortlisted"), 201


@app.delete("/api/shortlists/<string:challenge_id>/<string:startup_id>")
@auth(("admin", "officer", "startup"))
def delete_shortlist(challenge_id, startup_id):
    item = Shortlist.query.filter_by(user_id=g.user.id, challenge_id=challenge_id, startup_id=startup_id).first()
    if item: db.session.delete(item); db.session.commit()
    return "", 204


def score_pilot(pilot: Pilot, overrides=None):
    kpis = overrides.get("kpis", pilot.kpis) if overrides else pilot.kpis
    evidence = overrides.get("evidence", pilot.metadata_json.get("evidence", [])) if overrides else pilot.metadata_json.get("evidence", [])
    achieved = sum(1 for x in kpis if x.get("status") == "Target achieved" or x.get("progress", 0) >= 100)
    kpi_score = round(achieved / len(kpis) * 100) if kpis else 0
    evidence_score = round(sum(1 for x in evidence if x.get("status") in ("Submitted", "Available")) / len(evidence) * 100) if evidence else 0
    categories = [{"id": "kpi", "name": "KPI Achievement", "score": kpi_score, "weight": 40}, {"id": "evidence", "name": "Evidence Completeness", "score": evidence_score, "weight": 30}, {"id": "operations", "name": "Operational Feasibility", "score": 80, "weight": 30}]
    overall = round(sum(x["score"] * x["weight"] for x in categories) / 100)
    decision = "Ready for Scale Review" if overall >= 85 and kpi_score == 100 and evidence_score == 100 else "Conditional — Additional Evidence Required" if overall >= 60 else "Not Ready for Scale Review"
    return {"pilotId": pilot.id, "categories": categories, "overallScore": overall, "decision": decision, "generatedAt": utcnow().isoformat()}


@app.post("/api/pilots/<string:pilot_id>/score")
@auth(("admin", "officer", "evaluator"))
def score(pilot_id):
    pilot = db.session.get(Pilot, pilot_id)
    if not pilot: return jsonify(error="Not found"), 404
    result = score_pilot(pilot, request.get_json() or {})
    db.session.add(Score(pilot_id=pilot.id, categories=result["categories"], overall_score=result["overallScore"], decision=result["decision"])); db.session.commit()
    return jsonify(scorecard=result)


@app.get("/api/pilots/<string:pilot_id>/scorecard")
@auth()
def scorecard(pilot_id):
    pilot = db.session.get(Pilot, pilot_id)
    return (jsonify(scorecard=score_pilot(pilot)) if pilot else (jsonify(error="Not found"), 404))


@app.get("/api/pilots/<string:pilot_id>/procurement")
@auth()
def procurement(pilot_id):
    pilot = db.session.get(Pilot, pilot_id)
    if not pilot: return jsonify(error="Not found"), 404
    score = score_pilot(pilot); checklist = [{"id": "outcomes", "name": "Pilot Outcome Evidence", "status": "READY" if score["categories"][0]["score"] == 100 else "PARTIAL"}, {"id": "technical", "name": "Technical Documentation", "status": "PARTIAL"}, {"id": "risk", "name": "Risk Assessment", "status": "ACTION REQUIRED" if pilot.risks else "READY"}]
    readiness = round(sum(100 if x["status"] == "READY" else 65 if x["status"] == "PARTIAL" else 30 for x in checklist) / len(checklist))
    return jsonify(pilotId=pilot_id, overallReadiness=readiness, status="READY" if readiness >= 85 else "CONDITIONAL", checklist=checklist, outstandingRequirements=[x["name"] for x in checklist if x["status"] != "READY"])


@app.post("/api/files")
@auth(("admin", "officer", "startup", "evaluator"))
def upload_file():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename: return jsonify(error="file is required"), 400
    stored = f"{uuid.uuid4().hex}_{secure_filename(uploaded.filename)}"; path = Path(app.config["UPLOAD_FOLDER"]) / stored; uploaded.save(path)
    item = UploadedFile(pilot_id=request.form.get("pilot_id"), challenge_id=request.form.get("challenge_id"), uploaded_by=g.user.id, original_name=uploaded.filename, stored_name=stored, mime_type=uploaded.mimetype or "application/octet-stream", size_bytes=path.stat().st_size)
    db.session.add(item); db.session.commit(); return jsonify(file={**jsonable(item), "url": f"/api/files/{item.id}"}), 201


@app.get("/api/files/<int:file_id>")
@auth()
def download_file(file_id):
    item = db.session.get(UploadedFile, file_id)
    return (send_from_directory(app.config["UPLOAD_FOLDER"], item.stored_name, as_attachment=True, download_name=item.original_name) if item else (jsonify(error="Not found"), 404))


@app.errorhandler(413)
def too_large(_): return jsonify(error="File exceeds MAX_UPLOAD_MB"), 413


with app.app_context():
    db.create_all()
    db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ"))
    for role_name in ("admin", "officer", "evaluator", "startup"):
        if not Role.query.filter_by(name=role_name).first(): db.session.add(Role(name=role_name))
    db.session.commit()

if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
