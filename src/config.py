import os
from typing import Any
import yaml

__all__ = ["init", "get"]

def init():
    dn = os.path.dirname(__file__)
    with open(os.path.join(dn, "defaultsettings.yml"), "rt") as f:
        defaultsettings = yaml.safe_load(f)

def get(key: str, default: Any = None) -> Any:
    pass
