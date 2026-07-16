"""
config_loader.py
================
A tiny helper that loads `config.yaml` (the single control panel) and makes it
available to every other module. Both the ML scripts and the backend import
this so there is exactly ONE place that knows how to read the config.

Why a helper instead of `yaml.safe_load(open("config.yaml"))` everywhere?
  * It finds config.yaml no matter which folder you run from (it walks UP the
    directory tree until it finds the file). Beginners often run scripts from
    different folders; this makes that "just work".
  * It caches the result so we don't re-read the file constantly.
  * It fails with a clear, friendly message if the file is missing.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml


def _find_repo_root(start: str) -> str:
    """
    Walk upward from `start` until we find a folder containing config.yaml.

    Returns the folder path. Raises a clear error if we never find it.
    """
    current = os.path.abspath(start)
    # Keep going up until the filesystem root.
    while True:
        candidate = os.path.join(current, "config.yaml")
        if os.path.isfile(candidate):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            # We've reached the top of the filesystem without finding it.
            raise FileNotFoundError(
                "Could not find config.yaml. Make sure you run commands from "
                "inside the 'battery-health-system' project folder."
            )
        current = parent


# The project root is the folder that contains config.yaml.
REPO_ROOT: str = _find_repo_root(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH: str = os.path.join(REPO_ROOT, "config.yaml")


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """
    Read config.yaml and return it as a plain Python dictionary.

    The @lru_cache decorator means the file is read from disk only once; every
    later call returns the same cached dictionary (fast and consistent).
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if config is None:
        # An empty file would load as None; guard against that.
        raise ValueError(f"{CONFIG_PATH} is empty or invalid YAML.")
    return config


def artifact_path(filename_key: str) -> str:
    """
    Build an absolute path to a saved model artifact (e.g. model.joblib).

    `filename_key` is a key under config['paths'], for example "model_file".
    """
    config = load_config()
    artifacts_dir = os.path.join(REPO_ROOT, config["paths"]["artifacts_dir"])
    filename = config["paths"][filename_key]
    return os.path.join(artifacts_dir, filename)


if __name__ == "__main__":
    # Running this file directly prints the loaded config -- handy for checking
    # that your YAML is valid.
    import json

    print(f"Project root: {REPO_ROOT}")
    print(json.dumps(load_config(), indent=2))
