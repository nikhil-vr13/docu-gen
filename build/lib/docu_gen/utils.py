from __future__ import annotations
from pathlib import Path
from typing import Optional

import yaml


def find_repo_root(path: Optional[str] = None) -> Optional[Path]:
    start = Path(path or Path.cwd()).resolve()
    for p in [start] + list(start.parents):
        if (p / ".git").is_dir():
            return p
    return None


def save_config_template(path: str):
    from .config import write_example_config
    write_example_config(Path(path))
