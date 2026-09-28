"""Versioned evidence contract. Collectors submit observations, never pass/fail verdicts."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Evidence(StrictModel):
    source: Literal["gcp_api", "terraform_plan", "python_ast", "junit", "build", "fixture"]
    locator: str = Field(max_length=500)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    collected_at: datetime

    @field_validator("collected_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        if value > datetime.now(timezone.utc) + __import__('datetime').timedelta(minutes=5):
            raise ValueError("future evidence timestamp")
        return value

class Facts(StrictModel):
    # Only security-relevant normalized fields are accepted. No credentials or raw env values.
    invoker_iam_disabled: bool | None = None
    iam_bindings: list[dict[str, str | list[str] | bool]] = Field(default_factory=list, max_length=500)
    iam_complete: bool = False
    service_account: str | None = Field(default=None, max_length=300)
    image_digest: str | None = Field(default=None, max_length=300)
    ready: bool | None = None
    revision: str | None = Field(default=None, max_length=300)
    sql_connections: list[str] = Field(default_factory=list, max_length=100)
    secret_references: list[str] = Field(default_factory=list, max_length=100)
    public_ip_enabled: bool | None = None
    public_ip_present: bool | None = None
    ssl_mode: str | None = Field(default=None, max_length=100)
    connection_name: str | None = Field(default=None, max_length=300)
    public_access_prevention: str | None = Field(default=None, max_length=100)
    uniform_bucket_access: bool | None = None
    imports: list[str] = Field(default_factory=list, max_length=1000)
    routes: list[str] = Field(default_factory=list, max_length=1000)
    ai_signals: list[str] = Field(default_factory=list, max_length=100)
    env_references: list[str] = Field(default_factory=list, max_length=500)
    test_name: str | None = Field(default=None, max_length=500)
    test_passed: bool | None = None
    tested_image_digest: str | None = Field(default=None, max_length=300)

    @field_validator("iam_bindings")
    @classmethod
    def validate_bindings(cls, value):
        for binding in value:
            if set(binding) - {"role", "members", "conditional"}:
                raise ValueError("Unsupported IAM binding fields")
            if not isinstance(binding.get("role"), str) or len(binding["role"]) > 300:
                raise ValueError("IAM binding requires a role")
            members = binding.get("members")
            if not isinstance(members, list) or len(members) > 2000 or any(not isinstance(m, str) or len(m) > 500 for m in members):
                raise ValueError("Invalid IAM members")
        return value

class Resource(StrictModel):
    id: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["cloud_run", "cloud_sql", "gcs_bucket", "project_iam", "python_component", "authorization_test"]
    layer: Literal["deployed", "planned", "source", "test"]
    facts: Facts
    evidence: Evidence

class Edge(StrictModel):
    source: str = Field(max_length=500)
    target: str = Field(max_length=500)
    relationship: str = Field(max_length=100)
    confidence: Literal["evidenced", "inferred"]
    reason: str = Field(max_length=500)

class Bundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    bundle_id: UUID
    application_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    environment: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    repository: str = Field(min_length=1, max_length=500)
    commit: str = Field(pattern=r"^[a-fA-F0-9]{7,64}$")
    collected_at: datetime
    collector_version: str = Field(default="0.1.0", max_length=50)
    expected_image_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    deployment_status: Literal["succeeded", "failed", "unknown", "not_deployed"] = "unknown"
    demo: bool = False
    resources: list[Resource] = Field(max_length=1000)
    edges: list[Edge] = Field(default_factory=list, max_length=3000)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    _aware = field_validator("collected_at")(Evidence.aware.__func__)

    @model_validator(mode="after")
    def check_integrity(self):
        ids = [r.id for r in self.resources]
        if len(ids) != len(set(ids)):
            raise ValueError("resource ids must be unique within a bundle")
        if any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError("edge references missing resource")
        if not self.demo and any(r.evidence.source == "fixture" for r in self.resources):
            raise ValueError("fixture evidence requires demo=true")
        return self
