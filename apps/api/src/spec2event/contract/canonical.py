"""Canonical model contract for the Universal Micro-Integration Factory.

This module defines the Pydantic models that form the canonical contract between
source adapters, the generator service, and the downstream pipeline. The contract
is **direction-aware** and **connector/workflow/transform-based**.

Backward compatibility: the legacy keys (operations[], eventCandidates[],
stripeEnabled, testFixtures[], ingressType) remain supported and are populated
by existing adapters. The new connector/workflow/transform structure is additive.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Direction of data flow relative to Solace."""

    SOURCE = "source"  # External -> Solace
    TARGET = "target"  # Solace -> External
    BIDIRECTIONAL = "bidirectional"  # Both directions


class DeliveryModel(str, Enum):
    """How the connector delivers/receives data."""

    PUSH = "push"  # External system pushes (webhooks, HTTP POST)
    POLL = "poll"  # MI polls external system on a schedule
    STREAM = "stream"  # Continuous streaming (CDC, event bus)
    BATCH = "batch"  # Batch file/bulk transfer


class IngressType(str, Enum):
    """Legacy ingress pattern selection (kept for backward compat)."""

    REST_CONTROLLER = "rest_controller"
    POLLING_CONSUMER = "polling_consumer"
    EVENT_SUBSCRIBER = "event_subscriber"


class TransformEngine(str, Enum):
    """Available transformation engines."""

    PASSTHROUGH = "passthrough"
    FIELD_MAPPING = "field_mapping"
    JOLT = "jolt"
    DATAWEAVE = "dataweave"
    SCRIPTING = "scripting"  # JavaScript/Groovy/SpEL
    CUSTOM_JAVA = "custom_java"


# ---------------------------------------------------------------------------
# Event and Schema Models
# ---------------------------------------------------------------------------


class EventCandidate(BaseModel):
    """A candidate event that an operation may emit or consume."""

    operation_id: str = Field(alias="operationId", default="")
    canonical_event_name: str = Field(alias="canonicalEventName")
    topic_name: str = Field(alias="topicName")
    schema_name: str = Field(alias="schemaName")
    application_name: str = Field(alias="applicationName")
    emits_event: bool = Field(alias="emitsEvent", default=True)

    model_config = {"populate_by_name": True}


class Operation(BaseModel):
    """An operation extracted from the source specification.

    For REST sources these map to HTTP operations. For non-REST sources
    (streaming, database, file) the ``method`` and ``path`` fields may be
    synthetic or empty.
    """

    operation_id: str = Field(alias="operationId")
    method: str = ""
    path: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    request_schema_name: str | None = Field(alias="requestSchemaName", default=None)
    response_schema_name: str | None = Field(alias="responseSchemaName", default=None)
    request_schema: dict[str, Any] | None = Field(alias="requestSchema", default=None)
    response_schema: dict[str, Any] | None = Field(alias="responseSchema", default=None)
    emits_event: bool = Field(alias="emitsEvent", default=False)
    event_candidates: list[EventCandidate] = Field(
        alias="eventCandidates", default_factory=list
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Connector Model (new, additive)
# ---------------------------------------------------------------------------


class ConnectorSpec(BaseModel):
    """A connector declares how one side of a workflow binds to a system.

    One side of every workflow is always the Solace binder (id="solace").
    The other side is the external connector.
    """

    id: str
    system_kind: str = Field(
        default="rest",
        description=(
            "Category of the connected system "
            "(rest, database, file, kafka, mqtt, amqp, jms, sftp, grpc, graphql, etc.)"
        ),
    )
    direction: Direction = Direction.SOURCE
    transport: str = Field(default="", description="Spring Cloud Stream binder type")
    delivery_model: DeliveryModel = DeliveryModel.PUSH
    config: dict[str, Any] = Field(
        default_factory=dict, description="Connector-specific configuration"
    )


# ---------------------------------------------------------------------------
# Transform Model (new, additive)
# ---------------------------------------------------------------------------


class TransformSpec(BaseModel):
    """A transform declares how data is transformed between binders."""

    id: str = "passthrough"
    engine: TransformEngine = TransformEngine.PASSTHROUGH
    spec_ref: str | None = Field(
        default=None,
        description="Reference to transform spec (path to .dwl, .jolt, mapping file, etc.)",
    )
    input_schema_ref: str | None = Field(default=None)
    output_schema_ref: str | None = Field(default=None)
    config: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Workflow Model (new, additive)
# ---------------------------------------------------------------------------


class WorkflowSpec(BaseModel):
    """A workflow is one source-to-target pipeline within a micro-integration.

    Exactly one side (input or output connector) must be 'solace'.
    """

    id: str = ""
    input_connector_ref: str = Field(
        default="",
        description="ID of the connector acting as source (one must be 'solace')",
    )
    output_connector_ref: str = Field(
        default="",
        description="ID of the connector acting as target (one must be 'solace')",
    )
    transform_ref: str | None = Field(
        default=None, description="ID of the transform to apply (None = passthrough)"
    )
    topic: str = ""
    events: list[str] = Field(default_factory=list, description="Event names flowing through")


# ---------------------------------------------------------------------------
# Top-Level Canonical Model
# ---------------------------------------------------------------------------


class CanonicalModel(BaseModel):
    """The full canonical model contract for a micro-integration.

    This combines the legacy contract (operations, ingressType, stripeEnabled)
    with the new direction-aware connector/workflow/transform contract.
    Adapters may populate either or both sections; the generator service
    handles both.
    """

    # -- Identity --
    title: str = "Generated Service"
    service_name: str = Field(alias="serviceName", default="generated-service")
    service_version: str = Field(alias="serviceVersion", default="1.0.0")

    # -- Source metadata --
    servers: list[str] = Field(default_factory=list)
    auth_schemes: list[str] = Field(alias="authSchemes", default_factory=list)

    # -- Legacy operation/event contract (backward compat) --
    operations: list[Operation] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    schema_names: list[str] = Field(alias="schemaNames", default_factory=list)
    application_names: list[str] = Field(alias="applicationNames", default_factory=list)
    stripe_enabled: bool = Field(alias="stripeEnabled", default=False)
    test_fixtures: list[dict[str, Any]] = Field(alias="testFixtures", default_factory=list)
    ingress_type: str = Field(alias="ingressType", default="rest_controller")

    # -- New: direction-aware connector/workflow/transform contract --
    direction: Direction = Direction.SOURCE
    connectors: list[ConnectorSpec] = Field(default_factory=list)
    workflows: list[WorkflowSpec] = Field(default_factory=list)
    transforms: list[TransformSpec] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def to_legacy_dict(self) -> dict[str, Any]:
        """Serialize to the legacy dict format expected by generator_service.

        Returns the dict using the alias (camelCase) keys so existing template
        rendering continues to work unchanged.
        """
        return self.model_dump(by_alias=True)
