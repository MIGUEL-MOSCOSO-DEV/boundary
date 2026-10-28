import copy
import json
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

from boundary.cli import atomic_json
from boundary.config import SAFE_METHODS, document, operations, validate
from boundary.engine import audit

from .charts import Bars, PermissionMatrix
from .design import (
    Button,
    Card,
    Empty,
    Inspector,
    Metric,
    Search,
    Shell,
    Table,
    column,
    confirm,
    initialize,
    label,
    row,
)
from .dialogs import IdentityDialog, PolicyDialog
from .reporting import read_report, write_html

ACCENT = "#F59E0B"


class Boundary(Shell):
    def __init__(self):
        super().__init__("Boundary", "Authorization Policy Lab", ACCENT, "shield")
        self.config = {
            "schema": 1,
            "base_url": "",
            "identities": {},
            "cases": [],
            "rate": 2,
            "timeout_seconds": 8,
            "allow_mutations": False,
        }
        self.credentials = {}
        self.operations = []
        self.report = None
        self.cancel = threading.Event()
        overview = self.add_page("Resumen", "dashboard")
        identities = self.add_page("Identidades", "users")
        policies = self.add_page("Políticas", "shield")
        resources = self.add_page("Recursos", "servers")
        matrix = self.add_page("Matriz de permisos", "grid")
        results = self.add_page("Resultados", "evidence")
        exports = self.add_page("Exportaciones", "report")
        settings = self.add_page("Configuración", "settings")
        self.header_actions.addWidget(Button("Abrir plan", self.load, "folder", ACCENT, quiet=True))
        self.run_button = Button("Auditar matriz", self.run, "play", ACCENT, True)
        self.header_actions.addWidget(self.run_button)
        base_card = Card()
        self.base = QLineEdit()
        self.base.setPlaceholderText("Origen HTTP(S) autorizado")
        base_card.box.addLayout(
            row(
                label("Origen autorizado", "muted"),
                self.base,
                Button("Importar OpenAPI", self.import_spec, "upload", ACCENT, quiet=True),
            )
        )
        self.authorized = QCheckBox(
            "Tengo autorización sobre el origen y las identidades de prueba"
        )
        base_card.box.addWidget(self.authorized)
        overview.addWidget(base_card)
        self.metrics = []
        metric_row = QHBoxLayout()
        for title, glyph in [
            ("Identidades configuradas", "users"),
            ("Recursos definidos", "servers"),
            ("Políticas existentes", "shield"),
            ("Casos ejecutados", "check"),
        ]:
            metric = Metric(title, glyph, ACCENT)
            metric_row.addWidget(metric)
            self.metrics.append(metric)
        overview.addLayout(metric_row)
        self.overview_content = QStackedWidget()
        overview.addWidget(self.overview_content, 1)
        self.overview_content.addWidget(
            Empty(
                "La autorización se demuestra",
                "Define identidades y políticas por recurso.\nCada resultado se compara con una expectativa explícita, no con una suposición.",
                "shield",
                ACCENT,
                "Crear identidad",
                self.identity,
            )
        )
        chart = Card(
            "Resultados por estado",
            "Sólo resultados observados. Los inconclusos y las revisiones permanecen visibles.",
        )
        self.result_bars = Bars(ACCENT, "evaluaciones")
        chart.box.addWidget(self.result_bars, 1)
        self.overview_content.addWidget(chart)
        self.identity_table = Table(
            ["Identidad", "Tipo", "Referencias de cabeceras", "Descripción"]
        )
        self.identity_table.setColumnWidth(0, 180)
        self.identity_table.setColumnWidth(1, 130)
        self.identity_table.setColumnWidth(2, 330)
        identities.addLayout(
            row(
                label("Sesiones de prueba", "section"),
                None,
                Button("Añadir identidad", self.identity, "plus", ACCENT, True),
            )
        )
        identities.addWidget(
            label(
                "Los valores secretos viven en memoria y no se incluyen en planes ni reportes.",
                "muted",
                True,
            )
        )
        identities.addWidget(self.identity_table, 1)
        identities.addLayout(
            row(Button("Editar seleccionada", self.edit_identity, "settings", ACCENT), None)
        )
        self.identity_table.activated.connect(self.edit_identity)
        policy_tools = QHBoxLayout()
        self.policy_search = Search("Buscar recurso o política…")
        policy_tools.addWidget(self.policy_search, 1)
        policy_tools.addWidget(Button("Nueva política", self.policy, "plus", ACCENT, True))
        policies.addLayout(policy_tools)
        self.policy_table = Table(["Política", "Método", "Ruta", "Permitidas", "Denegadas"])
        self.policy_table.setColumnWidth(0, 180)
        self.policy_table.setColumnWidth(2, 300)
        policies.addWidget(self.policy_table, 1)
        policies.addLayout(
            row(
                Button("Editar seleccionada", self.edit_policy, "settings", ACCENT),
                Button("Guardar plan", self.save, "download", ACCENT, quiet=True),
                None,
            )
        )
        self.policy_table.activated.connect(self.edit_policy)
        self.policy_search.textChanged.connect(self.filter_policies)
        self.resource_table = Table(["Recurso", "Método", "Parámetros definidos", "Política"])
        self.resource_table.setColumnWidth(0, 330)
        self.resource_table.setColumnWidth(2, 330)
        resources.addWidget(label("Recursos concretos del plan", "section"))
        resources.addWidget(
            label(
                "Los identificadores se proporcionan explícitamente; no se enumeran ni adivinan objetos.",
                "muted",
                True,
            )
        )
        resources.addWidget(self.resource_table, 1)
        matrix_toolbar = QHBoxLayout()
        matrix_toolbar.addWidget(label("Identidad × Recurso", "section"), 1)
        self.matrix_mode = QComboBox()
        self.matrix_mode.addItems(["Política esperada", "Evaluación observada"])
        self.matrix_mode.currentIndexChanged.connect(self.refresh_matrix)
        matrix_toolbar.addWidget(self.matrix_mode)
        matrix.addLayout(matrix_toolbar)
        self.matrix_stack = QStackedWidget()
        self.matrix_stack.addWidget(
            Empty(
                "Todavía no hay una matriz",
                "Añade una identidad y una política para visualizar los permisos esperados.\nDespués de auditar, podrás compararlos con la evaluación observada.",
                "grid",
                ACCENT,
                "Definir política",
                self.policy,
            )
        )
        matrix_split = QSplitter()
        self.matrix = PermissionMatrix()
        self.matrix_inspector = Inspector("Política y resultado")
        matrix_split.addWidget(self.matrix)
        matrix_split.addWidget(self.matrix_inspector)
        matrix_split.setSizes([760, 330])
        self.matrix.selected.connect(self.matrix_inspector.display)
        self.matrix_stack.addWidget(matrix_split)
        matrix.addWidget(self.matrix_stack, 1)
        result_toolbar = QHBoxLayout()
        self.result_search = Search("Buscar caso, identidad o regla…")
        self.verdict = QComboBox()
        self.verdict.addItems(
            ["Todos los resultados", "pass", "violation", "review", "inconclusive"]
        )
        result_toolbar.addWidget(self.result_search, 1)
        result_toolbar.addWidget(self.verdict)
        results.addLayout(result_toolbar)
        result_split = QSplitter()
        self.result_table = Table(
            ["Caso", "Identidad", "Esperado", "HTTP", "Resultado", "Reglas"], (4,)
        )
        for index, width in [(0, 170), (1, 135), (2, 100), (3, 70), (4, 130)]:
            self.result_table.setColumnWidth(index, width)
        self.result_inspector = Inspector("Reproducción redactada")
        result_split.addWidget(self.result_table)
        result_split.addWidget(self.result_inspector)
        result_split.setSizes([760, 330])
        self.result_table.selected.connect(self.result_inspector.display)
        results.addWidget(result_split, 1)
        self.result_search.textChanged.connect(self.filter_results)
        self.verdict.currentIndexChanged.connect(self.filter_results)
        export_card = Card(
            "Evidencia para revisión",
            "Los reportes omiten credenciales y cuerpos de respuesta. Conserva el plan privado si necesitas reproducir una solicitud con cuerpo.",
        )
        export_card.box.addLayout(
            row(
                Button("Abrir reporte JSON", self.open_report, "folder", ACCENT),
                Button("Exportar HTML", self.export, "download", ACCENT),
                None,
            )
        )
        exports.addWidget(export_card)
        self.export_details = QPlainTextEdit()
        self.export_details.setReadOnly(True)
        self.export_details.setPlaceholderText(
            "Después de una auditoría aparecerán fecha, origen, número de solicitudes y resumen de resultados."
        )
        exports.addWidget(self.export_details, 1)
        settings_tabs = QTabWidget()
        settings.addWidget(settings_tabs, 1)
        execution = QWidget()
        execution_box = column(execution, 18, 20)
        self.rate = QSpinBox()
        self.rate.setRange(1, 20)
        self.rate.setValue(2)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 30)
        self.timeout.setValue(8)
        execution_box.addLayout(
            row(
                label("Solicitudes por segundo", "muted"),
                self.rate,
                None,
                label("Timeout / segundos", "muted"),
                self.timeout,
            )
        )
        self.mutations = QCheckBox("El plan permite métodos que modifican datos")
        self.mutations.setToolTip(
            "Además de esta opción, cada ejecución con escritura requiere confirmación explícita."
        )
        execution_box.addWidget(self.mutations)
        execution_box.addWidget(
            label(
                "GET, HEAD y OPTIONS no necesitan habilitar escritura. No se siguen redirecciones y la validación TLS permanece activa.",
                "muted",
                True,
            )
        )
        execution_box.addStretch()
        settings_tabs.addTab(execution, "Ejecución")
        json_page = QWidget()
        json_box = column(json_page, 14, 20)
        self.plan_editor = QPlainTextEdit()
        json_box.addWidget(self.plan_editor, 1)
        json_box.addLayout(
            row(None, Button("Aplicar y validar JSON", self.apply_json, "check", ACCENT))
        )
        settings_tabs.addTab(json_page, "Plan JSON")
        self.shortcut("Ctrl+O", self.load)
        self.shortcut("Ctrl+S", self.save)
        self.shortcut("Ctrl+Return", self.run)
        self.refresh()
        self.show_page("Resumen")

    def current(self):
        config = copy.deepcopy(self.config)
        config["base_url"] = self.base.text().strip()
        config["rate"] = self.rate.value()
        config["timeout_seconds"] = self.timeout.value()
        config["allow_mutations"] = self.mutations.isChecked()
        return config

    def refresh(self):
        self.identity_table.fill(
            [
                (
                    [
                        name,
                        "Anónima" if data.get("anonymous") else "Autenticada",
                        ", ".join(
                            header + " ← " + variable
                            for header, variable in data.get("headers_env", {}).items()
                        ),
                        data.get("description", ""),
                    ],
                    {"name": name, "data": data},
                    {},
                )
                for name, data in self.config["identities"].items()
            ]
        )
        self.filter_policies()
        self.resource_table.fill(
            [
                (
                    [
                        case["path"],
                        case["method"],
                        json.dumps(case.get("path_params", {}), ensure_ascii=False),
                        case["name"],
                    ],
                    case,
                    {},
                )
                for case in self.config["cases"]
            ]
        )
        values = [
            len(self.config["identities"]),
            len(
                {
                    (
                        case["method"],
                        case["path"],
                        json.dumps(case.get("path_params", {}), sort_keys=True),
                    )
                    for case in self.config["cases"]
                }
            ),
            len(self.config["cases"]),
            len((self.report or {}).get("cases", [])),
        ]
        for index, (metric, value) in enumerate(zip(self.metrics, values)):
            metric.set(value, "Configurado en el plan" if index < 3 else "En el reporte actual")
        self.plan_editor.setPlainText(json.dumps(self.current(), ensure_ascii=False, indent=2))
        self.refresh_matrix()

    def filter_policies(self, *args):
        text = self.policy_search.text().casefold()
        self.policy_table.fill(
            [
                (
                    [
                        case["name"],
                        case["method"],
                        case["path"],
                        ", ".join(case["allow"]),
                        ", ".join(case["deny"]),
                    ],
                    case,
                    {},
                )
                for case in self.config["cases"]
                if text in json.dumps(case, ensure_ascii=False).casefold()
            ]
        )

    def identity(self):
        self.identity_dialog(None)

    def edit_identity(self, payload=None):
        value = (
            payload
            if isinstance(payload, dict)
            else self.identity_table.payload(self.identity_table.currentRow())
        )
        if value:
            self.identity_dialog(value["name"])
        else:
            self.notify("Selecciona una identidad para editarla.")

    def identity_dialog(self, name):
        if self.busy:
            return
        dialog = IdentityDialog(
            self, name, self.config["identities"].get(name), self.credentials.get(name)
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key, data, session = dialog.result_value
            new = key not in self.config["identities"]
            self.config["identities"][key] = data
            self.credentials[key] = session
            if new:
                for case in self.config["cases"]:
                    case["deny"].append(key)
            self.refresh()
            self.notify(
                "Identidad guardada. Los valores secretos no se persisten."
                + (
                    " Se añadió como denegada a las políticas existentes."
                    if new and self.config["cases"]
                    else ""
                )
            )

    def policy(self):
        self.policy_dialog(None)

    def edit_policy(self, payload=None):
        value = (
            payload
            if isinstance(payload, dict)
            else self.policy_table.payload(self.policy_table.currentRow())
        )
        if value:
            self.policy_dialog(value["name"])
        else:
            self.notify("Selecciona una política para editarla.")

    def policy_dialog(self, name):
        if self.busy:
            return
        if not self.config["identities"]:
            self.show_page("Identidades")
            self.notify("Define al menos una identidad antes de crear una política.")
            return
        index = next(
            (i for i, case in enumerate(self.config["cases"]) if case["name"] == name), None
        )
        old = self.config["cases"][index] if index is not None else None

        def check(value):
            candidate = self.current()
            if index is None:
                candidate["cases"].append(value)
            else:
                candidate["cases"][index] = value
            validate(candidate)

        dialog = PolicyDialog(self, list(self.config["identities"]), self.operations, old, check)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if index is None:
                self.config["cases"].append(dialog.result_value)
            else:
                self.config["cases"][index] = dialog.result_value
            self.refresh()
            self.notify("Política guardada y validada.")

    def import_spec(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar OpenAPI", "", "OpenAPI (*.json *.yaml *.yml)"
        )
        if path:
            try:
                self.operations = operations(path)
                self.notify(
                    f"{len(self.operations)} operaciones disponibles. No se enviaron solicitudes."
                )
                self.show_page("Políticas")
            except (ValueError, OSError, TypeError) as error:
                self.notify(str(error), True)

    def apply_config(self, value):
        self.config = validate(copy.deepcopy(value))
        self.credentials = {}
        self.base.setText(self.config["base_url"])
        self.rate.setValue(self.config["rate"])
        self.timeout.setValue(self.config["timeout_seconds"])
        self.mutations.setChecked(self.config["allow_mutations"])
        self.authorized.setChecked(False)
        self.refresh()

    def load(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir plan", "", "Planes (*.json *.yaml *.yml)"
        )
        if path:
            try:
                self.apply_config(document(path))
                self.workspace_label.setText(Path(path).stem)
                self.show_page("Resumen")
                self.notify("Plan cargado. Confirma origen y credenciales antes de ejecutar.")
            except (ValueError, OSError, TypeError, KeyError) as error:
                self.notify(str(error), True)

    def save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar plan sin credenciales", "", "JSON (*.json)"
        )
        if path:
            try:
                atomic_json(path, self.current())
                self.notify("Plan guardado sin valores de sesión.")
            except (OSError, ValueError) as error:
                self.notify(str(error), True)

    def apply_json(self):
        try:
            self.apply_config(json.loads(self.plan_editor.toPlainText()))
            self.notify("Plan validado. Se descartaron las credenciales de sesión anteriores.")
        except (ValueError, TypeError, KeyError) as error:
            self.notify(str(error), True)

    def run(self):
        if self.busy:
            return
        try:
            config = validate(self.current())
            if not self.authorized.isChecked():
                self.show_page("Resumen")
                raise ValueError("Confirma autorización sobre el origen y las identidades.")
            mutation = any(case["method"] not in SAFE_METHODS for case in config["cases"])
            if mutation and not config["allow_mutations"]:
                self.show_page("Configuración")
                raise ValueError(
                    "Este plan contiene escritura. Habilítala explícitamente antes de ejecutar."
                )
            allowed_mutations = False
            if mutation:
                allowed_mutations = confirm(
                    self,
                    "Métodos de escritura",
                    f"Este plan enviará solicitudes que pueden modificar datos en {config['base_url']}. No hay reversión automática. ¿Ejecutar los casos definidos?",
                    "Autorizar esta ejecución",
                )
                if not allowed_mutations:
                    return
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar reporte de auditoría", "", "JSON (*.json)"
            )
            if not path:
                return
            overrides = copy.deepcopy(self.credentials)
            self.cancel.clear()

            def operation(note):
                result = audit(
                    config,
                    authorized=True,
                    allow_mutations=allowed_mutations,
                    overrides=overrides,
                    cancel=self.cancel,
                    progress=lambda done, total: note(f"Progress {done}/{total}"),
                )
                atomic_json(path, result)
                return result

            self.task(
                "Auditando la política de autorización…", operation, self.finished, self.cancel.set
            )
        except (ValueError, TypeError, KeyError) as error:
            self.notify(str(error), True)

    def finished(self, report):
        self.render(report)
        self.show_page("Matriz de permisos")
        self.notify(
            "Auditoría finalizada. Conserva la evidencia y revisa los inconclusos."
            if report["complete"]
            else "Auditoría cancelada; se guardaron los casos completados."
        )

    def update_actions(self):
        self.run_button.setEnabled(not self.busy)

    def render(self, report):
        if report.get("tool") != "Boundary":
            raise ValueError("El reporte pertenece a otra herramienta.")
        self.report = report
        self.result_bars.set_values(
            [
                (name, report["summary"].get(name, 0))
                for name in ["pass", "violation", "review", "inconclusive"]
            ]
        )
        self.overview_content.setCurrentIndex(1)
        self.matrix_mode.setCurrentIndex(1)
        self.filter_results()
        self.export_details.setPlainText(
            json.dumps(
                {
                    key: report.get(key)
                    for key in [
                        "created_at",
                        "base_url",
                        "complete",
                        "requests",
                        "summary",
                        "config_fingerprint",
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        self.refresh()

    def refresh_matrix(self, *args):
        observed = self.matrix_mode.currentIndex() == 1
        present = (
            bool((self.report or {}).get("cases"))
            if observed and self.report
            else bool(self.config["cases"] and self.config["identities"])
        )
        self.matrix_stack.setCurrentIndex(1 if present else 0)
        self.matrix.set_context(self.config, self.report if observed else None, observed)

    def filter_results(self, *args):
        rows = []
        for case in (self.report or {}).get("cases", []):
            for result in case["results"]:
                payload = {
                    "case": case["name"],
                    "resource_reference_stable": case["resource_reference_stable"],
                    **result,
                }
                if (
                    self.result_search.text().casefold()
                    not in json.dumps(payload, ensure_ascii=False).casefold()
                ):
                    continue
                if (
                    self.verdict.currentIndex() > 0
                    and result["verdict"] != self.verdict.currentText()
                ):
                    continue
                rows.append(
                    (
                        [
                            case["name"],
                            result["identity"],
                            result["expected"],
                            result["response"]["status"],
                            result["verdict"],
                            ", ".join(f["rule"] for f in result["findings"]),
                        ],
                        payload,
                        {4: result["verdict"]},
                    )
                )
        self.result_table.fill(rows)

    def open_report(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir reporte", "", "JSON (*.json)")
        if path:
            try:
                self.render(read_report(path))
                self.workspace_label.setText(Path(path).stem)
                self.show_page("Resultados")
                self.notify("Reporte abierto con evidencia redactada.")
            except (ValueError, OSError, TypeError, KeyError) as error:
                self.notify(str(error), True)

    def export(self):
        if not self.report:
            self.notify("Primero abre o genera un reporte.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar HTML local", "", "HTML (*.html)")
        if path:
            try:
                write_html(self.report, path)
                self.notify("HTML exportado sin credenciales ni cuerpos de respuesta.")
            except OSError as error:
                self.notify(str(error), True)

    def closeEvent(self, event):
        if not self.busy:
            self.credentials.clear()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    initialize(app, ACCENT)
    window = Boundary()
    window.show()
    sys.exit(app.exec())
