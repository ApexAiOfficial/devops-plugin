"""Verify the pinned apexai-ops installation before the launcher imports it.

Run with ``python -I`` (no PYTHONPATH, no user site, no script directory), so
nothing ambient is consulted. Standard library only: this file must not
import the package it verifies. Exit 0 when the pinned distribution is
installed at its exact version, every hashed RECORD file matches its digest
and size, and the ``apexai_ops`` package the import system resolves is one
of those files; otherwise exit 2 with one closed, token-free reason.
"""

import base64
import csv
import hashlib
import importlib.machinery
import io
import json
import re
import sys
from importlib import metadata
from pathlib import Path

_UNHASHED = re.compile(r"(?:^|/)RECORD(?:\.jws|\.p7s)?$|\.pyc$")


_PIN = {"name": "apexai-ops", "version": "the pinned version", "installed": ""}


def _hint(code: str) -> str:
    """What a person can do about ``code``: the next step, never a credential or a path secret."""

    name, version = _PIN["name"], _PIN["version"]
    install = f"install the licensed engine {name}=={version}"
    if code == "pin_unreadable":
        return "the plugin's pin.json is missing or malformed: reinstall the plugin"
    if code == "pinned_distribution_missing":
        return f"{install} into {sys.executable}, or set APEXAI_OPS_PYTHON to a Python that has it"
    if code == "version_mismatch":
        installed = _PIN["installed"]
        return f"{name} {installed} is installed; this plugin runs exactly {version}: {install}"
    return (
        f"the installed {name} does not match its own RECORD: reinstall it "
        f"(pip install --force-reinstall --no-deps {name}=={version})"
    )


def _refuse(code: str) -> None:
    print(f"apexai-ops mcp: refused ({code}); {_hint(code)}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        pin = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        name, version = str(pin["distribution"]), str(pin["version"])
    except (IndexError, OSError, ValueError, KeyError, TypeError):
        _refuse("pin_unreadable")
    _PIN.update(name=name, version=version)
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        _refuse("pinned_distribution_missing")
    if distribution.version != version:
        _PIN["installed"] = distribution.version
        _refuse("version_mismatch")
    text = distribution.read_text("RECORD")
    if text is None:
        _refuse("record_missing")
    verified = set()
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if len(row) != 3:
            _refuse("record_malformed")
        file_name, digest, size = row
        if not digest:
            if _UNHASHED.search(file_name):
                continue
            _refuse("record_unhashed_file")
        algorithm, _, expected = digest.partition("=")
        if algorithm != "sha256":
            _refuse("record_hash_unsupported")
        path = Path(str(distribution.locate_file(file_name))).resolve()
        try:
            data = path.read_bytes()
        except OSError:
            _refuse("record_file_missing")
        actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        if actual != expected or (size and size != str(len(data))):
            _refuse("record_digest_mismatch")
        verified.add(path)
    spec = importlib.machinery.PathFinder.find_spec("apexai_ops")
    if spec is None or spec.origin is None or Path(spec.origin).resolve() not in verified:
        _refuse("module_not_in_record")


if __name__ == "__main__":
    main()
