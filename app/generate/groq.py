from __future__ import annotations

import time
from typing import Any, Callable

from app import config
from app.generate.extractive import ExtractiveAnswerer
from app.generate.prompts import SYSTEM_PROMPT

RETRYABLE_NAMES = (
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailableError",
    "Timeout",
    "TimeoutError",
    "TooManyRequests",
)


def is_retryable(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    try:
        import httpx
    except ImportError:
        pass
    else:
        if isinstance(error, httpx.TimeoutException):
            return True
    try:
        from groq import GroqError
    except ImportError:
        return False
    if isinstance(error, GroqError):
        return type(error).__name__ in RETRYABLE_NAMES or "timeout" in type(
            error
        ).__name__.lower()
    return False


class GroqAnswerer:
    name = "groq"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        fallback: Any = None,
        max_retries: int | None = None,
        backoff: float | None = None,
        client: Any = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model or config.LLM_MODEL
        self._api_key = api_key
        self._base_url = base_url
        self.fallback = fallback if fallback is not None else ExtractiveAnswerer()
        self.max_retries = (
            config.LLM_MAX_RETRIES if max_retries is None else max_retries
        )
        self.backoff = (
            config.LLM_RETRY_BACKOFF_SECONDS if backoff is None else backoff
        )
        self._client = client
        self._sleeper = sleeper
        self.served_by = self.name
        self.attempts = 0
        self.last_error: str | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            from groq import Groq

            self._client = Groq(
                api_key=self._api_key or config.llm_api_key(),
                base_url=self._base_url or config.LLM_BASE_URL,
                timeout=config.LLM_TIMEOUT_SECONDS,
                max_retries=0,
            )
        return self._client

    def request_kwargs(self, system: str, user: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": config.LLM_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if config.LLM_TEMPERATURE is not None:
            payload["temperature"] = config.LLM_TEMPERATURE
        return payload

    def call(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(**self.request_kwargs(system, user))
        content = response.choices[0].message.content
        return (content or "").strip()

    def generate(self, system: str, user: str) -> str:
        self.served_by = self.name
        self.last_error = None
        try:
            self.attempts = 1
            return self.call(system, user)
        except Exception as error:
            if not is_retryable(error):
                self.last_error = f"{type(error).__name__}: {error}"
                return self._serve_fallback(system, user, error)
            for attempt in range(self.max_retries):
                self.attempts = attempt + 2
                self._sleeper(self.backoff * (attempt + 1))
                try:
                    return self.call(system, user)
                except Exception as retry_error:
                    error = retry_error
            self.last_error = f"{type(error).__name__}: {error}"
            return self._serve_fallback(system, user, error)

    def _serve_fallback(self, system: str, user: str, error: BaseException) -> str:
        self.served_by = getattr(self.fallback, "name", "extractive")
        return self.fallback.generate(system, user)

    def regenerate_short(
        self, system: str, user: str, instruction: str
    ) -> str:
        return self.call(system, f"{user}\n\n{instruction}")

    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT
