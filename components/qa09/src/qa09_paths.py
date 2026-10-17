"""Locate the verified QA08 parent produced by a standalone QA09 build.

QA09's builder embeds its parent at build/qa09/qa08_base; the historic
build/qa08 location is optional. Never silently accept a mismatching ROM.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

QA08_SHA256 = "41d7fc75e327ad15b72c7f6fc7119e031d6af8cfdb1527eb547b3c86d7cc32dc"


def qa08_rom(root: Path) -> Path:
    root = Path(root)
    candidates = [
        root / "build/qa08/Rockman_N1_English_QA08.wsc",
        root / "build/qa09/qa08_base/Rockman_N1_English_QA08.wsc",
    ]
    for path in candidates:
        if path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != QA08_SHA256:
                raise ValueError(f"QA08 candidate has unexpected SHA256: {path} = {actual}")
            return path
    raise FileNotFoundError(
        "QA08 parent not found. Run tools/build_qa09.py --source <original JP>. "
        "Expected either build/qa08/ or build/qa09/qa08_base/."
    )
