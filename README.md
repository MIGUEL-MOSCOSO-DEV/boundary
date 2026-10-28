# Boundary

Auditoría de autorización de APIs mediante identidades, políticas y evidencia redactada.

[![CI](https://github.com/MIGUEL-MOSCOSO-DEV/boundary/actions/workflows/ci.yml/badge.svg)](https://github.com/MIGUEL-MOSCOSO-DEV/boundary/actions/workflows/ci.yml) · [Descargas](https://github.com/MIGUEL-MOSCOSO-DEV/boundary/releases/latest) · [MIT](LICENSE)

![Interfaz de Boundary](docs/overview.png)

## Qué incluye

- Identidades con cabeceras leídas desde variables de entorno o valores temporales en memoria.
- Políticas explícitas de acceso por operación y matriz de permisos.
- Importación local de operaciones OpenAPI 3, sin inferir permisos.
- Comparación de recursos mediante JSON Pointer y detección de campos prohibidos.
- Credenciales redactadas y cuerpos de respuesta excluidos del informe.

GET, HEAD y OPTIONS son el comportamiento predeterminado. Las mutaciones requieren habilitación en el plan y autorización adicional por ejecución. Los resultados distinguen violaciones, revisión e inconclusos.

## Windows

Descarga **Boundary-windows-x64.zip**, extrae todo el contenido y abre **Boundary/Boundary.exe**. La carpeta `_internal` debe permanecer junto al ejecutable. No requiere Python ni instalación. Compatible con Windows 10/11 de 64 bits.

El ejecutable **boundary-cli.exe** permite trabajar desde terminal. Ejecuta `--help` para consultar sus opciones. Los archivos SHA256SUMS permiten verificar las descargas.

La aplicación inicia sin proyectos, objetivos, credenciales ni datos precargados. Los planes e informes se guardan localmente, en las rutas que selecciones.

## Desarrollo

Requiere Python 3.11 o posterior. Desde la raíz del repositorio:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python launch.py
```

Para generar la distribución en un entorno virtual limpio:

```text
.venv\Scripts\python tools/build_windows.py
```

El proceso compila la interfaz y el CLI, comprueba las dependencias nativas Qt, crea el ZIP y calcula sus hashes. Excluye la copia de ICU encontrada en PATH para que Qt utilice la API nativa de Windows. No copies DLL de otras instalaciones de Qt a `_internal`.

## Verificación

```text
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

La CI ejecuta las pruebas en Windows y Linux y genera el paquete Windows. Las pruebas usan recursos locales controlados; no auditan sistemas externos. La interfaz utiliza Qt/PySide6 y los motores funcionan de forma independiente.

## Uso responsable

Trabaja únicamente sobre sistemas e identidades para los que tengas autorización explícita. Revisa el alcance y las políticas antes de ejecutar. Conserva los informes como información sensible.

## Licencia

Código MIT. Las bibliotecas Qt se distribuyen de forma dinámica bajo su licencia correspondiente; consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) y la carpeta [licenses](licenses).
