"""Centralised configuration loaded from YAML + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DEFAULT_CONFIG_LOCATIONS = [
    Path("config.yaml"),
    Path("config.yml"),
    Path.home() / ".transync" / "config.yaml",
]

CONFIG_ENV_VAR = "TRANSYNC_CONFIG"


class GitConfig(BaseModel):
    default_branch: str = "main"
    commit_message: str = "chore: add translations for new strings"


class OpenAIConfig(BaseModel):
    model: str = "gpt-4o"
    api_key: str = ""
    max_batch_size: int = 20
    temperature: float = 0.2


class DeepLConfig(BaseModel):
    api_key: str = ""


class GoogleConfig(BaseModel):
    api_key: str = ""


class TranslationConfig(BaseModel):
    provider: str = "google_free"
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    deepl: DeepLConfig = Field(default_factory=DeepLConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)


class SyncConfig(BaseModel):
    dry_run: bool = False
    detect_modified: bool = False
    sort_keys: bool = True


class DatabaseConfig(BaseModel):
    path: str = "~/.transync/transync.db"

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()


class LoggingConfig(BaseModel):
    level: str = "INFO"


class AppConfig(BaseModel):
    default_strings_path: str = "strings.xml"
    res_directory: str = "."
    git: GitConfig = Field(default_factory=GitConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _overlay_env(cfg: AppConfig) -> AppConfig:
    """Override select config values from environment variables."""
    if key := os.getenv("OPENAI_API_KEY"):
        cfg.translation.openai.api_key = key
    if key := os.getenv("DEEPL_API_KEY"):
        cfg.translation.deepl.api_key = key
    if key := os.getenv("GOOGLE_TRANSLATE_API_KEY"):
        cfg.translation.google.api_key = key
    if provider := os.getenv("TRANSYNC_PROVIDER"):
        cfg.translation.provider = provider
    if lvl := os.getenv("TRANSYNC_LOG_LEVEL"):
        cfg.logging.level = lvl
    return cfg


def _find_config_file() -> Path | None:
    env_path = os.getenv(CONFIG_ENV_VAR)
    if env_path:
        p = Path(env_path)
        return p if p.is_file() else None
    for loc in _DEFAULT_CONFIG_LOCATIONS:
        if loc.is_file():
            return loc
    return None


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file, falling back to defaults."""
    config_path = path or _find_config_file()
    raw: dict[str, Any] = {}
    if config_path and config_path.is_file():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    cfg = AppConfig(**raw)
    return _overlay_env(cfg)
