"""Submit isolated builds and unlock artifacts only after real 1k/s evidence passes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import time
import uuid

from spec2event.services.service_confirmation import _key


def report_passes(report: dict) -> bool:
    if report.get("status") != "passed":
        return False
    for language in ["java", "go"]:
        data = report.get("runtimes", {}).get(language, {})
        rate = data.get("achievedRate", 0)
        if (
            data.get("passed") is not True
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate < 1000
            or data.get("targetRate") != 1000
            or data.get("durationSeconds", 0) < 10
            or data.get("sent", 0) < 10000
            or data.get("received") != data.get("sent")
            or data.get("errors") != 0
            or data.get("duplicates") != 0
        ):
            return False
    return True


class ValidationService:
    def __init__(self, session=None):
        self.bucket = os.getenv("VALIDATION_BUCKET", "")
        self.project = os.getenv("VALIDATION_PROJECT", "")
        self.session = session

    def _clients(self):
        import boto3

        session = self.session or boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
        from botocore.config import Config

        return session.client("s3", config=Config(signature_version="s3v4")), session.client(
            "codebuild"
        )

    def _token(self, job, digest):
        body = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {"job": job, "digest": digest, "expires": int(time.time()) + 7200}
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
        return (
            body
            + "."
            + hmac.new(_key(), ("validation:" + body).encode(), hashlib.sha256).hexdigest()
        )

    def _verify(self, job, token):
        if (
            not isinstance(token, str)
            or len(token) > 2000
            or not isinstance(job, str)
            or len(job) != 32
        ):
            raise ValueError("Invalid validation receipt")
        try:
            body, signature = token.rsplit(".", 1)
            expected = hmac.new(_key(), ("validation:" + body).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            receipt = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if receipt["job"] != job or receipt["expires"] < time.time():
                raise ValueError()
            return receipt
        except (ValueError, KeyError, TypeError):
            raise ValueError("Validation receipt expired or invalid. Start a new MI.") from None

    def _budget(self):
        table = os.getenv("QUOTA_TABLE")
        if not table:
            return
        import boto3
        from botocore.exceptions import ClientError

        now = int(time.time())
        try:
            boto3.resource("dynamodb").Table(table).update_item(
                Key={"bucket": "validation-day:" + str(now // 86400)},
                UpdateExpression="ADD uses :one SET expiresAt=:expires",
                ConditionExpression="attribute_not_exists(uses) OR uses < :limit",
                ExpressionAttributeValues={
                    ":one": 1,
                    ":expires": now + 172800,
                    ":limit": int(os.getenv("DAILY_VALIDATION_LIMIT", "20")),
                },
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(
                    "The daily validation limit has been reached. Try again later."
                ) from None
            raise

    def submit(self, project, sources=None):
        if not self.bucket or not self.project:
            raise RuntimeError(
                "The required build/performance validation service is not configured"
            )
        self._budget()
        s3, build = self._clients()
        job = uuid.uuid4().hex
        prefix = "jobs/" + job + "/"
        raw = json.dumps(
            {"project": project, "revision": os.getenv("FACTORY_REVISION", "development")},
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(raw).hexdigest()
        s3.put_object(
            Bucket=self.bucket, Key=prefix + "input.json", Body=raw, ContentType="application/json"
        )
        started = build.start_build(
            projectName=self.project,
            environmentVariablesOverride=[
                {"name": "VALIDATION_JOB_ID", "value": job, "type": "PLAINTEXT"}
            ],
        )["build"]
        s3.put_object(
            Bucket=self.bucket,
            Key=prefix + "job.json",
            Body=json.dumps(
                {"buildId": started["id"], "inputSha256": digest, "sources": sources or []}
            ).encode(),
            ContentType="application/json",
        )
        return {
            "status": "validating",
            "content": "Both implementations are generated. I’m compiling them and checking real delivery at 1,000 messages/s before enabling downloads.",
            "project": None,
            "jobId": job,
            "validationToken": self._token(job, digest),
            "sources": sources or [],
        }

    def status(self, job, token):
        receipt = self._verify(job, token)
        s3, build = self._clients()
        prefix = "jobs/" + job + "/"

        def read(name):
            try:
                return json.loads(
                    s3.get_object(Bucket=self.bucket, Key=prefix + name)["Body"].read()
                )
            except s3.exceptions.NoSuchKey:
                return None

        job_data = read("job.json")
        if not job_data or job_data["inputSha256"] != receipt["digest"]:
            raise ValueError("Validation job does not match the receipt")
        report = read("report.json")
        if report:
            if report.get("inputSha256") != receipt["digest"] or report.get("jobId") != job:
                raise ValueError("Validation evidence does not match this artifact")
            if not report_passes(report):
                return {
                    "status": "validation_failed",
                    "project": None,
                    "content": report.get(
                        "error",
                        "The build/performance checks did not pass. Downloads remain locked.",
                    ),
                    "performance": report,
                }
            original = read("input.json")["project"]
            downloads = {}
            artifact_kinds = ["java", "go", "configuration"]
            if "tests" in original:
                artifact_kinds.append("tests")
            for language in artifact_kinds:
                item = report.get("downloads", {}).get(language)
                if not item or not item["key"].startswith(prefix + "downloads/"):
                    raise RuntimeError("Validated artifact is missing")
                downloads[language] = {
                    key: item[key] for key in ["filename", "sha256", "contentType"]
                }
                downloads[language]["downloadUrl"] = s3.generate_presigned_url(
                    "get_object", Params={"Bucket": self.bucket, "Key": item["key"]}, ExpiresIn=3600
                )
            project = {
                **downloads,
                "coreJava": original["coreJava"],
                "coreGo": original["coreGo"],
                "contractExamples": original["contractExamples"],
                "goTransport": report["runtimes"]["go"].get("transport"),
                "performance": report,
                "files": original["files"],
            }
            return {
                "status": "generated",
                "content": "Both MIs passed build, contract, and >=1,000 messages/s delivery checks. Choose a runtime and complete the shared YAML with your credentials.",
                "project": project,
                "performance": report,
                "sources": job_data["sources"],
            }
        progress = read("progress.json") or {
            "stage": "queued",
            "note": "Waiting for an isolated benchmark worker",
        }
        state = build.batch_get_builds(ids=[job_data["buildId"]])["builds"]
        if state and state[0]["buildStatus"] in {"FAILED", "FAULT", "STOPPED", "TIMED_OUT"}:
            return {
                "status": "validation_failed",
                "project": None,
                "content": "The validation worker stopped before completing every check. Downloads remain locked.",
            }
        return {"status": "validating", "project": None, **progress}
