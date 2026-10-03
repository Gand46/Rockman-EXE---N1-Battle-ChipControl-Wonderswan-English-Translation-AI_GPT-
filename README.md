# Mega Man Battle Network — N1 Battle English + Chip Control

English localization and an optional Chip Control gameplay modification for **Rockman EXE N1 Battle on WonderSwan Color**.

This bundle combines **English v0.10.7-graphics-a9** with **Chip Control v0.5.8 RC6**, specifically adapted to that English release. The translation works on its own. Chip Control requires the exact A9-translated ROM.

## Included packages and patches

| File in the supplied bundle | Purpose |
|---|---|
| `Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips` | Cumulative English translation. Apply directly to the supported original Japanese ROM. Earlier translation patches are unnecessary. |
| `ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips` | Optional Chip Control add-on. Apply **after** the English A9 translation. |
| `N1Battle_English_Project_v0.10.7-graphics-a9.zip` | Editable translation manifests, graphics assets, character table, Python tools, Windows launchers, tests, and validation documentation. |
| `ChipControl_v0.5.8_RC6_EN_A9_RELEASE.zip` | Chip Control patch, compatibility documentation, checksums, screenshots, runtime reports, and a prepatched ROM in the supplied private archive. See the publication instructions below. |

The standalone IPS files are byte-identical to their corresponding copies inside the archives.

## What the English patch changes

The localization covers the catalogued story text, menus, chip information, and interface graphics. It includes an English title logo, PET menus, Program Deck, Chip Folder, Backpack, Data Library, NetNavi information, Shop, Save, class selection, Free Battle, and Host tournament interfaces.

The A9 release also incorporates the preceding typography and layout corrections:

- Dialogue with a portrait fits within **19 characters × 3 visible lines**. Battle/result text follows its own renderer limits and pointer grouping.
- Chip effect labels fit their six-character field while preserving the complete numeric value and applicable modifiers.
- Program Deck and Chip Folder headings use corrected graphics and shared-tile assignments.
- Backpack quantities use an isolated compact superscript font.
- `1 MONTH LATER...` is centered; residual Japanese pixels beneath the shared `NO CHIP SELECTED` card are removed.
- A9 restores the lower-left 8×8 portion of the first MegaMan chip beside `OK` in Program Deck, correcting an earlier beige-square artifact.

Graphics target the native **224×144** display, 8×8 tiles, packed 4-bpp data, and BGR444 palettes. Interface adjustments preserve the surrounding functional graphics and controls within the documented change ranges.

The project documentation reports **1,552/1,552 referenced text records** and **129/129 catalogued localizable graphic occurrences** translated. These figures describe the audited inventory; they do not establish that every possible playthrough or multiplayer state was exercised. The Inti Creates corporate splash logo remains Japanese intentionally. Unreferenced Japanese data is retained where removal would serve no functional purpose.

## What Chip Control changes

Chip Control modifies the battle chip-selection interface and adds a `CHIP CONTROL` label to the title screen. Its packaged evidence documents the following behavior:

| Situation | Behavior |
|---|---|
| Battle chip-selection screen | Hold **Y1** to display an **AP/SP information overlay** over the chip icons. In the packaged emulator report, Y1 is identified as `Up2`. |
| Y1 held | The overlay remains visible; the documented test holds it for 120 frames without flicker. The Navi image remains intact. |
| Y1 released | The normal chip icons return. |
| Selection confirmed | The enemy reveal phase is held for **150 frames**, approximately **1.99 seconds** in the recorded test, before battle proceeds. |

Map the emulator's **WonderSwan Y1** control to a convenient key or gamepad button. A PC keyboard arrow is not necessarily Y1 unless configured that way.

This release preserves the frozen **RC6** implementation. The discarded RC7 branch is not used. The supplied evidence reports unchanged palette 14 and SRAM during the tested battle sequence; it does not establish universal save compatibility across other versions or hardware.

The compatibility audit records seven hooks, 1,959 functional byte writes, and two checksum bytes, with zero conflicts against the English A9 base. The dedicated IPS has 167 records and 1,961 effective write bytes. The payload cave is at **ROM file offset `0x35C8A0`**; the title label uses tile IDs `0x0C3`–`0x0CC` and the two Screen2 map buffers at `0x2800`/`0x3000`. These are implementation details, not addresses users need to modify manually.

## Required ROM and patch order

Supply your own original Japanese ROM matching the supported revision exactly:

