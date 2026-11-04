"""Provision the private, bounded validation worker used by this factory only."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import time
import zipfile

NAME = "mi-factory-validation"


def provision(session):
    account = session.client("sts").get_caller_identity()["Account"]
    region = session.region_name
    bucket = NAME + "-" + account + "-" + region
    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        args = {"Bucket": bucket}
        if region != "us-east-1":
            args["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**args)
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration=dict(
            BlockPublicAcls=True,
            IgnorePublicAcls=True,
            BlockPublicPolicy=True,
            RestrictPublicBuckets=True,
        ),
    )
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-private-jobs",
                    "Filter": {"Prefix": "jobs/"},
                    "Status": "Enabled",
                    "Expiration": {"Days": 1},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                }
            ]
        },
    )
    s3.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": [
                        "https://solacese.github.io",
                        "http://localhost:8086",
                    ],
                    "AllowedMethods": ["GET", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 300,
                }
            ]
        },
    )
    iam = session.client("iam")
    role_name = NAME + "-worker"
    project_arn = f"arn:aws:codebuild:{region}:{account}:project/{NAME}"
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "codebuild.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnEquals": {"aws:SourceArn": project_arn},
                },
            }
        ],
    }
    try:
        role = iam.create_role(
            RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust)
        )["Role"]
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=role_name)["Role"]
    log_group = "/aws/codebuild/" + NAME
    logs = session.client("logs")
    try:
        logs.create_log_group(logGroupName=log_group)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    logs.put_retention_policy(logGroupName=log_group, retentionInDays=7)
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}/worker/*",
                    f"arn:aws:s3:::{bucket}/jobs/*/input.json",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["s3:PutObject"],
                "Resource": f"arn:aws:s3:::{bucket}/jobs/*",
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{region}:{account}:log-group:{log_group}:*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=role_name, PolicyName=NAME, PolicyDocument=json.dumps(policy)
    )
    buildspec = {
        "version": 0.2,
        "phases": {
            "install": {
                "runtime-versions": {"python": "3.13", "golang": "1.27"},
                "commands": [
                    "python3 -m pip install --quiet boto3==1.40.59",
                    "if ! docker info >/dev/null 2>&1; then nohup dockerd --host=unix:///var/run/docker.sock >/tmp/dockerd.log 2>&1 & fi",
                    "timeout 60 sh -c 'until docker info >/dev/null 2>&1; do sleep 1; done'",
                ],
            },
            "build": {"commands": ["python3 worker.py"]},
        },
    }
    root = Path(__file__).resolve().parent
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        paths = [root / "worker.py", *sorted((root / "loadtest").glob("*"))]
        for path in paths:
            if path.is_file() and (
                path.name
                in {
                    "worker.py",
                    "Dockerfile",
                    "go.mod",
                    "go.sum",
                    "main.go",
                    "broker.go",
                    "main_test.go",
                }
            ):
                info = zipfile.ZipInfo(
                    path.relative_to(root).as_posix(), date_time=(2026, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        archive.writestr("buildspec.yml", json.dumps(buildspec))
    data = payload.getvalue()
    source = "worker/" + hashlib.sha256(data).hexdigest() + ".zip"
    s3.put_object(Bucket=bucket, Key=source, Body=data, ContentType="application/zip")
    build = session.client("codebuild")
    args = dict(
        name=NAME,
        source={
            "type": "S3",
            "location": bucket + "/" + source,
            "buildspec": "buildspec.yml",
        },
        artifacts={"type": "NO_ARTIFACTS"},
        serviceRole=role["Arn"],
        environment={
            "type": "LINUX_CONTAINER",
            "image": "aws/codebuild/standard:8.0",
            "computeType": "BUILD_GENERAL1_LARGE",
            "privilegedMode": True,
            "environmentVariables": [
                {"name": "VALIDATION_BUCKET", "value": bucket, "type": "PLAINTEXT"},
                {
                    "name": "VALIDATION_COMPUTE",
                    "value": "CodeBuild Linux, 8 vCPU / 16 GiB; each MI 2 CPU, broker 4 CPU, generator 2 CPU",
                    "type": "PLAINTEXT",
                },
            ],
        },
        timeoutInMinutes=15,
        queuedTimeoutInMinutes=5,
        concurrentBuildLimit=1,
        logsConfig={
            "cloudWatchLogs": {
                "status": "ENABLED",
                "groupName": log_group,
                "streamName": "validation",
            }
        },
    )
    exists = bool(build.batch_get_projects(names=[NAME])["projects"])
    if exists:
        build.update_project(**args)
    else:
        for attempt in range(8):
            try:
                build.create_project(
                    **args,
                    tags=[
                        {"key": "Project", "value": "micro-integration-factory-skill"}
                    ],
                )
                break
            except build.exceptions.InvalidInputException as error:
                if "role" not in str(error).lower() or attempt == 7:
                    raise
                time.sleep(3)
    return {
        "VALIDATION_BUCKET": bucket,
        "VALIDATION_PROJECT": NAME,
        "DAILY_VALIDATION_LIMIT": "20",
    }, [
        {
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": f"arn:aws:s3:::{bucket}",
        },
        {
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject"],
            "Resource": f"arn:aws:s3:::{bucket}/jobs/*",
        },
        {
            "Effect": "Allow",
            "Action": ["codebuild:StartBuild", "codebuild:BatchGetBuilds"],
            "Resource": [
                project_arn,
                f"arn:aws:codebuild:{region}:{account}:build/{NAME}:*",
            ],
        },
    ]
