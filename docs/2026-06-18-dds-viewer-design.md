# DDS Viewer — Design Spec

Date: 2026-06-18
Status: Approved design — ready for implementation plan

## Goal

A lightweight desktop viewer for War of Rights (CryEngine) DDS textures. Run it, drag a
`.dds` file onto the window, see the full-resolution image, zoom/pan to inspect it, isolate
color channels, and view normal maps correctly. Drag in another file and it replaces the view.
The loop is: open once, drop many.

## Validated Findings (from feasibility probes)

These were confirmed empirically against real files in this Mods folder, not assumed:

- War of Rights textures are **CryEngine split DDS**. The dropped `.dds` is only ~300 bytes:
  a DX10 header plus the smallest mip (≈4×4). The real full-resolution pixel data lives in
  sibling files `name.dds.1 … name.dds.N`, where the **highest-numbered** file is mip 0
  (full res). Example: `Parrott_Rifled_diff.dds` (316 B) → `…dds.6` (512 KB) = 1024×1024 mip 0.
- The base header uses a **DX10 / DXGI** format code. Pillow refuses several of these
  (e.g. DXGI 72 = `BC1_UNORM_SRGB` → `NotImplementedError: Unimplemented DXGI format 72`).
- Fix that works: **rewrite the header to a legacy FourCC**. BC1/BC2/BC3/BC4/BC5 sRGB and
  UNORM blocks are byte-identical to legacy `DXT1`/`DXT3`/`DXT5`/`ATI1`/`ATI2`, so swapping the
  pixel-format to FourCC lets Pillow decode them. BC7 keeps its DX10 header (Pillow 11 decodes BC7).
- Confirmed decoding real files this way: `diff` (BC1, 1024², RGBA), `ddna` (BC5, 2048², RG
  normal), `spec` (BC1, 1024²). Previews render correctly.
- Normal maps (`_ddna`) are BC5: only X/Y are stored. Z must be reconstructed:
  `B = sqrt(max(0, 1 - X² - Y²))` after mapping channels from [0,255] to [-1,1].

## Stack

- **Python 3.13** (installed)
- **PyQt6** — GUI. Native drag-and-drop; `QGraphicsView`/`QGraphicsScene` for smooth continuous
  zoom and pan. **New dependency**: one-time `pip install PyQt6`.
- **Pillow 11.1** (installed) — block decode + resampling.
- **numpy 2.2** (installed) — channel isolation and normal-map Z reconstruction.
- **PyInstaller 6.12** (installed) — package to a single standalone `.exe`.

Rejected: tkinter (clunky zoom, needs `tkinterdnd2` for drag-drop) and web/Electron (must
bundle a JS BC7 decoder + browser runtime; heavier and riskier). PyQt6 was chosen by the user
and removes the drag-drop dependency entirely.

## Location

```
Mods/_Tools/ddsviewer/
  crydds.py          # decode logic (no UI)
  channels.py        # numpy channel + normal-map ops (no UI)
  viewer.py          # PyQt6 window
  run_viewer.pyw     # entry point (no console)
  build_exe.bat      # PyInstaller one-liner -> dist/ddsviewer.exe
  docs/2026-06-18-dds-viewer-design.md
```

## Modules

Each module has one job, a clear interface, and is testable without the others.

### 1. `crydds.py` — decode (pure logic, no UI)

Interface:
- `load_dds(path: str) -> DdsImage`
- `DdsImage` holds: `image: PIL.Image.Image` (RGBA), `width`, `height`, `format_name`
  (e.g. `"BC1 (DXT1)"`), `dxgi_code`, `is_normal: bool` (true if filename matches `_ddna`).

Behavior:
1. Read the base `.dds` header: dimensions, mip count, whether it is DX10, and the DXGI code.
2. Find the top mip: glob `path.dds.*`, keep names whose suffix after `.dds.` is all digits,
   pick the **highest** number, read its raw bytes. If no numeric split files exist (plain DDS),
   use the file's own pixel data after the header.
3. Build a Pillow-decodable single-mip DDS in memory:
   - Copy the 128-byte header, set mip count = 1, keep full width/height.
   - If DXGI maps to a legacy FourCC (the BC1–BC5 table), set pixel-format flags to FourCC and
     write the FourCC at offset 0x54.
   - Else if BC7 (DXGI 95–99), keep the 148-byte DX10 header.
   - Append the top-mip bytes.
