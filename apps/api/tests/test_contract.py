"""Tests for the canonical model contract (spec2event.contract)."""

from __future__ import annotations

from spec2event.contract import (
    CanonicalModel,
    ConnectorSpec,
    DeliveryModel,
    Direction,
    EventCandidate,
    TransformEngine,
    TransformSpec,
    WorkflowSpec,
)


def test_canonical_model_from_legacy_dict() -> None:
    """The canonical model can be instantiated from a legacy-shaped dict."""
    legacy = {
        "title": "Pet Store",
        "serviceName": "pet-store",
        "serviceVersion": "1.0.0",
        "servers": ["https://petstore.example.com"],
        "authSchemes": ["api_key"],
        "operations": [
            {
                "operationId": "createPet",
                "method": "POST",
                "path": "/pets",
                "summary": "Create a pet",
                "tags": ["pets"],
                "requestSchemaName": "Pet",
                "responseSchemaName": "PetResponse",
                "requestSchema": {"type": "object"},
                "responseSchema": {"type": "object"},
                "emitsEvent": True,
                "eventCandidates": [
                    {
                        "operationId": "createPet",
                        "canonicalEventName": "PetCreated",
                        "topicName": "pets/pet/created/v1",
                        "schemaName": "PetCreatedPayload",
                        "applicationName": "pet-store-integration",
                        "emitsEvent": True,
                    }
                ],
            }
        ],
        "topics": ["pets/pet/created/v1"],
        "schemaNames": ["PetCreatedPayload"],
        "applicationNames": ["pet-store-integration"],
        "stripeEnabled": False,
        "testFixtures": [],
        "ingressType": "rest_controller",
    }

    model = CanonicalModel.model_validate(legacy)

    assert model.title == "Pet Store"
    assert model.service_name == "pet-store"
    assert model.ingress_type == "rest_controller"
    assert model.stripe_enabled is False
    assert model.direction == Direction.SOURCE
    assert len(model.operations) == 1
    assert model.operations[0].operation_id == "createPet"
    assert len(model.operations[0].event_candidates) == 1
    assert model.operations[0].event_candidates[0].canonical_event_name == "PetCreated"


def test_canonical_model_to_legacy_dict_roundtrip() -> None:
    """to_legacy_dict() produces alias keys matching the original format."""
    legacy = {
        "title": "Test",
        "serviceName": "test",
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "operations": [],
        "topics": [],
        "schemaNames": [],
        "applicationNames": [],
        "stripeEnabled": True,
        "testFixtures": [],
        "ingressType": "polling_consumer",
    }

    model = CanonicalModel.model_validate(legacy)
    result = model.to_legacy_dict()

    assert result["serviceName"] == "test"
    assert result["stripeEnabled"] is True
    assert result["ingressType"] == "polling_consumer"
    assert result["schemaNames"] == []
    assert result["applicationNames"] == []


def test_canonical_model_with_connectors_and_workflows() -> None:
    """New connector/workflow/transform fields work alongside legacy fields."""
    data = {
        "title": "DB to Solace",
        "serviceName": "db-integration",
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "operations": [],
        "topics": ["db/orders/created/v1"],
        "schemaNames": ["OrderCreatedPayload"],
        "applicationNames": ["db-integration"],
        "stripeEnabled": False,
        "testFixtures": [],
        "ingressType": "event_subscriber",
        "direction": "source",
        "connectors": [
            {
                "id": "postgres-cdc",
                "system_kind": "database",
                "direction": "source",
                "transport": "debezium",
                "delivery_model": "stream",
                "config": {"table": "orders"},
            },
            {
                "id": "solace",
                "system_kind": "solace",
                "direction": "target",
                "transport": "solace",
                "delivery_model": "push",
            },
        ],
        "workflows": [
            {
                "id": "orders-cdc",
                "input_connector_ref": "postgres-cdc",
                "output_connector_ref": "solace",
                "transform_ref": "order-transform",
                "topic": "db/orders/created/v1",
                "events": ["OrderCreated"],
            }
        ],
        "transforms": [
            {
                "id": "order-transform",
                "engine": "field_mapping",
                "spec_ref": "mappings/order.json",
            }
        ],
    }

    model = CanonicalModel.model_validate(data)

    assert model.direction == Direction.SOURCE
    assert len(model.connectors) == 2
    assert model.connectors[0].system_kind == "database"
    assert model.connectors[0].delivery_model == DeliveryModel.STREAM
    assert model.connectors[1].id == "solace"
    assert len(model.workflows) == 1
    assert model.workflows[0].input_connector_ref == "postgres-cdc"
    assert model.workflows[0].output_connector_ref == "solace"
    assert model.workflows[0].transform_ref == "order-transform"
    assert len(model.transforms) == 1
    assert model.transforms[0].engine == TransformEngine.FIELD_MAPPING


def test_connector_spec_defaults() -> None:
    """ConnectorSpec has sensible defaults."""
    c = ConnectorSpec(id="test")
    assert c.system_kind == "rest"
    assert c.direction == Direction.SOURCE
    assert c.delivery_model == DeliveryModel.PUSH
    assert c.transport == ""
    assert c.config == {}


def test_transform_spec_defaults() -> None:
    """TransformSpec defaults to passthrough."""
    t = TransformSpec()
    assert t.id == "passthrough"
    assert t.engine == TransformEngine.PASSTHROUGH
    assert t.spec_ref is None


def test_workflow_spec_fields() -> None:
    """WorkflowSpec holds all required fields."""
    w = WorkflowSpec(
        id="wf-1",
        input_connector_ref="kafka-source",
        output_connector_ref="solace",
        transform_ref="jolt-transform",
        topic="orders/created/v1",
        events=["OrderCreated"],
    )
    assert w.id == "wf-1"
    assert w.input_connector_ref == "kafka-source"
    assert w.output_connector_ref == "solace"
    assert w.transform_ref == "jolt-transform"


def test_event_candidate_alias_parsing() -> None:
    """EventCandidate works with camelCase alias keys."""
    data = {
        "operationId": "op1",
        "canonicalEventName": "TestEvent",
        "topicName": "test/topic/v1",
        "schemaName": "TestPayload",
        "applicationName": "test-app",
        "emitsEvent": True,
    }
    ec = EventCandidate.model_validate(data)
    assert ec.canonical_event_name == "TestEvent"
    assert ec.topic_name == "test/topic/v1"
