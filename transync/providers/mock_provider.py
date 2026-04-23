"""Mock translation provider for testing and dry-run mode."""

from __future__ import annotations

from transync.providers.base import (
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)


class MockProvider(TranslationProvider):
    """Returns placeholder translations: wraps the source text with the target language tag."""

    @property
    def name(self) -> str:
        return "mock"

    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        return [
            TranslationResult(
                key=r.key,
                source_text=r.source_text,
                translated_text=f"[{r.target_language}] {r.source_text}",
                target_language=r.target_language,
                provider=self.name,
            )
            for r in requests
        ]