4. `Image.open(BytesIO(...))`, `.load()`, convert to RGBA, return `DdsImage`.

Error handling: on an unknown/unsupported format, raise `UnsupportedFormat(dxgi_code, name)`
carrying a human-readable message. Never let the UI crash.

### 2. `channels.py` — channel + normal ops (pure logic, no UI)

Interface (all take/return a `PIL.Image` RGBA, via numpy internally):
- `isolate(image, channel: "R"|"G"|"B"|"A") -> Image`  — show one channel as grayscale.
- `full_rgb(image) -> Image`  — original.
- `reconstruct_normal(image) -> Image`  — for `_ddna`: map RG to [-1,1], compute
  Z = √(1−X²−Y²), output an RGB normal where B is filled in (so it reads as a proper normal map).

### 3. `viewer.py` — PyQt6 window

- `QMainWindow` with a `QGraphicsView` + `QGraphicsScene` showing a `QGraphicsPixmapItem`.
- Accepts drops (`setAcceptDrops(True)`, `dragEnterEvent`, `dropEvent`); on a `.dds` drop it
  calls `crydds.load_dds`, converts the PIL image to `QImage`→`QPixmap`, and sets the scene.
- Zoom: mouse wheel scales the view about the cursor. Pan: `ScrollHandDrag` (left-drag).
  Keys: `1` fit-to-window, `0`/`Ctrl+0` reset 100%.
- Channel keys: `R`/`G`/`B`/`A` isolate a channel, `C` back to full RGB, `N` toggle normal-map
  reconstruction (auto-on for `_ddna` files). Re-renders from the cached source image.
- **Export** (`Ctrl+S`): open a `QFileDialog` save dialog defaulting to the source filename with
  a `.png` extension, with a PNG/JPEG filter. Saves **exactly what is currently displayed** — so
  an isolated channel or reconstructed normal exports as shown; otherwise the full RGB(A) image.
  PNG keeps alpha; JPEG flattens to RGB. Uses `PIL.Image.save`. Status bar confirms the written path.
- One-line status bar: `filename · WxH · format` (e.g. `Parrott_Rifled_diff.dds · 1024×1024 · BC1`).
- On `UnsupportedFormat`, show the message in the status bar and keep the window alive.

### 4. Entry + packaging

- `run_viewer.pyw` — creates the `QApplication`, shows the window. `.pyw` = no console.
- `build_exe.bat` — `pyinstaller --noconsole --onefile --name ddsviewer run_viewer.pyw`,
  output `dist/ddsviewer.exe`. The `.exe` runs with no Python/pip needed.

## Data Flow

```
drop .dds ─► crydds.load_dds ─► DdsImage(PIL RGBA + info)
                                   │
              channels.* (on key) ─┤
                                   ▼
                            PIL ─► QImage ─► QPixmap ─► QGraphicsScene ─► zoom/pan
```

## Testing

- `crydds`: decode the three known files (`diff` BC1, `ddna` BC5, `spec` BC1) and assert
  expected dimensions and mode; assert `UnsupportedFormat` on a corrupted/garbage header.
  Assert the plain-DDS fallback path (no split files) also returns an image.
- `channels`: assert `isolate("R")` zeroes G/B; assert `reconstruct_normal` produces B≈255 where
  X=Y=0 (flat normal) and stays in range.
- `viewer`: smoke test that the window constructs and `load_dds` → pixmap set works headlessly
  (offscreen Qt platform). Manual: drop several real files, zoom, toggle channels, export.
- `export`: save the displayed image to a temp `.png` and `.jpg` and assert the files exist,
  reopen, and match expected size/mode (PNG keeps alpha, JPEG is RGB).

## Out of Scope (YAGNI)

Metadata panel beyond the status line, batch/folder browsing, thumbnails grid, mip-level
selection, format conversion beyond PNG/JPEG export, editing. Can be added later if wanted.

## Open Risks

- BC7 files exist in this game but were not in the sampled folder; the BC7 keep-DX10 path is
  designed but should be verified against a real BC7 `_ddna`/`_diff` during implementation.
- A handful of CryEngine textures may use uncompressed or unusual DXGI codes; those hit the
  `UnsupportedFormat` path gracefully rather than crashing.
