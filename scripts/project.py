#!/usr/bin/env python3
"""Single entry point for the organized N1 repository; never overwrites a source ROM.

QA09 uses its editable cumulative manifest. Chip Control is an opt-in binary
adaptation with pinned historical inputs, not a source-complete RC6 engine.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from urllib.parse import unquote, urlsplit
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "components/qa09"
CC = ROOT / "components/chip-control"
MANIFEST = ROOT / "maintenance/source-manifest.json"
IGNORED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
BANNED = {".wsc", ".ws", ".gba", ".srm", ".sav", ".sram", ".ram", ".state",
          ".so", ".dll", ".exe", ".dylib", ".ttf", ".otf", ".woff", ".woff2", ".pyc"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def config() -> dict:
    return json.loads((ROOT / "project.json").read_text(encoding="utf-8"))


def json_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tracked_files(root: Path = ROOT) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()
                  and not set(p.relative_to(root).parts) & IGNORED)


def inventory(root: Path = ROOT) -> dict:
    return {p.relative_to(root).as_posix(): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
            for p in tracked_files(root)
            if p.relative_to(root).as_posix() != "maintenance/source-manifest.json"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"Cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def qa_modules():
    sys.path.insert(0, str(QA / "src"))
    import n1tool
    from build_qa07 import bps
    from continuity import apply_bps
    return n1tool, bps, apply_bps


def original(path: Path) -> bytes:
    data = path.read_bytes()
    c = config()["original"]
    require(len(data) == c["bytes"] and sha(data) == c["sha256"], "Wrong original Japanese ROM (size or SHA-256)")
    return data


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.links.append(v)


def documentation_links() -> dict:
    """Check maintained documentation, not archived narrative/embedded history."""
    paths = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
    paths += list((ROOT / "components").glob("*/README.md"))
    paths += list((ROOT / "patches").rglob("*.md"))
    paths += [ROOT / "docs/reports/index.html"]
    checked = 0; missing = []
    for p in paths:
        if not p.is_file(): continue
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".html":
            parser = Links(); parser.feed(text); links = parser.links
        else:
            text = re.sub(r"```.*?```", "", text, flags=re.S)
            links = re.findall(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", text)
        for link in links:
            u = urlsplit(link)
            if u.scheme or u.netloc or not u.path: continue
            dst = (p.parent / unquote(u.path)).resolve()
            if not dst.exists(): missing.append({"from":p.relative_to(ROOT).as_posix(), "to": link})
            checked += 1
    require(not missing, "Broken maintained documentation links: " + json.dumps(missing))
    return {"local_links_checked": checked, "broken_local_links": 0,
            "historical_embedded_reports": "preserved as original evidence, not current instructions"}


def check(snapshot: bool = True) -> dict:
    files = tracked_files(); names = [p.relative_to(ROOT).as_posix() for p in files]
    require(len({n.casefold() for n in names}) == len(names), "Case-insensitive filename collision")
    require(not any(p.is_symlink() for p in files), "Symlinks are not part of this portable source package")
    bad = [n for n in names if Path(n).suffix.lower() in BANNED or re.search(r"\.state\d+$", n, re.I)]
    require(not bad, "Prohibited distributable files: " + str(bad))
    for p in files:
        if p.suffix == ".py":
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    c = config()
    for v in c["variants"].values():
        data = (ROOT / v["patch"]).read_bytes()
        require(sha(data) == v["bps_sha256"], f"Published patch mismatch: {v['patch']}")
    m = json.loads((QA / "translation/en_qa09.json").read_text(encoding="utf-8"))
    require(m["source_sha256"] == c["original"]["sha256"], "Manifest source mismatch")
    for e in m["binary_entries"]:
        p = (QA / "translation" / e["asset"]).resolve()
        require(p.is_relative_to((QA / "translation").resolve()), "Asset outside translation tree")
        data = p.read_bytes()
        require(len(data) == int(e["length"],0) if isinstance(e["length"],str) else len(data)==e["length"], f"Asset length: {e['id']}")
        if e.get("asset_sha256"):
            require(sha(data)==e["asset_sha256"], f"Asset hash: {e['id']}")
    result = {"status":"PASS", "tracked_files":len(files), "root_files":len(list(ROOT.glob('*')))-sum(p.is_dir() for p in ROOT.glob('*')),
              "published_patches":2, "manifest_text_entries":len(m["entries"]), "manifest_binary_entries":len(m["binary_entries"]),
              "prohibited_files":0, "symlinks":0, "case_collisions":0, "python_syntax":"PASS"}
    result.update(documentation_links())
    if snapshot:
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        got = inventory()
        bad = sorted(k for k in set(expected)|set(got) if expected.get(k)!=got.get(k))
        require(not bad, "Source snapshot drift; inspect intentional edits before manifest refresh: " + str(bad[:15]))
        result["source_snapshot"]="PASS"
    return result


def output_guard(out: Path, source: Path) -> Path:
    out = out.resolve()
    require(not out.is_relative_to(QA / "translation"), "Output cannot be inside editable resources")
    if out.is_relative_to(ROOT):
        require("build" in out.relative_to(ROOT).parts or "dist" in out.relative_to(ROOT).parts,
                "Repository output must be under an ignored build/ or dist/ directory")
    require(source.resolve() != out, "Output equals input")
    return out


def build(source: Path, variant: str, out: Path | None = None, modified: bool = False) -> dict:
    require(not modified or variant == "qa09", "Edited QA09 is not eligible for the pinned RC6 adapter")
    raw = original(source); n1, make_bps, apply_bps = qa_modules(); c = config()
    out = output_guard(out or ROOT/"build", source)
    before = sha(source.read_bytes()); built = {}
    targets = ["qa09","chip-control"] if variant == "all" else [variant]
    # QA09 is built from editable sources even when the only requested output is RC6.
    mf = QA/"translation/en_qa09.json"
    m = json.loads(mf.read_text(encoding="utf-8")); _, encoder = n1.load_table(QA/"tables/n1battle_jp.tbl")
    qa09, entries = n1.patch_entries(raw, m, encoder, mf.parent)
    qa_patch = make_bps(raw, qa09)
    require(apply_bps(raw, qa_patch)==qa09,"QA09 BPS roundtrip mismatch")
    if not modified:
        require(sha(qa09)==c["variants"]["qa09"]["rom_sha256"], "QA09 differs from pinned release; use --allow-modified for an intentional QA09 development build")
        require(sha(qa_patch)==c["variants"]["qa09"]["bps_sha256"], "QA09 BPS differs from published patch")
    for key in targets:
        v = c["variants"][key]
        if key == "qa09":
            data, patch, details = qa09, qa_patch, {"source":"editable manifest + resource files", "entry_count":len(entries)}
        else:
            rc = load_module("rc6_adapter", CC/"src/verify_and_build_experimental.py")
            data, details = rc.analyse(raw, qa_patch,
                (CC/"vendor/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips").read_bytes(),
                (CC/"vendor/ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips").read_bytes())
            patch = rc.build_bps(raw,data)
            require(rc.apply_bps(raw,patch)==data,"RC6 roundtrip mismatch")
            require(sha(data)==v["rom_sha256"] and sha(patch)==v["bps_sha256"],"RC6 output differs from pinned experiment")
        stored, calculated = n1.checksum(data)
        require(stored==calculated,"Invalid WonderSwan checksum")
        dest = out/key; dest.mkdir(parents=True,exist_ok=True)
        name = Path(v["patch"]).stem + ("_DEV" if modified else "")
        rom = dest/(name+".wsc"); bps = dest/(name+".bps")
        require(source.resolve() not in (rom.resolve(),bps.resolve()),"Source ROM would be overwritten")
        rom.write_bytes(data); bps.write_bytes(patch)
        record = {"status":"DEVELOPMENT_OUTPUT_NOT_RELEASE" if modified else "PASS_EXACT_REBUILD",
                  "rom":str(rom),"rom_sha256":sha(data),"bps":str(bps),"bps_sha256":sha(patch),
                  "checksum":f"0x{stored:04X}","details":details,"runtime_retested":False}
        json_write(dest/"build.json",record); built[key]=record
    require(sha(source.read_bytes())==before,"Original source changed during build")
    return {"status":"PASS", "source_unchanged":True, "variants":built}


def legacy_rebuild(source: Path) -> dict:
    """Replay the inherited generator pipeline in isolation; never rewrite active edits."""
    before=inventory()
    (ROOT/"build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lineage-",dir=ROOT/"build") as tmp:
        working=Path(tmp)/"qa09"
        shutil.copytree(QA,working,ignore=shutil.ignore_patterns("build","__pycache__"))
        log=ROOT/"build/legacy-regeneration.log"
        with log.open('w',encoding="utf-8") as stream:
            proc=subprocess.run([sys.executable,str(working/"src/build_qa09.py"),"--source",str(source.resolve())],cwd=working,
                                stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        require(proc.returncode==0, f"Inherited generator pipeline failed; see {log}")
        v=config()["variants"]["qa09"]
        rom=working/"build/qa09/Rockman_N1_English_QA09.wsc"
        patch=rom.with_suffix('.bps')
        require(sha(rom.read_bytes())==v["rom_sha256"] and sha(patch.read_bytes())==v["bps_sha256"],"Inherited regeneration changed release output")
    require(inventory()==before,"Regeneration modified tracked source")
    return {"status":"PASS", "mode":"original QA04-QA09 generators in isolated source tree", "active_sources_unchanged":True,
            "rom_sha256":v["rom_sha256"],"bps_sha256":v["bps_sha256"]}


class CountingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = 0
    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes += 1


def tests(source: Path | None) -> dict:
    if source:
        raw=original(source); os.environ["CONTINUITY_INPUT_JP"]=str(source.resolve())
        # Private compatibility fixtures for inherited tests. These never ship.
        result=build(source,"qa09",QA/"build")
        v=result["variants"]["qa09"]
        n1, _, apply_bps=qa_modules()
        parent=apply_bps(raw,(QA/"tests/fixtures/patches/Rockman_N1_English_QA08.bps").read_bytes())
        p=QA/"build/qa09/qa08_base/Rockman_N1_English_QA08.wsc";p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(parent)
    else:
        os.environ.pop("CONTINUITY_INPUT_JP", None)
    logdir=ROOT/"build/test-logs";logdir.mkdir(parents=True,exist_ok=True)
    results={}
    for label, directory in [("qa09",QA/"tests"),("chip-control",CC/"tests"),("repository",ROOT/"tests")]:
        suite=unittest.TestLoader().discover(str(directory),pattern="test_*.py",top_level_dir=str(directory))
        with (logdir/(label+".log")).open('w',encoding="utf-8") as stream:
            res=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=CountingResult).run(suite)
        results[label]={"run":res.testsRun,"passed":res.successes,
                        "failures":len(res.failures),"errors":len(res.errors),
                        "skipped":[{"test":str(t),"reason":reason} for t,reason in res.skipped]}
        require(res.testsRun >= {"qa09": 60, "chip-control": 7, "repository": 12}[label], f"Missing {label} tests")
        require(res.wasSuccessful(),f"{label} test failure: see build/test-logs/{label}.log")
    return {"status":"PASS", "source_rom_provided":bool(source),"suites":results,"runtime_retested":False}


def package(path: Path) -> dict:
    check(snapshot=True)
    path=path.resolve();require(not path.is_relative_to(ROOT) or "dist" in path.relative_to(ROOT).parts,"ZIP must be outside source or in dist/")
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in tracked_files():
            info=zipfile.ZipInfo("Rockman_N1/"+p.relative_to(ROOT).as_posix(),(2026,10,16,0,0,0))
            info.create_system=3;info.external_attr=(0o100755 if p.suffix in ('.command','.sh') else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
    with zipfile.ZipFile(path) as z:require(z.testzip() is None,"ZIP integrity error")
    return {"status":"PASS","zip":str(path),"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}


def verify_history(archive: Path) -> dict:
    migration=json.loads((ROOT/"maintenance/migration.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(archive) as z:
        for e in migration["entries"]:
            if e.get("archive_path"):
                data=z.read("Rockman_N1_History/"+e["archive_path"])
            else:
                data=(ROOT/e["repository_path"]).read_bytes()
            require(sha(data)==e["original_sha256"],f"Missing original bytes: {e['original']}")
    return {"status":"PASS","original_files_verified":len(migration["entries"]),"missing_originals":0}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest="command",required=True)
    p=sub.add_parser("check",help="Check layout, links, patch identities and source inventory")
    p.add_argument("--structure-only",action="store_true",help="Skip source snapshot comparison for intentional edits")
    p=sub.add_parser("build",help="Rebuild from editable QA09 resources; no source files rewritten")
    p.add_argument("--source",type=Path,required=True);p.add_argument("--variant",choices=("qa09","chip-control","all"),default="qa09")
    p.add_argument("--output",type=Path);p.add_argument("--allow-modified",action="store_true")
    p=sub.add_parser("test",help="Run unit/structural tests, clearly reporting omitted private fixtures")
    p.add_argument("--source",type=Path)
    p=sub.add_parser("verify",help="Check, rebuild both, replay generator pipeline, and run tests")
    p.add_argument("--source",type=Path,required=True)
    p=sub.add_parser("snapshot",help="Explicitly accept reviewed source edits into the integrity inventory")
    p=sub.add_parser("package",help="Create deterministic ZIP, excluding build/ and private data")
    p.add_argument("--output",type=Path,required=True)
    p=sub.add_parser("verify-history",help="Verify retention of every original file using the companion archive")
    p.add_argument("--archive",type=Path,required=True)
    a=ap.parse_args()
    try:
        if a.command=="snapshot":
            check(snapshot=False); json_write(MANIFEST,{"schema":1,"files":inventory()}); result={"status":"PASS","snapshot":"maintenance/source-manifest.json"}
        elif a.command=="check":result=check(not a.structure_only)
        elif a.command=="build":result=build(a.source,a.variant,a.output,a.allow_modified)
        elif a.command=="test":result=tests(a.source)
        elif a.command=="verify":
            before=inventory()
            result={"status":"PASS","structure":check(),"builds":build(a.source,"all"),
                    "generator_pipeline":legacy_rebuild(a.source),"tests":tests(a.source),"runtime_retested":False}
            require(inventory()==before,"Verification changed tracked source")
            result["source_tree_unchanged"]=True
            json_write(ROOT/"build/verification.json",result)
        elif a.command=="package":result=package(a.output)
        else:result=verify_history(a.archive)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,AssertionError,subprocess.TimeoutExpired,unittest.SkipTest) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)},ensure_ascii=False),file=sys.stderr);return 1

if __name__=="__main__":raise SystemExit(main())
