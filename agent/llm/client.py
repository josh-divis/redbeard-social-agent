"""
OpenAI-compatible chat client for xAI Grok (or OpenAI).

Uses the official `openai` Python SDK pointed at an arbitrary base_url,
so switching between Grok and OpenAI is a config change only.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.config import LLMConfig

logger = logging.getLogger("redbeard.llm")


class LLMError(Exception):
    """Raised when the LLM call fails after retries or returns unusable content."""


class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completions."""

    def __init__(self, cfg: LLMConfig):
        if not cfg.api_key:
            raise LLMError("LLM API key is empty")
        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        logger.info(
            "LLM client ready provider=%s model=%s base=%s",
            cfg.provider,
            cfg.model,
            cfg.base_url,
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((LLMError, TimeoutError, ConnectionError)),
    )
    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """
        Run a single chat completion and return the assistant text.
        Retries on transient failures.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.cfg.max_tokens,
        }
        # json_object mode is widely supported on OpenAI-compatible APIs
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            logger.debug("LLM request model=%s json_mode=%s", self.cfg.model, json_mode)
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning("LLM request failed: %s", exc)
            raise LLMError(str(exc)) from exc

        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError) as exc:
            raise LLMError(f"Malformed LLM response: {exc}") from exc

        content = content.strip()
        if not content:
            raise LLMError("Empty LLM response")
        return content

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Request JSON and parse it, with a fallback strip of markdown fences."""
        raw = self.chat(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        # Strip ```json ... ``` fences if the model ignored json_mode
        fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # Last resort: find first { ... } block
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    raise LLMError(f"Could not parse JSON from model: {exc}") from exc
            else:
                raise LLMError(f"Could not parse JSON from model: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"Expected JSON object, got {type(data).__name__}")
        return data
