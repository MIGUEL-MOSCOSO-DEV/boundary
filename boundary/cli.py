import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .config import document, operations, validate
from .engine import audit


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".boundary-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Boundary · auditoría de autorización basada en políticas"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser(
        "operations", help="Listar operaciones de un OpenAPI sin enviar solicitudes"
    )
    inspect.add_argument("spec", type=Path)
    check = sub.add_parser("check", help="Validar un plan sin enviar solicitudes")
    check.add_argument("config", type=Path)
    execute = sub.add_parser("audit", help="Ejecutar la matriz autorizada")
    execute.add_argument("config", type=Path)
    execute.add_argument("--out", type=Path, required=True)
    execute.add_argument("--authorized", action="store_true")
    execute.add_argument("--allow-mutations", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "operations":
            print(json.dumps(operations(args.spec), ensure_ascii=False, indent=2))
        elif args.command == "check":
            plan = validate(document(args.config))
            print(
                json.dumps(
                    {
                        "valid": True,
                        "cases": len(plan["cases"]),
                        "identities": len(plan["identities"]),
                        "network_activity": False,
                    }
                )
            )
        else:
            if args.out.resolve() == args.config.resolve():
                raise ValueError("La salida no puede sobrescribir la configuración.")
            result = audit(
                document(args.config),
                authorized=args.authorized,
                allow_mutations=args.allow_mutations,
                progress=lambda done, total: print(f"Progress {done}/{total}", file=sys.stderr),
            )
            atomic_json(args.out, result)
            print(json.dumps(result["summary"], ensure_ascii=False))
            return (
                2
                if not result["complete"]
                else 1
                if result["summary"]["violation"]
                else 3
                if result["summary"]["review"] or result["summary"]["inconclusive"]
                else 0
            )
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print("Boundary: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
