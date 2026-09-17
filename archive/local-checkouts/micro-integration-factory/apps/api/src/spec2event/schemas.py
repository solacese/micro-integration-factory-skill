from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class ApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class UploadPreviewResponse(ApiSchema):
    upload_id: str
    filename: str
    source_type: str = "openapi"
    service_name: str
    summary: dict[str, Any]


class CreateRunRequest(ApiSchema):
    upload_id: str
    deployment_target: Literal[
        "local_docker", "ec2_docker_host", "kubernetes_helm", "ephemeral_ec2"
    ] = (
        "local_docker"
    )
    auto_build: bool = False
    auto_deploy: bool = False


class ActiveDeploymentResponse(ApiSchema):
    instance_id: str | None = None
    private_service_url: str | None = None
    public_ip: str | None = None
    expires_at: str | None = None
    target: str
    status: str


class RunStepLogResponse(ApiSchema):
    id: str
    step_name: str
    status: str
    message: str
    created_at: str


class RunResponse(ApiSchema):
    id: str
    upload_id: str
    source_type: str = "openapi"
    service_name: str
    status: str
    deployment_target: str
    image_tag: str | None = None
    service_url: str | None = None
    created_at: str
    updated_at: str
    last_message: str | None = None
    canonical_model: dict[str, Any] | None = None
    active_deployment: ActiveDeploymentResponse | None = None
    steps: list[RunStepLogResponse] = Field(default_factory=list)


class ArtifactResponse(ApiSchema):
    id: str
    run_id: str
    kind: str
    path: str
    language: str | None = None
    revision: int
    content: str | None = None
    created_at: str


class UpdateArtifactRequest(ApiSchema):
    content: str


class SettingsUpdateRequest(ApiSchema):
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    solace_broker_url: str | None = None
    solace_vpn: str | None = None
    solace_username: str | None = None
    solace_password: str | None = None
    solace_web_messaging_url: str | None = None
    event_portal_base_url: str | None = None
    event_portal_token: str | None = None
    k8s_api_server: str | None = None
    k8s_token: str | None = None
    k8s_namespace: str | None = None
    k8s_ca_cert: str | None = None
    rancher_url: str | None = None
    rancher_token: str | None = None
    container_registry: str | None = None
    container_registry_username: str | None = None
    container_registry_password: str | None = None
    container_image_prefix: str | None = None
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    litellm_model: str | None = None
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    deploy_ec2_host: str | None = None
    deploy_ec2_ssh_user: str | None = None
    deploy_ec2_ssh_private_key: str | None = None
    deploy_ec2_port: int | None = None
    public_base_url: str | None = None


class SettingsView(ApiSchema):
    has_aws_config: bool
    has_solace_config: bool
    has_event_portal_config: bool
    has_lite_llm_config: bool
    has_registry_config: bool
    has_ec2_config: bool
    public_base_url: str | None = None
    litellm_base_url: str | None = None
    litellm_model: str | None = None


class LiteLlmTestRequest(ApiSchema):
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    litellm_model: str | None = None


class LiteLlmTestResponse(ApiSchema):
    ok: bool
    message: str
    model: str | None = None


SchemaPackFormat = Literal[
    "hl7",
    "generic_edi",
    "edifact",
    "odette",
    "ansi_x12",
    "json_schema",
    "xml_schema",
    "csv_layout",
    "fixed_width",
]


class SchemaPackCreateRequest(ApiSchema):
    name: str
    schema_format: SchemaPackFormat
    version: str | None = None
    message_type: str | None = None
    industry: str | None = None
    raw_content: str
    filename: str | None = None
    content_type: str | None = None


class SchemaPackSummaryResponse(ApiSchema):
    id: str
    name: str
    schema_format: str
    version: str | None = None
    message_type: str | None = None
    industry: str | None = None
    filename: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class SchemaPackResponse(SchemaPackSummaryResponse):
    raw_content: str


class BuildDeployResponse(ApiSchema):
    run_id: str
    status: str
    message: str


class TestInvocationRequest(ApiSchema):
    operation_id: str | None = None
    method: str = "POST"
    path: str
    payload: dict[str, Any] | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class TestInvocationResponse(ApiSchema):
    invocation_id: str
    correlation_id: str
    response_status: int | None = None
    response_payload: dict[str, Any] | None = None


class EventLogResponse(ApiSchema):
    id: str
    run_id: str
    correlation_id: str
    stage: str
    topic_name: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str


class EventPortalSyncResponse(ApiSchema):
    id: str
    run_id: str
    artifact_type: str
    artifact_name: str
    external_id: str | None = None
    status: str
    manual_action: str | None = None
    created_at: str


TransformLanguage = Literal["java_sdk", "groovy", "dataweave"]


class SolaceSubscriptionRequest(ApiSchema):
    broker_url: str
    vpn: str
    username: str
    password: str
    topic_filter: str


class SolaceSubscriptionResponse(ApiSchema):
    id: str
    topic_filter: str
    status: str
    message: str


class CapturedEventResponse(ApiSchema):
    id: str
    subscription_id: str
    broker_url: str
    topic_filter: str
    topic_name: str
    headers: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


InputMessageFormat = Literal[
    "json",
    "xml",
    "csv",
    "fixed_width",
    "hl7",
    "edifact",
    "ansi_x12",
    "odette",
    "text",
]


class InputMessageRequest(ApiSchema):
    topic_name: str = "systems/input/message/v1"
    source_name: str | None = None
    input_format: InputMessageFormat = "json"
    payload: Any = Field(default_factory=dict)
    headers: dict[str, Any] = Field(default_factory=dict)


class CreateBuilderSessionRequest(ApiSchema):
    captured_event_id: str
    transform_language: TransformLanguage = "java_sdk"


class ChatMessageRequest(ApiSchema):
    content: str
    transform_language: TransformLanguage | None = None
    schema_context: str | None = None
    schema_pack_id: str | None = None


class ChatMessageResponse(ApiSchema):
    id: str
    role: str
    content: str
    draft: dict[str, Any] | None = None
    created_at: str


class BuilderSessionResponse(ApiSchema):
    id: str
    transform_language: TransformLanguage
    status: str
    intent_summary: str | None = None
    draft: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    generated_run_id: str | None = None
    captured_event: CapturedEventResponse
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class PreviewResponse(ApiSchema):
    session_id: str
    transform_language: TransformLanguage
    sample_output: dict[str, Any]
    draft: dict[str, Any] | None = None


class WorkerJobResponse(ApiSchema):
    id: str
    builder_session_id: str
    job_type: str
    status: str
    project_path: str | None = None
    image_tag: str | None = None
    logs: str
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class WorkerJobResultRequest(ApiSchema):
    status: str
    logs: str | None = None
    image_tag: str | None = None
    project_path: str | None = None
    result: dict[str, Any] | None = None


class GenerateBuilderResponse(ApiSchema):
    session: BuilderSessionResponse
    run: RunResponse
    worker_job: WorkerJobResponse
