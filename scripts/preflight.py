#!/usr/bin/env python3
"""Discover live prerequisites for Appeal and write docs/preflight.json.

This script deliberately fails closed. It does not select a model from memory,
claim access to a managed component without a probe, or fetch a payer policy
when robots/terms have not been cleared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, cast
from urllib import robotparser


JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
Status = Literal["pass", "warning", "blocked", "not_checked"]

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONFIG_DIR: Final[Path] = ROOT / "config"
OUTPUT_PATH: Final[Path] = ROOT / "docs" / "preflight.json"
USER_AGENT: Final[str] = "appeal-preflight/0.1"
GOOGLE_SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"


@dataclass(frozen=True)
class HttpResult:
    url: str
    status_code: int | None
    headers: dict[str, str]
    body: str
    error: str | None


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    summary: str
    evidence: JsonObject
    fallback: str | None = None

    def as_json(self) -> JsonObject:
        result: JsonObject = {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "evidence": self.evidence,
        }
        if self.fallback is not None:
            result["fallback"] = self.fallback
        return result


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> JsonObject:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"configuration must be an object: {path}")
    return cast(JsonObject, raw)


def string_value(value: JsonValue | None, default: str = "") -> str:
    return value if isinstance(value, str) else default


def int_value(value: JsonValue | None, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def object_value(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def list_value(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def redact_error(error: str) -> str:
    """Keep diagnostics useful without allowing tokens or key material into artifacts."""

    redacted = re.sub(r"(?i)(authorization|access_token|refresh_token|api[-_]?key)\\s*[:=]\\s*[^,;\\s]+", r"\1=[REDACTED]", error)
    redacted = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_KEY]", redacted)
    return redacted[:500]


def http_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
) -> HttpResult:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain;q=0.8"}
    if headers is not None:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        context = ssl.create_default_context()
        if not context.get_ca_certs():
            for ca_file in ["/etc/ssl/cert.pem", "/usr/local/etc/openssl@3/cert.pem"]:
                if Path(ca_file).is_file():
                    context.load_verify_locations(cafile=ca_file)
                    break
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return HttpResult(url, response.status, response_headers, response_body, None)
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        response_headers = {key.lower(): value for key, value in error.headers.items()}
        return HttpResult(url, error.code, response_headers, response_body[:4000], redact_error(str(error)))
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return HttpResult(url, None, {}, "", redact_error(str(error)))


def parse_json_body(result: HttpResult) -> JsonObject | None:
    try:
        raw: object = json.loads(result.body)
    except json.JSONDecodeError:
        return None
    return cast(JsonObject, raw) if isinstance(raw, dict) else None


def response_error(result: HttpResult) -> str:
    body = parse_json_body(result)
    if body is not None:
        error = object_value(body.get("error"))
        message = string_value(error.get("message"))
        status = string_value(error.get("status"))
        reasons: list[str] = []
        for detail in list_value(error.get("details")):
            if isinstance(detail, dict):
                reason = string_value(cast(JsonObject, detail).get("reason"))
                if reason:
                    reasons.append(reason)
        parts = [part for part in [status, ",".join(reasons), message] if part]
        if parts:
            return ": ".join(parts)[:1000]
    return result.error or f"HTTP {result.status_code}"


def list_strings(value: JsonValue | None) -> list[str]:
    return [item for item in list_value(value) if isinstance(item, str)]


def read_adc() -> tuple[str | None, str | None]:
    """Return a short credential status and detected project, never the credential."""

    project_env = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    auth_error = ""
    try:
        import google.auth  # type: ignore[import-not-found]
        from google.auth.transport.requests import Request  # type: ignore[import-not-found]

        credentials, detected_project = google.auth.default(scopes=[GOOGLE_SCOPE])
        credentials.refresh(Request())
        token = getattr(credentials, "token", None)
        if not isinstance(token, str) or not token:
            return "ADC found but did not yield an access token", project_env or detected_project
        return "ADC available", project_env or detected_project
    except Exception as error:  # noqa: BLE001 - discovery must record every auth failure.
        auth_error = redact_error(f"Python ADC client unavailable: {error}")
    cli_token = gcloud_adc_token()
    if cli_token is not None:
        return "ADC available through the gcloud CLI", project_env
    return f"ADC unavailable: {auth_error or 'no supported ADC provider'}", project_env


def gcloud_adc_token() -> str | None:
    executable = shutil.which("gcloud")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip()
    return token if result.returncode == 0 and token else None


def access_token() -> str | None:
    try:
        import google.auth  # type: ignore[import-not-found]
        from google.auth.transport.requests import Request  # type: ignore[import-not-found]

        credentials, _ = google.auth.default(scopes=[GOOGLE_SCOPE])
        credentials.refresh(Request())
        token = getattr(credentials, "token", None)
        if isinstance(token, str) and token:
            return token
    except Exception as error:  # noqa: BLE001 - an explicit CLI fallback is attempted and blocked state is recorded by the caller.
        fallback = gcloud_adc_token()
        if fallback is not None:
            return fallback
        _ = redact_error(f"Python ADC token acquisition failed: {error}")
        return None


def auth_headers(token: str | None, quota_project: str | None = None) -> dict[str, str]:
    if token is None:
        return {}
    headers = {"Authorization": f"Bearer {token}"}
    if quota_project:
        headers["x-goog-user-project"] = quota_project
    return headers


def discovery_catalog(url: str) -> tuple[Status, list[JsonObject], str | None]:
    result = http_request(url)
    if result.status_code != 200:
        return "blocked", [], result.error or f"HTTP {result.status_code}"
    body = parse_json_body(result)
    if body is None:
        return "blocked", [], "discovery response was not a JSON object"
    entries: list[JsonObject] = []
    for item in list_value(body.get("items")):
        if isinstance(item, dict):
            entries.append(cast(JsonObject, item))
    return "pass", entries, None


def catalog_match(entry: JsonObject, terms: list[str]) -> bool:
    searchable = " ".join(
        [
            string_value(entry.get("name")),
            string_value(entry.get("title")),
            string_value(entry.get("description")),
            string_value(entry.get("discoveryRestUrl")),
        ]
    ).lower()
    return any(term.lower() in searchable for term in terms)


def catalog_summary(entry: JsonObject) -> JsonObject:
    return {
        "name": string_value(entry.get("name")),
        "version": string_value(entry.get("version")),
        "title": string_value(entry.get("title")),
        "discovery_rest_url": string_value(entry.get("discoveryRestUrl")),
    }


def find_catalog_entry(entries: list[JsonObject], name: str) -> JsonObject | None:
    matches = [entry for entry in entries if string_value(entry.get("name")) == name]
    matches.sort(key=lambda entry: string_value(entry.get("version")), reverse=True)
    return matches[0] if matches else None


def discover_path(document_url: str, path_parts: list[str]) -> str | None:
    result = http_request(document_url)
    body = parse_json_body(result)
    if result.status_code != 200 or body is None:
        return None
    current: JsonValue = body
    for part in path_parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current if isinstance(current, str) else None


def format_google_path(template: str, *, project: str, location: str | None = None) -> str:
    parent = f"projects/{urllib.parse.quote(project, safe='')}"
    if location:
        parent = f"{parent}/locations/{urllib.parse.quote(location, safe='')}"
    path = template.replace("{+parent}", parent)
    path = path.replace("{parent}", f"projects/{urllib.parse.quote(project, safe='')}")
    path = path.replace("{parent=projects/*}", f"projects/{urllib.parse.quote(project, safe='')}")
    path = path.replace("{parent=projects/*/locations/*}", f"projects/{urllib.parse.quote(project, safe='')}/locations/{urllib.parse.quote(location or '', safe='')}")
    path = path.replace("{parent=projects/*/locations/*/publishers/*}", f"projects/{urllib.parse.quote(project, safe='')}/locations/{urllib.parse.quote(location or '', safe='')}/publishers/google")
    path = path.replace("{name=projects/*/locations/*/publishers/*/models/*}", "")
    path = path.replace("{name=projects/*/locations/*}", "")
    path = path.replace("{name=projects/*}", "")
    path = path.replace("{+name}", f"projects/{urllib.parse.quote(project, safe='')}")
    return path


def regional_api_url(location: str, path: str) -> str:
    return f"https://{urllib.parse.quote(location, safe='')}-aiplatform.googleapis.com/{path.lstrip('/')}"


def select_gemini_model(models: list[JsonObject], minimum_major: int, minimum_minor: int) -> tuple[JsonObject | None, list[JsonObject]]:
    version_pattern = re.compile(r"gemini[-_ ]?(\d+)(?:[.-](\d+))?", re.IGNORECASE)
    candidates: list[JsonObject] = []
    for model in models:
        name = string_value(model.get("name"))
        display_name = string_value(model.get("displayName"))
        version = string_value(model.get("version"))
        text = " ".join([name, display_name, version])
        match = version_pattern.search(text)
        if match is None:
            continue
        major = int(match.group(1))
        minor = int(match.group(2) or "0")
        methods = list_strings(model.get("supportedGenerationMethods"))
        if (major, minor) >= (minimum_major, minimum_minor) and "generateContent" in methods:
            candidates.append(
                {
                    "name": name,
                    "display_name": display_name,
                    "version": version,
                    "major": major,
                    "minor": minor,
                    "supported_generation_methods": methods,
                    "input_token_limit": model.get("inputTokenLimit"),
                    "output_token_limit": model.get("outputTokenLimit"),
                    "raw_create_time": model.get("createTime"),
                }
            )
    candidates.sort(
        key=lambda item: (
            int_value(item.get("major")),
            int_value(item.get("minor")),
            string_value(item.get("raw_create_time")),
            string_value(item.get("name")),
        ),
        reverse=True,
    )
    return (candidates[0] if candidates else None), candidates


def check_models(
    *,
    project: str | None,
    location: str | None,
    requirements: JsonObject,
    discovery: JsonObject,
    catalog_entries: list[JsonObject],
    token: str | None,
) -> Check:
    minimum = object_value(requirements.get("gemini"))
    minimum_major = int_value(minimum.get("minimum_major"), 3)
    minimum_minor = int_value(minimum.get("minimum_minor"), 5)
    catalog_name = string_value(discovery.get("aiplatform_catalog_name"), "aiplatform")
    catalog_entry = find_catalog_entry(catalog_entries, catalog_name)
    aiplatform_discovery_url = string_value(catalog_entry.get("discoveryRestUrl")) if catalog_entry else ""
    evidence: JsonObject = {
        "project": project or "",
        "location": location or "",
        "minimum": f"Gemini {minimum_major}.{minimum_minor}",
        "catalog_name": catalog_name,
        "catalog_entry": catalog_summary(catalog_entry) if catalog_entry else {},
        "discovery_url": aiplatform_discovery_url,
    }
    if project is None or location is None:
        evidence["reason"] = "Google Cloud project or region is not configured"
        return Check(
            "Gemini model discovery",
            "blocked",
            "Cannot list regional Gemini models without a project and region.",
            evidence,
            "Configure Google Cloud project, region, and Application Default Credentials before proceeding.",
        )
    if token is None:
        evidence["reason"] = "Application Default Credentials did not yield an access token"
        return Check(
            "Gemini model discovery",
            "blocked",
            "Cannot list models because authenticated Google Cloud access is unavailable.",
            evidence,
            "Authenticate with Application Default Credentials and rerun preflight.",
        )
    if not aiplatform_discovery_url:
        evidence["reason"] = "The live Google API catalog did not expose the configured Agent Platform API"
        return Check(
            "Gemini model discovery",
            "blocked",
            "The current discovery catalog did not expose an Agent Platform API document.",
            evidence,
            "Use the live API catalog to identify the current Agent Platform discovery URL.",
        )
    path = discover_path(
        aiplatform_discovery_url,
        ["resources", "projects", "resources", "locations", "resources", "models", "methods", "list", "path"],
    )
    if path is None:
        evidence["reason"] = "The live aiplatform discovery document did not expose a model-list method at the expected resource"
        return Check(
            "Gemini model discovery",
            "blocked",
            "The current API discovery document did not expose a model-list operation for this probe.",
            evidence,
            "Inspect the current discovery document and add the discovered operation without hardcoding a model ID.",
        )
    url = regional_api_url(location, format_google_path(path, project=project, location=location))
    result = http_request(url, headers=auth_headers(token, project))
    body = parse_json_body(result)
    evidence["list_url"] = url
    evidence["http_status"] = result.status_code if result.status_code is not None else -1
    evidence["etag"] = result.headers.get("etag", "")
    if result.status_code != 200 or body is None:
        evidence["error"] = response_error(result) if result.status_code != 200 else "model list response was not a JSON object"
        return Check(
            "Gemini model discovery",
            "blocked",
            "The live model-list request did not succeed.",
            evidence,
            "Resolve regional API access, quota, or IAM before building model-dependent components.",
        )
    models = [cast(JsonObject, item) for item in list_value(body.get("models")) if isinstance(item, dict)]
    selected, candidates = select_gemini_model(models, minimum_major, minimum_minor)
    evidence["listed_model_count"] = len(models)
    evidence["qualifying_models"] = candidates
    evidence["selected_model"] = selected or {}
    if selected is None:
        return Check(
            "Gemini model discovery",
            "blocked",
            f"No listed model satisfied Gemini {minimum_major}.{minimum_minor} with generateContent support.",
            evidence,
            "Stop and report the model availability blocker; do not substitute an unverified model ID.",
        )
    return Check("Gemini model discovery", "pass", "A qualifying Gemini model was selected from the live regional listing.", evidence)


def check_platform_components(
    *,
    components: JsonObject,
    catalog_entries: list[JsonObject],
    project: str | None,
    token: str | None,
) -> list[Check]:
    results: list[Check] = []
    for item in list_value(components.get("components")):
        if not isinstance(item, dict):
            continue
        component = cast(JsonObject, item)
        component_id = string_value(component.get("id"), "unknown")
        label = string_value(component.get("label"), component_id)
        terms = list_strings(component.get("catalog_terms"))
        matches = [catalog_summary(entry) for entry in catalog_entries if catalog_match(entry, terms)]
        evidence: JsonObject = {
            "component_id": component_id,
            "catalog_terms": terms,
            "public_discovery_matches": matches,
            "project": project or "",
        }
        fallback = string_value(component.get("fallback"))
        if token is None or project is None:
            evidence["probe"] = "not performed: authenticated project access unavailable"
            results.append(Check(label, "blocked", "The component could not be probed against a live project.", evidence, fallback))
            continue
        evidence["probe"] = "service enablement and component endpoint probing requires a discovered service binding"
        results.append(Check(label, "not_checked", "A public catalog match was recorded, but no authenticated component binding was discovered.", evidence, fallback))
    return results


def check_service_usage(
    *,
    project: str | None,
    token: str | None,
    discovery_url: str,
) -> Check:
    evidence: JsonObject = {"project": project or "", "discovery_url": discovery_url}
    if project is None or token is None:
        evidence["reason"] = "project or access token unavailable"
        return Check("Enabled Google APIs", "blocked", "Enabled-service discovery requires authenticated project access.", evidence, "Authenticate and rerun before treating any managed component as enabled.")
    path = discover_path(discovery_url, ["resources", "services", "methods", "list", "path"])
    if path is None:
        path = discover_path(discovery_url, ["resources", "projects", "resources", "services", "methods", "list", "path"])
    if path is None:
        evidence["reason"] = "serviceusage discovery document did not expose a service list method"
        return Check("Enabled Google APIs", "blocked", "The live Service Usage discovery document could not be resolved.", evidence, "Use the current Service Usage discovery document to locate the service-list method.")
    formatted = format_google_path(path, project=project)
    url = f"https://serviceusage.googleapis.com/{formatted.lstrip('/')}?filter=state:ENABLED&pageSize=200"
    result = http_request(url, headers=auth_headers(token, project))
    body = parse_json_body(result)
    evidence["list_url"] = url
    evidence["http_status"] = result.status_code if result.status_code is not None else -1
    evidence["etag"] = result.headers.get("etag", "")
    if result.status_code != 200 or body is None:
        evidence["error"] = response_error(result) if result.status_code != 200 else "service list response was not a JSON object"
        return Check("Enabled Google APIs", "blocked", "The live Service Usage request did not succeed.", evidence, "Resolve Service Usage IAM and quota before probing managed components.")
    services = [string_value(object_value(item).get("name")) for item in list_value(body.get("services")) if isinstance(item, dict)]
    evidence["enabled_service_count"] = len(services)
    evidence["enabled_services"] = services
    return Check("Enabled Google APIs", "pass", "Enabled services were listed from the live project.", evidence)


def check_region(project: str | None, location: str | None) -> Check:
    evidence: JsonObject = {
        "project": project or "",
        "requested_region": location or "",
        "model_region": location or "",
        "memory_bank_generation_region": "not discovered",
    }
    if project is None or location is None:
        return Check("Region and residency", "blocked", "Project region is not configured, and Memory Bank residency cannot be verified.", evidence, "Configure the target region and probe Memory Bank metadata before making a sovereignty claim.")
    return Check("Region and residency", "warning", "The requested model region is recorded; Memory Bank generation residency still requires an accessible Memory Bank probe.", evidence, "Do not claim same-region Memory Bank processing until the managed service reports it.")


def check_quota(
    *,
    project: str | None,
    token: str | None,
    discovery_url: str,
    load: JsonObject,
) -> Check:
    expected_cases = int_value(load.get("expected_open_cases"))
    sentinel_runs = int_value(load.get("sentinel_runs_per_day"))
    transitions = int_value(load.get("expected_case_transitions_per_case"))
    model_calls = int_value(load.get("expected_model_calls_per_case"))
    expected_daily_model_calls = expected_cases * model_calls * max(sentinel_runs, 1)
    expected_daily_transitions = expected_cases * transitions
    evidence: JsonObject = {
        "project": project or "",
        "services_to_probe": ["aiplatform.googleapis.com", "firestore.googleapis.com"],
        "expected_load": {
            "open_cases": expected_cases,
            "sentinel_runs_per_day": sentinel_runs,
            "daily_model_calls_upper_bound": expected_daily_model_calls,
            "daily_case_transitions_upper_bound": expected_daily_transitions,
        },
        "discovery_url": discovery_url,
    }
    if project is None or token is None:
        evidence["reason"] = "project or access token unavailable"
        return Check("Model, Agent Runtime, and Firestore quotas", "blocked", "Quota ceilings could not be queried without authenticated project access.", evidence, "Authenticate and rerun; do not record an unverified quota ceiling.")
    evidence["reason"] = "quota metric discovery is deferred until the live service bindings are identified"
    return Check("Model, Agent Runtime, and Firestore quotas", "not_checked", "The load arithmetic is recorded, but quota ceilings are not yet verified.", evidence, "Query consumer quota metrics for each discovered service before deployment.")


def choose_pas_version(package_list_url: str, ig_url: str, cms_url: str) -> Check:
    evidence: JsonObject = {"package_list_url": package_list_url, "ig_url": ig_url, "cms_context_url": cms_url}
    result = http_request(package_list_url)
    body = parse_json_body(result)
    evidence["package_list_status"] = result.status_code if result.status_code is not None else -1
    evidence["package_list_etag"] = result.headers.get("etag", "")
    if result.status_code != 200 or body is None:
        evidence["error"] = result.error or "package-list response was not a JSON object"
        return Check("Da Vinci PAS IG discovery", "blocked", "The published PAS package list could not be fetched.", evidence, "Resolve network access and fetch the published IG package list before implementing PAS operations.")
    entries = [cast(JsonObject, item) for item in list_value(body.get("list")) if isinstance(item, dict)]
    current = [item for item in entries if item.get("current") is True and string_value(item.get("status")).lower() in {"release", "trial-use", "normative"}]
    candidates = current or entries
    candidates.sort(key=lambda item: string_value(item.get("version")), reverse=True)
    selected = candidates[0] if candidates else None
    evidence["available_versions"] = [string_value(item.get("version")) for item in entries]
    evidence["selected"] = selected or {}
    evidence["selection_reason"] = "latest published release from HL7 package-list.json; CMS page retained for comparison"
    if selected is None:
        return Check("Da Vinci PAS IG discovery", "blocked", "The PAS package list was reachable but contained no published version.", evidence, "Inspect the live HL7 package list and select a version with an explicit status.")
    cms_result = http_request(cms_url)
    evidence["cms_context_status"] = cms_result.status_code if cms_result.status_code is not None else -1
    evidence["cms_context_etag"] = cms_result.headers.get("etag", "")
    return Check("Da Vinci PAS IG discovery", "pass", "A published PAS version was selected from the live HL7 package list.", evidence)


def check_synthea(releases_url: str, license_url: str, repository_url: str, seed: int, required_asset_name: str) -> Check:
    evidence: JsonObject = {"releases_api_url": releases_url, "license_api_url": license_url, "repository_url": repository_url, "seed": seed, "required_asset_name": required_asset_name}
    releases_result = http_request(releases_url, headers={"Accept": "application/vnd.github+json"})
    license_result = http_request(license_url, headers={"Accept": "application/vnd.github+json"})
    release_raw: object
    try:
        release_raw = json.loads(releases_result.body)
    except json.JSONDecodeError:
        release_raw = []
    releases = [cast(JsonObject, item) for item in release_raw if isinstance(item, dict)] if isinstance(release_raw, list) else []
    license_body = parse_json_body(license_result)
    evidence["releases_status"] = releases_result.status_code if releases_result.status_code is not None else -1
    evidence["license_status"] = license_result.status_code if license_result.status_code is not None else -1
    evidence["releases_etag"] = releases_result.headers.get("etag", "")
    evidence["license_etag"] = license_result.headers.get("etag", "")
    stable_releases = [
        release
        for release in releases
        if release.get("draft") is not True
        and release.get("prerelease") is not True
        and re.match(r"^v?\d+\.\d+\.\d+", string_value(release.get("tag_name"))) is not None
    ]
    stable_releases.sort(key=lambda release: string_value(release.get("published_at")), reverse=True)
    selected_release = stable_releases[0] if stable_releases else None
    if releases_result.status_code != 200 or not releases:
        evidence["release_error"] = releases_result.error or "release response did not contain a JSON list"
        return Check("Synthea availability and licence", "blocked", "Synthea release discovery failed.", evidence, "Resolve public GitHub access and pin the exact release before corpus generation.")
    if license_result.status_code != 200 or license_body is None:
        evidence["license_error"] = license_result.error or "license response was not a JSON object"
        return Check("Synthea availability and licence", "blocked", "Synthea licence discovery failed.", evidence, "Verify the repository licence before generating or redistributing the corpus.")
    license_metadata = object_value(license_body.get("license"))
    evidence["selected_release_tag"] = string_value(selected_release.get("tag_name")) if selected_release else ""
    evidence["selected_release_url"] = string_value(selected_release.get("html_url")) if selected_release else ""
    evidence["selected_release_published_at"] = string_value(selected_release.get("published_at")) if selected_release else ""
    evidence["license_spdx_id"] = string_value(license_metadata.get("spdx_id"))
    evidence["license_name"] = string_value(license_metadata.get("name"))
    assets = [cast(JsonObject, item) for item in list_value(selected_release.get("assets")) if isinstance(item, dict)] if selected_release else []
    selected_asset = next((asset for asset in assets if string_value(asset.get("name")) == required_asset_name), None)
    evidence["selected_asset"] = {
        "name": string_value(selected_asset.get("name")) if selected_asset else "",
        "browser_download_url": string_value(selected_asset.get("browser_download_url")) if selected_asset else "",
        "size": int_value(selected_asset.get("size")) if selected_asset else 0,
        "digest": string_value(selected_asset.get("digest")) if selected_asset else "",
    }
    if selected_release is None or not string_value(license_metadata.get("spdx_id")) or selected_asset is None or not string_value(selected_asset.get("digest")):
        return Check("Synthea availability and licence", "warning", "Synthea was reachable but the release or licence metadata was incomplete.", evidence, "Manually verify the exact pinned release and licence before Phase 1.")
    return Check("Synthea availability and licence", "pass", "Synthea release and licence metadata were discovered from the live repository.", evidence)


def check_policy_source(source: JsonObject) -> Check:
    source_id = string_value(source.get("id"), "unknown")
    index_url = string_value(source.get("index_url"))
    terms_url = string_value(source.get("terms_url"))
    robots_url = string_value(source.get("robots_url"))
    evidence: JsonObject = {
        "source_id": source_id,
        "payer": string_value(source.get("payer")),
        "index_url": index_url,
        "terms_url": terms_url,
        "robots_url": robots_url,
        "fetch_method": string_value(source.get("fetch_method")),
        "configured_automated_fetch_authorized": source.get("automated_fetch_authorized") is True,
    }
    robots_result = http_request(robots_url, headers={"Accept": "text/plain"})
    terms_result = http_request(terms_url, headers={"Accept": "text/html, text/plain;q=0.8"})
    evidence["robots_status"] = robots_result.status_code if robots_result.status_code is not None else -1
    evidence["terms_status"] = terms_result.status_code if terms_result.status_code is not None else -1
    evidence["index_status"] = -1
    evidence["robots_etag"] = robots_result.headers.get("etag", "")
    evidence["terms_etag"] = terms_result.headers.get("etag", "")
    evidence["index_etag"] = ""
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(robots_result.body.splitlines())
    allowed_by_robots = parser.can_fetch(USER_AGENT, index_url) if robots_result.status_code == 200 else False
    evidence["robots_allows_index"] = allowed_by_robots
    evidence["terms_interpretation"] = "manual legal/terms review required; preflight does not infer permission from HTTP success"
    evidence["policy_fetch_performed"] = False
    if robots_result.status_code != 200 or not allowed_by_robots:
        return Check(f"Policy source: {source_id}", "blocked", "Policy fetching is not permitted until robots access is confirmed.", evidence, "Use a source with permitted automated access or obtain a documented manual-fetch provenance path.")
    if terms_result.status_code is None or terms_result.status_code >= 400:
        return Check(f"Policy source: {source_id}", "warning", "robots.txt permits the index path, but the terms page could not be verified.", evidence, "Complete a human terms review before automated fetching.")
    if source.get("automated_fetch_authorized") is True:
        index_result = http_request(index_url, headers={"Accept": "text/html, application/xhtml+xml;q=0.8"})
        evidence["index_status"] = index_result.status_code if index_result.status_code is not None else -1
        evidence["index_etag"] = index_result.headers.get("etag", "")
        evidence["policy_fetch_performed"] = True
    return Check(f"Policy source: {source_id}", "warning", "robots.txt permits the index path; terms permission remains a human review item.", evidence, "Record explicit terms permission before enabling automated document ingestion.")


def check_real_corpus_source(source: JsonObject) -> Check:
    source_id = string_value(source.get("id"), "unknown")
    kind = string_value(source.get("kind"), "unknown")
    evidence: JsonObject = {
        "source_id": source_id,
        "kind": kind,
        "publisher": string_value(source.get("publisher")),
        "declared_license_url": string_value(source.get("declared_license_url")),
        "reported_coverage": string_value(source.get("reported_coverage")),
        "case_level_ground_truth_verified": source.get("case_level_ground_truth_verified") is True,
        "case_level_outcome_field_observed": source.get("case_level_outcome_field_observed") is True,
        "central_case_level_dataset": source.get("central_case_level_dataset") is True,
        "fetch_method": string_value(source.get("fetch_method")),
        "url_results": {},
    }
    urls: list[tuple[str, str]] = []
    for field in [
        "catalog_url",
        "open_data_url",
        "decisions_page_url",
        "search_url",
        "csv_url",
        "data_dictionary_url",
        "archive_url",
        "datastore_api_url",
        "faq_url",
        "template_url",
        "final_rule_fact_sheet_url",
    ]:
        url = string_value(source.get(field))
        if url:
            urls.append((field, url))
    for label, url in urls:
        result = http_request(url, method="HEAD", headers={"Accept": "text/html, application/json, application/pdf, text/csv;q=0.8"})
        results = object_value(evidence.get("url_results"))
        results[label] = {
            "url": url,
            "status": result.status_code if result.status_code is not None else -1,
            "etag": result.headers.get("etag", ""),
            "content_type": result.headers.get("content-type", ""),
            "error": result.error or "",
        }
        evidence["url_results"] = results

    if kind == "regulator_external_appeals":
        required_labels = {"archive_url"}
        results = object_value(evidence.get("url_results"))
        inaccessible = [
            label
            for label in required_labels
            if int_value(object_value(results.get(label)).get("status"), -1) >= 400
            or int_value(object_value(results.get(label)).get("status"), -1) < 0
        ]
        evidence["case_level_schema_observed"] = source.get("case_level_schema_observed") is True
        evidence["case_level_data_fetched"] = False
        evidence["inaccessible_data_urls"] = inaccessible
        if inaccessible:
            return Check(
                f"Real corpus source: {source_id}",
                "blocked",
                "The official external-appeal archive was discovered, but its archive endpoint is not currently retrievable by this client.",
                evidence,
                "Use the official browser export or another documented access path, then inspect the unmodified source before accepting it as case-level ground truth.",
            )
        return Check(
            f"Real corpus source: {source_id}",
            "warning",
            "The official external-appeal archive is reachable, but case-level reuse and privacy review still require inspection of the unmodified export.",
            evidence,
            "Inspect the export terms and records; do not claim a public benchmark until reuse and identifier review are complete.",
        )

    if kind == "regulator_determinations":
        data_labels = {"csv_url", "data_dictionary_url", "archive_url", "datastore_api_url"}
        data_results = object_value(evidence.get("url_results"))
        inaccessible = [
            label
            for label in data_labels
            if int_value(object_value(data_results.get(label)).get("status"), -1) >= 400
            or int_value(object_value(data_results.get(label)).get("status"), -1) < 0
        ]
        evidence["case_level_schema_observed"] = False
        evidence["case_level_data_fetched"] = False
        evidence["inaccessible_data_urls"] = inaccessible
        if inaccessible:
            return Check(
                f"Real corpus source: {source_id}",
                "blocked",
                "The official source was discovered, but its data or schema endpoint is not currently retrievable by this client.",
                evidence,
                "Use the official browser download or documented manual provenance path, then inspect the unmodified source before accepting it as case-level ground truth.",
            )
        return Check(
            f"Real corpus source: {source_id}",
            "warning",
            "The official regulator source is reachable, but case-level schema and ground truth still require inspection of the unmodified data.",
            evidence,
            "Inspect the official data dictionary and records; do not claim a case-level benchmark until the fields and determination labels are verified.",
        )

    required_labels = {"faq_url", "template_url", "final_rule_fact_sheet_url"}
    results = object_value(evidence.get("url_results"))
    inaccessible = [
        label
        for label in required_labels
        if int_value(object_value(results.get(label)).get("status"), -1) >= 400
        or int_value(object_value(results.get(label)).get("status"), -1) < 0
    ]
    evidence["inaccessible_urls"] = inaccessible
    if inaccessible:
        return Check(
            f"Real benchmark definition: {source_id}",
            "blocked",
            "The official CMS benchmark definition could not be retrieved from every required endpoint.",
            evidence,
            "Resolve official CMS access before calibrating the payer or reporting a benchmark.",
        )
    return Check(
        f"Real benchmark definition: {source_id}",
        "pass",
        "Official CMS-0057-F metric definitions and reporting guidance were retrieved.",
        evidence,
        "Collect actual public payer reports with provenance; the CMS template is a definition, not a case-level dataset.",
    )


def local_checks() -> list[Check]:
    version = sys.version_info
    required_python = (3, 12)
    python_status: Status = "pass" if (version.major, version.minor) >= required_python else "blocked"
    checks = [
        Check(
            "Python runtime",
            python_status,
            f"Python {version.major}.{version.minor}.{version.micro} detected.",
            {"version": platform.python_version(), "required": "3.12+"},
            "Install Python 3.12 or newer before running typed core packages.",
        )
    ]
    for executable in ["git", "curl"]:
        found = False
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if (Path(directory) / executable).is_file():
                found = True
                break
        checks.append(Check(f"Local tool: {executable}", "pass" if found else "blocked", f"{executable} {'is' if found else 'is not'} available on PATH.", {"executable": executable, "available": found}, "Install the missing tool before corpus or deployment work."))
    return checks


def build_preflight() -> tuple[JsonObject, int]:
    requirements = load_json(CONFIG_DIR / "requirements.json")
    load = load_json(CONFIG_DIR / "demo_load.json")
    components = load_json(CONFIG_DIR / "platform_components.json")
    policy_sources = load_json(CONFIG_DIR / "policy_sources.json")
    real_corpus_sources = load_json(CONFIG_DIR / "real_corpus_sources.json")
    discovery = object_value(requirements.get("discovery"))
    pas = object_value(requirements.get("pas"))
    synthea = object_value(requirements.get("synthea"))
    cloud = object_value(requirements.get("google_cloud"))
    project = next((os.environ.get(name) for name in list_strings(cloud.get("project_env_vars")) if os.environ.get(name)), None)
    location = next((os.environ.get(name) for name in list_strings(cloud.get("region_env_vars")) if os.environ.get(name)), None)
    auth_summary, detected_project = read_adc()
    project = project or detected_project
    token = access_token()
    catalog_status, catalog_entries, catalog_error = discovery_catalog(string_value(discovery.get("google_api_catalog_url")))
    checks: list[Check] = local_checks()
    checks.append(Check("Application Default Credentials", "pass" if token else "blocked", auth_summary or "ADC status unknown", {"available": token is not None, "project_detected": project or ""}, "Configure ADC with a user or workload identity; never commit a service-account key."))
    checks.append(Check("Google API discovery catalog", catalog_status, "Live Google API catalog retrieved." if catalog_status == "pass" else "Google API catalog could not be retrieved.", {"url": string_value(discovery.get("google_api_catalog_url")), "entry_count": len(catalog_entries), "error": catalog_error or ""}, "Use the live discovery catalog rather than a remembered API surface."))
    checks.append(check_models(project=project, location=location, requirements=requirements, discovery=discovery, catalog_entries=catalog_entries, token=token))
    checks.extend(check_platform_components(components=components, catalog_entries=catalog_entries, project=project, token=token))
    checks.append(check_service_usage(project=project, token=token, discovery_url=string_value(discovery.get("serviceusage_discovery_url"))))
    checks.append(check_region(project, location))
    checks.append(check_quota(project=project, token=token, discovery_url=string_value(discovery.get("serviceusage_discovery_url")), load=load))
    checks.append(choose_pas_version(string_value(pas.get("package_list_url")), string_value(pas.get("ig_url")), string_value(pas.get("cms_context_url"))))
    checks.append(check_synthea(string_value(synthea.get("releases_api_url")), string_value(synthea.get("license_api_url")), string_value(synthea.get("repository_url")), int_value(synthea.get("seed")), string_value(synthea.get("asset_name"))))
    for source in list_value(policy_sources.get("sources")):
        if isinstance(source, dict):
            checks.append(check_policy_source(cast(JsonObject, source)))
    for source in list_value(real_corpus_sources.get("sources")):
        if isinstance(source, dict):
            checks.append(check_real_corpus_source(cast(JsonObject, source)))
    blockers = [check.name for check in checks if check.status == "blocked"]
    warnings = [check.name for check in checks if check.status in {"warning", "not_checked"}]
    payload: JsonObject = {
        "schema_version": "0.1",
        "generated_at": now_iso(),
        "git_commit": os.environ.get("APPEAL_PREFLIGHT_COMMIT", "unknown"),
        "project": project or "",
        "region": location or "",
        "checks": [check.as_json() for check in checks],
        "summary": {
            "pass_count": sum(check.status == "pass" for check in checks),
            "warning_count": len(warnings),
            "blocker_count": len(blockers),
            "blockers": blockers,
            "warnings": warnings,
        },
        "policy_fetch_policy": "No payer policy document was fetched by Phase 0; robots and terms were checked before any future fetch.",
        "security_note": "No credential, access token, private key, or secret is written to this artifact.",
    }
    return payload, 2 if blockers else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    payload, exit_code = build_preflight()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.output.write_text(serialized, encoding="utf-8")
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    print(f"Preflight artifact: {args.output}")
    print(f"Artifact SHA-256: {digest}")
    print(f"Blockers: {int_value(object_value(payload.get('summary')).get('blocker_count'))}")
    for blocker in list_strings(object_value(payload.get("summary")).get("blockers")):
        print(f"BLOCKER: {blocker}")
    if exit_code:
        print("Preflight did not pass. Stop before Phase 1 and resolve the blockers.")
    else:
        print("Preflight passed. The Phase 0 exit criteria can be audited.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
