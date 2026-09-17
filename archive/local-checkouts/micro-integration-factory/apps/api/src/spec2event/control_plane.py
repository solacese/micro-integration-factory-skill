from __future__ import annotations

import argparse
import base64
import json
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from botocore.exceptions import ClientError, WaiterError

from spec2event.config import Settings, get_settings
from spec2event.services.aws_service import AwsService, NetworkConfig

CONTROL_PLANE_TAGS = [
    {"Key": "Name", "Value": "agentic-integration-factory-control-plane"},
    {"Key": "Project", "Value": "agentic-integration-factory"},
    {"Key": "Role", "Value": "control-plane"},
]
CONTROL_PLANE_EIP_TAGS = [
    {"Key": "Name", "Value": "agentic-integration-factory-control-plane-eip"},
    {"Key": "Project", "Value": "agentic-integration-factory"},
    {"Key": "Role", "Value": "control-plane-eip"},
]
CONTROL_PLANE_ROLE_NAME = "agentic-integration-factory-control-plane-ssm"
CONTROL_PLANE_INSTANCE_PROFILE_NAME = CONTROL_PLANE_ROLE_NAME
SSM_MANAGED_INSTANCE_POLICY_ARN = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
CONTROL_PLANE_STATE = get_settings().runs_root / "control-plane.json"
COMPOSE_TEMPLATE = get_settings().repo_root / "infra" / "docker" / "control-plane-compose.yaml"
NGINX_TEMPLATE = get_settings().repo_root / "infra" / "docker" / "control-plane-nginx.conf"


@dataclass
class ControlPlaneDeployment:
    instance_id: str
    public_ip: str
    public_url: str
    elastic_ip_allocation_id: str
    security_group_id: str
    subnet_id: str
    vpc_id: str
    api_image: str
    web_image: str


@dataclass
class ControlPlaneRuntimeFiles:
    compose: str
    nginx_conf: str
    api_env: str
    web_env: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the Agentic Integration Factory control-plane EC2 demo"
    )
    parser.add_argument("command", choices=["up", "deploy", "quick", "down", "status"])
    args = parser.parse_args()

    try:
        if args.command == "up":
            deployment = deploy_control_plane()
            print(json.dumps(asdict(deployment), indent=2))
            return
        if args.command in {"deploy", "quick"}:
            deployment = deploy_control_plane_fast()
            print(json.dumps(asdict(deployment), indent=2))
            return
        if args.command == "down":
            down_control_plane()
            print("Control-plane instances terminated.")
            return
        status = control_plane_status()
        print(json.dumps(status, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2))
        raise SystemExit(1) from exc


def deploy_control_plane() -> ControlPlaneDeployment:
    settings = get_settings()
    aws_service = AwsService(settings)
    auth = aws_service.ecr_auth()
    network = aws_service.resolve_network()
    security_group_id = ensure_control_plane_security_group(aws_service, network)
    allocation_id, elastic_ip = ensure_control_plane_elastic_ip(aws_service)
    api_image, web_image = build_and_push_control_plane_images(
        aws_service, auth.registry, auth.password
    )
    return replace_control_plane_instance(
        settings=settings,
        aws_service=aws_service,
        auth=auth,
        network=network,
        security_group_id=security_group_id,
        allocation_id=allocation_id,
        elastic_ip=elastic_ip,
        api_image=api_image,
        web_image=web_image,
    )


def deploy_control_plane_fast() -> ControlPlaneDeployment:
    settings = get_settings()
    aws_service = AwsService(settings)
    auth = aws_service.ecr_auth()
    network = aws_service.resolve_network()
    security_group_id = ensure_control_plane_security_group(aws_service, network)
    allocation_id, elastic_ip = ensure_control_plane_elastic_ip(aws_service)
    api_image, web_image = build_and_push_control_plane_images(
        aws_service, auth.registry, auth.password
    )
    public_url = (settings.public_base_url or f"http://{elastic_ip}").rstrip("/")
    for instance in running_control_plane_instances(aws_service):
        instance_id = instance["InstanceId"]
        try:
            update_control_plane_instance(
                settings=settings,
                aws_service=aws_service,
                auth=auth,
                network=network,
                security_group_id=security_group_id,
                instance_id=instance_id,
                elastic_ip=elastic_ip,
                api_image=api_image,
                web_image=web_image,
            )
            wait_for_control_plane(public_url)
            return write_control_plane_state(
                ControlPlaneDeployment(
                    instance_id=instance_id,
                    public_ip=elastic_ip,
                    public_url=public_url,
                    elastic_ip_allocation_id=allocation_id,
                    security_group_id=security_group_id,
                    subnet_id=network.subnet_id,
                    vpc_id=network.vpc_id,
                    api_image=api_image,
                    web_image=web_image,
                )
            )
        except RuntimeError:
            continue

    return replace_control_plane_instance(
        settings=settings,
        aws_service=aws_service,
        auth=auth,
        network=network,
        security_group_id=security_group_id,
        allocation_id=allocation_id,
        elastic_ip=elastic_ip,
        api_image=api_image,
        web_image=web_image,
    )


