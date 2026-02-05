from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@dataclass
class SchemaValidationError(Exception):
    schema_path: str
    message: str
    errors: list[str]

    def __str__(self) -> str:
        details = "\n".join(f"- {e}" for e in self.errors)
        return f"{self.message}\nSchema: {self.schema_path}\n{details}"


def _strict_citations_enabled() -> bool:
    return os.getenv("HRH_STRICT_CITATIONS", "").strip().lower() in ("1", "true", "yes", "on")


def _is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read JSON at {path}: {e}") from e


def _build_registry_for_dir(schema_dir: Path) -> Registry:
    """
    Build a registry of all *.json schemas in schema_dir so relative $ref like
    'common.json#/$defs/...' resolves reliably without deprecated RefResolver.
    """
    reg: Registry = Registry()
    for p in schema_dir.glob("*.json"):
        try:
            contents = _load_json(p)
            # Use a file URI so Draft202012Validator can resolve references
            uri = p.resolve().as_uri()
            reg = reg.with_resource(uri, Resource.from_contents(contents))
            # Also register the bare filename URI for convenience
            reg = reg.with_resource(p.name, Resource.from_contents(contents))
        except (ValueError, json.JSONDecodeError):
            # Skip empty or invalid schema files (placeholders)
            continue
    return reg


def validate_output(payload: Dict[str, Any], schema_path: str, base_dir: Optional[str] = None) -> None:
    """
    Validate an output payload against a JSON Schema (Draft 2020-12).

    - schema_path: path like 'schemas/phase1_discovery_qa.schema.json'
    - base_dir: optional base directory; defaults to current working directory
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    schema_file = (base / schema_path).resolve()

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema not found: {schema_file}")

    schema_dir = schema_file.parent
    registry = _build_registry_for_dir(schema_dir)

    schema = _load_json(schema_file)
    validator = Draft202012Validator(schema, registry=registry)

    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        formatted = []
        for e in errors:
            loc = "$"
            for part in e.path:
                if isinstance(part, int):
                    loc += f"[{part}]"
                else:
                    loc += f".{part}"
            formatted.append(f"{loc}: {e.message}")
        raise SchemaValidationError(
            schema_path=str(schema_file),
            message="Output failed schema validation",
            errors=formatted,
        )

    # Optional strict gate: citations must have real identifiers
    if _strict_citations_enabled():
        def walk(obj, path="$"):
            if isinstance(obj, dict):
                # If this dict looks like a citation, enforce identifier
                if "source_title" in obj and "locator" in obj:
                    su = obj.get("source_url")
                    ref = obj.get("reference")
                    doi = obj.get("doi")
                    isbn = obj.get("isbn")

                    has_http_url = isinstance(su, str) and _is_http_url(su)
                    has_ref = isinstance(ref, str) and ref.strip() != ""
                    has_doi = isinstance(doi, str) and doi.strip() != ""
                    has_isbn = isinstance(isbn, str) and isbn.strip() != ""

                    if not (has_http_url or has_ref or has_doi or has_isbn):
                        raise SchemaValidationError(
                            schema_path=str(schema_file),
                            message="Strict citation validation failed (HRH_STRICT_CITATIONS=1)",
                            errors=[f"{path} must include either a valid http(s) source_url OR a non-empty reference/doi/isbn."],
                        )
                for k, v in obj.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")

        walk(payload)
