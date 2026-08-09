from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import ProviderResult, ProviderUsage
from .security import canonical_body, sign_request


class ProviderUnavailable(RuntimeError):
    def __init__(self, message: str, *, accounted_neurons: int | None = None) -> None:
        super().__init__(message);self.accounted_neurons=accounted_neurons


@dataclass(frozen=True)
class LocalAiService:
    endpoint: str = "http://127.0.0.1:8080/v1/chat/completions"
    model: str = "local-model"
    timeout_seconds: int = 60
    api_key: str = ""

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local AI endpoint must use HTTP on loopback")

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> ProviderResult:
        started = time.monotonic()
        # llama.cpp's OpenAI-compatible server expects the JSON Schema in the
        # `schema` member (not OpenAI's nested `json_schema` member).
        data = json.dumps({"model": self.model, "messages": messages, "temperature": 0,
                           "chat_template_kwargs": {"enable_thinking": False},
                           "response_format": {"type": "json_object", "schema": response_schema}}).encode()
        try:
            headers={"Content-Type":"application/json"}
            if self.api_key: headers["Authorization"]=f"Bearer {self.api_key}"
            with urlopen(Request(self.endpoint, data=data, headers=headers),
                         timeout=self.timeout_seconds) as response:
                raw = json.load(response)
        except (OSError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("local model runtime unavailable") from exc
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try: payload = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError as exc: raise ProviderUnavailable("local model returned invalid JSON") from exc
        usage = raw.get("usage", {})
        return ProviderResult(payload, ProviderUsage(int(usage.get("prompt_tokens", 0)),
                              int(usage.get("completion_tokens", 0))), "LOCAL", self.model,
                              int((time.monotonic() - started) * 1000))


@dataclass(frozen=True)
class CloudAiService:
    worker_url: str
    hmac_secret: str
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        parsed = urlparse(self.worker_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("cloud Worker URL must be an HTTPS origin")
        if not self.hmac_secret: raise ValueError("cloud HMAC secret is required")

    def complete(self, task: str, model_role: str, message: str, request_id: str,
                 sanitized_image_data_url: str | None = None) -> ProviderResult:
        started = time.monotonic()
        payload: dict[str, Any] = {"task": task, "model_role": model_role,
                                  "message": message, "request_id": request_id}
        if sanitized_image_data_url:
            payload["sanitized_image_data_url"] = sanitized_image_data_url
        body = canonical_body(payload); timestamp = int(time.time())
        headers = {"Content-Type":"application/json", "Accept":"application/json",
                   "User-Agent":"BusinessAutomationCloudAiService/1.0", "X-AI-Timestamp":str(timestamp),
                   "X-AI-Signature":sign_request(self.hmac_secret, timestamp, body),
                   "X-AI-Body-SHA256":__import__("hashlib").sha256(body).hexdigest()}
        try:
            with urlopen(Request(self.worker_url, data=body, headers=headers), timeout=self.timeout_seconds) as response:
                raw = json.load(response)
        except HTTPError as exc:
            try:
                error_payload=json.loads(exc.read().decode("utf-8"));usage=error_payload.get("usage",{})
                estimate=usage.get("application_estimated_neurons")
                accounted=estimate if (usage.get("accounting_basis")=="CONSERVATIVE_APPLICATION_ESTIMATE" and
                    isinstance(estimate,int) and not isinstance(estimate,bool) and estimate>0) else None
            except (UnicodeDecodeError,json.JSONDecodeError,AttributeError): accounted=None
            raise ProviderUnavailable("authorized cloud AI Worker rejected provider output",
                                      accounted_neurons=accounted) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("authorized cloud AI Worker unavailable") from exc
        usage=raw.get("usage", {})
        estimate=usage.get("application_estimated_neurons")
        if (usage.get("accounting_basis") != "CONSERVATIVE_APPLICATION_ESTIMATE" or
                not isinstance(estimate, int) or isinstance(estimate, bool) or estimate < 1):
            raise ProviderUnavailable("cloud usage cannot be accounted safely under FREE_ONLY policy")
        provider_neurons=usage.get("provider_reported_neurons")
        if provider_neurons is not None and (not isinstance(provider_neurons, int) or provider_neurons < 0):
            raise ProviderUnavailable("provider usage metadata is invalid")
        resolved_model=str(raw.get("model", ""))
        if model_role == "TEXT_TOOL_MODEL" and resolved_model != "@cf/zai-org/glm-4.7-flash":
            raise ProviderUnavailable("Worker resolved an unexpected text model")
        if model_role == "VISION_DOCUMENT_MODEL" and resolved_model != "@cf/google/gemma-4-26b-a4b-it":
            raise ProviderUnavailable("Worker resolved an unexpected vision model")
        return ProviderResult(raw.get("proposal", {}), ProviderUsage(
                              int(usage.get("input_tokens",0)), int(usage.get("output_tokens",0)),
                              provider_neurons, estimate, estimate,
                              "CONSERVATIVE_APPLICATION_ESTIMATE",
                              usage.get("provider_usage_verifiable") is True),
                              "CLOUDFLARE_WORKERS_AI", resolved_model,
                              int((time.monotonic() - started) * 1000))
