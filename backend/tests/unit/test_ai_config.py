from pathlib import Path

import pytest

from aiskra.ai.config import AIConfig, is_internal_url, load_ai_config, parse_duration
from aiskra.shared.errors import ConfigError


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "ai.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_gives_safe_offline_default() -> None:
    cfg = load_ai_config("/nonexistent/ai.yaml")
    assert cfg.default_provider == "fake" and not cfg.allow_external


def test_env_interpolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_URL", "http://llm:8080/v1")
    cfg = load_ai_config(
        write(
            tmp_path,
            """
ai:
  default_provider: local
  providers:
    local: {kind: openai_compatible, base_url: "${LLM_URL}", model: "${LLM_MODEL:-qwen}"}
  tasks:
    judge: {provider: local, temperature: 0, cache_ttl: 7d}
""",
        )
    )
    assert cfg.providers["local"].base_url == "http://llm:8080/v1"
    assert cfg.providers["local"].model == "qwen"
    assert cfg.tasks["judge"].cache_ttl == 7 * 86400


def test_external_url_rejected_in_isolated_mode(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="запрещён"):
        load_ai_config(
            write(
                tmp_path,
                """
ai:
  default_provider: demo
  providers:
    demo: {kind: openai_compatible, base_url: "https://api.example.com/v1", model: m}
""",
            )
        )


def test_external_url_allowed_explicitly() -> None:
    cfg = AIConfig.model_validate(
        {
            "allow_external": True,
            "default_provider": "demo",
            "providers": {"demo": {"kind": "openai_compatible", "base_url": "https://api.example.com/v1"}},
        }
    )
    assert cfg.allow_external


def test_unknown_provider_in_task(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="неизвестный провайдер"):
        load_ai_config(write(tmp_path, "ai:\n  tasks:\n    judge: {provider: nope}\n"))


@pytest.mark.parametrize(
    ("url", "internal"),
    [
        ("http://localhost:11434/v1", True),
        ("http://ollama:11434/v1", True),
        ("http://10.0.0.5:8080/v1", True),
        ("http://gpu-box.internal/v1", True),
        ("https://api.openai.com/v1", False),
        ("http://8.8.8.8/v1", False),
    ],
)
def test_is_internal_url(url: str, internal: bool) -> None:
    assert is_internal_url(url) is internal


def test_parse_duration() -> None:
    assert parse_duration("30s") == 30 and parse_duration("15m") == 900 and parse_duration(5) == 5
    with pytest.raises(ValueError):
        parse_duration("7 weeks")


def test_yaml_off_is_not_boolean(tmp_path: Path) -> None:
    text = "ai:\n  cache: {backend: off}\n  tasks:\n    gen: {provider: fake, cache: off}\n"
    cfg = load_ai_config(write(tmp_path, text))
    assert cfg.tasks["gen"].cache == "off" and cfg.cache.backend == "off"


def test_repo_configs_are_valid() -> None:
    root = Path(__file__).resolve().parents[3] / "config"
    for name in ("ai.yaml", "ai.example.yaml"):
        cfg = load_ai_config(root / name)
        assert cfg.tasks, name


def test_unused_external_provider_is_tolerated() -> None:
    cfg = AIConfig.model_validate(
        {
            "default_provider": "fake",
            "providers": {
                "fake": {"kind": "fake"},
                "demo": {"kind": "openai_compatible", "base_url": "https://api.example.com/v1"},
            },
        }
    )
    assert "demo" in cfg.providers
