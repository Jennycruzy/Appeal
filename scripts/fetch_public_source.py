#!/usr/bin/env python3
"""Fetch an allow-listed public source with an ETag-backed local cache.

The command is intentionally fail-closed. It never accepts a URL from the
command line, never writes a payload without an ETag, and never substitutes a
cached payload after an unsuccessful revalidation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, cast


JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
FetchStatus = Literal["fetched", "not_modified", "blocked", "invalid"]

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONFIG_PATH: Final[Path] = ROOT / "config" / "real_corpus_sources.json"
DEFAULT_CACHE_DIR: Final[Path] = ROOT / ".cache" / "public-sources"
USER_AGENT: Final[str] = "appeal-public-source-fetch/0.1"


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    headers: dict[str, str]
    body: bytes
    error: str | None


@dataclass(frozen=True)
class CachePaths:
    directory: Path
    payload: Path
    metadata: Path
    attempt: Path


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_object(path: Path) -> JsonObject:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return cast(JsonObject, raw)


def list_value(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def object_value(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def string_value(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""


def safe_component(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    if not safe:
        raise ValueError("an empty cache path component is not allowed")
    return safe


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not context.get_ca_certs():
        for ca_file in ["/etc/ssl/cert.pem", "/usr/local/etc/openssl@3/cert.pem"]:
            if Path(ca_file).is_file():
                context.load_verify_locations(cafile=ca_file)
                break
    return context


def write_json(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")


def cache_paths(cache_dir: Path, source_id: str, resource: str) -> CachePaths:
    directory = cache_dir / safe_component(source_id) / safe_component(resource)
    return CachePaths(
        directory=directory,
        payload=directory / "payload.bin",
        metadata=directory / "metadata.json",
        attempt=directory / "latest-attempt.json",
    )


def http_get(url: str, etag: str | None) -> HttpResult:
    headers = {
        "Accept": "application/octet-stream, text/plain;q=0.8, application/json;q=0.8",
        "User-Agent": USER_AGENT,
    }
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=45, context=ssl_context()) as response:
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read(),
                None,
            )
    except urllib.error.HTTPError as error:
        # Do not retain or print an error body: public source responses can be
        # unexpectedly large and must not be treated as trusted data.
        return HttpResult(
            error.code,
            {key.lower(): value for key, value in error.headers.items()},
            b"",
            f"HTTP {error.code}: {error.reason}",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return HttpResult(None, {}, b"", f"{type(error).__name__}: {error}")


def source_and_url(config: JsonObject, source_id: str, resource: str) -> tuple[JsonObject, str]:
    sources = list_value(config.get("sources"))
    for item in sources:
        if not isinstance(item, dict):
            continue
        source = cast(JsonObject, item)
        if string_value(source.get("id")) != source_id:
            continue
        url = string_value(source.get(resource))
        if not url or not resource.endswith("_url"):
            raise ValueError(f"resource {resource!r} is not an allow-listed URL for {source_id!r}")
        return source, url
    raise ValueError(f"unknown source/resource: {source_id}/{resource}")


def make_record(
    *,
    source: JsonObject,
    source_id: str,
    resource: str,
    url: str,
    status: FetchStatus,
    checked_at: str,
    result: HttpResult,
    etag: str | None,
    payload_hash: str | None,
    payload_bytes: int,
    error: str | None = None,
) -> JsonObject:
    return {
        "schema_version": "0.1",
        "source_id": source_id,
        "resource": resource,
        "url": url,
        "publisher": string_value(source.get("publisher")),
        "declared_license_url": string_value(source.get("declared_license_url")),
        "status": status,
        "checked_at": checked_at,
        "http_status": result.status_code if result.status_code is not None else -1,
        "etag": etag or "",
        "content_type": result.headers.get("content-type", ""),
        "payload_bytes": payload_bytes,
        "sha256": payload_hash or "",
        "error": error or result.error or "",
    }


def fetch(source_id: str, resource: str, cache_dir: Path) -> JsonObject:
    config = load_object(CONFIG_PATH)
    source, url = source_and_url(config, source_id, resource)
    paths = cache_paths(cache_dir, source_id, resource)
    checked_at = now_iso()
    previous: JsonObject = load_object(paths.metadata) if paths.metadata.is_file() else {}
    previous_etag = string_value(previous.get("etag")) or None
    result = http_get(url, previous_etag)

    if result.status_code == 304:
        if not paths.payload.is_file() or not previous_etag:
            record = make_record(
                source=source,
                source_id=source_id,
                resource=resource,
                url=url,
                status="invalid",
                checked_at=checked_at,
                result=result,
                etag=previous_etag,
                payload_hash=string_value(previous.get("sha256")) or None,
                payload_bytes=0,
                error="server returned 304 but the cache payload or prior ETag is missing",
            )
            write_json(paths.attempt, record)
            raise RuntimeError(string_value(record.get("error")))
        record = dict(previous)
        record["last_checked_at"] = checked_at
        record["last_http_status"] = 304
        record["status"] = "not_modified"
        write_json(paths.metadata, cast(JsonObject, record))
        return cast(JsonObject, record)

    if result.status_code != 200:
        record = make_record(
            source=source,
            source_id=source_id,
            resource=resource,
            url=url,
            status="blocked",
            checked_at=checked_at,
            result=result,
            etag=None,
            payload_hash=None,
            payload_bytes=0,
        )
        write_json(paths.attempt, record)
        raise RuntimeError(f"source fetch blocked: {json.dumps(record, sort_keys=True)}")

    etag = result.headers.get("etag", "").strip()
    if not etag:
        record = make_record(
            source=source,
            source_id=source_id,
            resource=resource,
            url=url,
            status="invalid",
            checked_at=checked_at,
            result=result,
            etag=None,
            payload_hash=None,
            payload_bytes=len(result.body),
            error="successful response did not include an ETag; payload was not accepted",
        )
        write_json(paths.attempt, record)
        raise RuntimeError(string_value(record.get("error")))

    payload_hash = sha256_bytes(result.body)
    paths.directory.mkdir(parents=True, exist_ok=True)
    paths.payload.write_bytes(result.body)
    record = make_record(
        source=source,
        source_id=source_id,
        resource=resource,
        url=url,
        status="fetched",
        checked_at=checked_at,
        result=result,
        etag=etag,
        payload_hash=payload_hash,
        payload_bytes=len(result.body),
    )
    record["retrieved_at"] = checked_at
    write_json(paths.metadata, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--resource", required=True, help="A URL field present in config/real_corpus_sources.json")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args()
    try:
        record = fetch(args.source_id, args.resource, args.cache_dir)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}")
        return 2
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
