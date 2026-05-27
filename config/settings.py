"""配置管理模块：YAML 配置加载"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "workspace"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "state.db"
DEFAULT_USER_PROFILE_PATH = DEFAULT_CONFIG_DIR / "USER.md"
DEFAULT_SOUL_PATH = DEFAULT_CONFIG_DIR / "SOUL.md"
DEFAULT_AGENT_PATH = DEFAULT_CONFIG_DIR / "AGENT.md"
DEFAULT_SKILLS_DIR = DEFAULT_CONFIG_DIR / "skills"
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"


@dataclass
class LLMConfig:
    """LLM 相关配置"""
    model: str = "deepseek-v4-pro"
    base_url: str | None = "https://api.deepseek.com"
    api_key: str = ""
    context_window: int = 128000
    max_iterations: int = 50
    temperature: float = 0.7
    request_timeout: float = 120.0


@dataclass
class ToolConfig:
    """工具相关配置"""
    max_result_size: int = 50000


@dataclass
class MemoryConfig:
    """记忆相关配置"""
    prefetch_limit: int = 5


@dataclass
class MySQLConfig:
    """MySQL 连接配置（只读查询）"""
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    database: str = ""
    password_env: str = "MYSQL_PASSWORD"


@dataclass
class CompressorConfig:
    """上下文压缩配置"""
    threshold: float = 0.5
    min_saving: float = 0.1
    protected_head: int = 3
    protected_tail_tokens: int = 20000


@dataclass
class ApprovalConfig:
    """命令审批配置"""
    mode: str = "manual"   # "manual" | "off"


@dataclass
class SkillsHubConfig:
    """Skills Hub 配置"""
    github_token: str = ""


@dataclass
class AppConfig:
    """应用全局配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    compressor: CompressorConfig = field(default_factory=CompressorConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    skills_hub: SkillsHubConfig = field(default_factory=SkillsHubConfig)
    mysql: MySQLConfig | None = None
    db_path: str = str(DEFAULT_DB_PATH)
    user_profile_path: str = str(DEFAULT_USER_PROFILE_PATH)
    soul_path: str = str(DEFAULT_SOUL_PATH)
    agent_guidance_path: str = str(DEFAULT_AGENT_PATH)
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


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """加载配置：默认值 → YAML 文件"""
    config_dict = {}

    # 从 YAML 文件加载
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        config_dict = _deep_merge(config_dict, yaml_config)

    # 构造 AppConfig
    llm_dict = config_dict.pop("llm", {})
    tools_dict = config_dict.pop("tools", {})
    memory_dict = config_dict.pop("memory", {})
    compressor_dict = config_dict.pop("compressor", {})
    approval_dict = config_dict.pop("approval", {})
    skills_hub_dict = config_dict.pop("skills_hub", {})
    mysql_dict = config_dict.pop("mysql", None)

    return AppConfig(
        llm=LLMConfig(**llm_dict),
        tools=ToolConfig(**tools_dict),
        memory=MemoryConfig(**memory_dict),
        compressor=CompressorConfig(**compressor_dict),
        mysql=MySQLConfig(**mysql_dict) if mysql_dict else None,
        approval=ApprovalConfig(**approval_dict) if approval_dict else ApprovalConfig(),
        skills_hub=SkillsHubConfig(**skills_hub_dict) if skills_hub_dict else SkillsHubConfig(),
        **config_dict,
    )


def ensure_config_dir() -> Path:
    """确保配置目录存在，返回路径"""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR
