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
    service_name: str
    summary: dict[str, Any]
    source_mode: str = "openapi"
    runtime_blueprint: str | None = None


class CreateRunRequest(ApiSchema):
    upload_id: str
    deployment_target: Literal[
        "local_docker", "ec2_docker_host", "kubernetes_helm", "ephemeral_ec2"
    ] = (
        "local_docker"
    )
    auto_build: bool = False
    auto_deploy: bool = False


class ConnectorEventInput(ApiSchema):
    name: str
    entity: str | None = None
    action: str | None = None
    summary: str | None = None
    topic_name: str | None = None
    schema_name: str | None = None
    payload_example: dict[str, Any] | None = None


class ConnectorSpecRequest(ApiSchema):
    source_mode: Literal[
        "webhook",
        "file",
        "mqtt",
        "kafka",
        "queue",
        "amqp",
        "jms",
        "sftp",
        "ftp",
        "object_storage",
    ]
    name: str
    version: str = "1.0.0"
    description: str | None = None
    application_domain_name: str | None = None
    connector_pattern: str | None = None
    topic_root: str = "integration"
    source_details: dict[str, Any] = Field(default_factory=dict)
    events: list[ConnectorEventInput] = Field(default_factory=list)


class DatabaseDiscoveryRequest(ApiSchema):
    database_url: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    schema_name: str = Field(default="public", alias="schema")
    preferred_table: str = "products"
    sslmode: str = "require"
    application_domain_name: str | None = None
    topic_root: str = "commerce"


class DeploymentApprovalRequest(ApiSchema):
    notes: str | None = None
    approved_by: str = "human-review"


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
    service_name: str
    status: str
    deployment_target: str
    source_mode: str = "openapi"
    adapter_type: str | None = None
    runtime_blueprint: str | None = None
    image_tag: str | None = None
    service_url: str | None = None
    created_at: str
    updated_at: str
    last_message: str | None = None
    canonical_model: dict[str, Any] | None = None
    active_deployment: ActiveDeploymentResponse | None = None
    deployment_approval_status: str = "not_requested"
    deployment_approval_notes: str | None = None
    deployment_approval_requested_at: str | None = None
    deployment_approved_at: str | None = None
    deployment_approved_by: str | None = None
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
