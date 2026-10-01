"""AgentPost configuration - loads from agentpost.yaml + environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class ApiConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8765
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])


class ScanConfig(BaseSettings):
    default_interval_sec: int = 15


class SecurityConfig(BaseSettings):
    require_from_match: bool = True
    allow_broadcast: bool = False
    script_timeout_sec: int = 5


class ReceiptsConfig(BaseSettings):
    always_on_reject: bool = True
    on_deliver_if_ack: bool = True


class Settings(BaseSettings):
    domain: str = "agentpost.local"
    root: str = "/var/lib/agentpost"
    watch_interval_ms: int = 500
    max_attachment_bytes: int = 10_485_760
    max_message_bytes: int = 2_097_152
    api: ApiConfig = Field(default_factory=ApiConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    receipts: ReceiptsConfig = Field(default_factory=ReceiptsConfig)
    operator_token: str = Field(default="", alias="AGENTPOST_OPERATOR_TOKEN")
    auto_init: bool = Field(default=True, alias="AGENTPOST_AUTO_INIT")

    model_config = {"env_prefix": "AGENTPOST_", "env_nested_delimiter": "__", "extra": "ignore"}

    @property
    def root_path(self) -> Path:
        return Path(self.root)


def load_settings() -> Settings:
    """Load settings from YAML file (if exists) merged with environment variables."""
    yaml_path = os.environ.get("AGENTPOST_CONFIG", "")
    yaml_data: dict[str, Any] = {}

    if not yaml_path:
        root = os.environ.get("AGENTPOST_ROOT", "/var/lib/agentpost")
        candidate = Path(root) / "agentpost.yaml"
        if candidate.exists():
            yaml_path = str(candidate)

    if yaml_path and Path(yaml_path).exists():
        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f) or {}

    return Settings(**yaml_data)
