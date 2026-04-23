"""Abstract base class for all translation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranslationRequest:
    key: str
    source_text: str
    target_language: str


@dataclass
class TranslationResult:
    key: str
    source_text: str
    translated_text: str
    target_language: str
    provider: str


class TranslationProvider(ABC):
    """Interface every translation provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        """Translate a batch of strings. May raise TranslationError."""
        ...


class TranslationError(Exception):
    """Raised when translation fails."""
