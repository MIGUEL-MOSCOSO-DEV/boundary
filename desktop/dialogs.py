import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from boundary.config import ENV, HEADER, NAME

from .design import Button, column, label, row, scrollable, text_field


class IdentityDialog(QDialog):
    def __init__(self, parent, name=None, data=None, session=None):
        super().__init__(parent)
        self.setWindowTitle("Identidad de prueba")
        self.resize(690, 600)
        self.accent = parent.accent
        self.original = name
        self.data = data or {}
        self.session = session or {}
        self.result_value = None
        box = column(self, 18, 24)
        box.addWidget(label("Configurar identidad", "title"))
        box.addWidget(
            label("El plan guarda referencias a variables, no sus valores secretos.", "muted", True)
        )
        fields = QHBoxLayout()
        name_wrap, self.name = text_field("Nombre de identidad")
        description_wrap, self.description = text_field("Descripción")
        self.name.setText(name or "")
        self.name.setReadOnly(name is not None)
        self.description.setText(self.data.get("description", ""))
        fields.addWidget(name_wrap)
        fields.addWidget(description_wrap)
        box.addLayout(fields)
        self.anonymous = QCheckBox("Identidad anónima / sin credenciales")
        self.anonymous.setChecked(self.data.get("anonymous", False))
        box.addWidget(self.anonymous)
        self.headers = QTableWidget(0, 3)
        self.headers.setHorizontalHeaderLabels(
            ["Cabecera", "Variable de entorno", "Valor de esta sesión"]
        )
        self.headers.verticalHeader().hide()
        self.headers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.headers.setMinimumHeight(190)
        box.addWidget(self.headers, 1)
        for header, variable in self.data.get("headers_env", {}).items():
            self.add_header(header, variable, self.session.get(header, ""))
        if self.headers.rowCount() == 0:
            self.add_header("Authorization", "")
        actions = row(
            Button("Añadir cabecera", lambda: self.add_header(), "plus", self.accent, quiet=True),
            Button("Quitar seleccionada", self.remove_header, "close", self.accent, quiet=True),
            None,
        )
        box.addLayout(actions)
        self.anonymous.toggled.connect(lambda value: self.headers.setEnabled(not value))
        self.headers.setEnabled(not self.anonymous.isChecked())
        box.addWidget(
            label(
                "Los valores de sesión se mantienen únicamente en memoria y se muestran enmascarados. Puedes dejarlos vacíos para usar el entorno.",
                "muted",
                True,
            )
        )
        self.error = label("", "muted", True)
        self.error.setStyleSheet("color:#EF4444;")
        box.addWidget(self.error)
        box.addLayout(
            row(
                None,
                Button("Volver", self.reject, quiet=True),
                Button("Guardar identidad", self.save, "check", self.accent, True),
            )
        )

    def add_header(self, header="", variable="", secret=""):
        if self.headers.rowCount() >= 10:
            self.error.setText("Se admiten hasta diez cabeceras.")
            return
        row_index = self.headers.rowCount()
        self.headers.insertRow(row_index)
        self.headers.setItem(row_index, 0, QTableWidgetItem(header))
        self.headers.setItem(row_index, 1, QTableWidgetItem(variable))
        entry = QLineEdit()
        entry.setEchoMode(QLineEdit.EchoMode.Password)
        entry.setText(secret)
        entry.setPlaceholderText("Sólo esta sesión")
        self.headers.setCellWidget(row_index, 2, entry)
        self.headers.setRowHeight(row_index, 46)

    def remove_header(self):
        index = self.headers.currentRow()
        if index >= 0:
            self.headers.removeRow(index)

    def save(self):
        try:
            name = self.name.text().strip()
            if not NAME.fullmatch(name):
                raise ValueError(
                    "El nombre debe empezar por una letra y usar letras, números, guiones o guiones bajos."
                )
            headers, session = {}, {}
            if not self.anonymous.isChecked():
                for index in range(self.headers.rowCount()):
                    header = (
                        self.headers.item(index, 0).text() if self.headers.item(index, 0) else ""
                    ).strip()
                    variable = (
                        self.headers.item(index, 1).text() if self.headers.item(index, 1) else ""
                    ).strip()
                    if not HEADER.fullmatch(header) or not ENV.fullmatch(variable):
                        raise ValueError(
                            "Define nombres válidos para la cabecera y su variable de entorno."
                        )
                    if header.lower() in {
                        "host",
                        "content-length",
                        "connection",
                        "transfer-encoding",
                        "proxy-authorization",
                        "accept-encoding",
                    } or header.lower() in {key.lower() for key in headers}:
                        raise ValueError("Cabecera reservada o repetida.")
                    headers[header] = variable
                    secret = self.headers.cellWidget(index, 2).text()
                    if secret:
                        if not 4 <= len(secret) <= 8192 or "\r" in secret or "\n" in secret:
                            raise ValueError(
                                "Revisa longitud y saltos de línea del valor de sesión."
                            )
                        session[header] = secret
                if not headers:
                    raise ValueError("Añade una cabecera o utiliza una identidad anónima.")
            self.result_value = (
                name,
                {
                    "anonymous": self.anonymous.isChecked(),
                    "description": self.description.text().strip(),
                    "headers_env": headers,
                },
                session,
            )
            self.accept()
        except ValueError as error:
            self.error.setText(str(error))


