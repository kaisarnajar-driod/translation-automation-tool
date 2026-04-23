"""OpenAI / GPT-based translation provider."""

from __future__ import annotations

import json
import logging
import time

from openai import OpenAI, APIError, RateLimitError

from transync.providers.base import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a professional Android app translator. You translate UI strings accurately while:
1. Preserving ALL format placeholders exactly as-is: %s, %d, %1$s, %2$d, etc.
2. Preserving HTML tags: <b>, <i>, <u>, <br/>, <a href="...">, etc.
3. Keeping the tone appropriate for a mobile app UI.
4. NOT translating brand names or technical terms unless they have standard translations.
5. Handling plurals and gender-specific language naturally for the target locale.

Reply ONLY with a JSON object mapping each key to its translated value. No extra text."""


class OpenAIProvider(TranslationProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        max_batch_size: int = 20,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise TranslationError("OpenAI API key is required")
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._max_batch = max_batch_size
        self._temperature = temperature
        self._max_retries = max_retries

    @property
    def name(self) -> str:
        return "openai"

    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        if not requests:
            return []

        # All requests in a batch target the same language
        target_lang = requests[0].target_language
        results: list[TranslationResult] = []

        # Split into sub-batches
        for i in range(0, len(requests), self._max_batch):
            chunk = requests[i : i + self._max_batch]
            results.extend(self._translate_chunk(chunk, target_lang))

        return results

    def _translate_chunk(
        self, chunk: list[TranslationRequest], target_lang: str
    ) -> list[TranslationResult]:
        source_map = {r.key: r.source_text for r in chunk}
        user_msg = (
            f"Translate the following Android string resources to '{target_lang}'.\n"
            f"Return a JSON object mapping each key to its translation.\n\n"
            f"{json.dumps(source_map, ensure_ascii=False, indent=2)}"
        )

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                )
                raw = response.choices[0].message.content or "{}"
                translated = json.loads(raw)
                break
            except RateLimitError:
                wait = 2**attempt
                logger.warning("Rate limited, retrying in %ds (attempt %d)", wait, attempt)
                time.sleep(wait)
                if attempt == self._max_retries:
                    raise TranslationError("OpenAI rate limit exceeded after retries")
            except (APIError, json.JSONDecodeError) as exc:
                if attempt == self._max_retries:
                    raise TranslationError(f"OpenAI translation failed: {exc}") from exc
                time.sleep(1)

        results: list[TranslationResult] = []
        for req in chunk:
            text = translated.get(req.key, req.source_text)
            results.append(
                TranslationResult(
                    key=req.key,
                    source_text=req.source_text,
                    translated_text=text,
                    target_language=target_lang,
                    provider=self.name,
                )
            )
        return results
