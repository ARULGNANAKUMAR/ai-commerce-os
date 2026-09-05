"""
ai/provider_adapters.py
───────────────────────
Provider-agnostic adapter layer. Adding a new AI provider (Claude,
Mistral, Cohere…) means adding one adapter class and registering it
in ADAPTER_REGISTRY — zero changes to the rest of the codebase.

Each adapter exposes:
    test_connection(api_key, model) → (success: bool, message: str)
    complete(api_key, model, prompt, system=None) → str

For Phase 2, only test_connection is used publicly. complete() is
the Phase 3 hook for the AI agent engine.
"""

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from config import Config


class BaseAdapter(ABC):
    PROVIDER_ID: str = ""
    MODELS: list = []

    @abstractmethod
    def test_connection(self, api_key: str, model: str) -> tuple[bool, str]:
        ...

    @abstractmethod
    def complete(self, api_key: str, model: str, prompt: str, system: str = None) -> str:
        ...

    def _http_post(self, url: str, headers: dict, payload: dict) -> dict:
        """Shared HTTP POST with standard error mapping."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=Config.AI_TEST_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            raise _ProviderHTTPError(e.code, body)
        except urllib.error.URLError as e:
            raise _ProviderNetworkError(str(e.reason))

    @staticmethod
    def _safe_message(http_error: "ProviderHTTPError") -> str:
        code = http_error.status_code
        if code == 400:
            return "Invalid request — check your API key format."
        if code == 401:
            return "Invalid or expired API key."
        if code == 403:
            return "API key does not have permission for this model."
        if code == 429:
            return "Rate limit reached on your API key. Try again shortly."
        if code >= 500:
            return f"Provider server error ({code}). Try again later."
        return f"Provider returned HTTP {code}."


class _ProviderHTTPError(Exception):
    def __init__(self, status_code, body=""):
        self.status_code = status_code
        self.body = body


class _ProviderNetworkError(Exception):
    pass


# ── Gemini adapter ────────────────────────────────────────────────────

class GeminiAdapter(BaseAdapter):
    PROVIDER_ID = "gemini"
    MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def _url(self, model: str) -> str:
        return f"{self.BASE_URL}/{model}:generateContent"

    def _headers(self, api_key: str) -> dict:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

    def _payload(self, prompt: str, system: str = None) -> dict:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": contents}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        return payload

    def test_connection(self, api_key: str, model: str) -> tuple[bool, str]:
        try:
            result = self._http_post(
                self._url(model),
                self._headers(api_key),
                self._payload("Reply with exactly one word: CONNECTED"),
            )
            if "candidates" in result and result["candidates"]:
                return True, "Connection successful."
            return False, "Unexpected response format from Gemini."
        except _ProviderHTTPError as e:
            return False, self._safe_message(e)
        except _ProviderNetworkError:
            return False, "Network error — could not reach Google AI. Check your server's internet access."
        except Exception:
            return False, "Connection test failed — unexpected error."

    def complete(self, api_key: str, model: str, prompt: str, system: str = None) -> str:
        result = self._http_post(self._url(model), self._headers(api_key), self._payload(prompt, system))
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""


# ── OpenAI adapter ────────────────────────────────────────────────────

class OpenAIAdapter(BaseAdapter):
    PROVIDER_ID = "openai"
    MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def _headers(self, api_key: str) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def _payload(self, prompt: str, model: str, system: str = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return {"model": model, "messages": messages, "max_tokens": 20}

    def test_connection(self, api_key: str, model: str) -> tuple[bool, str]:
        try:
            result = self._http_post(
                self.BASE_URL,
                self._headers(api_key),
                self._payload("Reply with exactly one word: CONNECTED", model),
            )
            if result.get("choices") and result["choices"][0].get("message"):
                return True, "Connection successful."
            return False, "Unexpected response format from OpenAI."
        except _ProviderHTTPError as e:
            return False, self._safe_message(e)
        except _ProviderNetworkError:
            return False, "Network error — could not reach OpenAI. Check your server's internet access."
        except Exception:
            return False, "Connection test failed — unexpected error."

    def complete(self, api_key: str, model: str, prompt: str, system: str = None) -> str:
        result = self._http_post(self.BASE_URL, self._headers(api_key), self._payload(prompt, model, system))
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return ""


# ── Registry ──────────────────────────────────────────────────────────

ADAPTER_REGISTRY: dict[str, BaseAdapter] = {
    "gemini": GeminiAdapter(),
    "openai": OpenAIAdapter(),
}


def get_adapter(provider: str) -> BaseAdapter:
    adapter = ADAPTER_REGISTRY.get(provider)
    if not adapter:
        from utils import ApiError
        raise ApiError(f"Unknown AI provider '{provider}'.", 400, code="UNKNOWN_PROVIDER")
    return adapter


def get_provider_models(provider: str) -> list:
    adapter = ADAPTER_REGISTRY.get(provider)
    return adapter.MODELS if adapter else []
