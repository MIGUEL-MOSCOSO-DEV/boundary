import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import yaml

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
METHODS = SAFE_METHODS | {"POST", "PUT", "PATCH", "DELETE"}
NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
HEADER = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_|~-]+$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def document(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("El documento supera 2 MB.")
    try:
        with path.open(encoding="utf-8-sig") as file:
            result = (
                yaml.safe_load(file)
                if path.suffix.lower() in {".yaml", ".yml"}
                else json.load(file)
            )
    except (yaml.YAMLError, ValueError, RecursionError):
        raise ValueError("No se pudo interpretar el documento JSON o YAML.") from None
    if not isinstance(result, dict):
        raise ValueError("Se esperaba un objeto JSON o YAML.")
    return result


def operations(path):
    spec = document(path)
    if not str(spec.get("openapi", "")).startswith("3."):
        raise ValueError("Se requiere OpenAPI 3.x.")
    result = []
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("paths no es un objeto.")
    for route, item in paths.items():
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or not isinstance(item, dict)
            or "$ref" in item
        ):
            continue
        for method, operation in item.items():
            if method.upper() not in METHODS or not isinstance(operation, dict):
                continue
            result.append(
                {
                    "method": method.upper(),
                    "path": route,
                    "operation_id": operation.get("operationId", ""),
                    "summary": str(operation.get("summary", ""))[:200],
                    "parameters": re.findall(r"\{([^{}]+)\}", route),
                }
            )
    if len(result) > 5000:
        raise ValueError("El documento supera 5000 operaciones.")
    return result


def origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url debe ser HTTP(S), sin credenciales, query ni fragmento.")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Puerto inválido.") from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Puerto inválido.")
    if any(character in value for character in "\r\n\\"):
        raise ValueError("URL inválida.")
    return parsed


