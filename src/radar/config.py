"""Configuration: environment variables (secrets) + YAML file (behaviour)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GithubReleasesSourceCfg(BaseModel):
    include_prereleases: bool = False
    targets: list[str] = Field(default_factory=list)


class SourcesCfg(BaseModel):
    github_releases: GithubReleasesSourceCfg = Field(default_factory=GithubReleasesSourceCfg)


class FilterCfg(BaseModel):
    enabled: bool = False
    provider: str = "anthropic"
    model: str = "claude-haiku-5-5"
    criteria: str = ""


class NotifyCfg(BaseModel):
    alerts: str = "discord"
    health: str = "discord"


class YamlConfig(BaseModel):
    poll_interval_s: int = 30
    jitter_s: int = 3
    fail_alert_after_s: int = 300
    heartbeat_interval_s: int = 21600
    sources: SourcesCfg = Field(default_factory=SourcesCfg)
    filter: FilterCfg = Field(default_factory=FilterCfg)
    notify: NotifyCfg = Field(default_factory=NotifyCfg)


class Settings(BaseSettings):
    """Secrets and runtime knobs pulled from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    LLM_PROVIDER: str = "anthropic"
    LLM_MODEL: str = "claude-haiku-5-5"
    ANTHROPIC_API_KEY: str = ""

    GITHUB_TOKEN: str = ""

    SANDBOX_REPO: str = ""
    SANDBOX_GITHUB_TOKEN: str = ""

    DISCORD_ALERTS_WEBHOOK_URL: str = ""
    DISCORD_HEALTH_WEBHOOK_URL: str = ""

    HEALTHCHECKS_PING_URL: str = ""

    RADAR_DB_PATH: str = "data/radar.db"


class Config(BaseModel):
    """Merged runtime config used by the scheduler."""

    settings: Settings
    yaml: YamlConfig

    @property
    def db_path(self) -> Path:
        return Path(self.settings.RADAR_DB_PATH)


def load_yaml(path: str | Path | None = None) -> YamlConfig:
    """Load the YAML behaviour config; fall back to defaults if missing."""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        env_path = os.environ.get("RADAR_CONFIG")
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend([Path("config.yaml"), Path("config.example.yaml")])
    for p in candidates:
        if p.is_file():
            data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            return YamlConfig.model_validate(data)
    return YamlConfig()


def load_config(config_path: str | Path | None = None) -> Config:
    """Merge env settings with the YAML behaviour file."""
    settings = Settings(_env_file=os.environ.get("RADAR_ENV_FILE", ".env"))
    return Config(settings=settings, yaml=load_yaml(config_path))