| Property | Required value |
|---|---|
| Platform | WonderSwan Color |
| Revision | Japanese Rev 1, as identified by the project tools |
| Size | **4,194,304 bytes** (4 MiB) |
| CRC32 | `1F10CA75` |
| MD5 | `d902afdadf17b452621c50a1ffda2fa9` |
| SHA-1 | `9b4786adca7b83fe66a9d4b9fd4ffaf32abe7656` |
| SHA-256 | `4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed` |

1. Apply `Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips` to the verified Japanese ROM.
2. Verify that the resulting English ROM has the A9 SHA-256 listed below.
3. Optionally apply `ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips` to that English ROM.
4. Verify the final SHA-256, then open the `.wsc` file in your WonderSwan Color emulator.

**Do not apply Chip Control directly to the Japanese ROM, an earlier English release, or RC7.** These are two sequential IPS patches, not alternative patches for the same input. IPS does not embed an input-ROM hash, so an IPS patcher accepting a file is not proof that its base is correct.

## Applying the patches

An IPS-compatible patcher can apply both files in the order above. For the first stage, the included Python tool also verifies the Japanese base and the output's WonderSwan checksum.

Extract the translation project and run the following commands from its root folder, where `tools/`, `translation/`, and `patches/` are present.

### English translation — Windows

With Python 3 available through the Windows Python launcher:

```bat
APPLY_PATCH.bat "C:\ROMs\Rockman EXE - N1 Battle (Japan).wsc" "C:\ROMs\N1Battle_English_A9.wsc"
```

### English translation — Linux / macOS

```bash
python3 tools/n1tool.py apply \
  "/path/to/Rockman EXE - N1 Battle (Japan).wsc" \
  patches/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips \
  "/path/to/N1Battle_English_A9.wsc"
```

### Chip Control add-on

Apply the Chip Control IPS with an IPS-compatible patcher, choosing `N1Battle_English_A9.wsc` as its input and a separate output file.

**The included `n1tool.py apply` command is reserved for the original Japanese input.** It rejects the English A9 ROM, so it cannot be used directly for this second stage.

The following optional Python recipe uses its IPS implementation with explicit A9 input and RC6 output hash checks. Place the English A9 ROM and the Chip Control IPS in the extracted translation project's root folder, then run this from that folder. On Windows, replace `python3` with `py -3` when running a saved Python script.

```python
from hashlib import sha256
from pathlib import Path
import sys

sys.path.insert(0, str(Path("tools").resolve()))
from n1tool import apply_ips, checksum

source_path = Path("N1Battle_English_A9.wsc")
patch_path = Path("ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips")
output_path = Path("N1Battle_English_A9_ChipControl_RC6.wsc")

expected_source = "27c189a8303ff1ba75a624ea686380c3d9bff618da2a06d8e3e1b0d8ceda53f6"
expected_patch = "c4f088078bf42b6a3e56f3b42704ffe92377c91b32a98b3a0017461c92d0540b"
expected_output = "18aa0fe6af0e49d37f135768d748941800480c2c385ddbd5ad08290d483a78e0"

source = source_path.read_bytes()
patch = patch_path.read_bytes()
if sha256(source).hexdigest() != expected_source:
    raise SystemExit("Input must be the exact English graphics-a9 ROM.")
if sha256(patch).hexdigest() != expected_patch:
    raise SystemExit("Chip Control IPS does not match this release.")
target = apply_ips(source, patch)
if sha256(target).hexdigest() != expected_output:
    raise SystemExit("Unexpected output; no ROM was written.")
stored, calculated = checksum(target)
if stored != calculated:
    raise SystemExit("Invalid WonderSwan checksum; no ROM was written.")
if output_path.exists():
    raise SystemExit("Output already exists; choose another filename.")
output_path.write_bytes(target)
print(output_path)
```

## Rebuilding the English translation

The editable A9 manifest is `translation/en_v0_10_7_graphics_a9.json`. The character table is `tables/n1battle_jp.tbl`. The builder verifies the source ROM and guarded source fragments before writing translated data.

On Windows:

```bat
BUILD_PATCH.bat "C:\ROMs\Rockman EXE - N1 Battle (Japan).wsc"
```

On Linux or macOS, from the extracted translation project's root:

```bash
python3 tools/n1tool.py build \
  "/path/to/Rockman EXE - N1 Battle (Japan).wsc" \
  translation/en_v0_10_7_graphics_a9.json \
  build/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.wsc \
  --table tables/n1battle_jp.tbl \
  --ips build/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9-rebuilt.ips \
  --report build/build_v0_10_7_graphics_a9-rebuilt.json
```

The English ROM must match the A9 hash below. This builds the translation; apply Chip Control afterward if desired.

