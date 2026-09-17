"""Tests for the binder renderer registry."""

from __future__ import annotations

from spec2event.renderers import (
    BinderRenderer,
    RenderOutput,
    available_renderers,
    get_renderer,
    register_renderer,
)


def test_builtin_source_renderers_registered() -> None:
    """All three built-in source renderers are registered."""
    renderers = available_renderers()
    assert ("rest_controller", "source") in renderers
    assert ("polling_consumer", "source") in renderers
    assert ("event_subscriber", "source") in renderers


def test_rest_controller_renderer_binder_type() -> None:
    """REST controller source renderer uses 'solace' binder."""
    renderer = get_renderer("rest_controller", "source")
    assert renderer is not None
    assert renderer.binder_type == "solace"


def test_polling_consumer_renderer_binder_type() -> None:
    """Polling consumer source renderer uses 'polling' binder."""
    renderer = get_renderer("polling_consumer", "source")
    assert renderer is not None
    assert renderer.binder_type == "polling"


def test_event_subscriber_renderer_binder_type() -> None:
    """Event subscriber source renderer uses 'external' binder."""
    renderer = get_renderer("event_subscriber", "source")
    assert renderer is not None
    assert renderer.binder_type == "external"


def test_rest_controller_outputs_without_stripe() -> None:
    """REST controller renders only GeneratedApiController when stripe is off."""
    renderer = get_renderer("rest_controller", "source")
    assert renderer is not None
    outputs = renderer.get_outputs({"stripe_enabled": False})
    assert len(outputs) == 1
    assert "GeneratedApiController" in outputs[0].relative_path


def test_rest_controller_outputs_with_stripe() -> None:
    """REST controller renders extra Stripe files when stripe_enabled."""
    renderer = get_renderer("rest_controller", "source")
    assert renderer is not None
    outputs = renderer.get_outputs({"stripe_enabled": True})
    assert len(outputs) == 3
    paths = [o.relative_path for o in outputs]
    assert any("StripeWebhookController" in p for p in paths)
    assert any("StripeSignatureVerifier" in p for p in paths)


def test_unknown_renderer_returns_none() -> None:
    """Unknown pattern/direction returns None."""
    assert get_renderer("unknown_pattern", "source") is None
    assert get_renderer("rest_controller", "target") is None


def test_custom_renderer_registration() -> None:
    """A custom renderer can be registered and retrieved."""
    custom = BinderRenderer(
        pattern="custom_sink",
        direction="target",
        binder_type="custom",
        outputs=[
            RenderOutput(
                relative_path="src/main/java/CustomSink.java",
                template_name="custom/Sink.java.j2",
            )
        ],
    )
    register_renderer(custom)
    retrieved = get_renderer("custom_sink", "target")
    assert retrieved is not None
    assert retrieved.binder_type == "custom"
    assert len(retrieved.get_outputs({})) == 1
