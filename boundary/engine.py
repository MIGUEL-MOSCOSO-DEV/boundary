import copy
import hashlib
import json
import os
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .config import SAFE_METHODS, build_url, fingerprint, validate

LIMIT = 256 * 1024
MISSING = object()


def pointer(document, path):
    value = document
    if path == "":
        return value
    for token in path.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            return MISSING
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class Client:
    def __init__(self, timeout):
        self.timeout = timeout
        self.opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect()
        )

    def request(self, method, url, headers, body):
        started = time.monotonic()
        request = Request(
            url,
            data=json.dumps(body, allow_nan=False).encode() if body is not MISSING else None,
            headers={
                "User-Agent": "Boundary/1.0 (authorized-policy-audit)",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                **headers,
            },
            method=method,
        )
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                data = bytearray()
                while len(data) <= LIMIT:
                    if time.monotonic() - started > self.timeout:
                        raise TimeoutError()
                    chunk = response.read1(min(16384, LIMIT + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                truncated = len(data) > LIMIT
                data = bytes(data[:LIMIT])
                parsed = None
                if not truncated and "json" in response.headers.get("Content-Type", "").lower():
                    try:
                        parsed = json.loads(data)
                    except (ValueError, UnicodeError, RecursionError):
                        pass
                return {
                    "status": response.code,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "bytes_captured": len(data),
                    "truncated": truncated,
                    "body_sha256": hashlib.sha256(data).hexdigest(),
                    "json": parsed,
                    "error": None,
                }
        except (URLError, OSError, TimeoutError, ValueError):
            return {
                "status": None,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "bytes_captured": 0,
                "truncated": False,
                "body_sha256": None,
                "json": None,
                "error": "TLS, network or timeout error",
            }


def resolve_identities(config, overrides=None):
    overrides = overrides or {}
    headers = {}
    secrets = []
    for name, identity in config["identities"].items():
        values = {}
        for header, variable in identity.get("headers_env", {}).items():
            value = overrides.get(name, {}).get(header, os.environ.get(variable, ""))
            if (
                not isinstance(value, str)
                or not 4 <= len(value) <= 8192
                or "\r" in value
                or "\n" in value
            ):
                raise ValueError(
                    f"Falta una credencial válida para {name}: {header} (variable {variable})."
                )
            values[header] = value
            secrets.append(value)
            if value.lower().startswith("bearer "):
                secrets.append(value[7:])
        headers[name] = values
    return headers, secrets


def redact(value, secrets):
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {redact(str(key), secrets): redact(item, secrets) for key, item in value.items()}
    return value


def public_url(value):
    parts = urlsplit(value)
    query = urlencode(
        [(name, "[REDACTED]") for name, _ in parse_qsl(parts.query, keep_blank_values=True)]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def baseline_identity(case, result):
    if (
        result["error"]
        or result["status"] is None
        or not 200 <= result["status"] < 300
        or result["truncated"]
    ):
        return MISSING
    path = case.get("resource_pointer")
    if not path:
        return MISSING
    value = pointer(result["json"], path)
    if value is None or value is MISSING or isinstance(value, (dict, list)):
        return MISSING
    if "resource_value" in case and value != case["resource_value"]:
        return MISSING
    return value


def evaluate(case, identity, result, baseline, stable):
    status = result["status"]
    if result["error"] or status is None:
        return "inconclusive", [
            {
                "rule": "request-failed",
                "severity": "info",
                "summary": "No se obtuvo una respuesta evaluable.",
            }
        ]
    findings = []
    forbidden = []
    if 200 <= status < 300 and not result["truncated"]:
        for path in case.get("forbidden_fields", {}).get(identity, []):
            if pointer(result["json"], path) is not MISSING:
                forbidden.append(path)
    if forbidden:
        findings.append(
            {
                "rule": "forbidden-field-present",
                "severity": "high",
                "summary": "La respuesta incluye campos que la política prohíbe a esta identidad.",
                "pointers": forbidden,
            }
        )
    if identity in case["allow"]:
        if 200 <= status < 300 and (
            case.get("resource_pointer")
            and baseline_identity(case, result) is MISSING
            or result["truncated"]
            and case.get("forbidden_fields", {}).get(identity)
        ):
            return "inconclusive", findings + [
                {
                    "rule": "resource-assertion-unavailable",
                    "severity": "info",
                    "summary": "No se pudo verificar el recurso o todos los campos esperados.",
                }
            ]
        if 200 <= status < 300:
            return ("violation" if findings else "pass"), findings
        return "inconclusive", findings + [
            {
                "rule": "expected-access-failed",
                "severity": "info",
                "summary": "La identidad que debería tener acceso no recibió 2xx.",
            }
        ]
    if status in case.get("deny_statuses", [401, 403, 404]):
        return "pass", findings
    if 200 <= status < 300:
        value = (
            pointer(result["json"], case.get("resource_pointer", ""))
            if case.get("resource_pointer")
            else MISSING
        )
        same_resource = baseline is not MISSING and value is not MISSING and value == baseline
        if stable and same_resource and not result["truncated"]:
            findings.append(
                {
                    "rule": "unauthorized-resource-access",
                    "severity": "high",
                    "summary": "Una identidad denegada obtuvo el mismo identificador de recurso que la referencia permitida.",
                    "resource_pointer": case["resource_pointer"],
                }
            )
            return "violation", findings
        findings.append(
            {
                "rule": "unexpected-success",
                "severity": "review",
                "summary": "Una identidad denegada recibió 2xx; no se pudo confirmar una referencia de recurso estable.",
            }
        )
        return ("violation" if forbidden else "review"), findings
    return "inconclusive", findings + [
        {
            "rule": "unexpected-status",
            "severity": "info",
            "summary": "El estado no coincide con los códigos de denegación definidos.",
        }
    ]


def audit(
    config,
    authorized=False,
    allow_mutations=False,
    overrides=None,
    client=None,
    cancel=None,
    progress=None,
    clock=time.monotonic,
    sleep=time.sleep,
):
    config = validate(copy.deepcopy(config))
    if not authorized:
        raise ValueError("Confirma que tienes autorización sobre el origen y las identidades.")
    if any(case["method"] not in SAFE_METHODS for case in config["cases"]):
        if not config["allow_mutations"] or not allow_mutations:
            raise ValueError(
                "Los métodos que modifican datos necesitan allow_mutations y habilitación explícita de la ejecución."
            )
    identity_headers, secrets = resolve_identities(config, overrides)
    client = client or Client(config["timeout_seconds"])
    cancel = cancel or threading.Event()
    report = {
        "schema": 1,
        "tool": "Boundary",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_fingerprint": fingerprint(config),
        "base_url": config["base_url"],
        "complete": False,
        "cases": [],
        "summary": {"pass": 0, "violation": 0, "review": 0, "inconclusive": 0},
        "requests": 0,
    }
    next_request = clock()

    def request(case, identity):
        nonlocal next_request
        while clock() < next_request:
            if cancel.is_set():
                raise InterruptedError("Auditoría cancelada.")
            sleep(min(0.1, next_request - clock()))
        if cancel.is_set():
            raise InterruptedError("Auditoría cancelada.")
        next_request = clock() + 1 / config["rate"]
        headers = dict(identity_headers[identity])
        if "body" in case:
            headers["Content-Type"] = "application/json"
        result = client.request(
            case["method"], build_url(config, case), headers, case.get("body", MISSING)
        )
        report["requests"] += 1
        return result

    try:
        for index, case in enumerate(config["cases"]):
            baseline_name = case["allow"][0]
            initial = request(case, baseline_name)
            results = {baseline_name: initial}
            for identity in config["identities"]:
                if identity != baseline_name:
                    results[identity] = request(case, identity)
            reference = baseline_identity(case, initial)
            stable = False
            if case["method"] in SAFE_METHODS and reference is not MISSING:
                repeated = request(case, baseline_name)
                repeated_reference = baseline_identity(case, repeated)
                stable = repeated_reference is not MISSING and reference == repeated_reference
            case_report = {
                "name": case["name"],
                "method": case["method"],
                "url": public_url(build_url(config, case)),
                "baseline_identity": baseline_name,
                "resource_reference_stable": stable,
                "results": [],
            }
            for identity, result in results.items():
                verdict, findings = evaluate(case, identity, result, reference, stable)
                reproduction = {
                    "method": case["method"],
                    "url": case_report["url"],
                    "headers": {
                        header: "<set from " + variable + ">"
                        for header, variable in config["identities"][identity]
                        .get("headers_env", {})
                        .items()
                    },
                    "body": "<omitted; use private configuration>" if "body" in case else None,
                }
                safe = {key: value for key, value in result.items() if key != "json"}
                case_report["results"].append(
                    {
                        "identity": identity,
                        "expected": "allow" if identity in case["allow"] else "deny",
                        "verdict": verdict,
                        "response": safe,
                        "findings": findings,
                        "request": reproduction,
                    }
                )
                report["summary"][verdict] += 1
            report["cases"].append(case_report)
            if progress:
                progress(index + 1, len(config["cases"]))
        report["complete"] = True
    except InterruptedError:
        report["cancelled"] = True
    return redact(report, secrets)
