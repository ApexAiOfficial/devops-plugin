"""Verify the pinned apexai-ops installation before the launcher imports it.

Run with ``python -I`` (no PYTHONPATH, no user site, no script directory), so
nothing ambient is consulted. Standard library only: this file must not
import the package it verifies. Exit 0 when the pinned distribution is
installed at its exact version, every hashed RECORD file matches its digest
and size, the package's files are exactly the build pin.json names, and the
``apexai_ops`` package the import system resolves contains only those files;
otherwise exit 2 with one closed, token-free reason.

A RECORD only proves that files match the RECORD shipped beside them, which
any package with the engine's name and version can satisfy. The build digest
(``package_sha256`` in pin.json) ties the package's files to ApexAi's build:
the SHA-256 of the lines ``apexai_ops/<path>,<RECORD digest>\\n``, sorted by
path, for every verified file inside the package directory except bytecode.
Files count by where they are on disk, not by how RECORD spells them, so the
digest does not depend on the installer, the Python version or the install
location. It is checked when the engine starts; it cannot undo an
installation, whose own code may already have run.

To pin a new engine version, set its version in pin.json and run
``verify_pin.py pin.json --print-package-sha256`` with the Python of an
installation made from ApexAi's own artifact. That mode runs every other check
and prints the digest of whatever is installed: it cannot tell where the
installation came from, so the value is ApexAi's only if the artifact was.
"""

import base64
import csv
import hashlib
import importlib.machinery
import io
import json
import os
import re
import sys
from importlib import metadata
from pathlib import Path

_UNHASHED = re.compile(r"(?:^|/)RECORD(?:\.jws|\.p7s)?$|\.pyc$")
_PACKAGE = "apexai_ops"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_UNSAFE = re.compile(r"[^0-9A-Za-z.+!_-]")
_PRINT = "--print-package-sha256"


_PIN = {"name": "apexai-ops", "version": "the pinned version", "installed": ""}


def _hint(code: str) -> str:
    """What a person can do about ``code``: the next step, never a credential or a path secret.

    No hint names a package index or an install command: the engine is proprietary and is
    installed only by ApexAi, from its own artifact, in the environments it operates.
    """

    name, version = _PIN["name"], _PIN["version"]
    if code == "pin_unreadable":
        return "the plugin's pin.json is missing or malformed: reinstall the plugin"
    if code == "pinned_distribution_missing":
        return (
            f"the DevOps engine {name} {version} is not installed for {sys.executable}: "
            "set APEXAI_OPS_PYTHON to the Python of the engine installation ApexAi operates here"
        )
    if code == "version_mismatch":
        installed = _PIN["installed"]
        return (
            f"{name} {installed} is installed; this plugin runs exactly {version}: use the plugin "
            "version that matches the installation, or have ApexAi update the installation"
        )
    if code == "package_digest_mismatch":
        return (
            f"the installed {name} {version} is not the build this plugin pins: do not run it. "
            "Have ApexAi reinstall the engine from its own artifact, or use the plugin version made for "
            "that build; the engine is not on any public package index"
        )
    if code == "module_not_in_record":
        return f"Python would import another copy of {_PACKAGE}, not the verified installation: remove the other copy"
    if code == "package_unrecorded_file":
        return f"the installed {_PACKAGE} contains files its RECORD does not list: remove them, or have ApexAi reinstall it"
    if code == "package_unreadable":
        return f"part of the installed {_PACKAGE} cannot be read: fix its permissions"
    return f"the installed {name} does not match its own RECORD: the installation is damaged or altered"


def _refuse(code: str) -> None:
    print(f"apexai-ops mcp: refused ({code}); {_hint(code)}", file=sys.stderr)
    raise SystemExit(2)


def _unreadable(_error: OSError) -> None:
    _refuse("package_unreadable")


def main() -> None:
    printing = sys.argv[2:] == [_PRINT]
    try:
        pin = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        name, version = str(pin["distribution"]), str(pin["version"])
        pinned_digest = "" if printing else str(pin["package_sha256"])
    except (IndexError, OSError, ValueError, KeyError, TypeError):
        _refuse("pin_unreadable")
    if not printing and not _SHA256_HEX.fullmatch(pinned_digest):
        _refuse("pin_unreadable")
    _PIN.update(name=name, version=version)
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        _refuse("pinned_distribution_missing")
    if distribution.version != version:
        # Installed metadata is not trusted: keep the refusal one short line.
        _PIN["installed"] = _UNSAFE.sub("?", str(distribution.version))[:40]
        _refuse("version_mismatch")
    text = distribution.read_text("RECORD")
    if text is None:
        _refuse("record_missing")
    root = Path(str(distribution.locate_file(_PACKAGE))).resolve()
    verified = set()
    build = []
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
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            if not _UNHASHED.search(relative) and "__pycache__" not in relative.split("/"):
                build.append((f"{_PACKAGE}/{relative}", digest))
    package_digest = hashlib.sha256("".join(f"{p},{d}\n" for p, d in sorted(build)).encode()).hexdigest()
    if not printing and package_digest != pinned_digest:
        _refuse("package_digest_mismatch")
    spec = importlib.machinery.PathFinder.find_spec(_PACKAGE)
    if spec is None or spec.origin is None:
        _refuse("module_not_in_record")
    origin = Path(spec.origin).resolve()
    if origin not in verified or origin.parent != root:
        _refuse("module_not_in_record")
    # Nothing but the verified files may sit inside the package: no module added by another
    # distribution, and no directory the walk cannot read or would not follow.
    for directory, subdirectories, files in os.walk(root, onerror=_unreadable):
        here = Path(directory)
        if any((here / subdirectory).is_symlink() for subdirectory in subdirectories):
            _refuse("package_unrecorded_file")
        if here.name == "__pycache__":
            continue  # bytecode caches, which installers record without digests
        for entry in files:
            try:
                resolved = (here / entry).resolve()
            except OSError:
                _refuse("package_unreadable")
            if resolved not in verified:
                _refuse("package_unrecorded_file")
    if printing:
        print(package_digest)


if __name__ == "__main__":
    main()
