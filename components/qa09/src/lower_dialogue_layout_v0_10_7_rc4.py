#!/usr/bin/env python3
"""Reflow narrow lower-dialogue pages for v0.10.7 RC4.

The original dynamic dialogue font advances in fixed 8x16-pixel cells.  A
lower box that reserves the 64-pixel portrait area therefore has 19 visible
columns and three rows.  RC3 contains 71 literal lines of exactly 20 columns.

This tool transforms the immutable RC3 manifest into a separate RC4 manifest.
It preserves the exact wording whenever word reflow is sufficient and applies
eleven reviewed, minimal condensations where the original wording cannot fit
within three 19-column rows.  It also proves that every encoded entry remains
inside its original in-place byte span.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SOURCE_MANIFEST_SHA256 = (
    "2a0d1096a2a898c7fa4191b733da3abaab89aff284de5592fc1e8b19b81e07f1"
)
SOURCE_VERSION = "0.10.7-rc3"
OUTPUT_VERSION = "0.10.7-rc4"
MAX_COLUMNS = 19
MAX_LINES = 3
EXPECTED_SOURCE_OVERFLOW_LINES = 71
EXPECTED_AFFECTED_PAGES = 67
EXPECTED_AFFECTED_ENTRIES = 52
EXPECTED_CONDENSED_PAGES = 11

PORTRAIT_PREFIX_RE = re.compile(r"^(?:\[PORTRAIT:[0-9A-Fa-f]{2}\])+")
TAG_RE = re.compile(r"\[[^]]+\]")


@dataclass(frozen=True)
class Condensation:
    entry_id: str
    page: int
    expected_lines: tuple[str, ...]
    replacement_lines: tuple[str, ...]


# These are the only pages whose exact RC3 wording cannot be redistributed in
# three 19-column rows.  Each replacement was reviewed independently.
CONDENSATIONS = (
    Condensation(
        "manual_data_and_capacity", 8,
        ("Within that limit,", "use any number of", "BattleChips, even 0."),
        ("Within that limit,", "use any number of", "BattleChips, even 0"),
    ),
    Condensation(
        "manual_battle_flow", 2,
        ("Drawn chips act in", "highest-SP order and", "hit enemy NaviChip."),
        ("Drawn chips act in", "highest-SP order;", "hit enemy NaviChip."),
    ),
    Condensation(
        "manual_analysis_and_code", 3,
        ("On Program Deck,", "press START to see", "odds or NetNavi code"),
        ("On Program Deck,", "press START to see", "odds or Navi code"),
    ),
    Condensation(
        "novice_tournament_briefing", 3,
        ("Use all your chips", "in the Program Deck.", "You can't lose!"),
        ("Use all your chips", "in Program Deck.", "You can't lose!"),
    ),
    Condensation(
        "novice_tournament_briefing", 7,
        ("Reach top 4 in every", "class tournament to", "move up a class."),
        ("Reach top 4 in each", "class tournament to", "move up a class."),
    ),
    Condensation(
        "guts_round_1_intro", 2,
        ("First NetBattle with", "a Program Deck.", "Go easy on me!"),
        ("First battle with", "a Program Deck.", "Go easy on me!"),
    ),
    Condensation(
        "quick_round_2_intro", 2,
        ("You improve at what", "you love. NetBattles", "are great fun!"),
        ("You improve at what", "you love. Battles", "are great fun!"),
    ),
    Condensation(
        "east_semifinal_intro", 2,
        ("I'll show you", "Netopia's finest", "skills and teamwork!"),
        ("I'll show you", "Netopia's finest", "skill and teamwork!"),
    ),
    Condensation(
        "west_semifinal_intro", 2,
        ("Chaud isn't the only", "skilled Official", "NetBattler!"),
        ("Chaud isn't alone!", "I'm an Official", "NetBattler too!"),
    ),
    Condensation(
        "master_round_4_intro", 2,
        ("Real battle data is", "vital to researching", "Navis and chips."),
        ("Real battle data is", "vital for research", "Navis and chips."),
    ),
    Condensation(
        "master_semifinal_intro", 2,
        ("Beat my Navi and", "you'll fear nothing!", "If you can, that is."),
        ("Beat my Navi and", "you'll fear no one!", "If you can, that is"),
    ),
)

CONDENSATION_BY_PAGE = {
    (item.entry_id, item.page): item for item in CONDENSATIONS
}


# Exact-wording pages for which a small explicit distribution reads better
# than generic first-fit wrapping.  These do not count as condensations.
EXACT_LAYOUT_OVERRIDES: dict[tuple[str, int], tuple[str, ...]] = {
    ("tutorial_healing_tournament", 5): (
        "Yai, you know a", "lot!", "about BattleChipGP!",
    ),
    ("block_round_1_intro", 2): (
        "Go, GutsMan!", "Battle routine,", "set!",
    ),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def visible_text(text: str) -> str:
    """Return literal visible characters, excluding engine tags."""
    return TAG_RE.sub("", text)


def visible_lines(page: str) -> tuple[str, ...]:
    return tuple(visible_text(line) for line in page.split("[LINE]"))


def normalized_page_text(lines: Iterable[str]) -> str:
    return " ".join(lines)


def first_fit_wrap(text: str, width: int = MAX_COLUMNS) -> tuple[str, ...]:
    words = text.split()
    if not words:
        return ("",)
    output: list[str] = []
    current = words[0]
    if len(current) > width:
        raise ValueError(f"word exceeds {width} columns: {current!r}")
    for word in words[1:]:
        if len(word) > width:
            raise ValueError(f"word exceeds {width} columns: {word!r}")
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            output.append(current)
            current = word
    output.append(current)
    return tuple(output)


def page_prefix(page: str) -> str:
    match = PORTRAIT_PREFIX_RE.match(page)
    return match.group(0) if match else ""


def validate_layout(lines: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(lines)
    if len(result) > MAX_LINES:
        raise ValueError(f"{label}: {len(result)} lines exceeds {MAX_LINES}")
    overflow = [(index + 1, line) for index, line in enumerate(result) if len(line) > MAX_COLUMNS]
    if overflow:
        raise ValueError(f"{label}: lines exceed {MAX_COLUMNS} columns: {overflow}")
    return result


def load_n1tool(root: Path) -> Any:
    path = root / "src" / "n1tool.py"
    spec = importlib.util.spec_from_file_location("n1tool_dialogue_rc4", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def serialize_manifest(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def transform_manifest(
    source_payload: bytes,
    encode: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    actual_source_hash = sha256(source_payload)
    if actual_source_hash != SOURCE_MANIFEST_SHA256:
        raise ValueError(
            "RC4 lower-dialogue transform requires the immutable RC3 manifest; "
            f"got SHA-256 {actual_source_hash}"
        )
    source = json.loads(source_payload)
    if source.get("project_version") != SOURCE_VERSION:
        raise ValueError("source manifest project_version is not RC3")

    output = json.loads(source_payload)
    source_entries = {entry["id"]: entry for entry in source["entries"]}
    output_entries = {entry["id"]: entry for entry in output["entries"]}
    if len(source_entries) != len(source["entries"]) or set(source_entries) != set(output_entries):
        raise ValueError("entry IDs are not unique and stable")

    affected_entries: set[str] = set()
    affected_pages: list[dict[str, Any]] = []
    source_overflow_lines = 0
    exact_pages = 0
    condensed_pages = 0

    for entry_id, source_entry in source_entries.items():
        output_entry = output_entries[entry_id]
        source_pages = str(source_entry["translation"]).split("[WAIT]")
        output_pages = list(source_pages)
        entry_changed = False

        for page_number, source_page in enumerate(source_pages, 1):
            old_lines = visible_lines(source_page)
            old_overflow = sum(len(line) > MAX_COLUMNS for line in old_lines)
            if old_overflow == 0:
                continue
            source_overflow_lines += old_overflow
            key = (entry_id, page_number)
            prefix = page_prefix(source_page)
            body = source_page[len(prefix):]
            if TAG_RE.search(body.replace("[LINE]", "")):
                raise ValueError(f"{entry_id} page {page_number}: unexpected tag in reflow body")

            condensation = CONDENSATION_BY_PAGE.get(key)
            if condensation is not None:
                if old_lines != condensation.expected_lines:
                    raise ValueError(
                        f"{entry_id} page {page_number}: condensation source changed; "
                        f"expected {condensation.expected_lines}, got {old_lines}"
                    )
                new_lines = condensation.replacement_lines
                mode = "condensed"
                condensed_pages += 1
            else:
                joined = normalized_page_text(old_lines)
                new_lines = EXACT_LAYOUT_OVERRIDES.get(key, first_fit_wrap(joined))
                if normalized_page_text(new_lines) != joined:
                    raise AssertionError(f"{entry_id} page {page_number}: exact reflow changed wording")
                mode = "exact_reflow"
                exact_pages += 1

            new_lines = validate_layout(new_lines, f"{entry_id} page {page_number}")
            output_pages[page_number - 1] = prefix + "[LINE]".join(new_lines)
            affected_pages.append({
                "entry_id": entry_id,
                "entry_offset": source_entry["offset"],
                "entry_span_bytes": source_entry["length"],
                "page": page_number,
                "mode": mode,
                "old_lines": list(old_lines),
                "new_lines": list(new_lines),
                "old_widths": [len(line) for line in old_lines],
                "new_widths": [len(line) for line in new_lines],
            })
            entry_changed = True

        if entry_changed:
            output_entry["translation"] = "[WAIT]".join(output_pages)
            affected_entries.add(entry_id)

    if source_overflow_lines != EXPECTED_SOURCE_OVERFLOW_LINES:
        raise AssertionError(
            f"expected {EXPECTED_SOURCE_OVERFLOW_LINES} RC3 overflow lines, "
            f"found {source_overflow_lines}"
        )
    if len(affected_pages) != EXPECTED_AFFECTED_PAGES:
        raise AssertionError(
            f"expected {EXPECTED_AFFECTED_PAGES} affected pages, found {len(affected_pages)}"
        )
    if len(affected_entries) != EXPECTED_AFFECTED_ENTRIES:
        raise AssertionError(
            f"expected {EXPECTED_AFFECTED_ENTRIES} affected entries, found {len(affected_entries)}"
        )
    if condensed_pages != EXPECTED_CONDENSED_PAGES:
        raise AssertionError(
            f"expected {EXPECTED_CONDENSED_PAGES} condensed pages, found {condensed_pages}"
        )

    output["project_version"] = OUTPUT_VERSION
    output["scope"] = (
        "v0.10.7 RC4 lower-dialogue layout correction generated reproducibly "
        "from the immutable RC3 manifest. All portrait-backed lower dialogue "
        "is limited to three 8x16 rows of nineteen visible cells. Fifty-six "
        "pages preserve exact wording through line reflow; eleven pages use "
        "reviewed minimal condensations. Offsets, spans, controls, portraits, "
        "dynamic fields, binary assets and every unrelated RC3 change remain "
        "unchanged."
    )

    capacity_rows = []
    remaining_overflow = []
    vertical_overflow = []
    for entry in output["entries"]:
        translation = str(entry["translation"])
        for page_number, page in enumerate(translation.split("[WAIT]"), 1):
            lines = visible_lines(page)
            if len(lines) > MAX_LINES:
                vertical_overflow.append((entry["id"], page_number, len(lines)))
            for line_number, line in enumerate(lines, 1):
                if len(line) > MAX_COLUMNS:
                    remaining_overflow.append(
                        (entry["id"], page_number, line_number, len(line), line)
                    )
        words = n1tool_words = len(encode_text(translation, encode)) + 1
        required_bytes = n1tool_words * 2
        span_bytes = int(str(entry["length"]), 0) if isinstance(entry["length"], str) else int(entry["length"])
        if required_bytes > span_bytes:
            raise ValueError(
                f"{entry['id']}: encoded RC4 payload needs {required_bytes} bytes, "
                f"span is {span_bytes}"
            )
        if entry["id"] in affected_entries:
            source_translation = str(source_entries[entry["id"]]["translation"])
            source_bytes = (len(encode_text(source_translation, encode)) + 1) * 2
            capacity_rows.append({
                "entry_id": entry["id"],
                "offset": entry["offset"],
                "span_bytes": span_bytes,
                "source_payload_bytes": source_bytes,
                "rc4_payload_bytes": required_bytes,
                "rc4_free_bytes": span_bytes - required_bytes,
            })

    if remaining_overflow:
        raise AssertionError(f"RC4 literal overflow remains: {remaining_overflow[:3]}")
    if vertical_overflow:
        raise AssertionError(f"RC4 vertical overflow remains: {vertical_overflow[:3]}")

    report = {
        "format": "n1-lower-dialogue-layout-report-v0.10.7-rc4",
        "status": "PASS",
        "source_manifest": {
            "version": SOURCE_VERSION,
            "sha256": actual_source_hash,
        },
        "output_version": OUTPUT_VERSION,
        "geometry": {
            "glyph_cell_pixels": [8, 16],
            "portrait_reserved_pixels": 64,
            "narrow_visible_pixels": 152,
            "max_columns": MAX_COLUMNS,
            "max_lines": MAX_LINES,
        },
        "source_overflow_lines": source_overflow_lines,
        "affected_pages": len(affected_pages),
        "affected_entries": len(affected_entries),
        "exact_reflow_pages": exact_pages,
        "condensed_pages": condensed_pages,
        "remaining_literal_overflow_lines": 0,
        "remaining_vertical_overflow_pages": 0,
        "entry_capacity": capacity_rows,
        "pages": affected_pages,
    }
    return output, report


def encode_text(text: str, encode: dict[str, int]) -> list[int]:
    """Local strict encoder equivalent to n1tool.encode_text."""
    words: list[int] = []
    cursor = 0
    controls = {"LINE": 0x0800, "WAIT": 0x4000, "END": 0x8000}
    while cursor < len(text):
        if text[cursor] == "[":
            close = text.find("]", cursor + 1)
            if close < 0:
                raise ValueError(f"unclosed tag in translation: {text!r}")
            tag = text[cursor + 1:close]
            upper = tag.upper()
            if upper in controls:
                words.append(controls[upper])
            elif upper.startswith("RAW:"):
                words.append(int(tag.split(":", 1)[1], 16))
            elif upper.startswith("PORTRAIT:"):
                words.append(0x0900 | int(tag.split(":", 1)[1], 16))
            else:
                raise ValueError(f"unsupported translation tag [{tag}]")
            cursor = close + 1
            continue
        character = text[cursor]
        if character not in encode:
            raise ValueError(f"character {character!r} is not present in the table")
        words.append(encode[character])
        cursor += 1
    return words


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--source",
        type=Path,
        default=root / "translation" / "lineage/en_v0_10_7_rc3.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "translation" / "lineage/en_v0_10_7_rc4_dialogue.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=root / "translation" / "assets" / "lower_dialogue_layout_report_v0_10_7_rc4.json",
    )
    args = parser.parse_args()

    n1tool = load_n1tool(root)
    _, encode = n1tool.load_table(root / "tables" / "n1battle_jp.tbl")
    output, report = transform_manifest(args.source.read_bytes(), encode)
    output_payload = serialize_manifest(output)
    report["output_manifest"] = {
        "file": args.output.name,
        "sha256": sha256(output_payload),
        "bytes": len(output_payload),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_payload)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "output_sha256": report["output_manifest"]["sha256"],
        "source_overflow_lines": report["source_overflow_lines"],
        "affected_pages": report["affected_pages"],
        "affected_entries": report["affected_entries"],
        "exact_reflow_pages": report["exact_reflow_pages"],
        "condensed_pages": report["condensed_pages"],
        "remaining_literal_overflow_lines": report["remaining_literal_overflow_lines"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
