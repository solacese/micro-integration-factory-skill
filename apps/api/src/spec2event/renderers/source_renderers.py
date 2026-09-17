"""Built-in source binder renderers.

These reproduce the existing generator_service if/elif behavior as pluggable
renderer registrations. Output is byte-for-byte identical to the prior
hardcoded paths.
"""

from __future__ import annotations

from typing import Any

from spec2event.renderers.base import BinderRenderer, RenderOutput, register_renderer

# ---------------------------------------------------------------------------
# REST Controller Source Renderer
# ---------------------------------------------------------------------------

_REST_BASE = "src/main/java/com/spec2event/generated"


class RestControllerSourceRenderer(BinderRenderer):
    """Renders REST controller ingress (OpenAPI / JSON Schema sources)."""

    def __init__(self) -> None:
        super().__init__(
            pattern="rest_controller",
            direction="source",
            binder_type="solace",
            outputs=[
                RenderOutput(
                    relative_path=f"{_REST_BASE}/api/GeneratedApiController.java",
                    template_name="integration-java-mdk/base/GeneratedApiController.java.j2",
                ),
            ],
        )

    def get_outputs(self, context: dict[str, Any]) -> list[RenderOutput]:
        outputs = list(self.outputs)
        if context.get("stripe_enabled"):
            outputs.extend([
                RenderOutput(
                    relative_path=f"{_REST_BASE}/api/StripeWebhookController.java",
                    template_name="integration-java-mdk/base/StripeWebhookController.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_REST_BASE}/service/StripeSignatureVerifier.java",
                    template_name="integration-java-mdk/base/StripeSignatureVerifier.java.j2",
                ),
            ])
        return outputs


# ---------------------------------------------------------------------------
# Polling Consumer Source Renderer
# ---------------------------------------------------------------------------


class PollingConsumerSourceRenderer(BinderRenderer):
    """Renders polling consumer ingress (database, file, scheduled poll sources)."""

    def __init__(self) -> None:
        super().__init__(
            pattern="polling_consumer",
            direction="source",
            binder_type="polling",
            outputs=[
                RenderOutput(
                    relative_path=f"{_REST_BASE}/service/PollingConsumerService.java",
                    template_name="integration-java-mdk/base/PollingConsumerService.java.j2",
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Event Subscriber Source Renderer
# ---------------------------------------------------------------------------


class EventSubscriberSourceRenderer(BinderRenderer):
    """Renders event subscriber ingress (MQTT, Kafka, AMQP stream sources)."""

    def __init__(self) -> None:
        super().__init__(
            pattern="event_subscriber",
            direction="source",
            binder_type="external",
            outputs=[
                RenderOutput(
                    relative_path=f"{_REST_BASE}/service/EventSubscriberService.java",
                    template_name="integration-java-mdk/base/EventSubscriberService.java.j2",
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_builtin_source_renderers() -> None:
    """Register all built-in source binder renderers."""
    register_renderer(RestControllerSourceRenderer())
    register_renderer(PollingConsumerSourceRenderer())
    register_renderer(EventSubscriberSourceRenderer())
