from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml

CONFIG_FILE_NAME = "docu-gen.yaml"


@dataclass
class ConfluenceConfig:
    url: str = ""
    username: str = ""
    api_token: str = ""
    space_key: str = ""
    parent_page_id: Optional[str] = None


@dataclass
class LLMConfig:
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.3


@dataclass
class Config:
    confluence: ConfluenceConfig = field(default_factory=ConfluenceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    default_output: str = "markdown"

    @classmethod
    def load(cls, path: Optional[str] = None) -> Config:
        search_paths = []
        if path:
            search_paths.append(Path(path))
        search_paths.extend([
            Path.cwd() / CONFIG_FILE_NAME,
            Path.home() / ".config" / "docu-gen" / CONFIG_FILE_NAME,
            Path.home() / CONFIG_FILE_NAME,
        ])

        cfg = cls()

        for sp in search_paths:
            if sp.exists():
                raw = yaml.safe_load(sp.read_text())
                if raw:
                    cfg._merge(raw)
                break

        cfg._apply_env_overrides()
        return cfg

    def _merge(self, raw: dict):
        if "confluence" in raw:
            c = raw["confluence"]
            if "url" in c:
                self.confluence.url = c["url"]
            if "username" in c:
                self.confluence.username = c["username"]
            if "api_token" in c:
                self.confluence.api_token = c["api_token"]
            if "space_key" in c:
                self.confluence.space_key = c["space_key"]
            if "parent_page_id" in c:
                self.confluence.parent_page_id = str(c["parent_page_id"])
        if "llm" in raw:
            l = raw["llm"]
            if "provider" in l:
                self.llm.provider = l["provider"]
            if "api_key" in l:
                self.llm.api_key = l["api_key"]
            if "model" in l:
                self.llm.model = l["model"]
            if "temperature" in l:
                self.llm.temperature = float(l["temperature"])
        if "default_output" in raw:
            self.default_output = raw["default_output"]

    def _apply_env_overrides(self):
        env_map = {
            "DOCU_GEN_CONFLUENCE_URL": ("confluence", "url"),
            "DOCU_GEN_CONFLUENCE_USERNAME": ("confluence", "username"),
            "DOCU_GEN_CONFLUENCE_API_TOKEN": ("confluence", "api_token"),
            "DOCU_GEN_CONFLUENCE_SPACE_KEY": ("confluence", "space_key"),
            "DOCU_GEN_CONFLUENCE_PARENT_PAGE_ID": ("confluence", "parent_page_id"),
            "DOCU_GEN_LLM_API_KEY": ("llm", "api_key"),
            "DOCU_GEN_LLM_MODEL": ("llm", "model"),
            "DOCU_GEN_LLM_PROVIDER": ("llm", "provider"),
            "OPENAI_API_KEY": ("llm", "api_key"),  # fallback
            "ANTHROPIC_API_KEY": ("llm", "api_key"),  # fallback
        }
        for env_var, (section, field) in env_map.items():
            val = os.environ.get(env_var)
            if val:
                setattr(getattr(self, section), field, val)


def write_example_config(path: Path):
    example = {
        "confluence": {
            "url": "https://your-domain.atlassian.net/wiki",
            "username": "your-email@example.com",
            "api_token": "your-api-token",
            "space_key": "PROJ",
            "parent_page_id": "123456",
        },
        "llm": {
            "provider": "openai",
            "api_key": "sk-...",
            "model": "gpt-4o",
            "temperature": 0.3,
        },
        "default_output": "confluence",
    }
    path.write_text(yaml.safe_dump(example, default_flow_style=False))
