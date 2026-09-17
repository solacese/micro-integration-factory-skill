"""Built-in target (egress) binder renderers.

Target renderers generate the Java files for the Solace->External direction.
The Solace binder is the source side (we consume from Solace), and the external
system is the target side (we produce/write to it).
"""

from __future__ import annotations

from spec2event.renderers.base import BinderRenderer, RenderOutput, register_renderer

_BASE = "src/main/java/com/spec2event/generated"


class RestSinkTargetRenderer(BinderRenderer):
    """Renders REST/webhook sink target (Solace -> external REST endpoint)."""

    def __init__(self) -> None:
        super().__init__(
            pattern="rest_sink",
            direction="target",
            binder_type="rest",
            outputs=[
                RenderOutput(
                    relative_path=f"{_BASE}/service/SolaceConsumerService.java",
                    template_name="integration-java-mdk/base/SolaceConsumerService.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/service/TargetDispatcherService.java",
                    template_name="integration-java-mdk/base/TargetDispatcherService.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/service/RestTargetSinkService.java",
                    template_name="integration-java-mdk/base/RestTargetSinkService.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/binding/TargetConsumerBindingCapabilitiesFactory.java",
                    template_name=(
                        "integration-java-mdk/base/"
                        "TargetConsumerBindingCapabilitiesFactory.java.j2"
                    ),
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/binding/TargetProducerBindingCapabilitiesFactory.java",
                    template_name=(
                        "integration-java-mdk/base/"
                        "TargetProducerBindingCapabilitiesFactory.java.j2"
                    ),
                ),
            ],
        )


class GenericTargetRenderer(BinderRenderer):
    """Generic target renderer (Solace -> placeholder target dispatcher).

    Used when the specific target system is not specified or is custom Java.
    Renders the consumer + dispatcher skeleton without a specific sink.
    """

    def __init__(self) -> None:
        super().__init__(
            pattern="generic_target",
            direction="target",
            binder_type="custom",
            outputs=[
                RenderOutput(
                    relative_path=f"{_BASE}/service/SolaceConsumerService.java",
                    template_name="integration-java-mdk/base/SolaceConsumerService.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/service/TargetDispatcherService.java",
                    template_name="integration-java-mdk/base/TargetDispatcherService.java.j2",
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/binding/TargetConsumerBindingCapabilitiesFactory.java",
                    template_name=(
                        "integration-java-mdk/base/"
                        "TargetConsumerBindingCapabilitiesFactory.java.j2"
                    ),
                ),
                RenderOutput(
                    relative_path=f"{_BASE}/binding/TargetProducerBindingCapabilitiesFactory.java",
                    template_name=(
                        "integration-java-mdk/base/"
                        "TargetProducerBindingCapabilitiesFactory.java.j2"
                    ),
                ),
            ],
        )


def register_builtin_target_renderers() -> None:
    """Register all built-in target binder renderers."""
    register_renderer(RestSinkTargetRenderer())
    register_renderer(GenericTargetRenderer())
