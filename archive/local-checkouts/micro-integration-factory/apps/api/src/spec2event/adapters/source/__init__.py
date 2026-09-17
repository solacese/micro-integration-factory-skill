from spec2event.adapters.source.json_schema_adapter import JsonSchemaSourceAdapter
from spec2event.adapters.source.openapi_adapter import OpenApiSourceAdapter
from spec2event.adapters.source.registry import register_source

register_source("openapi", OpenApiSourceAdapter)
register_source("json_schema", JsonSchemaSourceAdapter)
