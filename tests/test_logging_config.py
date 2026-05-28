import logging
from unittest.mock import MagicMock, patch

from config.settings import AppConfig, LLMConfig
from main import configure_logging, main


FIRST_PARTY_LOGGER_NAMES = (
    "main",
    "agent",
    "cli",
    "config",
    "context",
    "db",
    "llm",
    "memory",
    "tools",
)


def _reset_logging_state():
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.WARNING)

    for logger_name in FIRST_PARTY_LOGGER_NAMES + (
        "openai",
        "openai._base_client",
        "httpcore",
        "markdown_it",
    ):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def _flush_root_handlers():
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_configure_logging_does_not_write_openai_debug_request_body(tmp_path):
    _reset_logging_state()
    try:
        log_dir = tmp_path / "logs"

        configure_logging(log_dir)

        logging.getLogger("openai._base_client").debug(
            "Request options: system prompt SECRET_SYSTEM_PROMPT "
            "user SECRET_USER_MESSAGE tools SECRET_TOOL_SCHEMA"
        )
        _flush_root_handlers()

        log_file = log_dir / "agent.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "SECRET_SYSTEM_PROMPT" not in content
        assert "SECRET_USER_MESSAGE" not in content
        assert "SECRET_TOOL_SCHEMA" not in content
    finally:
        _reset_logging_state()


def test_configure_logging_writes_first_party_debug_logs(tmp_path):
    _reset_logging_state()
    try:
        log_dir = tmp_path / "logs"

        configure_logging(log_dir)

        logging.getLogger("llm.client").debug("FAGENT_FIRST_PARTY_DEBUG_MARKER")
        _flush_root_handlers()

        content = (log_dir / "agent.log").read_text(encoding="utf-8")
        assert "llm.client" in content
        assert "DEBUG" in content
        assert "FAGENT_FIRST_PARTY_DEBUG_MARKER" in content
    finally:
        _reset_logging_state()


def test_main_delegates_logging_setup_to_configure_logging(tmp_path):
    config = AppConfig(
        llm=LLMConfig(api_key="sk-test"),
        log_dir=str(tmp_path / "logs"),
    )

    with (
        patch("main.get_config", return_value=config),
        patch("main.ensure_config_dir"),
        patch("main.configure_logging") as configure_logging_mock,
        patch("main.CLIInterface") as cli_interface,
    ):
        cli_instance = MagicMock()
        cli_interface.return_value = cli_instance

        main()

    configure_logging_mock.assert_called_once_with(str(tmp_path / "logs"))
    cli_interface.assert_called_once_with()
    cli_instance.run.assert_called_once_with()
