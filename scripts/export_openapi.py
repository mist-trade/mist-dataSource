"""Export mode-specific TDX/QMT OpenAPI contracts and route summaries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_PATH = ROOT / "docs" / "references" / "tdx-openapi.json"
DEFAULT_SUMMARY_PATH = ROOT / "docs" / "references" / "tdx-openapi-summary.md"
ARTIFACTS = {
    ("tdx", "builtin"): (
        "tdx-openapi-builtin.json",
        "tdx-openapi-builtin-summary.md",
    ),
    ("qmt", "off"): ("qmt-openapi-off.json", "qmt-openapi-off-summary.md"),
    ("qmt", "builtin"): (
        "qmt-openapi-builtin.json",
        "qmt-openapi-builtin-summary.md",
    ),
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(cast(list[Any] | tuple[Any, ...], value))
    return []


def _schema_name(schema: Any) -> str:
    schema_mapping = _mapping(schema)
    if not schema_mapping:
        return ""
    ref = schema_mapping.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    if "items" in schema_mapping:
        item_name = _schema_name(schema_mapping["items"])
        return f"array[{item_name}]" if item_name else "array"
    if "anyOf" in schema_mapping:
        names = [_schema_name(item) for item in _sequence(schema_mapping["anyOf"])]
        return " | ".join(name for name in names if name)
    schema_type = schema_mapping.get("type")
    return str(schema_type) if schema_type else json.dumps(schema_mapping, ensure_ascii=False, sort_keys=True)


def _request_body_schema(operation: Mapping[str, Any]) -> str:
    request_body = _mapping(operation.get("requestBody"))
    content = _mapping(request_body.get("content"))
    json_content = _mapping(content.get("application/json"))
    return _schema_name(json_content.get("schema")) or "-"


def _response_schemas(operation: Mapping[str, Any]) -> list[str]:
    responses: list[str] = []
    for status_code, response in _mapping(operation.get("responses")).items():
        response_mapping = _mapping(response)
        content = _mapping(response_mapping.get("content"))
        json_content = _mapping(content.get("application/json"))
        schema_name = _schema_name(json_content.get("schema")) or "-"
        responses.append(f"{status_code}: {schema_name}")
    return responses or ["-"]


def _parameters(operation: Mapping[str, Any]) -> list[str]:
    rows: list[str] = []
    for parameter in _sequence(operation.get("parameters")):
        parameter_mapping = _mapping(parameter)
        if not parameter_mapping:
            continue
        name = parameter_mapping.get("name", "-")
        location = parameter_mapping.get("in", "-")
        required = parameter_mapping.get("required", False)
        schema_name = _schema_name(parameter_mapping.get("schema", {})) or "-"
        rows.append(f"{name} ({location}, {schema_name}, required={str(required).lower()})")
    return rows or ["-"]


def build_summary(
    openapi: dict[str, Any], *, source: str = "tdx", mode: str = "builtin"
) -> str:
    info = _mapping(openapi.get("info"))
    paths = _mapping(openapi.get("paths"))
    lines = [
        f"# {source.upper()} OpenAPI Summary ({mode})",
        "",
        f"Title: {info.get('title', '-')}",
        f"Version: {info.get('version', '-')}",
        "",
        f"Generated from the `{source}` FastAPI app in `{mode}` mode.",
        "",
    ]

    for path in sorted(str(path) for path in paths):
        path_item = _mapping(paths[path])
        for method in sorted(path_item):
            operation = _mapping(path_item[method])
            if not operation:
                continue
            method_upper = method.upper()
            tags = [str(tag) for tag in _sequence(operation.get("tags"))]
            lines.extend(
                [
                    f"## {method_upper} {path}",
                    "",
                    f"- Operation ID: `{operation.get('operationId', '-')}`",
                    f"- Tags: {', '.join(tags) or '-'}",
                    f"- Summary: {operation.get('summary', '-')}",
                    f"- Request Body: `{_request_body_schema(operation)}`",
                    f"- Parameters: {'; '.join(_parameters(operation))}",
                    f"- Responses: {'; '.join(_response_schemas(operation))}",
                    "",
                ]
            )

    components = _mapping(openapi.get("components"))
    schemas = sorted(str(schema) for schema in _mapping(components.get("schemas")))
    lines.extend(
        [
            "## Schemas",
            "",
            *[f"- `{schema}`" for schema in schemas],
            "",
        ]
    )
    return "\n".join(lines)


def _load_app(source: str, mode: str):
    if source == "tdx":
        from tdx.main import app

        return app
    os.environ["QMT_REALTIME_MODE"] = mode
    from qmt.main import create_qmt_app

    return create_qmt_app(realtime_mode=mode)


def export_openapi(
    json_path: Path,
    summary_path: Path,
    *,
    source: str = "tdx",
    mode: str = "builtin",
) -> None:
    app = _load_app(source, mode)
    openapi = app.openapi()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(openapi, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(build_summary(openapi, source=source, mode=mode), encoding="utf-8")


def export_all() -> None:
    for (source, mode), (json_name, summary_name) in ARTIFACTS.items():
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--source",
                source,
                "--mode",
                mode,
                "--json",
                str(ROOT / "docs" / "references" / json_name),
                "--summary",
                str(ROOT / "docs" / "references" / summary_name),
            ],
            check=True,
        )
    tdx_json, tdx_summary = ARTIFACTS[("tdx", "builtin")]
    DEFAULT_JSON_PATH.write_text(
        (ROOT / "docs" / "references" / tdx_json).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    DEFAULT_SUMMARY_PATH.write_text(
        (ROOT / "docs" / "references" / tdx_summary).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="export every supported mode")
    parser.add_argument("--source", choices=("tdx", "qmt"), default="tdx")
    parser.add_argument("--mode", default="builtin")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    if args.all:
        export_all()
        return
    allowed_modes = {
        "tdx": {"builtin"},
        "qmt": {"off", "builtin"},
    }
    if args.mode not in allowed_modes[args.source]:
        parser.error(f"unsupported mode {args.mode!r} for {args.source}")
    export_openapi(args.json, args.summary, source=args.source, mode=args.mode)
    print(f"Wrote {args.json}")
    print(f"Wrote {args.summary}")


if __name__ == "__main__":
    main()
