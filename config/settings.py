"""配置管理模块：YAML 配置加载 + 环境变量覆盖"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".fagent"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "state.db"
DEFAULT_USER_PROFILE_PATH = DEFAULT_CONFIG_DIR / "USER.md"
DEFAULT_SKILLS_DIR = DEFAULT_CONFIG_DIR / "skills"
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"


@dataclass
class LLMConfig:
    """LLM 相关配置"""
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    api_key: str = ""
    context_window: int = 128000
    max_iterations: int = 50
    temperature: float = 0.7


@dataclass
class ToolConfig:
    """工具相关配置"""
    max_result_size: int = 50000


@dataclass
class MemoryConfig:
    """记忆相关配置"""
    prefetch_limit: int = 5


@dataclass
class AppConfig:
    """应用全局配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    db_path: str = str(DEFAULT_DB_PATH)
    user_profile_path: str = str(DEFAULT_USER_PROFILE_PATH)
    skills_dir: str = str(DEFAULT_SKILLS_DIR)
    log_dir: str = str(DEFAULT_LOG_DIR)


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 优先"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config_dict: dict) -> dict:
    """用环境变量覆盖配置项"""
    env_mapping = {
        "FAGENT_MODEL": ("llm", "model"),
        "FAGENT_BASE_URL": ("llm", "base_url"),
        "FAGENT_API_KEY": ("llm", "api_key"),
        "FAGENT_CONTEXT_WINDOW": ("llm", "context_window"),
        "FAGENT_MAX_ITERATIONS": ("llm", "max_iterations"),
        "FAGENT_DB_PATH": ("db_path",),
        "FAGENT_TEMPERATURE": ("llm", "temperature"),
    }

    for env_key, path in env_mapping.items():
        value = os.environ.get(env_key)
        if value is not None:
            current = config_dict
            for key in path[:-1]:
                current = current.setdefault(key, {})
            # 数值类型转换
            leaf_key = path[-1]
            if leaf_key in ("context_window", "max_iterations"):
                current[leaf_key] = int(value)
            elif leaf_key == "temperature":
                current[leaf_key] = float(value)
            else:
                current[leaf_key] = value

    return config_dict


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """加载配置：默认值 → YAML 文件 → 环境变量覆盖"""
    config_dict = {}

    # 从 YAML 文件加载
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        config_dict = _deep_merge(config_dict, yaml_config)

    # 环境变量覆盖
    config_dict = _apply_env_overrides(config_dict)

    # 构造 AppConfig
    llm_dict = config_dict.pop("llm", {})
    tools_dict = config_dict.pop("tools", {})
    memory_dict = config_dict.pop("memory", {})

    return AppConfig(
        llm=LLMConfig(**llm_dict),
        tools=ToolConfig(**tools_dict),
        memory=MemoryConfig(**memory_dict),
        **config_dict,
    )


def ensure_config_dir() -> Path:
    """确保配置目录存在，返回路径"""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR
