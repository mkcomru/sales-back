from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, ValidationError


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    suffix = path.suffix.lower()
    with path.open("r", encoding="utf-8") as f:
        if suffix in (".yml", ".yaml"):
            return yaml.safe_load(f) or {}
        if suffix == ".json":
            return json.load(f) or {}

        # default to YAML
        return yaml.safe_load(f) or {}


def load_typed_config[T: BaseModel](
    config_dir: str,
    name: str,
    model: type[T],
) -> T:
    """Load a typed config from `config_dir/{name}.yml|yaml|json`.

    Order: yml -> yaml -> json. Missing or invalid -> return model() defaults.
    """
    log = structlog.get_logger()
    base = Path(config_dir) / name

    candidates = [
        base.with_suffix(".yml"),
        base.with_suffix(".yaml"),
        base.with_suffix(".json"),
    ]

    data: dict[str, Any] = {}
    for p in candidates:
        if p.exists():
            try:
                data = _read_config_file(p)
                break
            except Exception as e:
                log.warning("config.read_error", path=str(p), err=str(e))
                data = {}
                break

    try:
        return model.model_validate(data)
    except ValidationError as e:
        log.warning("config.validation_error", name=name, err=str(e))
        return model()
    except Exception as e:
        log.warning("config.unknown_error", name=name, err=str(e))
        return model()
