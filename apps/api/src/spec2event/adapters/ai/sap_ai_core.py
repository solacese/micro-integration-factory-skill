"""SAP AI Core inference with server-side credentials and renewable OAuth tokens."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx


class SapAiCoreProvider:
    def __init__(self, credentials: dict[str, str] | None = None, client=None):
        self._credentials = credentials
        self.client = client or httpx.Client(timeout=httpx.Timeout(90, connect=10))
        self._token = ""
        self._expires = 0.0

    @property
    def credentials(self) -> dict[str, str]:
        if self._credentials is None:
            secret_id = os.environ.get("AI_CORE_SECRET_ID")
            if secret_id:
                import boto3

                secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
                self._credentials = json.loads(secret["SecretString"])
            else:
                self._credentials = dict(os.environ)
        return self._credentials

    def _access_token(self, refresh=False) -> str:
        if not refresh and self._token and time.monotonic() < self._expires:
            return self._token
        c = self.credentials
        response = self.client.post(
            c["SAP_AUTH_URL"].rstrip("/") + "/oauth/token",
            data={"grant_type": "client_credentials"},
            auth=(c["SAP_CLIENT_ID"], c["SAP_CLIENT_SECRET"]),
        )
        if response.status_code != 200:
            raise RuntimeError("SAP AI Core authentication failed; check server credentials")
        data = response.json()
        self._token = data["access_token"]
        self._expires = time.monotonic() + max(0, int(data.get("expires_in", 300)) - 60)
        return self._token

    def complete(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        c = self.credentials
        deployment = c.get("AI_CORE_DEPLOYMENT_ID") or c.get("SAP_DEPLOYMENT_GPT56_SOL")
        if not deployment:
            raise ValueError(
                "Set AI_CORE_DEPLOYMENT_ID to an existing OpenAI-compatible AI Core deployment"
            )
        base = c["SAP_API_BASE_URL"].rstrip("/")
        model = c.get("AI_CORE_MODEL", "gpt-5.6-sol")
        # Use the same native Responses route as the user's working Claude Code
        # proxy, preserving tool calls and reasoning items between tool rounds.
        inputs = []
        instructions = []
        for message in messages:
            if message["role"] == "system":
                instructions.append(message["content"])
            elif message["role"] == "tool":
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["tool_call_id"],
                        "output": message["content"],
                    }
                )
            elif message.get("_response_output"):
                inputs.extend(message["_response_output"])
            else:
                inputs.append({"role": message["role"], "content": message.get("content") or ""})
        body = {
            "model": model,
            "instructions": "\n".join(instructions),
            "input": inputs,
            "max_output_tokens": 16000,
            "reasoning": {"effort": "medium"},
            "tools": [{"type": "function", **tool["function"]} for tool in tools],
        }
        if len(tools) == 1:
            body["tool_choice"] = {"type": "function", "name": tools[0]["function"]["name"]}
        for attempt in range(2):
            token = self._access_token(refresh=attempt > 0)
            response = self.client.post(
                f"{base}/v2/inference/deployments/{deployment}/responses",
                headers={
                    "Authorization": "Bearer " + token,
                    "AI-Resource-Group": c.get("SAP_RESOURCE_GROUP", "default"),
                },
                json=body,
            )
            if response.status_code == 401 and attempt == 0:
                continue
            if response.is_error:
                # Do not reflect upstream URLs, credentials, or request bodies to browsers.
                raise RuntimeError(f"SAP AI Core inference failed (HTTP {response.status_code})")
            data = response.json()
            output = data.get("output", [])
            text = "\n".join(
                part.get("text", "")
                for item in output
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            calls = [
                {
                    "id": item["call_id"],
                    "type": "function",
                    "function": {"name": item["name"], "arguments": item["arguments"]},
                }
                for item in output
                if item.get("type") == "function_call"
            ]
            if not text and not calls:
                raise RuntimeError("SAP AI Core returned no complete answer or tool call")
            return {
                "role": "assistant",
                "content": text,
                "tool_calls": calls,
                "_response_output": output,
            }
        raise RuntimeError("SAP AI Core token refresh failed")
