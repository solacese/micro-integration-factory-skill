from __future__ import annotations

from pathlib import Path

import spec2event.control_plane as control_plane
from spec2event.config import get_settings
from spec2event.control_plane import (
    deploy_control_plane,
    env_file_content,
    render_control_plane_files,
    render_control_plane_user_data,
)
from spec2event.services.aws_service import NetworkConfig


def test_env_file_content_skips_empty_values() -> None:
    rendered = env_file_content(
        {
            "APP_ENV": "production",
            "EMPTY": "",
            "NONE": None,
            "PUBLIC_BASE_URL": "http://demo.local",
        }
    )

    assert "APP_ENV=production" in rendered
    assert "PUBLIC_BASE_URL=http://demo.local" in rendered
    assert "EMPTY=" not in rendered
    assert "NONE=" not in rendered


def test_render_control_plane_user_data_contains_expected_runtime_material() -> None:
    settings = get_settings()
    runtime_files = render_control_plane_files(
        settings=settings,
        api_image="123456789012.dkr.ecr.ca-central-1.amazonaws.com/agentic-integration-factory-control-plane-api:latest",
        web_image="123456789012.dkr.ecr.ca-central-1.amazonaws.com/agentic-integration-factory-control-plane-web:latest",
        network=NetworkConfig(
            vpc_id="vpc-12345",
            subnet_id="subnet-67890",
            control_plane_security_group_id=None,
        ),
        security_group_id="sg-control",
    )
    user_data = render_control_plane_user_data(
        settings=settings,
        registry="123456789012.dkr.ecr.ca-central-1.amazonaws.com",
        registry_password="secret-token",
        api_image="123456789012.dkr.ecr.ca-central-1.amazonaws.com/agentic-integration-factory-control-plane-api:latest",
        web_image="123456789012.dkr.ecr.ca-central-1.amazonaws.com/agentic-integration-factory-control-plane-web:latest",
        network=NetworkConfig(
            vpc_id="vpc-12345",
            subnet_id="subnet-67890",
            control_plane_security_group_id=None,
        ),
        security_group_id="sg-control",
    )

    assert "docker-compose" in user_data
    assert "agentic-integration-factory-control-plane-api:latest" in runtime_files.compose
    assert "agentic-integration-factory-control-plane-web:latest" in runtime_files.compose
    assert "/usr/bin/docker:/usr/bin/docker:ro" in runtime_files.compose
    assert "CONTROL_PLANE_SECURITY_GROUP_ID=sg-control" in runtime_files.api_env
    assert "CONTROL_PLANE_SUBNET_ID=subnet-67890" in runtime_files.api_env
    assert "PUBLIC_URL=" in user_data


def test_deploy_control_plane_waits_for_running_before_associating_eip(
    monkeypatch, tmp_path: Path
) -> None:
    order: list[str] = []

    class FakeEc2:
        def run_instances(self, **kwargs):  # noqa: ANN003
            return {"Instances": [{"InstanceId": "i-demo"}]}

    class FakeAwsService:
        def __init__(self) -> None:
            self.ec2 = FakeEc2()

        def ecr_auth(self):
            return type("Auth", (), {"registry": "registry.example", "password": "secret"})()

        def resolve_network(self) -> NetworkConfig:
            return NetworkConfig(
                vpc_id="vpc-12345",
                subnet_id="subnet-67890",
                control_plane_security_group_id=None,
            )

        def amazon_linux_ami(self) -> str:
            return "ami-demo"

        def wait_for_instance_running(self, instance_id: str) -> None:
            assert instance_id == "i-demo"
            order.append("wait_running")

        def wait_for_instance_status(self, instance_id: str) -> None:
            assert instance_id == "i-demo"
            order.append("wait_status")

    fake_aws = FakeAwsService()

    monkeypatch.setattr(control_plane, "AwsService", lambda _settings=None: fake_aws)
    monkeypatch.setattr(control_plane, "CONTROL_PLANE_STATE", tmp_path / "control-plane.json")
    monkeypatch.setattr(
        control_plane,
        "build_and_push_control_plane_images",
        lambda *args: ("api:latest", "web:latest"),
    )
    monkeypatch.setattr(
        control_plane,
        "ensure_control_plane_security_group",
        lambda *args: "sg-demo",
    )
    monkeypatch.setattr(
        control_plane,
        "ensure_control_plane_elastic_ip",
        lambda *args: ("eipalloc-demo", "52.60.115.223"),
    )
    monkeypatch.setattr(control_plane, "terminate_instances", lambda *args, **kwargs: [])
    monkeypatch.setattr(control_plane, "wait_for_control_plane", lambda *args: None)
    monkeypatch.setattr(
        control_plane,
        "render_control_plane_user_data",
        lambda **kwargs: "#!/bin/bash",
    )

    def fake_associate(*args) -> None:  # noqa: ANN002
        order.append("associate")

    monkeypatch.setattr(control_plane, "associate_control_plane_elastic_ip", fake_associate)

    deployment = deploy_control_plane()

    assert deployment.public_ip == "52.60.115.223"
    assert order == ["wait_running", "associate", "wait_status"]
