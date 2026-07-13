"""
Configuration loader for RedBeard Social Agent.

Loads YAML defaults from config.yaml and secrets/overrides from .env.
Paths resolve relative to the project root so the agent runs cleanly
from cron, systemd, or an interactive shell on the Raspberry Pi.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root = parent of the `agent` package
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class LLMConfig:
    """Settings for the OpenAI-compatible chat completions client."""

    api_key: str
    base_url: str
    model: str
    temperature: float = 0.75
    max_tokens: int = 900
    provider: str = "xai"  # "xai" | "openai"


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 5050
    secret_key: str = "dev-only-change-me"
    password: str = ""


@dataclass
class SafetyConfig:
    require_human_approval: bool = True
    auto_post_enabled: bool = False
    export_on_approve: bool = True


@dataclass
class AppConfig:
    """Fully resolved application configuration."""

    brand: dict[str, Any] = field(default_factory=dict)
    industries: list[str] = field(default_factory=list)
    services: list[dict[str, str]] = field(default_factory=list)
    pillars: dict[str, Any] = field(default_factory=dict)
    platforms: dict[str, Any] = field(default_factory=dict)
    generation: dict[str, Any] = field(default_factory=dict)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    llm: LLMConfig | None = None
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    data_dir: Path = DEFAULT_DATA_DIR
    posts_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "posts")
    logs_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "logs")
    exports_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "exports")
    log_level: str = "INFO"
    log_file: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "logs" / "agent.log")
    log_max_bytes: int = 5_242_880
    log_backup_count: int = 5
    project_root: Path = PROJECT_ROOT

    def ensure_directories(self) -> None:
        """Create data directories if missing (safe to call repeatedly)."""
        for path in (self.data_dir, self.posts_dir, self.logs_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_yaml_config(path: Path | None = None) -> dict[str, Any]:
    """Load the YAML config file, returning an empty dict if missing."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {cfg_path}")
    return data


def load_config(
    config_path: Path | None = None,
    env_path: Path | None = None,
    *,
    require_api_key: bool = False,
) -> AppConfig:
    """
    Build AppConfig from YAML + environment.

    Parameters
    ----------
    require_api_key:
        If True, raise when no LLM API key is present (used by generate job).
        Dashboard and status commands can load without a key.
    """
    env_file = env_path or DEFAULT_ENV_PATH
    # load_dotenv does not override existing env vars
    load_dotenv(env_file)

    raw = load_yaml_config(config_path)

    data_dir = Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
    posts_dir = data_dir / "posts"
    logs_dir = data_dir / "logs"
    exports_dir = data_dir / "exports"

    logging_raw = raw.get("logging", {}) or {}
    log_file_rel = logging_raw.get("file", "logs/agent.log")
    log_file = data_dir / Path(log_file_rel).name if not Path(log_file_rel).is_absolute() else Path(log_file_rel)
    # Prefer data/logs/agent.log layout
    if not Path(log_file_rel).is_absolute():
        log_file = data_dir / log_file_rel

    safety_raw = raw.get("safety", {}) or {}
    auto_from_env = os.getenv("AUTO_POST_ENABLED")
    safety = SafetyConfig(
        require_human_approval=bool(safety_raw.get("require_human_approval", True)),
        auto_post_enabled=_truthy(
            auto_from_env,
            default=bool(safety_raw.get("auto_post_enabled", False)),
        ),
        export_on_approve=bool(safety_raw.get("export_on_approve", True)),
    )

    # Hard safety: never allow auto-post unless explicitly flipped AND YAML agrees
    if safety.auto_post_enabled and safety.require_human_approval:
        # Human approval still required in v1 — force auto_post off
        safety.auto_post_enabled = False

    use_openai = _truthy(os.getenv("USE_OPENAI"), default=False)
    if use_openai:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        provider = "openai"
    else:
        api_key = os.getenv("XAI_API_KEY", "").strip()
        base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip()
        model = os.getenv("XAI_MODEL", "grok-2-latest").strip()
        provider = "xai"

    generation = raw.get("generation", {}) or {}
    llm = LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=float(generation.get("temperature", 0.75)),
        max_tokens=int(generation.get("max_tokens", 900)),
        provider=provider,
    )

    if require_api_key and not llm.api_key:
        raise RuntimeError(
            "No LLM API key found. Set XAI_API_KEY (or OPENAI_API_KEY with USE_OPENAI=true) in .env"
        )

    dashboard = DashboardConfig(
        host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("DASHBOARD_PORT", "5050")),
        secret_key=os.getenv("FLASK_SECRET_KEY", "dev-only-change-me"),
        password=os.getenv("DASHBOARD_PASSWORD", ""),
    )

    cfg = AppConfig(
        brand=raw.get("brand", {}) or {},
        industries=list(raw.get("industries", []) or []),
        services=list(raw.get("services", []) or []),
        pillars=raw.get("pillars", {}) or {},
        platforms=raw.get("platforms", {}) or {},
        generation=generation,
        safety=safety,
        llm=llm,
        dashboard=dashboard,
        data_dir=data_dir,
        posts_dir=posts_dir,
        logs_dir=logs_dir,
        exports_dir=exports_dir,
        log_level=os.getenv("LOG_LEVEL", logging_raw.get("level", "INFO")),
        log_file=log_file,
        log_max_bytes=int(logging_raw.get("max_bytes", 5_242_880)),
        log_backup_count=int(logging_raw.get("backup_count", 5)),
        project_root=PROJECT_ROOT,
    )
    cfg.ensure_directories()
    return cfg
