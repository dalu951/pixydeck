#!/usr/bin/env python3
"""Regenerate the AUTO-GENERATED sections of the documentation.

Sources of truth:
  pyproject.toml           commands, optional extras, dependencies
  pixydeck.backend         CLI_COMMANDS
  pixydeck.gui             SHORTCUTS
  install.sh / deploy/     files the installer puts on the system

Usage: python tools/gen_docs.py [--check]
--check exits non-zero if a document is out of date (used in CI).
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pixydeck.backend import CLI_COMMANDS  # noqa: E402
from pixydeck.gui import SHORTCUTS  # noqa: E402

PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def cli_reference() -> str:
    rows = [(f"`pixydeck-cli {name}{' ' + value if value else ''}`".replace("|", "\\|"), description)
            for name, (value, description) in CLI_COMMANDS.items()]
    return ("`pixydeck-cli` is on your `PATH` with the .deb and AUR packages; after `./install.sh` "
            "it is `~/.local/share/pixydeck/venv/bin/pixydeck-cli`.\n\n"
            + table(("Command", "Description"), rows))


def shortcut_reference() -> str:
    def keys(entry):
        names = entry[0]
        if len(names) == 4 and names[0] == "Left":
            return "Arrow keys"
        if len(names) == 4 and names[0].endswith("1"):
            return f"`{names[0]}`–`{names[-1]}`"
        return " / ".join(f"`{n}`" for n in names)
    rows = [(keys(entry), entry[1]) for entry in SHORTCUTS]
    rows.insert(3, ("Mouse wheel on the preview", "Zoom"))
    return table(("Key", "Action"), rows)


def command_reference() -> str:
    project = PYPROJECT["project"]
    rows = [(f"`{name}`", f"`{target}`") for name, target in project["scripts"].items()]
    rows += [
        ("`python tools/gen_docs.py`", "Regenerate AUTO-GENERATED doc sections"),
        ("`python tools/gen_docs.py --check`", "Fail if docs are stale (CI)"),
        ("`QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests`", "Run the test suite"),
        ("`python -m coverage run -m unittest discover -s tests && python -m coverage report`",
         "Test suite with coverage (CI floor in `pyproject.toml`)"),
        ("`PIXYDECK_HARDWARE=1 PYTHONPATH=src python -m unittest tests.test_hardware -v`",
         "Round-trip checks on a connected PIXY"),
        ("`python -m pyflakes src tests`", "Lint"),
    ]
    return table(("Command", "Entry point / purpose"), rows)


def dependency_reference() -> str:
    project = PYPROJECT["project"]
    rows = [(f"`{dep}`", "required") for dep in project["dependencies"]]
    for extra, deps in project.get("optional-dependencies", {}).items():
        rows += [(f"`{dep}`", f"extra `[{extra}]`") for dep in deps]
    return (f"Python `{project['requires-python']}`.\n\n"
            + table(("Package", "Needed for"), rows))


def installed_files() -> str:
    text = (ROOT / "install.sh").read_text()
    variables = dict(re.findall(r"^(LIBDIR|POLICY)=(\S+)$", text, re.M))

    def expand(value: str) -> str:
        value = value.strip('"')
        for name, replacement in variables.items():
            value = value.replace(f"${name}", replacement)
        return value

    rows = []
    for origin, source, target in re.findall(r'sudo install -m \d+ "\$(ROOT|TMP)/([^"]+)" (\S+)', text):
        label = f"`{source}`" if origin == "ROOT" else f"`{source}` (generated from a `deploy/*.in` template)"
        rows.append((label, f"`{expand(target)}`"))
    services = sorted(set(re.findall(r"sudo systemctl (?:re)?enable (\S+)", text)))
    rows += [(f"systemd unit `{s}`", "enabled at boot") for s in services]
    rows.append(("private virtualenv", "`~/.local/share/pixydeck/venv`"))
    rows.append(("desktop entry and icon", "`~/.local/share/applications/pixydeck.desktop`, hicolor icon theme"))
    return ("Installed by `./install.sh`; the `.deb` and AUR packages use `/usr/lib/pixydeck` "
            "and `/usr/lib/{systemd,udev}` instead.\n\n" + table(("Installed item", "Location"), rows))


GENERATORS = {
    "cli": cli_reference,
    "shortcuts": shortcut_reference,
    "commands": command_reference,
    "dependencies": dependency_reference,
    "installed-files": installed_files,
}
DOCUMENTS = ["docs/en/user-guide.md", "docs/de/benutzerhandbuch.md", "docs/CONTRIBUTING.md", "docs/RUNBOOK.md"]
MARKER = re.compile(
    r"(?P<open><!-- AUTO-GENERATED:(?P<name>[\w-]+) -->).*?(?P<close><!-- /AUTO-GENERATED:(?P=name) -->)", re.S)


def render(text: str) -> str:
    return MARKER.sub(
        lambda m: f"{m['open']}\n{GENERATORS[m['name']]()}\n{m['close']}", text)


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for name in DOCUMENTS:
        path = ROOT / name
        current = path.read_text()
        updated = render(current)
        if updated != current:
            stale.append(name)
            if not check:
                path.write_text(updated)
    if check and stale:
        print("Out of date (run python tools/gen_docs.py):", ", ".join(stale))
        return 1
    print("Updated:" if stale else "Up to date:", ", ".join(stale or DOCUMENTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
