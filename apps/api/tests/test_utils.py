"""Tests for spec2event.services.utils shared helpers."""

from __future__ import annotations

from spec2event.services.utils import (
    camel,
    example_from_schema,
    pascal,
    safe_slug,
    singularize,
)


class TestSafeSlug:
    def test_basic_conversion(self) -> None:
        assert safe_slug("Swagger Petstore") == "swagger-petstore"

    def test_special_chars(self) -> None:
        assert safe_slug("my_app v2.0!") == "my-app-v2-0"

    def test_empty_string(self) -> None:
        assert safe_slug("") == "generated-service"

    def test_only_special_chars(self) -> None:
        assert safe_slug("@#$%") == "generated-service"


class TestPascal:
    def test_basic(self) -> None:
        assert pascal("order-created") == "OrderCreated"

    def test_multi_word(self) -> None:
        assert pascal("stripe payment intent succeeded") == "StripePaymentIntentSucceeded"

    def test_already_pascal(self) -> None:
        assert pascal("AlreadyPascal") == "AlreadyPascal"


class TestCamel:
    def test_basic(self) -> None:
        assert camel("OrderCreated") == "orderCreated"

    def test_multi_word(self) -> None:
        assert camel("StripePaymentIntentSucceeded") == "stripePaymentIntentSucceeded"

    def test_with_separators(self) -> None:
        assert camel("order-created-event") == "orderCreatedEvent"

    def test_empty(self) -> None:
        assert camel("") == "generatedBinding"


class TestSingularize:
    def test_regular_plural(self) -> None:
        assert singularize("orders") == "order"

    def test_ies_plural(self) -> None:
        assert singularize("categories") == "category"

    def test_already_singular(self) -> None:
        assert singularize("order") == "order"

    def test_double_s(self) -> None:
        assert singularize("address") == "address"


class TestExampleFromSchema:
    def test_string_type(self) -> None:
        assert example_from_schema({"type": "string"}) == "string"

    def test_integer_type(self) -> None:
        assert example_from_schema({"type": "integer"}) == 1

    def test_number_type(self) -> None:
        assert example_from_schema({"type": "number"}) == 1.0

    def test_boolean_type(self) -> None:
        assert example_from_schema({"type": "boolean"}) is True

    def test_object_type(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        result = example_from_schema(schema)
        assert result == {"name": "string", "age": 1}

    def test_array_type(self) -> None:
        schema = {"type": "array", "items": {"type": "string"}}
        assert example_from_schema(schema) == ["string"]

    def test_explicit_example(self) -> None:
        schema = {"type": "string", "example": "hello"}
        assert example_from_schema(schema) == "hello"

    def test_enum(self) -> None:
        schema = {"type": "string", "enum": ["active", "inactive"]}
        assert example_from_schema(schema) == "active"

    def test_date_time_format(self) -> None:
        schema = {"type": "string", "format": "date-time"}
        assert example_from_schema(schema) == "2026-01-01T00:00:00Z"

    def test_uuid_format(self) -> None:
        schema = {"type": "string", "format": "uuid"}
        assert "0000" in example_from_schema(schema)

    def test_none_schema(self) -> None:
        assert example_from_schema(None) is None

    def test_depth_limit(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        assert example_from_schema(schema, depth=5) is None
