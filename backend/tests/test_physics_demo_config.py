"""One typed flag, safe defaults, aliases and real settings-source precedence."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_demo_settings(monkeypatch):
    for name in ("ENABLE_PHYSICS_DEMO", "LIVE_PHYSICS_DEMO_ENABLED", "ENV", "PHYSICS_ENABLED"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("profile", ["production", "development", "local-demo", "", None])
def test_default_disabled_even_without_or_with_explicit_profile(monkeypatch, profile):
    if profile is not None:
        monkeypatch.setenv("ENV", profile)
    assert Settings(_env_file=None).live_physics_demo_enabled is False


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("FALSE", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        (" on ", True),
        ("off", False),
    ],
)
def test_preferred_boolean_environment(monkeypatch, value, expected):
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", value)
    assert Settings(_env_file=None).live_physics_demo_enabled is expected


@pytest.mark.parametrize("value", ["", "maybe", "2", "NaN", "[]"])
def test_invalid_environment_fails_configuration(monkeypatch, value):
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", value)
    with pytest.raises(ValidationError, match="ENABLE_PHYSICS_DEMO must be a boolean"):
        Settings(_env_file=None)


def test_legacy_alias_and_preferred_alias_precedence(monkeypatch):
    monkeypatch.setenv("LIVE_PHYSICS_DEMO_ENABLED", "true")
    assert Settings(_env_file=None).live_physics_demo_enabled is True
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", "false")
    assert Settings(_env_file=None).live_physics_demo_enabled is False


def test_dotenv_environment_and_constructor_precedence(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("ENABLE_PHYSICS_DEMO=true\nENV=local-demo\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).live_physics_demo_enabled is True
    monkeypatch.setenv("LIVE_PHYSICS_DEMO_ENABLED", "false")
    assert Settings(_env_file=dotenv).live_physics_demo_enabled is False
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", "true")
    assert Settings(_env_file=dotenv).live_physics_demo_enabled is True
    assert Settings(_env_file=dotenv, ENABLE_PHYSICS_DEMO=False).live_physics_demo_enabled is False
    assert (
        Settings(_env_file=dotenv, live_physics_demo_enabled=False).live_physics_demo_enabled
        is False
    )


def test_cached_effective_instance_is_shared_and_not_changed_by_late_environment(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", "true")
    first = get_settings()
    assert first is get_settings()
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", "false")
    assert get_settings() is first and first.live_physics_demo_enabled is True
    get_settings.cache_clear()
    assert get_settings().live_physics_demo_enabled is False
