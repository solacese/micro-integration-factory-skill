from spec2event.adapters.source.database_adapter import DatabaseSourceAdapter
from spec2event.adapters.source.integration_spec_adapter import IntegrationSpecAdapter
from spec2event.adapters.source.json_schema_adapter import JsonSchemaSourceAdapter
from spec2event.adapters.source.kafka_adapter import KafkaSourceAdapter
from spec2event.adapters.source.openapi_adapter import OpenApiSourceAdapter
from spec2event.adapters.source.registry import register_source
from spec2event.adapters.source.webhook_adapter import WebhookSourceAdapter

register_source("openapi", OpenApiSourceAdapter)
register_source("json_schema", JsonSchemaSourceAdapter)
register_source("database", DatabaseSourceAdapter)
register_source("kafka", KafkaSourceAdapter)
register_source("webhook", WebhookSourceAdapter)
register_source("integration_spec", IntegrationSpecAdapter)
