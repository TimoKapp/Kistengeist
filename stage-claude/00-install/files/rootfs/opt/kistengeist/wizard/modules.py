#!/usr/bin/env python3
"""Modulverwaltung für Kistengeist.

Liest die module.conf-Dateien, prüft eine Auswahl und erzeugt den
Installationsplan. Wird vom Setup-Assistenten und vom Installer genutzt,
damit beide dieselbe Logik verwenden.

Aufruf:
  modules.py plan --modules-dir DIR --setup /etc/kistengeist/setup.conf
  modules.py list --modules-dir DIR
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field

MODES = ("desktop", "rdp", "both")


class PlanError(ValueError):
    """Ungültige Modulauswahl."""


@dataclass
class Module:
    id: str
    name: str
    description: str = ""
    group: str = "Werkzeuge"
    order: int = 50
    required: bool = False
    default: bool = False
    depends: list[str] = field(default_factory=list)
    modes: list[str] = field(default_factory=lambda: list(MODES))
    note: str = ""

    def supports(self, mode: str) -> bool:
        return mode in self.modes


def parse_conf(text: str) -> dict[str, str]:
    """Liest KEY=Wert-Zeilen (Werte optional in Anführungszeichen)."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_modules(modules_dir: str) -> dict[str, Module]:
    modules: dict[str, Module] = {}
    for entry in sorted(os.listdir(modules_dir)):
        conf_path = os.path.join(modules_dir, entry, "module.conf")
        if not os.path.isfile(conf_path):
            continue
        with open(conf_path, encoding="utf-8") as fh:
            conf = parse_conf(fh.read())
        modes = conf.get("MODES", " ".join(MODES)).split()
        unknown = [m for m in modes if m not in MODES]
        if unknown:
            raise PlanError(f"Modul {entry}: unbekannter Modus {unknown}")
        modules[entry] = Module(
            id=entry,
            name=conf.get("NAME", entry),
            description=conf.get("DESCRIPTION", ""),
            group=conf.get("GROUP", "Werkzeuge"),
            order=int(conf.get("ORDER", "50")),
            required=conf.get("REQUIRED", "no") == "yes",
            default=conf.get("DEFAULT", "off") == "on",
            depends=conf.get("DEPENDS", "").split(),
            modes=modes,
            note=conf.get("NOTE", ""),
        )
    for mod in modules.values():
        for dep in mod.depends:
            if dep not in modules:
                raise PlanError(f"Modul {mod.id} braucht unbekanntes Modul {dep}")
    return modules


def plan(modules: dict[str, Module], mode: str, selected: list[str]) -> list[str]:
    """Liefert die Module in Installationsreihenfolge."""
    if mode not in MODES:
        raise PlanError(f"Unbekannte Zugangsart: {mode!r}")
    unknown = [m for m in selected if m not in modules]
    if unknown:
        raise PlanError(f"Unbekannte Module: {', '.join(unknown)}")

    wanted = {m.id for m in modules.values() if m.required and m.supports(mode)}
    wanted.update(m for m in selected if modules[m].supports(mode))

    stack = list(wanted)
    while stack:
        current = modules[stack.pop()]
        for dep in current.depends:
            if not modules[dep].supports(mode):
                raise PlanError(
                    f"{current.name} braucht {modules[dep].name}, "
                    f"das in dieser Zugangsart nicht verfügbar ist"
                )
            if dep not in wanted:
                wanted.add(dep)
                stack.append(dep)

    return sorted(wanted, key=lambda mid: (modules[mid].order, mid))


def read_setup(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return parse_conf(fh.read())


def module_list(modules: dict[str, Module]) -> list[dict]:
    ordered = sorted(modules.values(), key=lambda m: (m.order, m.id))
    return [asdict(m) for m in ordered]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "list"))
    parser.add_argument("--modules-dir", default="/opt/kistengeist/modules")
    parser.add_argument("--setup", default="/etc/kistengeist/setup.conf")
    args = parser.parse_args(argv)

    try:
        modules = load_modules(args.modules_dir)
        if args.command == "list":
            print(json.dumps(module_list(modules), ensure_ascii=False, indent=2))
            return 0
        setup = read_setup(args.setup)
        result = plan(modules, setup.get("MODE", ""), setup.get("MODULES", "").split())
    except (PlanError, OSError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    print("\n".join(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
