# DDS Viewer

Lightweight viewer for War of Rights / CryEngine DDS textures. Drag a `.dds` onto the
window to see it full-resolution (it auto-reassembles the CryEngine split mips), zoom,
pan, isolate channels, view normal maps correctly, and export to PNG/JPEG.

## Run (from source)

```
pip install PyQt6        # Pillow + numpy already required; one-time install
py -3.13 run_viewer.pyw
```

## Build the standalone .exe

Double-click `build_exe.bat` (or run it). Output: `dist\DDSViewer.exe` — runs with no
Python install needed. You can also drag a `.dds` onto the `.exe` to open it directly.

## Controls

| Action | Key / Input |
|--------|-------------|
| Open texture | Drag a `.dds` onto the window, or **File ▸ Open** (`Ctrl+O`) |
| Zoom | Mouse wheel (zooms toward cursor) |
| Pan | Left-click drag |
| Fit to window | `1` |
| Reset zoom (100%) | `0` or `Ctrl+0` |
| Isolate channel | `R` / `G` / `B` / `A` |
| Back to full color | `C` |
| Toggle normal-map view | `N` (auto-on for `_ddna` files) |
| Flip horizontal / vertical | `F` / `V` |
| Invert colors | `I` |
| Rotate 90° left / right | `,` / `.` |
| Rotate by exact degrees | `Ctrl+R` |
| Reset all transforms | `T` |
| Export PNG/JPEG | `Ctrl+S` (choose folder + name; defaults to source name) |
| Show/hide controls panel | `H`, or **View ▸ Controls** |

Flip, invert, and rotation are **baked into the export** — whatever you see is what gets saved.
Transforms reset when you open a new texture. Zoom/pan is just the on-screen view and is not
part of the saved image.

A **Controls** panel is docked on the right with this list; toggle it with `H`. The export
dialog lets you pick the folder and filename — it pre-fills the source texture's name (with a
`_r`/`_g`/`_normal` suffix when a channel/normal view is active) and folder.

## How it works

- `crydds.py` — finds the highest-numbered `.dds.N` split (= mip 0), rewrites the DX10/sRGB
  header to a Pillow-decodable legacy FourCC (or keeps DX10 for BC7), returns a PIL image.
- `channels.py` — numpy channel isolation and `_ddna` normal-map Z reconstruction.
- `viewer.py` — PyQt6 window (drag-drop, `QGraphicsView` zoom/pan, export).
- `run_viewer.pyw` — entry point.
