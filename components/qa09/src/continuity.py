#!/usr/bin/env python3
"""Project Continuity Guard 1.0.0. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import configparser
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

VERSION = "1.0.1"
META = ".continuity"
CONFIG = "CONTINUITY.json"
MIGRATIONS = "CONTINUITY_MIGRATIONS.json"
DEFAULT_EXCLUDES = ["build/**", "dist/**", "**/__pycache__/**", "**/*.pyc"]
MAX_ARCHIVE_BYTES = 10 * 1024**3
HEX = re.compile(r"^[a-f0-9]{64}$")
LFS = b"version https://git-lfs.github.com/spec/v1\n"
AGENT_BLOCK = """<!-- project-continuity:start -->
## Continuidad verificable
Antes de editar, leer .continuity/RESUME.md y PROJECT_CONTEXT.md si existe;
ejecutar python3 tools/continuity.py verify . y contrastar el snapshot esperado.
Usar las fuentes activas verificadas. No elegir una base solo por fecha/nombre,
ni retroceder a una compilacion antigua porque falten fuentes recientes.
Conservar fuentes, recursos, herramientas, tablas, licencias y dependencias
heredadas. Registrar movimientos/retiros justificados en CONTINUITY_MIGRATIONS.json.
Guardar avances con checkpoint; entregar fuentes formales con release.
Un checkpoint conserva trabajo y no certifica compilacion, jugabilidad o calidad.
Probar release desde el ZIP extraido; no usar salidas de compilacion anteriores.
Guardar el ZIP en un destino duradero autorizado y registrar su id/hash antes
de cerrar. Un archivo local o un enlace sandbox no confirma guardado duradero.
Ante un faltante, preservar el WIP y recuperar solo el objeto identificado.
No pedir al usuario archivos que ya pueden recuperarse en los recursos conectados.
<!-- project-continuity:end -->
"""


class GuardError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise GuardError(code, message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def own_source():
    """Read editable code from a regular script or its zipapp importer."""
    path = Path(__file__)
    if path.is_file():
        return path.read_bytes()
    loader = globals().get("__loader__")
    if loader is not None and hasattr(loader, "get_data"):
        return loader.get_data(__file__)
    fail("TOOL_SOURCE_UNAVAILABLE", "No se pudo recuperar el fuente del control")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail("INVALID_JSON", f"{path}: {e}")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def relative(name):
    """Require names portable to Windows, macOS and Linux."""
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        fail("UNSAFE_PATH", str(name))
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ("", ".", "..") for x in name.split("/")):
        fail("UNSAFE_PATH", name)
    for part in p.parts:
        if re.search(r'[:*?"<>|\x00-\x1f]', part) or part.endswith((" ", ".")):
            fail("NONPORTABLE_PATH", name)
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part):
            fail("NONPORTABLE_PATH", name)
    return p


def inside(root, path):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def excluded(name, config):
    # Git internals and guard metadata are not project sources.
    parts = PurePosixPath(name).parts
    if parts[0] == META or ".git" in parts or ".DS_Store" in parts:
        return True
    for pattern in config.get("exclude", []):
        if fnmatch.fnmatchcase(name, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatchcase(name, pattern[3:]):
            return True
        if pattern.endswith("/**") and name == pattern[:-3]:
            return True
    return False


def inventory(root, config):
    root = Path(root).resolve()
    entries = {}
    folded = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        for name in list(dirs) + files:
            p = Path(folder) / name
            rel = p.relative_to(root).as_posix()
            if excluded(rel, config):
                if name in dirs:
                    dirs.remove(name)
                continue
            relative(rel)
            key = unicodedata.normalize("NFC", rel).casefold()
            if key in folded and folded[key] != rel:
                fail("PATH_COLLISION", f"{folded[key]} / {rel}")
            folded[key] = rel
            if p.is_symlink():
                if name in dirs:
                    dirs.remove(name)
                target = os.readlink(p)
                if os.path.isabs(target) or not inside(root, p.parent / target):
                    fail("EXTERNAL_SYMLINK", rel)
                if not p.exists():
                    fail("BROKEN_SYMLINK", rel)
                entries[rel] = {"kind": "symlink", "target": target,
                                "sha256": digest(target.encode()), "size": len(target.encode())}
            elif p.is_file():
                entries[rel] = {"kind": "file", "sha256": file_hash(p),
                                "size": p.stat().st_size,
                                "executable": bool(p.stat().st_mode & 0o111)}
            elif not p.is_dir():
                fail("UNSUPPORTED_FILE", rel)
    return dict(sorted(entries.items()))


def same(a, b):
    if os.name == "nt":
        a, b = dict(a), dict(b)
        a.pop("executable", None)
        b.pop("executable", None)
    return a == b


def differences(before, after):
    return {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(k for k in before.keys() & after.keys()
                          if not same(before[k], after[k])),
        "unchanged": sum(same(before[k], after[k]) for k in before.keys() & after.keys()),
    }


def config_for(root):
    c = read_json(Path(root) / CONFIG)
    if not isinstance(c, dict) or c.get("schema") != 1:
        fail("CONFIG_SCHEMA", "CONTINUITY.json debe usar schema=1")
    if not isinstance(c.get("project_id"), str) or not c["project_id"].strip():
        fail("CONFIG_PROJECT_ID", "Falta project_id")
    for field in ("exclude", "required_paths", "external_inputs"):
        if not isinstance(c.get(field, []), list):
            fail("CONFIG_SCHEMA", field)
    if not all(isinstance(x, str) for x in c.get("exclude", [])):
        fail("CONFIG_SCHEMA", "exclude debe contener patrones de texto")
    for name in c.get("required_paths", []):
        relative(name)
    ids, envs = set(), set()
    for item in c.get("external_inputs", []):
        if not isinstance(item, dict):
            fail("INPUT_SCHEMA", "Entrada externa invalida")
        ident, env = item.get("id", ""), item.get("env", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", ident) or ident in ids:
            fail("INPUT_SCHEMA", "id externo invalido/duplicado")
        if not re.fullmatch(r"CONTINUITY_INPUT_[A-Z0-9_]+", env) or env in envs:
            fail("INPUT_SCHEMA", "Usar variables unicas CONTINUITY_INPUT_*")
        if not HEX.fullmatch(str(item.get("sha256", ""))):
            fail("INPUT_SCHEMA", f"{ident}: falta SHA-256 fijado")
        if item.get("kind", "file") not in ("file", "tree"):
            fail("INPUT_SCHEMA", f"{ident}: kind invalido")
        ids.add(ident)
        envs.add(env)
    return c


def snapshot_id(manifest):
    m = dict(manifest)
    m.pop("snapshot_id", None)
    return digest(canonical(m))


def head_for(root):
    root = Path(root)
    state = read_json(root / META / "state.json")
    ident = state.get("active_snapshot", "")
    if not HEX.fullmatch(str(ident)):
        fail("STATE_INVALID", "active_snapshot invalido")
    head = read_json(root / META / "manifests" / (ident + ".json"))
    seen = set()
    item = head
    while True:
        this = item.get("snapshot_id", "")
        if this in seen or this != snapshot_id(item):
            fail("MANIFEST_TAMPERED", str(this))
        seen.add(this)
        if item.get("project_id") != head.get("project_id"):
            fail("LINEAGE_PROJECT_CHANGED", this)
        parent = item.get("parent_snapshot")
        if parent is None:
            break
        if not HEX.fullmatch(str(parent)):
            fail("MANIFEST_INVALID", "parent_snapshot invalido")
        item = read_json(root / META / "manifests" / (parent + ".json"))
        if item.get("snapshot_id") != parent:
            fail("MANIFEST_TAMPERED", parent)
    return state, head


def inspect_sources(root, config, files):
    root = Path(root)
    issues = []
    for name in [CONFIG] + config.get("required_paths", []):
        if name not in files and not any(x.startswith(name + "/") for x in files):
            issues.append({"code": "REQUIRED_PATH_MISSING", "path": name})
    gm = root / ".gitmodules"
    if gm.exists():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(gm.read_text(encoding="utf-8"))
            for section in parser.sections():
                name = parser.get(section, "path", fallback="")
                relative(name)
                if not any(x.startswith(name + "/") for x in files):
                    issues.append({"code": "SUBMODULE_CONTENT_MISSING", "path": name})
        except (configparser.Error, UnicodeError) as e:
            issues.append({"code": "GITMODULES_INVALID", "detail": str(e)})
    for name, record in files.items():
        if record["kind"] == "file" and record["size"] < 2048:
            with (root / name).open("rb") as f:
                if f.read(len(LFS)) == LFS:
                    issues.append({"code": "LFS_POINTER_WITHOUT_CONTENT", "path": name})
    return issues


def enforce_migrations(root, before, after):
    delta = differences(before, after)
    records = read_json(Path(root) / MIGRATIONS) if (Path(root) / MIGRATIONS).exists() else []
    if not isinstance(records, list):
        fail("MIGRATION_SCHEMA", "La bitacora de migraciones debe ser una lista")
    for name in delta["removed"]:
        found = [r for r in records if isinstance(r, dict) and r.get("path") == name
                 and r.get("old_sha256") == before[name]["sha256"]]
        if len(found) != 1:
            fail("INHERITED_FILE_MISSING", f"{name}: falta migracion explicita con hash anterior")
        r = found[0]
        if not isinstance(r.get("reason"), str) or len(r["reason"].strip()) < 8:
            fail("MIGRATION_REASON_MISSING", name)
        if r.get("action") in ("move", "replace"):
            target = r.get("to", "")
            relative(target)
            expected = before[name]["sha256"] if r["action"] == "move" else r.get("new_sha256")
            if target not in after or after[target]["sha256"] != expected:
                fail("MIGRATION_TARGET_INVALID", name)
        elif r.get("action") != "retire":
            fail("MIGRATION_ACTION_INVALID", name)
    return delta


def validate_evidence(root, state, head):
    root = Path(root)
    report_path = root / META / "reports" / (head["snapshot_id"] + ".json")
    if not report_path.is_file() or file_hash(report_path) != state.get("report_sha256"):
        fail("REPORT_TAMPERED", "El informe activo no coincide con su hash")
    report = read_json(report_path)
    if report.get("snapshot_id") != head["snapshot_id"]:
        fail("REPORT_WRONG_SNAPSHOT", str(report_path))
    if state.get("authority") == "REBUILT_RELEASE":
        if report.get("build") != "PASS" or len(report.get("runs", [])) != 2:
            fail("STATE_OVERCLAIM", "La autoridad declara una reconstruccion sin evidencia")
        if state.get("last_rebuilt_snapshot") != head["snapshot_id"]:
            fail("STATE_OVERCLAIM", "Ultima reconstruccion no corresponde a la release activa")
    for artifact in report.get("artifacts", []):
        rel = artifact["stored_path"]
        relative(rel)
        p = root / rel
        if not p.is_file() or not inside(root, p) or file_hash(p) != artifact["sha256"]:
            fail("ARTIFACT_TAMPERED", rel)
    return report


def verify(root, expected=None):
    root = Path(root).resolve()
    c = config_for(root)
    state, head = head_for(root)
    if c["project_id"] != head["project_id"]:
        fail("PROJECT_ID_CHANGED", "La identidad del proyecto no coincide")
    if expected and state["active_snapshot"] != expected:
        fail("AUTHORITY_MISMATCH", "El snapshot no coincide con la referencia esperada")
    delta = differences(head["files"], inventory(root, c))
    if delta["added"] or delta["removed"] or delta["changed"]:
        fail("SOURCE_TREE_CHANGED", json.dumps(delta, ensure_ascii=False))
    validate_evidence(root, state, head)
    return {"status": "PASS", "project_id": c["project_id"],
            "version": head["version"], "snapshot_id": head["snapshot_id"],
            "parent_snapshot": head["parent_snapshot"],
            "files": len(head["files"]), "authority": state["authority"],
            "last_rebuilt_snapshot": state.get("last_rebuilt_snapshot"),
            "source_completeness": "BASELINE_INHERITED_ONLY",
            "scope": "Inventario activo; no certifica contenido omitido antes de la adopcion"}


def resume_text(state, manifest):
    return "\n".join([
        "# Reanudar desde esta autoridad",
        f"Proyecto: {manifest['project_id']}",
        f"Version: {manifest['version']}",
        f"Snapshot activo: {manifest['snapshot_id']}",
        f"Padre: {manifest['parent_snapshot']}",
        f"Estado: {state['authority']}",
        f"Ultima reconstruccion comprobada: {state.get('last_rebuilt_snapshot')}",
        "Primero: python3 tools/continuity.py verify . --expect-id " + manifest["snapshot_id"],
        "Leer PROJECT_CONTEXT.md para objetivo, alcance, pendientes y evidencia.",
        "Conservar el trabajo activo aunque la ultima compilacion comprobada sea anterior.",
        "Revisar delivery-receipt.json si existe; un ZIP local no prueba guardado duradero.",
        "No cambiar la base, inventar fuentes perdidas ni exigir ZIP historicos por rutina.",
        "",
    ])


@contextmanager
def locked(root):
    p = Path(root) / META / "operation.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        fail("OPERATION_LOCKED", "Hay otra operacion o un lock de una interrupcion; diagnosticarlo")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "created": now()}))
        yield
    finally:
        p.unlink(missing_ok=True)


def make_manifest(c, files, version, parent, sequence):
    m = {"schema": 1, "guard_version": VERSION, "project_id": c["project_id"],
         "version": version, "sequence": sequence, "created_utc": now(),
         "parent_snapshot": parent, "files": files}
    m["snapshot_id"] = snapshot_id(m)
    return m


def install(root, name):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / META / "state.json").exists():
        fail("ALREADY_INITIALIZED", "No reinicializar ni sustituir la autoridad existente")
    destination = root / "src" / "continuity.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    code = own_source()
    if destination.exists() and file_hash(destination) != digest(code):
        fail("TOOL_CONFLICT", str(destination))
    if Path(__file__).resolve() != destination:
        destination.write_bytes(code)
    agent = root / "AGENTS.md"
    previous = agent.read_text(encoding="utf-8") if agent.exists() else ""
    if "<!-- project-continuity:start -->" not in previous:
        agent.write_text(previous.rstrip() + "\n\n" + AGENT_BLOCK, encoding="utf-8")
    if not (root / CONFIG).exists():
        write_json(root / CONFIG, {
            "schema": 1, "project_id": str(uuid.uuid4()), "name": name,
            "exclude": DEFAULT_EXCLUDES, "required_paths": ["AGENTS.md", "src/continuity.py"],
            "external_inputs": [], "build": None,
        })
    with locked(root):
        c = config_for(root)
        files = inventory(root, c)
        manifest = make_manifest(c, files, "adopted-baseline", None, 0)
        issues = inspect_sources(root, c, files)
        report = {"schema": 1, "snapshot_id": manifest["snapshot_id"],
                  "source_inventory": "PASS", "build": "NOT_VALIDATED",
                  "issues": issues, "source_completeness": "NOT_VALIDATED",
                  "note": "El inventario inicial no demuestra que las fuentes previas esten completas"}
        state = {"schema": 1, "active_snapshot": manifest["snapshot_id"],
                 "authority": "IMPORTED_UNAUDITED", "last_rebuilt_snapshot": None,
                 "report_sha256": digest((json.dumps(report, ensure_ascii=False, sort_keys=True,
                                                     indent=2) + "\n").encode())}
        write_json(root / META / "manifests" / (manifest["snapshot_id"] + ".json"), manifest)
        write_json(root / META / "reports" / (manifest["snapshot_id"] + ".json"), report)
        (root / META / "RESUME.md").write_text(resume_text(state, manifest), encoding="utf-8")
        write_json(root / META / "state.json", state)
    result = verify(root)
    result["issues"] = issues
    return result


def copy_sources(source, dest, entries):
    source, dest = Path(source), Path(dest)
    for name, item in entries.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["kind"] == "file":
            shutil.copy2(source / name, target)
            if file_hash(target) != item["sha256"]:
                fail("COPY_RACE", name)
        else:
            os.symlink(item["target"], target)
    # Symlinks may refer to a later entry; check them after all files exist.
    for name, item in entries.items():
        if item["kind"] == "symlink" and not (dest / name).exists():
            fail("BROKEN_SYMLINK", name)


def metadata_copy(root, stage):
    for folder in ("manifests", "reports", "artifacts"):
        p = Path(root) / META / folder
        if p.exists():
            shutil.copytree(p, Path(stage) / META / folder, dirs_exist_ok=True, symlinks=True)


def zip_tree(root, out):
    root, out = Path(root), Path(out)
    index_path = root / META / "package_index.json"
    index_path.unlink(missing_ok=True)
    index = inventory(root, {"exclude": []})  # This intentionally excludes guard metadata.
    # Include all metadata too, without locks or mutable delivery receipts.
    meta_entries = {}
    for p in sorted((root / META).rglob("*")):
        if p.is_file() and not p.is_symlink():
            name = p.relative_to(root).as_posix()
            relative(name)
            meta_entries[name] = {"kind": "file", "sha256": file_hash(p),
                                  "size": p.stat().st_size,
                                  "executable": bool(p.stat().st_mode & 0o111)}
        elif p.is_symlink():
            fail("METADATA_SYMLINK", str(p))
    index.update(meta_entries)
    write_json(index_path, {"schema": 1, "entries": index})
    all_files = sorted([p for p in root.rglob("*") if p.is_file() or p.is_symlink()])
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in all_files:
            name = p.relative_to(root).as_posix()
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.create_system = 3
            zi.compress_type = zipfile.ZIP_DEFLATED
            if p.is_symlink():
                zi.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(zi, os.readlink(p).encode())
            else:
                mode = 0o755 if p.stat().st_mode & 0o111 else 0o644
                zi.external_attr = (stat.S_IFREG | mode) << 16
                with z.open(zi, "w") as dst, p.open("rb") as src:
                    shutil.copyfileobj(src, dst, 1024 * 1024)


def extract_zip(archive, destination):
    destination = Path(destination)
    if destination.exists():
        fail("RESTORE_DEST_EXISTS", "Restaurar solo en una carpeta nueva")
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as z:
            names, folded, links = set(), set(), []
            total = 0
            for item in z.infolist():
                name = item.filename.rstrip("/") if item.is_dir() else item.filename
                relative(name)
                key = unicodedata.normalize("NFC", name).casefold()
                if name in names or key in folded:
                    fail("ZIP_DUPLICATE_PATH", name)
                names.add(name)
                folded.add(key)
                total += item.file_size
                if total > MAX_ARCHIVE_BYTES:
                    fail("ARCHIVE_TOO_LARGE", "El ZIP excede 10 GiB sin comprimir")
                mode = item.external_attr >> 16
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.is_dir():
                    target.mkdir(exist_ok=True)
                elif stat.S_ISLNK(mode):
                    text = z.read(item).decode("utf-8")
                    if os.path.isabs(text) or not inside(destination, target.parent / text):
                        fail("ZIP_EXTERNAL_SYMLINK", name)
                    links.append((target, text))
                elif stat.S_IFMT(mode) in (0, stat.S_IFREG):
                    with z.open(item) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    if mode:
                        target.chmod(mode & 0o777)
                else:
                    fail("ZIP_UNSUPPORTED_ENTRY", name)
            # Refuse a symlink used as the parent of another archive entry.
            for target, text in links:
                rel = target.relative_to(destination).as_posix()
                if any(n.startswith(rel + "/") for n in names):
                    fail("ZIP_SYMLINK_PARENT", rel)
                os.symlink(text, target)
            for target, text in links:
                if not inside(destination, target) or not target.exists():
                    fail("ZIP_BROKEN_SYMLINK", target.relative_to(destination).as_posix())
        index = read_json(destination / META / "package_index.json")
        expected = index["entries"]
        actual = inventory(destination, {"exclude": []})
        for p in (destination / META).rglob("*"):
            if p.is_symlink():
                fail("METADATA_SYMLINK", str(p))
            if p.is_file() and p.name != "package_index.json":
                actual[p.relative_to(destination).as_posix()] = {
                    "kind": "file", "sha256": file_hash(p), "size": p.stat().st_size,
                    "executable": bool(p.stat().st_mode & 0o111)}
        delta = differences(expected, actual)
        if delta["added"] or delta["removed"] or delta["changed"]:
            fail("PACKAGE_INDEX_MISMATCH", json.dumps(delta))
        return verify(destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def external_fingerprint(path, kind):
    p = Path(path)
    if kind == "file":
        if not p.is_file() or p.is_symlink():
            fail("INPUT_MISSING", str(p))
        return file_hash(p)
    if not p.is_dir():
        fail("INPUT_MISSING", str(p))
    return digest(canonical(inventory(p, {"exclude": []})))


def external_inputs(config):
    resolved = {}
    for item in config.get("external_inputs", []):
        text = os.environ.get(item["env"])
        if not text:
            fail("INPUT_MISSING", f"{item['id']}: indicar {item['env']}")
        p = Path(text).resolve()
        if external_fingerprint(p, item.get("kind", "file")) != item["sha256"]:
            fail("INPUT_HASH_MISMATCH", item["id"])
        if "size" in item and item.get("kind", "file") == "file" and p.stat().st_size != item["size"]:
            fail("INPUT_SIZE_MISMATCH", item["id"])
        resolved[item["id"]] = p
    return resolved


def apply_bps(source, patch):
    if len(patch) < 19 or patch[:4] != b"BPS1":
        fail("BPS_INVALID", "Cabecera BPS invalida")
    source_crc, target_crc, patch_crc = struct.unpack("<III", patch[-12:])
    if zlib.crc32(patch[:-4]) != patch_crc or zlib.crc32(source) != source_crc:
        fail("BPS_CRC_MISMATCH", "Base o parche BPS incorrecto")
    cursor, end = 4, len(patch) - 12

    def byte():
        nonlocal cursor
        if cursor >= end:
            fail("BPS_TRUNCATED", "Parche truncado")
        value = patch[cursor]
        cursor += 1
        return value

    def integer():
        value, shift = 0, 1
        for _ in range(10):
            b = byte()
            value += (b & 0x7f) * shift
            if b & 0x80:
                return value
            shift <<= 7
            value += shift
        fail("BPS_INTEGER_INVALID", "Entero BPS excesivo")

    if integer() != len(source):
        fail("BPS_SOURCE_SIZE", "Tamano de base BPS no coincide")
    target_size, metadata_size = integer(), integer()
    if target_size > 256 * 1024**2 or cursor + metadata_size > end:
        fail("BPS_BOUNDS", "Longitud BPS invalida")
    cursor += metadata_size
    output = bytearray()
    source_relative = target_relative = 0
    while cursor < end:
        command = integer()
        action, length = command & 3, (command >> 2) + 1
        if len(output) + length > target_size:
            fail("BPS_BOUNDS", "Comando excede destino")
        if action == 0:
            offset = len(output)
            if offset + length > len(source):
                fail("BPS_BOUNDS", "SourceRead fuera de base")
            output.extend(source[offset:offset + length])
        elif action == 1:
            if cursor + length > end:
                fail("BPS_BOUNDS", "TargetRead truncado")
            output.extend(patch[cursor:cursor + length])
            cursor += length
        else:
            offset = integer()
            change = -(offset >> 1) if offset & 1 else offset >> 1
            if action == 2:
                source_relative += change
                if source_relative < 0 or source_relative + length > len(source):
                    fail("BPS_BOUNDS", "SourceCopy fuera de base")
                output.extend(source[source_relative:source_relative + length])
                source_relative += length
            else:
                target_relative += change
                if target_relative < 0 or target_relative >= len(output):
                    fail("BPS_BOUNDS", "TargetCopy fuera de datos producidos")
                for _ in range(length):
                    output.append(output[target_relative])
                    target_relative += 1
    if len(output) != target_size or zlib.crc32(output) != target_crc:
        fail("BPS_TARGET_MISMATCH", "Destino BPS invalido")
    return bytes(output)


def rebuild(extracted, config, source_files, supplied, inputs_dir):
    recipe = config.get("build")
    if not isinstance(recipe, dict) or not recipe.get("argv") or not recipe.get("artifacts"):
        fail("BUILD_RECIPE_MISSING", "Definir build.argv y build.artifacts antes de release")
    argv = recipe["argv"]
    if not isinstance(argv, list) or not all(isinstance(x, str) and x for x in argv):
        fail("BUILD_ARGV_INVALID", "Usar una lista de argumentos; no una cadena shell")
    if recipe.get("platforms") and sys.platform not in recipe["platforms"]:
        fail("BUILD_PLATFORM_UNSUPPORTED", sys.platform)
    env = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}
    # Windows process startup requires these system paths.
    for key in ("SYSTEMROOT", "WINDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    copied = {}
    for item in config.get("external_inputs", []):
        target = inputs_dir / item["id"]
        if item.get("kind", "file") == "tree":
            shutil.copytree(supplied[item["id"]], target, symlinks=True)
        else:
            shutil.copy2(supplied[item["id"]], target)
        if external_fingerprint(target, item.get("kind", "file")) != item["sha256"]:
            fail("INPUT_COPY_MISMATCH", item["id"])
        env[item["env"]] = str(target)
        copied[item["id"]] = target
    command = [sys.executable if x == "{python}" else x for x in argv]
    if Path(command[0]).is_absolute() and command[0] != sys.executable:
        fail("BUILD_ABSOLUTE_EXECUTABLE", "Usar {python}, un binario del sistema o una ruta relativa")
    timeout = recipe.get("timeout_seconds", 60)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        fail("BUILD_TIMEOUT_INVALID", "timeout_seconds debe ser positivo")
    started = time.monotonic()
    log = extracted.parent / "build.log"
    try:
        with log.open("wb") as f:
            process = subprocess.Popen(command, cwd=extracted, env=env, stdout=f,
                                       stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                raise
    except subprocess.TimeoutExpired:
        fail("BUILD_TIMEOUT", f"Supero {timeout} segundos")
    except OSError as e:
        fail("BUILD_EXEC_FAILED", str(e))
    # Logs are captured, not printed: build output can contain private paths or data.
    if code != 0:
        fail("BUILD_FAILED", f"Codigo {code}; no se promueve la autoridad")
    delta = differences(source_files, inventory(extracted, config))
    if delta["added"] or delta["removed"] or delta["changed"]:
        fail("BUILD_MUTATED_SOURCES", json.dumps(delta))
    records = []
    for item in recipe["artifacts"]:
        path = item.get("path", "")
        relative(path)
        if not excluded(path, config) or PurePosixPath(path).parts[0] == META:
            fail("ARTIFACT_PATH_INVALID", "Los resultados deben estar en una ruta excluida, p.ej. build/")
        p = extracted / path
        if not inside(extracted, p) or not p.is_file() or p.is_symlink():
            fail("BUILD_ARTIFACT_MISSING", path)
        h = file_hash(p)
        if not HEX.fullmatch(str(item.get("sha256", ""))):
            fail("ARTIFACT_EXPECTATION_MISSING", path)
        if h != item["sha256"]:
            fail("BUILD_ARTIFACT_MISMATCH", path)
        if "size" in item and p.stat().st_size != item["size"]:
            fail("BUILD_ARTIFACT_MISMATCH", path + " (size)")
        records.append({"path": path, "sha256": h, "size": p.stat().st_size})
    for item in config.get("external_inputs", []):
        if external_fingerprint(copied[item["id"]], item.get("kind", "file")) != item["sha256"]:
            fail("BUILD_MUTATED_INPUT", item["id"])
    bps = config.get("bps_roundtrip")
    if bps:
        if bps.get("base_input") not in copied:
            fail("BPS_INPUT_MISSING", "Declarar base_input como entrada externa")
        for key in ("patch_path", "target_path"):
            relative(bps.get(key, ""))
        patch_path, target_path = extracted / bps["patch_path"], extracted / bps["target_path"]
        if not inside(extracted, patch_path) or not inside(extracted, target_path):
            fail("BPS_PATH_INVALID", "Ruta BPS fuera de carpeta extraida")
        output = apply_bps(copied[bps["base_input"]].read_bytes(), patch_path.read_bytes())
        if output != target_path.read_bytes():
            fail("BPS_ROUNDTRIP_MISMATCH", "BPS y builder producen bytes distintos")
    return {"platform": sys.platform, "machine": platform.machine(),
            "python": platform.python_version(), "argv": argv, "returncode": 0,
            "seconds": round(time.monotonic() - started, 3),
            "log_sha256": file_hash(log), "artifacts": records,
            "external_inputs": [{k: v for k, v in i.items() if k != "local_path"}
                                for i in config.get("external_inputs", [])],
            "bps_roundtrip": "PASS" if bps else "N/A",
            "network_isolated": False, "os_sandbox": False,
            "isolation": "Carpeta extraida nueva, entorno reducido, entradas copiadas con hashes"}


def package(root, output, version, formal=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if inside(root, output):
        fail("OUTPUT_INSIDE_SOURCES", "Guardar el ZIP fuera de la carpeta de fuentes")
    if output.exists():
        fail("OUTPUT_EXISTS", "No sobrescribir una entrega existente")
    output.parent.mkdir(parents=True, exist_ok=True)
    with locked(root):
        c = config_for(root)
        old_state, old_head = head_for(root)
        validate_evidence(root, old_state, old_head)
        if c["project_id"] != old_head["project_id"]:
            fail("PROJECT_ID_CHANGED", "No cambiar identidad para resetear la herencia")
        files = inventory(root, c)
        delta = enforce_migrations(root, old_head["files"], files)
        issues = inspect_sources(root, c, files)
        if formal and issues:
            fail("SOURCE_DEPENDENCY_INCOMPLETE", json.dumps(issues, ensure_ascii=False))
        manifest = make_manifest(c, files, version, old_head["snapshot_id"], old_head["sequence"] + 1)
        ident = manifest["snapshot_id"]
        report = {"schema": 1, "snapshot_id": ident, "source_inventory": "PASS",
                  "inheritance": delta, "issues": issues, "build": "NOT_VALIDATED",
                  "source_completeness": "BASELINE_INHERITED_ONLY", "artifacts": []}
        state = {"schema": 1, "active_snapshot": ident,
                 "authority": "WIP_CHECKPOINT",
                 "last_rebuilt_snapshot": old_state.get("last_rebuilt_snapshot")}
        with tempfile.TemporaryDirectory(prefix="continuity-", dir=output.parent) as work:
            work = Path(work)
            stage = work / "source"
            stage.mkdir()
            copy_sources(root, stage, files)
            metadata_copy(root, stage)
            write_json(stage / META / "manifests" / (ident + ".json"), manifest)

            def write_active():
                rp = stage / META / "reports" / (ident + ".json")
                write_json(rp, report)
                state["report_sha256"] = file_hash(rp)
                write_json(stage / META / "state.json", state)
                (stage / META / "RESUME.md").write_text(resume_text(state, manifest), encoding="utf-8")

            write_active()
            candidate = work / "candidate.zip"
            zip_tree(stage, candidate)
            if formal:
                supplied = external_inputs(c)
                runs = []
                for i in range(2):
                    run_dir = work / ("run" + str(i))
                    run_dir.mkdir()
                    extracted = run_dir / "source"
                    extract_zip(candidate, extracted)
                    input_dir = run_dir / "inputs"
                    input_dir.mkdir()
                    run = rebuild(extracted, c, files, supplied, input_dir)
                    runs.append(run)
                    log_name = f"{META}/artifacts/{ident}/build_run{i}.log"
                    log_path = stage / log_name
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(run_dir / "build.log", log_path)
                    report["artifacts"].append({
                        "path": f"build_run{i}.log", "stored_path": log_name,
                        "sha256": file_hash(log_path), "size": log_path.stat().st_size})
                    if i == 0:
                        for artifact in run["artifacts"]:
                            name = f"{META}/artifacts/{ident}/{artifact['path']}"
                            p = stage / name
                            p.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(extracted / artifact["path"], p)
                            report["artifacts"].append(dict(artifact, stored_path=name))
                if runs[0]["artifacts"] != runs[1]["artifacts"]:
                    fail("NONDETERMINISTIC_BUILD", "Las dos reconstrucciones no coinciden")
                report.update({"build": "PASS", "runs": runs,
                               "rebuild_scope": "Dos carpetas nuevas extraidas del ZIP candidato"})
                state["authority"] = "REBUILT_RELEASE"
                state["last_rebuilt_snapshot"] = ident
                write_active()
                zip_tree(stage, candidate)
            extract_zip(candidate, work / "final-verify")
            # Refuse source changes during packaging; leave the old authority intact.
            current = inventory(root, c)
            if differences(files, current) != {"added": [], "removed": [], "changed": [],
                                             "unchanged": len(files)}:
                fail("SOURCE_CHANGED_DURING_PACKAGE", "Las fuentes cambiaron durante la operacion")
            h = file_hash(candidate)
            # Publish a new path exclusively. Never replace an earlier ZIP.
            with output.open("xb") as dst, candidate.open("rb") as src:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            if file_hash(output) != h:
                output.unlink(missing_ok=True)
                fail("OUTPUT_HASH_MISMATCH", "La copia final no coincide")
            # Manifests/reports first, active pointer last: failed builds never promote.
            metadata_copy(stage, root)
            (root / META / "RESUME.md").write_text(resume_text(state, manifest), encoding="utf-8")
            write_json(root / META / "state.json", state)
        return {"status": "PASS", "authority": state["authority"], "snapshot_id": ident,
                "parent_snapshot": old_head["snapshot_id"], "files": len(files),
                "inheritance": delta, "issues": issues, "build": report["build"],
                "archive": str(output), "archive_sha256": h,
                "durable_saved": False, "last_rebuilt_snapshot": state["last_rebuilt_snapshot"]}


def record_receipt(root, archive, reference):
    root, archive = Path(root).resolve(), Path(archive).resolve()
    if not reference.strip():
        fail("SAVE_REFERENCE_EMPTY", "Indicar la referencia real devuelta por el guardado")
    with locked(root):
        with tempfile.TemporaryDirectory() as work:
            check = extract_zip(archive, Path(work) / "source")
        state, head = head_for(root)
        if check["snapshot_id"] != head["snapshot_id"]:
            fail("SAVE_SNAPSHOT_MISMATCH", "El archivo guardado no corresponde al WIP activo")
        receipt = {"schema": 1, "snapshot_id": head["snapshot_id"],
                   "archive_filename": archive.name, "archive_sha256": file_hash(archive),
                   "saved_reference": reference, "recorded_utc": now(),
                   "reference_verification": "CALLER_REPORTED_NOT_NETWORK_VERIFIED"}
        write_json(root / META / "delivery-receipt.json", receipt)
        return receipt


def audit_archive(path):
    """Read-only upstream archive checks, independent of adopting a baseline."""
    with zipfile.ZipFile(path) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        issues = []
        for item in files:
            if item.filename.endswith("/.gitmodules") or item.filename == ".gitmodules":
                p = configparser.ConfigParser(interpolation=None)
                p.read_string(z.read(item).decode("utf-8"))
                parent = PurePosixPath(item.filename).parent
                for section in p.sections():
                    name = p.get(section, "path")
                    prefix = (parent / name).as_posix() + "/"
                    if not any(i.filename.startswith(prefix) for i in files):
                        issues.append({"code": "SUBMODULE_CONTENT_MISSING", "path": prefix})
            if item.file_size < 2048 and z.read(item).startswith(LFS):
                issues.append({"code": "LFS_POINTER_WITHOUT_CONTENT", "path": item.filename})
        return {"archive": str(Path(path).resolve()), "sha256": file_hash(path),
                "files": len(files), "status": "INCOMPLETE_DEPENDENCIES" if issues else "NO_KNOWN_GAPS",
                "issues": issues, "scope": "Submodulos vacios y punteros LFS; no prueba compilacion"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Adoptar inventario sin certificar completitud previa")
    init.add_argument("root")
    init.add_argument("--project", required=True)
    for name in ("verify", "check", "status"):
        p = sub.add_parser(name)
        p.add_argument("root")
        if name == "verify":
            p.add_argument("--expect-id")
    for name in ("checkpoint", "release"):
        p = sub.add_parser(name)
        p.add_argument("root")
        p.add_argument("--version", required=True)
        p.add_argument("--output", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("archive")
    restore.add_argument("destination")
    restore.add_argument("--sha256", required=True, help="Hash del recibo/destino duradero")
    restore.add_argument("--expect-id")
    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("path")
    fingerprint.add_argument("--kind", choices=("file", "tree"), default="file")
    audit = sub.add_parser("audit-archive")
    audit.add_argument("archive")
    receipt = sub.add_parser("receipt")
    receipt.add_argument("root")
    receipt.add_argument("--archive", required=True)
    receipt.add_argument("--reference", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = install(args.root, args.project)
        elif args.command == "verify":
            result = verify(args.root, args.expect_id)
        elif args.command == "status":
            state, head = head_for(args.root)
            result = {"state": state, "version": head["version"], "files": len(head["files"]),
                      "working_changes": differences(head["files"],
                                                     inventory(args.root, config_for(args.root)))}
        elif args.command == "check":
            c = config_for(args.root)
            state, head = head_for(args.root)
            validate_evidence(args.root, state, head)
            if c["project_id"] != head["project_id"]:
                fail("PROJECT_ID_CHANGED", "Identidad del proyecto alterada")
            files = inventory(args.root, c)
            result = {"inheritance": enforce_migrations(args.root, head["files"], files),
                      "issues": inspect_sources(args.root, c, files), "status": "PASS",
                      "build": "NOT_VALIDATED"}
        elif args.command in ("checkpoint", "release"):
            result = package(args.root, args.output, args.version, args.command == "release")
        elif args.command == "restore":
            if file_hash(args.archive) != args.sha256:
                fail("ARCHIVE_HASH_MISMATCH", "El archivo no coincide con la referencia duradera")
            result = extract_zip(args.archive, args.destination)
            if args.expect_id and result["snapshot_id"] != args.expect_id:
                shutil.rmtree(args.destination)
                fail("AUTHORITY_MISMATCH", "El archivo contiene otra autoridad")
        elif args.command == "fingerprint":
            result = {"kind": args.kind, "sha256": external_fingerprint(args.path, args.kind)}
        elif args.command == "audit-archive":
            result = audit_archive(args.archive)
        else:
            result = record_receipt(args.root, args.archive, args.reference)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except GuardError as e:
        print(json.dumps({"status": "FAIL", "code": e.code, "detail": str(e)}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as e:
        print(json.dumps({"status": "FAIL", "code": "IO_OR_FORMAT_ERROR",
                          "detail": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())

