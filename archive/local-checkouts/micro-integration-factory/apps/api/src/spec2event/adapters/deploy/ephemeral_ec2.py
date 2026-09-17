from __future__ import annotations

import shlex
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from spec2event.adapters.deploy.base import DeploymentAdapter, DeployResult
from spec2event.services.aws_service import AwsService


class EphemeralEc2DeploymentAdapter(DeploymentAdapter):
    def __init__(self, aws_service: AwsService | None = None) -> None:
        self.aws_service = aws_service or AwsService()

    def deploy(
        self, workspace_path: Path, image_tag: str, runtime_env: dict[str, str], run_id: str
    ) -> DeployResult:
        del workspace_path
        logs: list[str] = []
        try:
            terminated = self.aws_service.terminate_run_instances(run_id)
            if terminated:
                logs.append(f"Terminated previous instances: {', '.join(terminated)}")

            ttl_minutes = self.aws_service.settings.ephemeral_ec2_ttl_minutes
            network = self.aws_service.resolve_network()
            security_group_id = self.aws_service.ensure_ephemeral_security_group(network)
            auth = self.aws_service.ecr_auth()
            ami_id = self.aws_service.amazon_linux_ami()

            user_data = _render_user_data(
                image_tag=image_tag,
                registry=auth.registry,
                registry_password=auth.password,
                runtime_env=runtime_env,
                ttl_minutes=ttl_minutes,
            )
            launch = self.aws_service.ec2.run_instances(
                ImageId=ami_id,
                InstanceType="t3.small",
                MinCount=1,
                MaxCount=1,
                InstanceInitiatedShutdownBehavior="terminate",
                NetworkInterfaces=[
                    {
                        "DeviceIndex": 0,
                        "AssociatePublicIpAddress": True,
                        "SubnetId": network.subnet_id,
                        "Groups": [security_group_id],
                    }
                ],
                UserData=user_data,
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": f"spec2event-mi-{run_id[:8]}"},
                            {"Key": "Project", "Value": "agentic-integration-factory"},
                            {"Key": "RunId", "Value": run_id},
                            {"Key": "TTL", "Value": f"{ttl_minutes}m"},
                        ],
                    }
                ],
            )["Instances"][0]
            instance_id = launch["InstanceId"]
            logs.append(f"Launched instance {instance_id}")
            self.aws_service.wait_for_instance_status(instance_id)
            instance = self.aws_service.describe_instance(instance_id)
            private_ip = instance.get("PrivateIpAddress")
            public_ip = instance.get("PublicIpAddress")
            private_service_url = f"http://{private_ip}:8080" if private_ip else None
            public_service_url = f"http://{public_ip}:8080" if public_ip else None
            service_url = (
                private_service_url
                if self.aws_service.settings.control_plane_security_group_id
                else public_service_url
            )
            if not service_url:
                return DeployResult(
                    status="failed",
                    message="Instance launched without a reachable service URL",
                    logs="\n".join(logs),
                )
            self._wait_for_http(service_url)
            expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
            metadata = {
                "instanceId": instance_id,
                "privateServiceUrl": private_service_url,
                "publicIp": public_ip,
                "expiresAt": expires_at.isoformat(),
                "ecrImage": image_tag,
                "securityGroupId": security_group_id,
                "logs": "\n".join(logs),
            }
            return DeployResult(
                status="completed",
                message="Deployed generated integration to ephemeral EC2",
                service_url=service_url,
                logs="\n".join(logs),
                metadata=metadata,
            )
        except Exception as exc:
            logs.append(str(exc))
            return DeployResult(
                status="failed",
                message="Ephemeral EC2 deployment failed",
                logs="\n".join(logs),
            )

    def _wait_for_http(self, service_url: str) -> None:
        last_error = "service did not become ready"
        for _ in range(30):
            try:
                response = httpx.get(f"{service_url}/actuator/health", timeout=10.0)
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(5)
        raise RuntimeError(last_error)


def _render_user_data(
    *,
    image_tag: str,
    registry: str,
    registry_password: str,
    runtime_env: dict[str, str],
    ttl_minutes: int,
) -> str:
    env_exports = " ".join(
        f"-e {shlex.quote(key)}={shlex.quote(value)}" for key, value in runtime_env.items()
    )
    container_name = image_tag.replace("/", "-").replace(":", "-")
    return f"""#!/bin/bash
set -euxo pipefail
dnf install -y docker
systemctl enable docker
systemctl start docker
docker login {shlex.quote(registry)} -u AWS -p {shlex.quote(registry_password)}
docker pull {shlex.quote(image_tag)}
docker rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true
docker run -d --restart unless-stopped \\
  --name {shlex.quote(container_name)} \\
  -p 8080:8080 \\
  {env_exports} \\
  {shlex.quote(image_tag)}
shutdown -h +{ttl_minutes}
"""