def validate(config):
    allowed = {
        "schema",
        "base_url",
        "identities",
        "cases",
        "rate",
        "timeout_seconds",
        "allow_mutations",
    }
    if set(config) - allowed:
        raise ValueError("Hay opciones de configuración desconocidas.")
    if config.get("schema") != 1:
        raise ValueError("schema debe ser 1.")
    origin(config.get("base_url", ""))
    identities = config.get("identities", {})
    if not isinstance(identities, dict) or not 1 <= len(identities) <= 16:
        raise ValueError("Define de 1 a 16 identidades.")
    for name, identity in identities.items():
        if (
            not isinstance(name, str)
            or not NAME.fullmatch(name)
            or not isinstance(identity, dict)
            or set(identity) - {"headers_env", "anonymous", "description"}
        ):
            raise ValueError("Identidad inválida.")
        headers = identity.get("headers_env", {})
        if not isinstance(headers, dict) or len(headers) > 10:
            raise ValueError("headers_env debe ser un objeto de hasta 10 cabeceras.")
        if identity.get("anonymous") and headers:
            raise ValueError("Una identidad anónima no lleva credenciales.")
        if not identity.get("anonymous") and not headers:
            raise ValueError("Las identidades autenticadas necesitan headers_env.")
        for header, variable in headers.items():
            if (
                not HEADER.fullmatch(header)
                or header.lower()
                in {
                    "host",
                    "content-length",
                    "connection",
                    "transfer-encoding",
                    "proxy-authorization",
                    "accept-encoding",
                }
                or not isinstance(variable, str)
                or not ENV.fullmatch(variable)
            ):
                raise ValueError("Cabecera o variable de entorno inválida.")
    cases = config.get("cases", [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("Define de 1 a 200 casos con sus reglas de acceso.")
    names = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) - {
            "name",
            "method",
            "path",
            "path_params",
            "query",
            "allow",
            "deny",
            "resource_pointer",
            "resource_value",
            "forbidden_fields",
            "body",
            "deny_statuses",
        }:
            raise ValueError("Caso u opciones desconocidos.")
        name = case.get("name", "")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in names:
            raise ValueError("Cada caso necesita un nombre único.")
        names.add(name)
        method = case.get("method", "").upper()
        if method not in METHODS:
            raise ValueError("Método HTTP no admitido.")
        case["method"] = method
        route = case.get("path", "")
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or route.startswith("//")
            or any(ch in route for ch in "?#\r\n\\")
            or ".." in route.split("/")
        ):
            raise ValueError("La ruta debe ser relativa al origen y no incluir query.")
        params = case.get("path_params", {})
        if not isinstance(params, dict) or set(re.findall(r"\{([^{}]+)\}", route)) != set(params):
            raise ValueError("Define exactamente todos los parámetros de ruta.")
        if not all(
            isinstance(v, (str, int))
            and not isinstance(v, bool)
            and len(str(v)) <= 500
            and str(v) not in {".", ".."}
            for v in params.values()
        ):
            raise ValueError("Valor de parámetro no admitido.")
        query = case.get("query", {})
        if (
            not isinstance(query, dict)
            or len(query) > 30
            or not all(
                isinstance(k, str) and isinstance(v, (str, int)) and len(str(v)) <= 1000
                for k, v in query.items()
            )
        ):
            raise ValueError("query debe ser un objeto simple de hasta 30 parámetros.")
        allow, deny = case.get("allow", []), case.get("deny", [])
        if (
            not isinstance(allow, list)
            or not isinstance(deny, list)
            or not all(isinstance(v, str) for v in allow + deny)
            or not allow
            or len(set(allow + deny)) != len(allow + deny)
            or set(allow + deny) != set(identities)
        ):
            raise ValueError(
                "Cada identidad debe aparecer una vez en allow o deny; al menos una debe tener acceso."
            )
        pointer = case.get("resource_pointer", "")
        if pointer and (
            not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 300
        ):
            raise ValueError("resource_pointer debe ser un JSON Pointer.")
        forbidden = case.get("forbidden_fields", {})
        if not isinstance(forbidden, dict) or set(forbidden) - set(identities):
            raise ValueError("forbidden_fields debe usar identidades conocidas.")
        for pointers in forbidden.values():
            if (
                not isinstance(pointers, list)
                or len(pointers) > 50
                or not all(
                    isinstance(p, str) and p.startswith("/") and len(p) <= 300 for p in pointers
                )
            ):
                raise ValueError("Define hasta 50 JSON Pointers por identidad.")
        statuses = case.get("deny_statuses", [401, 403, 404])
        if (
            not isinstance(statuses, list)
            or not statuses
            or not all(type(s) is int and 400 <= s <= 499 for s in statuses)
        ):
            raise ValueError("deny_statuses solo admite estados 4xx.")
        if "body" in case and len(json.dumps(case["body"], allow_nan=False).encode()) > 65536:
            raise ValueError("El body del caso supera 64 KB.")
        if method in SAFE_METHODS and "body" in case:
            raise ValueError("No se envían cuerpos en GET, HEAD u OPTIONS.")
    rate = config.setdefault("rate", 2)
    timeout = config.setdefault("timeout_seconds", 8)
    if (
        type(rate) is not int
        or not 1 <= rate <= 20
        or type(timeout) is not int
        or not 1 <= timeout <= 30
    ):
        raise ValueError("rate debe ir de 1 a 20 y timeout_seconds de 1 a 30.")
    if not isinstance(config.setdefault("allow_mutations", False), bool):
        raise ValueError("allow_mutations debe ser booleano.")
    return config


def fingerprint(config):
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def build_url(config, case):
    route = case["path"]
    for name, value in case.get("path_params", {}).items():
        route = route.replace("{" + name + "}", quote(str(value), safe=""))
    from urllib.parse import urlencode

    result = config["base_url"].rstrip("/") + route
    if case.get("query"):
        result += "?" + urlencode(case["query"])
    if origin(result.split("?", 1)[0]).netloc != origin(config["base_url"]).netloc:
        raise ValueError("La solicitud sale del origen autorizado.")
    return result