class PolicyDialog(QDialog):
    def __init__(self, parent, identities, operations, value=None, validate_case=None):
        super().__init__(parent)
        self.setWindowTitle("Política de acceso al recurso")
        self.resize(780, 730)
        self.accent = parent.accent
        self.value = value or {}
        self.identities = identities
        self.operations = operations
        self.validate_case = validate_case
        self.result_value = None
        outer = column(self, 18, 24)
        outer.addWidget(label("Una política comprobable", "title"))
        outer.addWidget(
            label(
                "Define un recurso concreto y las identidades que deberían tener acceso.",
                "muted",
                True,
            )
        )
        tabs = QTabWidget()
        outer.addWidget(tabs, 1)
        basic = QWidget()
        box = column(basic, 14, 18)
        self.operation = QComboBox()
        self.operation.addItem("Seleccionar operación importada")
        self.operation.addItems([op["method"] + " " + op["path"] for op in operations])
        box.addWidget(label("Operación de OpenAPI", "muted"))
        box.addWidget(self.operation)
        self.inputs = {}
        for key, title, default in [
            ("name", "Nombre único", self.value.get("name", "")),
            ("path", "Ruta", self.value.get("path", "")),
            (
                "path_params",
                "Parámetros de ruta / JSON",
                json.dumps(self.value.get("path_params", {})),
            ),
            ("query", "Parámetros query / JSON", json.dumps(self.value.get("query", {}))),
        ]:
            holder, entry = text_field(title)
            entry.setText(default)
            self.inputs[key] = entry
            box.addWidget(holder)
        self.method = QComboBox()
        self.method.addItems(["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
        self.method.setCurrentText(self.value.get("method", "GET"))
        box.addLayout(row(label("Método", "muted"), self.method, None))
        tabs.addTab(scrollable(basic), "Recurso")
        access = QWidget()
        access_box = column(access, 14, 18)
        access_box.addWidget(label("Identidades permitidas", "section"))
        access_box.addWidget(
            label("Las identidades que no marques se evalúan como denegadas.", "muted", True)
        )
        self.allow = QListWidget()
        for name in identities:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if name in self.value.get("allow", [])
                else Qt.CheckState.Unchecked
            )
            self.allow.addItem(item)
        access_box.addWidget(self.allow, 1)
        tabs.addTab(access, "Acceso esperado")
        assertions = QWidget()
        assertions_box = column(assertions, 14, 18)
        for key, title, default in [
            (
                "resource_pointer",
                "JSON Pointer del identificador del recurso",
                self.value.get("resource_pointer", ""),
            ),
            (
                "resource_value",
                "Valor esperado opcional / literal JSON",
                json.dumps(self.value["resource_value"]) if "resource_value" in self.value else "",
            ),
            (
                "forbidden_fields",
                "Campos prohibidos por identidad / JSON",
                json.dumps(self.value.get("forbidden_fields", {})),
            ),
            (
                "deny_statuses",
                "Estados aceptados como denegación",
                ", ".join(map(str, self.value.get("deny_statuses", [401, 403, 404]))),
            ),
        ]:
            holder, entry = text_field(title)
            entry.setText(default)
            self.inputs[key] = entry
            assertions_box.addWidget(holder)
        assertions_box.addWidget(
            label(
                "Para confirmar acceso indebido, el motor necesita una referencia de recurso estable. Un 2xx aislado se marca para revisión.",
                "muted",
                True,
            )
        )
        assertions_box.addStretch()
        tabs.addTab(assertions, "Afirmaciones")
        body_page = QWidget()
        body_box = column(body_page, 12, 18)
        body_box.addWidget(label("Cuerpo de solicitud JSON", "section"))
        body_box.addWidget(
            label(
                "Sólo para métodos de escritura. El cuerpo no se incluye en el reporte.",
                "muted",
                True,
            )
        )
        self.body = QPlainTextEdit()
        self.body.setPlainText(
            json.dumps(self.value["body"], indent=2) if "body" in self.value else ""
        )
        body_box.addWidget(self.body, 1)
        tabs.addTab(body_page, "Cuerpo opcional")
        self.operation.currentIndexChanged.connect(self.choose_operation)
        self.error = label("", "muted", True)
        self.error.setStyleSheet("color:#EF4444;")
        outer.addWidget(self.error)
        outer.addLayout(
            row(
                None,
                Button("Volver", self.reject, quiet=True),
                Button("Guardar política", self.save, "check", self.accent, True),
            )
        )

    def choose_operation(self, index):
        if index > 0:
            operation = self.operations[index - 1]
            self.method.setCurrentText(operation["method"])
            self.inputs["path"].setText(operation["path"])
            self.inputs["path_params"].setText(
                json.dumps({name: "" for name in operation["parameters"]})
            )

    def save(self):
        try:
            allowed = [
                self.allow.item(i).text()
                for i in range(self.allow.count())
                if self.allow.item(i).checkState() == Qt.CheckState.Checked
            ]
            value = {
                "name": self.inputs["name"].text().strip(),
                "method": self.method.currentText(),
                "path": self.inputs["path"].text().strip(),
                "path_params": json.loads(self.inputs["path_params"].text()),
                "query": json.loads(self.inputs["query"].text()),
                "allow": allowed,
                "deny": [name for name in self.identities if name not in allowed],
                "forbidden_fields": json.loads(self.inputs["forbidden_fields"].text()),
                "deny_statuses": [
                    int(item.strip()) for item in self.inputs["deny_statuses"].text().split(",")
                ],
            }
            if self.inputs["resource_pointer"].text():
                value["resource_pointer"] = self.inputs["resource_pointer"].text()
            if self.inputs["resource_value"].text():
                value["resource_value"] = json.loads(self.inputs["resource_value"].text())
            if self.body.toPlainText().strip():
                value["body"] = json.loads(self.body.toPlainText())
            if self.validate_case:
                self.validate_case(value)
            self.result_value = value
            self.accept()
        except (ValueError, TypeError, KeyError) as error:
            self.error.setText(str(error))
