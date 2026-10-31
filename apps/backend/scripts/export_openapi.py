"""Export backend OpenAPI schema to a JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi

from src.backend.main import app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export backend OpenAPI schema")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write openapi.json (absolute or relative to repo root)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = get_openapi(
        title=app.title or "Pulse Backend",
        version="1.0.0",
        routes=app.routes,
        description=app.description,
    )
    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {output_path}")


if __name__ == "__main__":
    main()
