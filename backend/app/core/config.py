"""Environment configuration; optional integrations are disabled by default."""

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.schemas.common import ReasonCode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    database_url: str = "postgresql+psycopg://transformer:transformer@localhost:5432/transformer"
    env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    schema_version: str = "1.0.0"
    default_transformer_id: str = "TX-001"
    ml_backend: Literal["stub", "python", "http"] = "stub"
    ml_http_url: str | None = None
    ml_python_entrypoint: str | None = None
    ml_history_window: int = Field(default=4096, ge=1, le=4096)
    physics_enabled: bool = False
    physics_demo_input_mode: Literal["standalone", "accepted-telemetry"] = "standalone"
    live_physics_demo_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_PHYSICS_DEMO", "LIVE_PHYSICS_DEMO_ENABLED"),
    )

    @field_validator("live_physics_demo_enabled", mode="before")
    @classmethod
    def parse_physics_demo_flag(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            value = value.strip().lower()
            if value in {"true", "1", "yes", "on"}:
                return True
            if value in {"false", "0", "no", "off"}:
                return False
        if type(value) is int and value in (0, 1):
            return bool(value)
        raise ValueError("ENABLE_PHYSICS_DEMO must be a boolean: true/false, 1/0, yes/no or on/off")

    @model_validator(mode="after")
    def physics_demo_configuration(self):
        if self.live_physics_demo_enabled and self.physics_demo_input_mode == "accepted-telemetry":
            if not self.operational_fleet_file:
                raise ValueError(
                    "PHYSICS_DEMO_INPUT_MODE=accepted-telemetry requires OPERATIONAL_FLEET_FILE"
                )
            from ml.demo_physics.fleet import load_fleet

            try:
                load_fleet(self.operational_fleet_file)
            except (OSError, KeyError, TypeError) as exc:
                raise ValueError("OPERATIONAL_FLEET_FILE is unreadable or invalid") from exc
        return self

    analytics_policy_file: str | None = None
    operational_fleet_file: str | None = None
    ml_runtime_workers: Literal[1] = 1
    ml_timeout_seconds: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    ml_max_retries: int = Field(default=2, ge=0)
    max_batch_size: int = Field(default=5000, ge=1)
    alert_health_warn: float = Field(default=60, ge=0, le=100, allow_inf_nan=False)
    alert_health_crit: float = Field(default=40, ge=0, le=100, allow_inf_nan=False)
    alert_anomaly_critical: float = Field(default=0.9, ge=0, le=1, allow_inf_nan=False)
    alert_fault_risk_warn: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    alert_fault_risk_crit: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    alert_auto_resolve_after: int = Field(default=5, ge=1)
    alert_reason_severity: dict[ReasonCode, Literal["INFO", "WARNING", "CRITICAL"]] = Field(
        default_factory=lambda: dict.fromkeys(
            [
                "HIGH_OIL_TEMP",
                "RAPID_TEMP_RISE",
                "OVERLOAD",
                "CURRENT_IMBALANCE",
                "VOLTAGE_IMBALANCE",
                "LOW_OIL_LEVEL",
                "ANOMALOUS_PATTERN",
            ],
            "WARNING",
        )
    )
    default_window_hours: int = Field(default=24, ge=1)
    max_window_days: int = Field(default=31, ge=1)
    max_page_limit: int = Field(default=5000, ge=1)
    demo_reset_enabled: bool = False
    demo_admin_token: SecretStr | None = None
    demo_source_names: str = "simulator,replay,demo,seed,mqtt,mqtt-simulator,analytics-backfill"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id: str = Field(default="transformer-backend", min_length=1)
    mqtt_topic: str = Field(default="transformer/+/telemetry", min_length=1)
    mqtt_qos: int = Field(default=1, ge=0, le=2)
    mqtt_queue_max: int = Field(default=10000, ge=1)
    mqtt_source_name: str = Field(default="mqtt", min_length=1, max_length=255)
    mqtt_reconnect_min_s: int = Field(default=1, ge=1)
    mqtt_reconnect_max_s: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def mqtt_configuration(self) -> "Settings":
        import os

        if self.ml_backend == "python" and int(os.environ.get("WEB_CONCURRENCY", "1")) != 1:
            raise ValueError("H01 runtime supports exactly one backend process/worker")
        if self.alert_health_crit > self.alert_health_warn:
            raise ValueError("ALERT_HEALTH_CRIT must be <= ALERT_HEALTH_WARN")
        if self.alert_fault_risk_crit < self.alert_fault_risk_warn:
            raise ValueError("ALERT_FAULT_RISK_CRIT must be >= ALERT_FAULT_RISK_WARN")
        if self.default_window_hours > self.max_window_days * 24:
            raise ValueError("DEFAULT_WINDOW_HOURS exceeds MAX_WINDOW_DAYS")
        if self.mqtt_reconnect_max_s < self.mqtt_reconnect_min_s:
            raise ValueError("MQTT_RECONNECT_MAX_S must be >= MQTT_RECONNECT_MIN_S")
        segments = self.mqtt_topic.split("/")
        if segments.count("+") > 1:
            raise ValueError("MQTT_TOPIC permits at most one identity wildcard")
        for index, segment in enumerate(segments):
            if ("+" in segment and segment != "+") or (
                "#" in segment and (segment != "#" or index != len(segments) - 1)
            ):
                raise ValueError("MQTT_TOPIC contains an invalid wildcard")
        return self

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @field_validator(
        "ml_http_url", "ml_python_entrypoint", "mqtt_username", "mqtt_password", mode="before"
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
