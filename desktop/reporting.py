import html
import json
import os
import tempfile
from pathlib import Path

CSS = """body{margin:0;background:#0b1018;color:#e6edf6;font:15px system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:48px 28px}header{border-bottom:1px solid #2a3a4e;padding-bottom:24px}small{color:#99aabd;letter-spacing:.12em}h1{font-size:44px;letter-spacing:-.04em;margin:12px 0}p{line-height:1.6;color:#b6c5d6}.cards{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.card{background:#142131;border:1px solid #26394f;padding:20px;min-width:140px}.card strong{display:block;font:32px ui-monospace,monospace;margin-bottom:8px}section{margin:32px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:#a4b6ca;font:11px ui-monospace,monospace;letter-spacing:.08em}td,th{padding:14px;border-bottom:1px solid #26394f;vertical-align:top}td{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#111b28;padding:20px;line-height:1.6;color:#c7d8e9}details{margin:10px 0;background:#111b28;padding:16px}summary{cursor:pointer}a{color:#80d9d2}.tag{font-family:ui-monospace,monospace;color:#80d9d2}.notice{border-left:3px solid #e3b26e;padding:12px 18px;background:#211f1b}.footer{margin-top:48px;color:#99aabd;font-size:12px}@media print{body{background:#fff;color:#111}p,small,th{color:#333}pre,details,.card{background:#f2f4f6;color:#111}details{break-inside:avoid}header{border-color:#aaa}}"""


def esc(value):
    if value is None:
        value = "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return html.escape(str(value), quote=True)


def table(headers, rows):
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join("<th>" + esc(item) + "</th>" for item in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + esc(cell) + "</td>" for cell in row) + "</tr>" for row in rows
        )
        + "</tbody></table></div>"
    )


def render(report):
    tool = report.get("tool", "")
    if report.get("schema") != 1 or tool not in {"ScopeForge", "TraceHound", "Boundary"}:
        raise ValueError("Reporte no compatible.")
    cards = []
    sections = []
    if tool == "ScopeForge":
        assets = report.get("assets", [])
        cards = [
            ("Objetivos", len(assets)),
            ("Completados", sum(a["outcome"] == "complete" for a in assets)),
            ("Bloqueados", sum(a["outcome"] == "blocked" for a in assets)),
            ("Cambios", len(report.get("changes", []))),
        ]
        rows = []
        for asset in assets:
            last = (asset.get("visits") or [{}])[-1]
            rows.append(
                (
                    asset["target"],
                    asset["outcome"],
                    last.get("status"),
                    ", ".join(last.get("addresses", [])),
                    asset.get("error") or last.get("title", ""),
                )
            )
        sections.append(
            "<h2>Inventario</h2>"
            + table(["Objetivo", "Resultado", "HTTP", "Direcciones", "Evidencia"], rows)
        )
        sections.append(
            "<h2>Cambios respecto a la referencia</h2>"
            + table(
                ["Objetivo", "Cambio", "Campos"],
                [(c["target"], c["kind"], c["fields"]) for c in report.get("changes", [])],
            )
        )
        sections.append(
            "<h2>Detalle técnico</h2>"
            + "".join(
                "<details><summary>"
                + esc(a["target"])
                + "</summary><pre>"
                + esc(json.dumps(a, ensure_ascii=False, indent=2))
                + "</pre></details>"
                for a in assets
            )
        )
    elif tool == "TraceHound":
        coverage = report.get("coverage", {})
        cards = [
            ("Paquetes", coverage.get("packets", 0)),
            ("Flujos", len(report.get("flows", []))),
            ("Alertas", len(report.get("alerts", []))),
            (
                "Paquetes no interpretados",
                coverage.get("malformed", 0)
                + coverage.get("unsupported", 0)
                + coverage.get("fragments", 0),
            ),
        ]
        sections.append(
            "<h2>Alertas y evidencia</h2>"
            + "".join(
                '<details open><summary><span class="tag">'
                + esc(a["severity"].upper())
                + "</span> / "
                + esc(a["rule"])
                + "</summary><p>"
                + esc(a["subject"])
                + " · "
                + esc(a["summary"])
                + "</p><pre>"
                + esc(json.dumps(a["evidence"], ensure_ascii=False, indent=2))
                + "</pre></details>"
                for a in report.get("alerts", [])
            )
        )
        sections.append(
            "<h2>Flujos observados</h2>"
            + table(
                ["Protocolo", "A", "B", "Paquetes", "Bytes", "Huecos / solapes"],
                [
                    (
                        f["protocol"],
                        f["a"],
                        f["b"],
                        f["packets"],
                        f["bytes"],
                        str(f["gaps"]) + " / " + str(f["conflicting_overlaps"]),
                    )
                    for f in report.get("flows", [])
                ],
            )
        )
        sections.append(
            "<h2>Cobertura</h2><pre>"
            + esc(json.dumps(coverage, ensure_ascii=False, indent=2))
            + "</pre>"
        )
    else:
        summary = report.get("summary", {})
        cards = [
            ("Correctos", summary.get("pass", 0)),
            ("Violaciones", summary.get("violation", 0)),
            ("Revisar", summary.get("review", 0)),
            ("Inconclusos", summary.get("inconclusive", 0)),
        ]
        rows = []
        for case in report.get("cases", []):
            for result in case["results"]:
                rows.append(
                    (
                        case["name"],
                        result["identity"],
                        result["expected"],
                        result["response"]["status"],
                        result["verdict"],
                        ", ".join(f["rule"] for f in result["findings"]),
                    )
                )
        sections.append(
            "<h2>Matriz de autorización</h2>"
            + table(["Caso", "Identidad", "Política", "HTTP", "Resultado", "Reglas"], rows)
        )
        sections.append(
            "<h2>Evidencia y reproducción redactada</h2>"
            + "".join(
                "<details><summary>"
                + esc(c["name"])
                + " / "
                + esc(c["method"])
                + " "
                + esc(c["url"])
                + "</summary><pre>"
                + esc(json.dumps(c, ensure_ascii=False, indent=2))
                + "</pre></details>"
                for c in report.get("cases", [])
            )
        )
    notice = (
        "Ejecución completa."
        if report.get("complete")
        else "Ejecución parcial: revisa cobertura, límites y errores antes de interpretar resultados."
    )
    return (
        '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'"><title>'
        + esc(tool)
        + " / Reporte</title><style>"
        + CSS
        + "</style><main><header><small>SECURITY OPERATIONS / OFFLINE REPORT</small><h1>"
        + esc(tool)
        + "</h1><p>"
        + esc(report.get("created_at", ""))
        + '</p></header><p class="notice">'
        + esc(notice)
        + '</p><div class="cards">'
        + "".join(
            '<div class="card"><strong>' + esc(value) + "</strong>" + esc(label) + "</div>"
            for label, value in cards
        )
        + "</div>"
        + "".join("<section>" + s + "</section>" for s in sections)
        + '<p class="footer">Reporte local · Sin recursos externos · Los hallazgos requieren interpretación dentro del alcance y la política definidos.</p></main></html>'
    )


def write_html(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(render(report))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_report(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("El reporte supera 64 MB.")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("schema") != 1:
        raise ValueError("Reporte no compatible.")
    return result
