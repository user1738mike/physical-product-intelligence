"""Replaceable, optional OpenAI SDK adapter. No network calls on import or availability checks."""

import importlib.util
import json
import logging
import os
from typing import Protocol

from django.conf import settings

from .ai_schema import INSTRUCTIONS, MAX_OUTPUT, SCHEMA, VERSION


class ProviderFailure(Exception):
    def __init__(self, category, retryable=False):
        self.category, self.retryable = category, retryable
        super().__init__(category)


class ExtractionProvider(Protocol):
    def extract(self, segments: list[dict]) -> tuple[str, dict]: ...


def availability():
    if not settings.AI_EXTRACTION_ENABLED:
        return False, "disabled"
    if settings.AI_EXTRACTION_PROVIDER == "recorded":
        if getattr(settings, "ALLOW_REHEARSAL_PROVIDER", False):
            return True, "synthetic_rehearsal_only"
        return False, "unsupported_provider"
    if settings.AI_EXTRACTION_PROVIDER != "openai":
        return False, "unsupported_provider"
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return False, "credentials_unavailable"
    if not settings.AI_EXTRACTION_MODEL:
        return False, "model_unconfigured"
    if importlib.util.find_spec("openai") is None:
        return False, "sdk_unavailable"
    return True, "available"


class OpenAIProvider:
    def __init__(self, max_output_tokens=2500):
        self.max_output_tokens = max(100, min(2500, max_output_tokens))

    def extract(self, segments):
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

        # Prevent opt-in SDK wire debugging from recording private source text.
        prefixes = ("openai", "httpx", "httpcore", "httpx2", "httpcore2")
        for name in set(prefixes) | set(logging.Logger.manager.loggerDict):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
                logging.getLogger(name).disabled = True
        try:
            # Fixed origin: ignore ambient OPENAI_BASE_URL and browser-supplied configuration.
            with OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url="https://api.openai.com/v1",
                timeout=8.0,
                max_retries=0,
            ) as client:
                response = client.responses.create(
                    model=settings.AI_EXTRACTION_MODEL,
                    store=False,
                    input=[
                        {"role": "system", "content": INSTRUCTIONS},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"untrusted_segments": segments}, ensure_ascii=False
                            ),
                        },
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": VERSION.replace("-", "_"),
                            "strict": True,
                            "schema": SCHEMA,
                        }
                    },
                    max_output_tokens=self.max_output_tokens,
                )
        except APITimeoutError:
            raise ProviderFailure("timeout", True) from None
        except APIConnectionError:
            raise ProviderFailure("unavailable", True) from None
        except APIStatusError as error:
            code = error.status_code
            raise ProviderFailure(
                "rate_limit"
                if code == 429
                else "unavailable"
                if code >= 500
                else "authorization"
                if code in {401, 403}
                else "provider_validation",
                code == 429 or code >= 500,
            ) from None
        if response.status != "completed" or len(response.output_text.encode("utf-8")) > MAX_OUTPUT:
            raise ProviderFailure("incomplete_output")
        usage = response.usage
        return response.output_text, {
            key: max(0, min(int(getattr(usage, key, 0) or 0), 1000000))
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }


def configured_provider(*, max_output_tokens=2500):
    ready, category = availability()
    if not ready:
        raise ProviderFailure(category)
    if category == "synthetic_rehearsal_only":
        from .rehearsal_provider import RecordedProvider

        return RecordedProvider()
    return OpenAIProvider(max_output_tokens=max_output_tokens)
