from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

_SCHEMA_VERSION = 1
_METRICS = ("installs_30d", "installs_90d", "installs_365d")


class SeedError(ValueError):
    """The bundled cache seed is absent or malformed."""


@dataclass(frozen=True)
class SeedMetadata:
    schema_version: int
    generated_at: int


def validate(data: dict[str, Any]) -> SeedMetadata:
    try:
        raw_metadata = data["_brewq_seed"]
        metadata = SeedMetadata(
            schema_version=int(raw_metadata["schema_version"]),
            generated_at=int(raw_metadata["generated_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SeedError(f"invalid seed metadata: {exc}") from exc
    if metadata.schema_version != _SCHEMA_VERSION:
        raise SeedError(f"unsupported seed schema: {metadata.schema_version}")
    if metadata.generated_at <= 0:
        raise SeedError("seed generation time must be positive")

    for group in ("formulae", "casks"):
        records = data.get(group)
        if not isinstance(records, list) or not records:
            raise SeedError(f"seed has no {group}")
        for record in records:
            if not isinstance(record, dict):
                raise SeedError(f"seed {group} contains a non-object record")
            for metric in _METRICS:
                if metric not in record:
                    raise SeedError(f"seed {group} record lacks {metric}")
    return metadata


def encode(data: dict[str, Any], generated_at: int) -> bytes:
    normalized = json.loads(json.dumps(data))
    normalized["_brewq_seed"] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": generated_at,
    }
    validate(normalized)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as archive:
        archive.write(payload)
    return output.getvalue()


def decode(payload: bytes) -> tuple[dict[str, Any], SeedMetadata]:
    try:
        data = json.loads(gzip.decompress(payload))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedError(f"invalid compressed seed: {exc}") from exc
    if not isinstance(data, dict):
        raise SeedError("seed root is not an object")
    return data, validate(data)


def load_resource() -> tuple[dict[str, Any], SeedMetadata]:
    resource = resources.files("brewq").joinpath("data/brew-all.json.gz")
    try:
        return decode(resource.read_bytes())
    except (FileNotFoundError, OSError) as exc:
        raise SeedError(f"bundled seed unavailable: {exc}") from exc
