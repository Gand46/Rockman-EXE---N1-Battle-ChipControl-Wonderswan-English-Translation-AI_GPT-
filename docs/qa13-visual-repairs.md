# QA13 / MANT04 — visual corrections and provenance

**Build authority:** `scripts/build_mant04.py` layered on the original QA09 editable manifest (`components/qa09/translation/en_qa09.json`). `scripts/qa13_visual_repair.py` contains the editable, deterministic 4bpp/WSC tile editors, glyph masks and write allowlists. No non-gameplay dependency or external TTF is required for the new repairs.

## Submitted issues

| Report | Resolution | Bounded affected spans |
| --- | --- | --- |
| Font mismatch in SHOP product labels | Re-rasterized `1 CHIP`, `10 CHIPS`, `INFO` using the project's documented compact 5×7 **native-style extension** instead of the earlier external font. Dynamic prices and their tiles were preserved | BG0 `0x04604C` and tiles `0x0818A0` |
| PET, SHOP, HOST TOURNEY use inconsistent fonts | SHOP, FREE BATTLE, HOST TOURNEY labels now share editable compact masks. PET menu glyph pixels stay byte-identical to its already-approved visual language and move vertically without changing their design | Maps `0x041BB2`, `0x0424B6`, `0x042938`, `0x042DBA` and associated tile banks |
| `NAME`, `ATK`, `TYPE` inconsistent | Rebuilt only 13 exclusively used sorting bar tiles using a 4×6 grid, with same pixel palette/baseline as unchanged `ID / HP / SP / CS`; no changes to cursor or their original captions | bank `0x07EC10`, IDs `0x97..0x9F`, `0xB1..0xB4` |
| PET menu lines high relative to selector | Shifted each 16px high bitmap down 6 pixels *without rerasterizing the letter shapes* or modifying the cursor | menu map `0x042DBA`; bank `0x07C330` |
| Orange detail by `TOTALCHIPS` | **Not an introduced defect.** Japanese ROM has identical map words/tile bitmaps for this header; keep it. The icon was initially misidentified as number corruption. | No modifications; proof in `evidence/qa13/native_netnavi_provenance.json` |

These are static/graphic-layer repairs. Pixel masks in `qa03/compact_display_font.json` are documented authored **native-style** glyph extensions, not the literal original Japanese glyphs. We explicitly distinguish native-style continuity from byte-for-byte preservation of the original PET lettering. Original native engine and font banks are left unchanged; no new TTF is embedded.

## Pixel and gameplay guardrails

- Repairs are deterministic and refuse a wrong QA09 MANT03 SHA-256; tile IDs must be exclusive to allowed map cells, and attributes/palette and shared tile consumer bytes are guarded.
- 2,400 non-checksum bytes changed on QA09, all inside approved graphics spans; additionally WonderSwan checksum only.
- RC6 baseline game-code differences are preserved exactly; MANT04 graphics do not overlap RC6 functional bytes.
- Independently rebuild from original Japanese ROM, verify source CRC, BPS roundtrip, checksum and expected SHA-256.
- Actual emulator captures on repaired graphical loading transitions are in `docs/evidence/qa13/`; all pixel changes should be within inspected GUI regions. Static source provenance for native orange header is separately documented.
- Save/load, all chips, all menus, and physical hardware are not certified by this bounded QA; further reports should be tracked as issues without silently widening the PASS.

## SHA-256

| Artifact | SHA-256 |
| --- | --- |
| Japanese original | `4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed` |
| QA09 MANT03 original (unchanged reference) | `d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326` |
| QA09 MANT04 ROM | `e9fcfec134135c2f129da79d20b8f42ec4e7b7051e4b3b927036731041418800` |
| QA09 MANT04 BPS | `01210be2d2571db66387e48b06f1e6176fe257f1af4e7ee044848e655c3ff69c` |
| RC6 MANT04 ROM | `3937167ede996dcb3ae59a3fa0e0a00fc720783aece66efdd059294792ff2c62` |
| RC6 MANT04 BPS | `8867456010b3b727fe558735b17f9aec3269f9593901cbf2891a4f398fbd365f` |

## Reproduce

```sh
python scripts/project.py build --source /path/to/jp_original.wsc --variant all
python scripts/project.py verify --source /path/to/jp_original.wsc
```

**Avoid loading a stale savestate and evaluating it without transitioning**: runtime VRAM may still contain old tiles until a menu reload.
