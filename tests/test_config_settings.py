from config.settings import load_config


def test_default_cron_config():
    from config.settings import AppConfig

    config = AppConfig()

    assert config.cron.enabled is True
    assert config.cron.tick_interval_seconds == 60
    assert config.cron.grace_seconds == 120


def test_load_cron_config_from_yaml(tmp_path):
    from config.settings import load_config

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "cron:\n"
        "  enabled: false\n"
        "  tick_interval_seconds: 5\n"
        "  grace_seconds: 30\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.cron.enabled is False
    assert config.cron.tick_interval_seconds == 5
    assert config.cron.grace_seconds == 30


def test_load_config_reads_baidu_ai_search_tool_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
tools:
  max_result_size: 12345
  baidu_ai_search_api_key: sk-baidu-test
  baidu_ai_search_timeout: 12.5
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.tools.max_result_size == 12345
    assert config.tools.baidu_ai_search_api_key == "sk-baidu-test"
    assert config.tools.baidu_ai_search_timeout == 12.5
