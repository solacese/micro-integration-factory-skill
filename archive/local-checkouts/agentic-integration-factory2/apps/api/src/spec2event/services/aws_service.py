from __future__ import annotations

import base64
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from spec2event.config import Settings, get_settings


@dataclass
class EcrAuth:
    registry: str
    password: str


@dataclass
class NetworkConfig:
    vpc_id: str
    subnet_id: str
    control_plane_security_group_id: str | None


class AwsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session = boto3.Session(
            region_name=self.settings.aws_region,
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            aws_session_token=self.settings.aws_session_token,
        )
        self.ec2 = self._session.client("ec2")
        self.ecr = self._session.client("ecr")
        self.ssm = self._session.client("ssm")
        self.sts = self._session.client("sts")

    @property
    def region(self) -> str:
        return self.settings.aws_region

    def account_id(self) -> str:
        return self.sts.get_caller_identity()["Account"]

    def ensure_ecr_repository(self, repository_name: str | None = None) -> str:
        name = repository_name or self.settings.ecr_repository_name
        try:
            response = self.ecr.describe_repositories(repositoryNames=[name])
            return response["repositories"][0]["repositoryUri"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "RepositoryNotFoundException":
                raise
        response = self.ecr.create_repository(repositoryName=name)
        return response["repository"]["repositoryUri"]

    def ecr_auth(self) -> EcrAuth:
        token = self.ecr.get_authorization_token()["authorizationData"][0]
        decoded = base64.b64decode(token["authorizationToken"]).decode()
        _, password = decoded.split(":", 1)
        registry = token["proxyEndpoint"].replace("https://", "")
        return EcrAuth(registry=registry, password=password)

    def amazon_linux_ami(self) -> str:
        return self.ssm.get_parameter(
            Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
        )["Parameter"]["Value"]

    def resolve_network(self) -> NetworkConfig:
        if self.settings.control_plane_subnet_id:
            if self.settings.control_plane_vpc_id:
                vpc_id = self.settings.control_plane_vpc_id
            else:
                subnet = self.ec2.describe_subnets(
                    SubnetIds=[self.settings.control_plane_subnet_id]
                )["Subnets"][0]
                vpc_id = subnet["VpcId"]
            return NetworkConfig(
                vpc_id=vpc_id,
                subnet_id=self.settings.control_plane_subnet_id,
                control_plane_security_group_id=self.settings.control_plane_security_group_id,
            )

        vpc = self.ec2.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )["Vpcs"][0]
        subnet = self.ec2.describe_subnets(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc["VpcId"]]},
                {"Name": "default-for-az", "Values": ["true"]},
            ]
        )["Subnets"][0]
        return NetworkConfig(
            vpc_id=vpc["VpcId"],
            subnet_id=subnet["SubnetId"],
            control_plane_security_group_id=self.settings.control_plane_security_group_id,
        )

    def ensure_ephemeral_security_group(self, network: NetworkConfig) -> str:
        group_name = "spec2event-ephemeral-mi-http"
        groups = self.ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [group_name]},
                {"Name": "vpc-id", "Values": [network.vpc_id]},
            ]
        )["SecurityGroups"]
        if groups:
            group_id = groups[0]["GroupId"]
        else:
            group_id = self.ec2.create_security_group(
                GroupName=group_name,
                Description="HTTP access for Spec2Event ephemeral micro-integrations",
                VpcId=network.vpc_id,
            )["GroupId"]

        permission: dict[str, object]
        if network.control_plane_security_group_id:
            permission = {
                "IpProtocol": "tcp",
                "FromPort": 8080,
                "ToPort": 8080,
                "UserIdGroupPairs": [
                    {
                        "GroupId": network.control_plane_security_group_id,
                        "Description": "agentic-integration-factory-control-plane",
                    }
                ],
            }
        else:
            permission = {
                "IpProtocol": "tcp",
                "FromPort": 8080,
                "ToPort": 8080,
                "IpRanges": [
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "fallback-public-http",
                    }
                ],
            }
        try:
            self.ec2.authorize_security_group_ingress(
                GroupId=group_id, IpPermissions=[permission]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                raise
        return group_id

    def terminate_run_instances(self, run_id: str) -> list[str]:
        response = self.ec2.describe_instances(
            Filters=[
                {"Name": "tag:RunId", "Values": [run_id]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ]
        )
        instance_ids = [
            instance["InstanceId"]
            for reservation in response["Reservations"]
            for instance in reservation["Instances"]
        ]
        if instance_ids:
            self.ec2.terminate_instances(InstanceIds=instance_ids)
        return instance_ids

    def wait_for_instance_status(self, instance_id: str) -> None:
        self.ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])

    def wait_for_instance_running(self, instance_id: str) -> None:
        self.ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])

    def describe_instance(self, instance_id: str) -> dict[str, object]:
        response = self.ec2.describe_instances(InstanceIds=[instance_id])
        return response["Reservations"][0]["Instances"][0]
