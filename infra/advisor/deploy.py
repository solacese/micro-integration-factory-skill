#!/usr/bin/env python3
"""Deploy only the small public advisor, using SAP credentials from a private env file."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import zipfile
import sys
from pathlib import Path
from secrets import token_urlsafe

import boto3
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
NAME = "mi-factory-core-v1"


def deploy(env_file: Path, region: str):
    values = dotenv_values(env_file)
    keys = [
        "SAP_CLIENT_ID",
        "SAP_CLIENT_SECRET",
        "SAP_AUTH_URL",
        "SAP_API_BASE_URL",
        "SAP_RESOURCE_GROUP",
        "SAP_DEPLOYMENT_GPT56_SOL",
        "AI_CORE_DEPLOYMENT_ID",
        "AI_CORE_MODEL",
        "SAP_OPENAI_API_VERSION",
    ]
    credentials = {k: values[k] for k in keys if values.get(k)}
    for key in [
        "SAP_CLIENT_ID",
        "SAP_CLIENT_SECRET",
        "SAP_AUTH_URL",
        "SAP_API_BASE_URL",
    ]:
        if not credentials.get(key):
            raise ValueError(f"Missing {key} in the private AI Core env file")
    if not (
        credentials.get("AI_CORE_DEPLOYMENT_ID")
        or credentials.get("SAP_DEPLOYMENT_GPT56_SOL")
    ):
        raise ValueError("An existing OpenAI-compatible deployment ID is required")
    session = boto3.Session(region_name=region)
    try:
        session.client("sts").get_caller_identity()
    except Exception as error:
        from botocore.exceptions import TokenRetrievalError

        if not isinstance(error, TokenRetrievalError):
            raise
        # Newer CLI may have refreshed SSO credentials the bundled SDK cannot refresh.
        # Keep them in process memory; never write or print credential values.
        temporary = json.loads(
            subprocess.check_output(
                ["aws", "configure", "export-credentials", "--format", "process"],
                text=True,
            )
        )
        session = boto3.Session(
            region_name=region,
            aws_access_key_id=temporary["AccessKeyId"],
            aws_secret_access_key=temporary["SecretAccessKey"],
            aws_session_token=temporary["SessionToken"],
        )
    sys.path.insert(0, str(ROOT))
    from infra.validation.deploy_worker import provision

    validation_environment, validation_policy = provision(session)
    account = session.client("sts").get_caller_identity()["Account"]
    build = ROOT / ".runtime/advisor-package"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(build),
            "--python-version",
            "3.13",
            "--python-platform",
            "x86_64-manylinux2014",
            "--only-binary",
            ":all:",
            "-r",
            str(ROOT / "infra/advisor/requirements.txt"),
        ],
        check=True,
    )
    for relative in [
        "apps/api/src/spec2event",
        "apps/api/resources/templates/core-java",
        "apps/api/resources/templates/core-go",
        "infra/advisor",
    ]:
        shutil.copytree(
            ROOT / relative,
            build / relative,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )
    package = ROOT / ".runtime/advisor.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in build.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(build))
    print("Packaged advisor source and runtime templates", flush=True)
    secrets = session.client("secretsmanager")
    try:
        secret = secrets.create_secret(
            Name=NAME + "/ai-core",
            SecretString=json.dumps(credentials),
            Tags=[{"Key": "Project", "Value": "micro-integration-factory-skill"}],
        )
    except secrets.exceptions.ResourceExistsException:
        secret = secrets.describe_secret(SecretId=NAME + "/ai-core")
        secrets.put_secret_value(
            SecretId=secret["ARN"], SecretString=json.dumps(credentials)
        )
    table_name = NAME + "-quota"
    dynamo = session.client("dynamodb")
    try:
        dynamo.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "bucket", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "bucket", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            Tags=[{"Key": "Project", "Value": "micro-integration-factory-skill"}],
        )
        dynamo.get_waiter("table_exists").wait(
            TableName=table_name, WaiterConfig={"Delay": 2, "MaxAttempts": 30}
        )
        dynamo.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expiresAt"},
        )
    except dynamo.exceptions.ResourceInUseException:
        pass
    iam = session.client("iam")
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        role = iam.create_role(
            RoleName=NAME, AssumeRolePolicyDocument=json.dumps(trust)
        )["Role"]
    except iam.exceptions.EntityAlreadyExistsException:
        role = iam.get_role(RoleName=NAME)["Role"]
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": secret["ARN"],
            },
            {
                "Effect": "Allow",
                "Action": ["dynamodb:UpdateItem"],
                "Resource": f"arn:aws:dynamodb:{region}:{account}:table/{table_name}",
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{NAME}:*",
            },
        ],
    }
    policy["Statement"].extend(validation_policy)
    iam.put_role_policy(
        RoleName=NAME, PolicyName=NAME, PolicyDocument=json.dumps(policy)
    )
    logs = session.client("logs")
    try:
        logs.create_log_group(logGroupName="/aws/lambda/" + NAME)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    logs.put_retention_policy(logGroupName="/aws/lambda/" + NAME, retentionInDays=7)
    function = session.client("lambda")
    environment = {
        "AI_CORE_SECRET_ID": secret["ARN"],
        "QUOTA_TABLE": table_name,
        "RUNS_ROOT": "/tmp/factory-runs",
        "FACTORY_REVISION": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    environment.update(validation_environment)
    # Shared across Lambda instances and retained on redeploys. Never sent to the browser.
    existing_config = None
    try:
        existing_config = function.get_function_configuration(FunctionName=NAME)
        confirmation_key = (
            existing_config.get("Environment", {})
            .get("Variables", {})
            .get("FACTORY_CONFIRMATION_KEY")
        )
    except function.exceptions.ResourceNotFoundException:
        confirmation_key = None
    environment["FACTORY_CONFIRMATION_KEY"] = confirmation_key or token_urlsafe(32)
    if existing_config and not confirmation_key:
        bootstrap = dict(existing_config.get("Environment", {}).get("Variables", {}))
        bootstrap["FACTORY_CONFIRMATION_KEY"] = environment["FACTORY_CONFIRMATION_KEY"]
        function.update_function_configuration(
            FunctionName=NAME, Environment={"Variables": bootstrap}
        )
        function.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    try:
        function.get_function(FunctionName=NAME)
        function.update_function_code(FunctionName=NAME, ZipFile=package.read_bytes())
        function.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        function.update_function_configuration(
            FunctionName=NAME,
            Role=role["Arn"],
            Handler="infra.advisor.handler.lambda_handler",
            Runtime="python3.13",
            Timeout=240,
            MemorySize=1024,
            Environment={"Variables": environment},
        )
        function.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    except function.exceptions.ResourceNotFoundException:
        for attempt in range(10):
            try:
                function.create_function(
                    FunctionName=NAME,
                    Runtime="python3.13",
                    Role=role["Arn"],
                    Handler="infra.advisor.handler.lambda_handler",
                    Code={"ZipFile": package.read_bytes()},
                    Timeout=240,
                    MemorySize=1024,
                    Architectures=["x86_64"],
                    Environment={"Variables": environment},
                    Tags={"Project": "micro-integration-factory-skill"},
                )
                break
            except function.exceptions.InvalidParameterValueException as error:
                if "assumed" not in str(error) or attempt == 9:
                    raise
                time.sleep(3)
        function.get_waiter("function_active_v2").wait(FunctionName=NAME)
    function.put_function_concurrency(FunctionName=NAME, ReservedConcurrentExecutions=3)
    cors = {
        "AllowOrigins": ["https://solacese.github.io", "http://localhost:8086"],
        "AllowMethods": ["GET", "POST"],
        "AllowHeaders": ["Content-Type"],
        "MaxAge": 300,
    }
    try:
        url = function.create_function_url_config(
            FunctionName=NAME, AuthType="NONE", Cors=cors
        )["FunctionUrl"]
    except function.exceptions.ResourceConflictException:
        url = function.update_function_url_config(
            FunctionName=NAME, AuthType="NONE", Cors=cors
        )["FunctionUrl"]
    for sid, action, extra in [
        ("public-url", "lambda:InvokeFunctionUrl", {"FunctionUrlAuthType": "NONE"}),
        ("public-via-url", "lambda:InvokeFunction", {"InvokedViaFunctionUrl": True}),
    ]:
        try:
            function.add_permission(
                FunctionName=NAME,
                StatementId=sid,
                Action=action,
                Principal="*",
                **extra,
            )
        except function.exceptions.ResourceConflictException:
            pass
    config = {"apiBaseUrl": url.rstrip("/")}
    (ROOT / "docs/demo-config.json").write_text(json.dumps(config, indent=2) + "\n")
    (ROOT / ".runtime/advisor-deployment.json").write_text(
        json.dumps({"function": NAME, "region": region, "url": url}, indent=2) + "\n"
    )
    print("Advisor deployed:", url, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-core-env", required=True, type=Path)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    deploy(args.ai_core_env.expanduser(), args.region)