The Chip Control README names `tools/build_v058_rc6_en_a9.py`, `tests/test_v058_rc6_en_a9.py`, and `43_BUILD_RC6_EN_A9.bat`, but **those files are absent from the supplied Chip Control archive**. This bundle therefore supports applying the existing Chip Control IPS, but does not contain its documented source builder and test suite.

## Release identities

| Artifact | SHA-256 |
|---|---|
| Original Japanese ROM | `4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed` |
| English A9 ROM, before Chip Control | `27c189a8303ff1ba75a624ea686380c3d9bff618da2a06d8e3e1b0d8ceda53f6` |
| English A9 IPS | `9a1bf3430a4e213eb10d3a1f340532dc43f4a7554fad83821263c21bef9e9cb5` |
| Chip Control RC6 for A9 IPS | `c4f088078bf42b6a3e56f3b42704ffe92377c91b32a98b3a0017461c92d0540b` |
| English A9 + Chip Control RC6 ROM | `18aa0fe6af0e49d37f135768d748941800480c2c385ddbd5ad08290d483a78e0` |

The final combined ROM is 4 MiB, with documented CRC32 `3543C4AB` and WonderSwan checksum `0x1BE8`. The English A9 checksum is documented as `0xB86D`.

## Validation evidence and limits

The supplied documentation records translation checks, native screenshots, and regression comparisons, including `docs/GRAPHICS_ADVANCE_9.md`, `build/build_v0_10_7_graphics_a9.json`, and `docs/runtime_graphics_advances/advance_9_gate_final/`.

Chip Control includes `docs/COMPATIBILITY_AUDIT_RC6_EN_A9.md`, `docs/FINAL_AUDIT_v058_RC6_EN_A9.txt`, `evidence/runtime_report.json`, `evidence/battle_runtime_report.json`, and title/battle acceptance screenshots. These report Mesen 2.1.1 testing from `NEW GAME` to a real Free Battle using normal controls, stable overlay rendering, icon restoration, and the reveal delay.

For this README, the supplied IPS copies were compared by SHA-256; the packaged combined ROM's SHA-256 and stored/calculated checksum were checked; and the Chip Control patch writes were confirmed to agree with that ROM. Emulator testing and a fresh build from the original Japanese ROM were **not rerun** while preparing this document. Hardware and complete multiplayer certification are not established by this inspection.

## Preparing this bundle for GitHub

Publish the two IPS patches, this README, and the selected project sources and documentation. Keep the translation project's `LICENSE.txt` and applicable notices with its code.

**The supplied `MegamanBN_GP_Mods.zip` is not ready to upload unchanged:** its nested Chip Control release includes this complete game image:

```text
roms/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9_ChipControl_v0.5.8_RC6.wsc
```

Remove that ROM before publishing, and recreate any release archive containing it. Do not upload the original outer ZIP or the unmodified Chip Control ZIP. Keep locally generated ROMs, BIOS files, private saves, and savestates outside the public repository. ROM hashes may remain in documentation for verification.

The supplied translation `README_ES.md` still contains some A7 command examples. Use the **A9 filenames and manifest in this README**, or update those older examples before publication. Package-local Chip Control documentation also refers to some evidence under `docs/evidence/`; the actual supplied reports and acceptance images are under `evidence/`.

## License and credits

Rockman EXE N1 Battle, Mega Man, and the original game assets and trademarks belong to their respective rights holders. This is an unofficial fan project.

**Original Chip Control project:** [Prof9/MegaManBCC-ChipControl](https://github.com/Prof9/MegaManBCC-ChipControl), a mod for the **Game Boy Advance** version of *Mega Man Battle Chip Challenge*. Its [README](https://github.com/Prof9/MegaManBCC-ChipControl/blob/main/readme.md) credits **Prof. 9** with planning and programming, and **weenie** with Japanese translation. Please retain that attribution when discussing the original mod and link to its repository.

The original repository distributes its own source under the [MIT License (copyright © 2022 Prof. 9)](https://github.com/Prof9/MegaManBCC-ChipControl/blob/main/license.txt). Its GBA source and patch are distinct from the **WonderSwan Color RC6-for-A9 IPS** in this bundle. The supplied WSC archive does not document who wrote its port or adaptation, or establish which portions, if any, derive from the GBA source; this credit does not assign the WSC implementation to Prof. 9 or weenie.

The translation project includes an **MIT license limited to original project code and project-authored translation data**. It does not grant rights to the ROM, original game assets, or other third-party materials, including referenced fonts. The supplied Chip Control archive has no separate license file; its redistribution terms should not be inferred from the translation project's MIT license.

Preserve the contributors' notices supplied with the projects. If original Prof. 9 source or other MIT-licensed material is incorporated into a public release, include its copyright and license notice with that material.