def replace_control_plane_instance(
    *,
    settings: Settings,
    aws_service: AwsService,
    auth,
    network: NetworkConfig,
    security_group_id: str,
    allocation_id: str,
    elastic_ip: str,
    api_image: str,
    web_image: str,
) -> ControlPlaneDeployment:
    terminate_instances(
        aws_service,
        filters=[
            {"Name": "tag:Project", "Values": ["agentic-integration-factory"]},
            {"Name": "tag:Role", "Values": ["control-plane"]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ],
    )

    ami_id = aws_service.amazon_linux_ami()
    instance_profile_name = ensure_control_plane_instance_profile(aws_service)
    user_data = render_control_plane_user_data(
        settings=settings,
        registry=auth.registry,
        registry_password=auth.password,
        api_image=api_image,
        web_image=web_image,
        network=network,
        security_group_id=security_group_id,
    )
    launch_kwargs = {
        "ImageId": ami_id,
        "InstanceType": "t3.large",
        "MinCount": 1,
        "MaxCount": 1,
        "NetworkInterfaces": [
            {
                "DeviceIndex": 0,
                "AssociatePublicIpAddress": True,
                "SubnetId": network.subnet_id,
                "Groups": [security_group_id],
            }
        ],
        "UserData": user_data,
        "TagSpecifications": [{"ResourceType": "instance", "Tags": CONTROL_PLANE_TAGS}],
    }
    if instance_profile_name:
        launch_kwargs["IamInstanceProfile"] = {"Name": instance_profile_name}
    try:
        launch = aws_service.ec2.run_instances(**launch_kwargs)["Instances"][0]
    except ClientError as exc:
        if not instance_profile_name or exc.response["Error"]["Code"] not in {
            "AccessDenied",
            "AccessDeniedException",
            "UnauthorizedOperation",
            "InvalidParameterValue",
        }:
            raise
        launch_kwargs.pop("IamInstanceProfile", None)
        launch = aws_service.ec2.run_instances(**launch_kwargs)["Instances"][0]
    instance_id = launch["InstanceId"]
    aws_service.wait_for_instance_running(instance_id)
    associate_control_plane_elastic_ip(aws_service, allocation_id, instance_id)
    aws_service.wait_for_instance_status(instance_id)
    public_ip = elastic_ip
    public_url = (settings.public_base_url or f"http://{public_ip}").rstrip("/")
    wait_for_control_plane(public_url)

    return write_control_plane_state(
        ControlPlaneDeployment(
            instance_id=instance_id,
            public_ip=public_ip,
            public_url=public_url,
            elastic_ip_allocation_id=allocation_id,
            security_group_id=security_group_id,
            subnet_id=network.subnet_id,
            vpc_id=network.vpc_id,
            api_image=api_image,
            web_image=web_image,
        )
    )


def write_control_plane_state(deployment: ControlPlaneDeployment) -> ControlPlaneDeployment:
    CONTROL_PLANE_STATE.write_text(json.dumps(asdict(deployment), indent=2), encoding="utf-8")
    return deployment


def down_control_plane() -> None:
    aws_service = AwsService()
    terminate_instances(
        aws_service,
        filters=[
            {"Name": "tag:Project", "Values": ["agentic-integration-factory"]},
            {"Name": "tag:Role", "Values": ["control-plane"]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ],
    )
    if CONTROL_PLANE_STATE.exists():
        CONTROL_PLANE_STATE.unlink()


def control_plane_status() -> dict[str, object]:
    if CONTROL_PLANE_STATE.exists():
        return json.loads(CONTROL_PLANE_STATE.read_text(encoding="utf-8"))
    aws_service = AwsService()
    try:
        response = aws_service.ec2.describe_instances(
            Filters=[
                {"Name": "tag:Project", "Values": ["agentic-integration-factory"]},
                {"Name": "tag:Role", "Values": ["control-plane"]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ]
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        return {
            "error": error.get("Code", "AwsClientError"),
            "message": error.get("Message", str(exc)),
        }
    instances = [
        {
            "instanceId": instance["InstanceId"],
            "state": instance["State"]["Name"],
            "publicIp": instance.get("PublicIpAddress"),
        }
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]
    return {"instances": instances}


def running_control_plane_instances(aws_service: AwsService) -> list[dict[str, object]]:
    response = aws_service.ec2.describe_instances(
        Filters=[
            {"Name": "tag:Project", "Values": ["agentic-integration-factory"]},
            {"Name": "tag:Role", "Values": ["control-plane"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    instances = [
        instance
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]
    return sorted(instances, key=lambda instance: instance["LaunchTime"], reverse=True)


def update_control_plane_instance(
    *,
    settings: Settings,
    aws_service: AwsService,
    auth,
    network: NetworkConfig,
    security_group_id: str,
    instance_id: str,
    elastic_ip: str,
    api_image: str,
    web_image: str,
) -> None:
    runtime_files = render_control_plane_files(
        settings=settings,
        api_image=api_image,
        web_image=web_image,
        network=network,
        security_group_id=security_group_id,
    )
    public_url = (settings.public_base_url or f"http://{elastic_ip}").rstrip("/")
    commands = render_control_plane_update_commands(
        runtime_files=runtime_files,
        public_url=public_url,
        registry=auth.registry,
        registry_password=auth.password,
    )
    try:
        response = aws_service.ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands, "executionTimeout": ["900"]},
            Comment="Update Micro Integration Factory control plane",
        )
        command_id = response["Command"]["CommandId"]
        aws_service.ssm.get_waiter("command_executed").wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={"Delay": 5, "MaxAttempts": 180},
        )
        invocation = aws_service.ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id,
        )
    except (ClientError, WaiterError) as exc:
        raise RuntimeError(f"SSM in-place update unavailable for {instance_id}: {exc}") from exc
    if invocation["Status"] != "Success":
        output = invocation.get("StandardErrorContent") or invocation.get(
            "StandardOutputContent", ""
        )
        raise RuntimeError(f"SSM in-place update failed for {instance_id}: {output}")


def render_control_plane_update_commands(
    *,
    runtime_files: ControlPlaneRuntimeFiles,
    public_url: str,
    registry: str,
    registry_password: str,
) -> list[str]:
    return [
        "set -euxo pipefail",
        "mkdir -p /opt/spec2event/generated-runs",
        "systemctl start docker",
        "test -x /usr/local/bin/docker-compose || "
        "curl -fsSL https://github.com/docker/compose/releases/download/v2.39.2/"
        "docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose",
        "chmod +x /usr/local/bin/docker-compose",
        f"cat <<'EOF' >/opt/spec2event/compose.yaml.b64\n{to_base64(runtime_files.compose)}\nEOF",
        "base64 -d /opt/spec2event/compose.yaml.b64 >/opt/spec2event/compose.yaml",
        f"cat <<'EOF' >/opt/spec2event/nginx.conf.b64\n{to_base64(runtime_files.nginx_conf)}\nEOF",
        "base64 -d /opt/spec2event/nginx.conf.b64 >/opt/spec2event/nginx.conf",
        f"cat <<'EOF' >/opt/spec2event/api.env.b64\n{to_base64(runtime_files.api_env)}\nEOF",
        "base64 -d /opt/spec2event/api.env.b64 >/opt/spec2event/api.env",
        f"cat <<'EOF' >/opt/spec2event/web.env.b64\n{to_base64(runtime_files.web_env)}\nEOF",
        "base64 -d /opt/spec2event/web.env.b64 >/opt/spec2event/web.env",
        f"sed -i 's|__PUBLIC_URL__|{public_url}|g' /opt/spec2event/api.env",
        f"docker login {shlex.quote(registry)} -u AWS -p {shlex.quote(registry_password)}",
        "/usr/local/bin/docker-compose -f /opt/spec2event/compose.yaml pull",
        "/usr/local/bin/docker-compose -f /opt/spec2event/compose.yaml up -d",
    ]


def build_and_push_control_plane_images(
    aws_service: AwsService, registry: str, registry_password: str
) -> tuple[str, str]:
    repo_root = aws_service.settings.repo_root
    login = subprocess.run(
        ["docker", "login", registry, "-u", "AWS", "--password-stdin"],
        cwd=repo_root,
        input=registry_password,
        text=True,
        capture_output=True,
        check=False,
    )
    if login.returncode != 0:
        raise RuntimeError(login.stderr or login.stdout or "docker login failed")

    api_repo = aws_service.ensure_ecr_repository("agentic-integration-factory-control-plane-api")
    web_repo = aws_service.ensure_ecr_repository("agentic-integration-factory-control-plane-web")
    api_image = f"{api_repo}:latest"
    web_image = f"{web_repo}:latest"

    buildx(
        repo_root,
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "-t",
            api_image,
            "-f",
            "apps/api/Dockerfile",
            ".",
            "--push",
        ],
    )
    buildx(
        repo_root,
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "-t",
            web_image,
            "-f",
            "apps/web/Dockerfile",
            ".",
            "--push",
        ],
    )
    return api_image, web_image


def buildx(cwd: Path, command: list[str]) -> None:
    process = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(
            process.stderr or process.stdout or f"command failed: {' '.join(command)}"
        )


def ensure_control_plane_instance_profile(aws_service: AwsService) -> str | None:
    try:
        return _ensure_control_plane_instance_profile(aws_service)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {
            "AccessDenied",
            "AccessDeniedException",
            "UnauthorizedOperation",
        }:
            return None
        raise


def _ensure_control_plane_instance_profile(aws_service: AwsService) -> str:
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        aws_service.iam.get_role(RoleName=CONTROL_PLANE_ROLE_NAME)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        aws_service.iam.create_role(
            RoleName=CONTROL_PLANE_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="SSM access for Micro Integration Factory control-plane updates",
        )
    aws_service.iam.attach_role_policy(
        RoleName=CONTROL_PLANE_ROLE_NAME,
        PolicyArn=SSM_MANAGED_INSTANCE_POLICY_ARN,
    )
    try:
        profile = aws_service.iam.get_instance_profile(
            InstanceProfileName=CONTROL_PLANE_INSTANCE_PROFILE_NAME
        )["InstanceProfile"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        profile = aws_service.iam.create_instance_profile(
            InstanceProfileName=CONTROL_PLANE_INSTANCE_PROFILE_NAME
        )["InstanceProfile"]

    if all(role["RoleName"] != CONTROL_PLANE_ROLE_NAME for role in profile.get("Roles", [])):
        try:
            aws_service.iam.add_role_to_instance_profile(
                InstanceProfileName=CONTROL_PLANE_INSTANCE_PROFILE_NAME,
                RoleName=CONTROL_PLANE_ROLE_NAME,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"LimitExceeded", "EntityAlreadyExists"}:
                raise
        time.sleep(10)
    return CONTROL_PLANE_INSTANCE_PROFILE_NAME


def ensure_control_plane_security_group(aws_service: AwsService, network: NetworkConfig) -> str:
    group_name = "agentic-integration-factory-control-plane-http"
    groups = aws_service.ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [group_name]},
            {"Name": "vpc-id", "Values": [network.vpc_id]},
        ]
    )["SecurityGroups"]
    if groups:
        group_id = groups[0]["GroupId"]
    else:
        group_id = aws_service.ec2.create_security_group(
            GroupName=group_name,
            Description="Public HTTP access for the Spec2Event control plane",
            VpcId=network.vpc_id,
        )["GroupId"]
    allowed_cidr = control_plane_allowed_cidr(aws_service.settings)
    revoke_unrestricted_http(aws_service, group_id)
    permission = {
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "IpRanges": [{"CidrIp": allowed_cidr, "Description": "control-plane-http"}],
    }
    try:
        aws_service.ec2.authorize_security_group_ingress(
            GroupId=group_id, IpPermissions=[permission]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise
    return group_id


def control_plane_allowed_cidr(settings: Settings) -> str:
    if settings.control_plane_allowed_cidr:
        return settings.control_plane_allowed_cidr
    return "0.0.0.0/0"


def revoke_unrestricted_http(aws_service: AwsService, group_id: str) -> None:
    permission = {
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
    }
    try:
        aws_service.ec2.revoke_security_group_ingress(
            GroupId=group_id, IpPermissions=[permission]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.NotFound":
            raise


def ensure_control_plane_elastic_ip(aws_service: AwsService) -> tuple[str, str]:
    response = aws_service.ec2.describe_addresses(
        Filters=[
            {"Name": "tag:Project", "Values": ["spec2event"]},
            {"Name": "tag:Role", "Values": ["control-plane-eip"]},
        ]
    )
    addresses = response["Addresses"]
    if addresses:
        address = addresses[0]
        return address["AllocationId"], address["PublicIp"]

    address = aws_service.ec2.allocate_address(Domain="vpc")
    allocation_id = address["AllocationId"]
    aws_service.ec2.create_tags(Resources=[allocation_id], Tags=CONTROL_PLANE_EIP_TAGS)
    return allocation_id, address["PublicIp"]


def associate_control_plane_elastic_ip(
    aws_service: AwsService, allocation_id: str, instance_id: str
) -> None:
    response = aws_service.ec2.describe_addresses(AllocationIds=[allocation_id])
    addresses = response["Addresses"]
    association_id = addresses[0].get("AssociationId") if addresses else None
    if association_id:
        try:
            aws_service.ec2.disassociate_address(AssociationId=association_id)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidAssociationID.NotFound":
                raise
    for attempt in range(12):
        try:
            aws_service.ec2.associate_address(
                AllocationId=allocation_id,
                InstanceId=instance_id,
                AllowReassociation=True,
            )
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidNetworkInterfaceID.NotFound":
                raise
            if attempt == 11:
                raise
            time.sleep(5)


def render_control_plane_user_data(
    *,
    settings: Settings,
    registry: str,
    registry_password: str,
    api_image: str,
    web_image: str,
    network: NetworkConfig,
    security_group_id: str,
) -> str:
    runtime_files = render_control_plane_files(
        settings=settings,
        api_image=api_image,
        web_image=web_image,
        network=network,
        security_group_id=security_group_id,
    )
    public_url_assignment = (
        shlex.quote(settings.public_base_url.rstrip("/"))
        if settings.public_base_url
        else '"http://${PUBLIC_IPV4}"'
    )

    return f"""#!/bin/bash
set -euxo pipefail

dnf install -y docker
systemctl enable docker
systemctl start docker
curl -fsSL \
  https://github.com/docker/compose/releases/download/v2.39.2/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PUBLIC_IPV4=""
for _ in $(seq 1 30); do
  PUBLIC_IPV4=$(curl -sfH "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/public-ipv4 || true)
  if [ -n "${{PUBLIC_IPV4}}" ]; then
    break
  fi
  sleep 2
done
if [ -z "${{PUBLIC_IPV4}}" ]; then
  echo "public ipv4 not available" >&2
  exit 1
fi
PUBLIC_URL={public_url_assignment}

mkdir -p /opt/spec2event/generated-runs

cat <<'EOF' >/opt/spec2event/compose.yaml.b64
{to_base64(runtime_files.compose)}
EOF
base64 -d /opt/spec2event/compose.yaml.b64 >/opt/spec2event/compose.yaml

cat <<'EOF' >/opt/spec2event/nginx.conf.b64
{to_base64(runtime_files.nginx_conf)}
EOF
base64 -d /opt/spec2event/nginx.conf.b64 >/opt/spec2event/nginx.conf

cat <<'EOF' >/opt/spec2event/api.env.b64
{to_base64(runtime_files.api_env)}
EOF
base64 -d /opt/spec2event/api.env.b64 >/opt/spec2event/api.env

cat <<'EOF' >/opt/spec2event/web.env.b64
{to_base64(runtime_files.web_env)}
EOF
base64 -d /opt/spec2event/web.env.b64 >/opt/spec2event/web.env

sed -i "s|__PUBLIC_URL__|${{PUBLIC_URL}}|g" /opt/spec2event/api.env

docker login {shlex.quote(registry)} -u AWS -p {shlex.quote(registry_password)}
/usr/local/bin/docker-compose -f /opt/spec2event/compose.yaml pull
/usr/local/bin/docker-compose -f /opt/spec2event/compose.yaml up -d
"""


def render_control_plane_files(
    *,
    settings: Settings,
    api_image: str,
    web_image: str,
    network: NetworkConfig,
    security_group_id: str,
) -> ControlPlaneRuntimeFiles:
    compose = (
        COMPOSE_TEMPLATE.read_text(encoding="utf-8")
        .replace("__API_IMAGE__", api_image)
        .replace("__WEB_IMAGE__", web_image)
    )
    nginx_conf = NGINX_TEMPLATE.read_text(encoding="utf-8")
    api_env = env_file_content(
        {
            "APP_ENV": "production",
            "APP_HOST": "0.0.0.0",
            "APP_PORT": "8000",
            "APP_URL": "__PUBLIC_URL__/api",
            "NEXT_PUBLIC_APP_URL": "__PUBLIC_URL__",
            "NEXT_PUBLIC_API_BASE_URL": "",
            "DATABASE_URL": "postgresql+psycopg://spec2event:spec2event@postgres:5432/spec2event",
            "REDIS_URL": "redis://localhost:6379/0",
            "APP_ENCRYPTION_KEY": settings.app_encryption_key,
            "DEMO_ADMIN_PASSWORD": settings.demo_admin_password,
            "ALLOW_INSECURE_LOCAL_LOGIN": "false",
            "RUNS_ROOT": "/workspace/generated-runs",
            "MDK_SAMPLE_ROOT": "/workspace/mdk-reference/micro-integration",
            "ENABLE_RQ": "false",
            "LOG_LEVEL": settings.log_level,
            "PUBLIC_BASE_URL": "__PUBLIC_URL__",
            "AWS_REGION": settings.aws_region,
            "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": settings.aws_secret_access_key,
            "AWS_SESSION_TOKEN": settings.aws_session_token,
            "ECR_REPOSITORY_NAME": settings.ecr_repository_name,
            "CONTROL_PLANE_SECURITY_GROUP_ID": security_group_id,
            "CONTROL_PLANE_SUBNET_ID": network.subnet_id,
            "CONTROL_PLANE_VPC_ID": network.vpc_id,
            "SOLACE_BROKER_URL": settings.solace_broker_url,
            "SOLACE_VPN": settings.solace_vpn,
            "SOLACE_USERNAME": settings.solace_username,
            "SOLACE_PASSWORD": settings.solace_password,
            "SOLACE_WEB_MESSAGING_URL": settings.solace_web_messaging_url,
            "STRIPE_SECRET_KEY": settings.stripe_secret_key,
            "STRIPE_WEBHOOK_SECRET": settings.stripe_webhook_secret,
        }
    )
    web_env = env_file_content(
        {
            "NODE_ENV": "production",
            "HOSTNAME": "0.0.0.0",
            "PORT": "3000",
            "NEXT_PUBLIC_API_BASE_URL": "",
        }
    )
    return ControlPlaneRuntimeFiles(
        compose=compose,
        nginx_conf=nginx_conf,
        api_env=api_env,
        web_env=web_env,
    )


def env_file_content(values: dict[str, str | None]) -> str:
    lines = []
    for key, value in values.items():
        if value in (None, ""):
            continue
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def to_base64(content: str) -> str:
    return base64.b64encode(content.encode()).decode()


def terminate_instances(aws_service: AwsService, filters: list[dict[str, object]]) -> list[str]:
    response = aws_service.ec2.describe_instances(Filters=filters)
    instance_ids = [
        instance["InstanceId"]
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]
    if instance_ids:
        aws_service.ec2.terminate_instances(InstanceIds=instance_ids)
    return instance_ids


def wait_for_control_plane(public_url: str) -> None:
    last_error = "control plane did not become healthy"
    for _ in range(60):
        try:
            response = httpx.get(f"{public_url}/health", timeout=10.0)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(10)
    raise RuntimeError(last_error)


if __name__ == "__main__":
    main()
