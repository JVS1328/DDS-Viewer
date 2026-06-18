"""PyQt6 DDS viewer window: drag-drop, zoom/pan, channel isolation, normal maps, export."""

from __future__ import annotations

import os

from PIL import Image, ImageOps
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDockWidget, QFileDialog, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QInputDialog, QLabel, QMainWindow,
)

import channels
import crydds

_PNG_JPG_FILTER = "PNG image (*.png);;JPEG image (*.jpg *.jpeg)"

_CONTROLS = (
    "<b>Open</b><br>"
    "&nbsp;&nbsp;Drag a .dds in, or File ▸ Open (Ctrl+O)<br><br>"
    "<b>View</b><br>"
    "&nbsp;&nbsp;Zoom — mouse wheel<br>"
    "&nbsp;&nbsp;Pan — left-drag<br>"
    "&nbsp;&nbsp;Fit — <b>1</b>&nbsp;&nbsp;&nbsp;100% — <b>0</b><br><br>"
    "<b>Channels</b><br>"
    "&nbsp;&nbsp;Isolate — <b>R G B A</b><br>"
    "&nbsp;&nbsp;Full color — <b>C</b><br>"
    "&nbsp;&nbsp;Normal map — <b>N</b><br><br>"
    "<b>Transform</b><br>"
    "&nbsp;&nbsp;Flip — <b>F</b> horiz, <b>V</b> vert<br>"
    "&nbsp;&nbsp;Invert colors — <b>I</b><br>"
    "&nbsp;&nbsp;Rotate 90° — <b>,</b> left, <b>.</b> right<br>"
    "&nbsp;&nbsp;Rotate by degrees — Ctrl+R<br>"
    "&nbsp;&nbsp;Reset transforms — <b>T</b><br><br>"
    "<b>Export</b><br>"
    "&nbsp;&nbsp;Save PNG / JPEG — Ctrl+S<br>"
    "&nbsp;&nbsp;<i>(saves current flip / rotate / invert)</i><br><br>"
    "<i>Toggle this panel — H</i>"
)


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4,
                  QImage.Format.Format_RGBA8888).copy()  # copy detaches from `data`
    return QPixmap.fromImage(qimg)


class ImageView(QGraphicsView):
    """Graphics view with cursor-anchored wheel zoom and hand-drag panning."""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self._win = window
        self.setScene(QGraphicsScene(self))
        self._item = QGraphicsPixmapItem()
        self.scene().addItem(self._item)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setAcceptDrops(True)

    def set_pixmap(self, pm: QPixmap, fit: bool):
        self._item.setPixmap(pm)
        self.scene().setSceneRect(self._item.boundingRect())
        if fit:
            self.fit()

    def fit(self):
        if not self._item.pixmap().isNull():
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def reset_zoom(self):
        self.resetTransform()

    def wheelEvent(self, e):
        if self._item.pixmap().isNull():
            return
        factor = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    # --- drag & drop ---
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".dds"):
                self._win.load_path(path)
                break


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DDS Viewer")
        self.resize(900, 700)
        self.view = ImageView(self)
        self.setCentralWidget(self.view)
        self.status = self.statusBar()
        self.status.showMessage("Drag a .dds onto the window, or use File ▸ Open.")

        self._dds: crydds.DdsImage | None = None
        self._mode = "rgb"          # rgb | R | G | B | A | normal
        self._display: Image.Image | None = None
        self._last_dir = ""
        # Orientation/color transforms — baked into _display, so export saves them.
        self._rot = 0               # degrees clockwise, cumulative
        self._flip_h = False
        self._flip_v = False
        self._invert = False

        self._build_controls_dock()
        self._build_menu()

        # NOTE: Ctrl+O / Ctrl+S / Ctrl+Q live on the menu QActions only — registering
        # them here too would make Qt treat them as an "ambiguous shortcut overload"
        # and fire neither.
        binds = {
            "R": lambda: self.set_mode("R"), "G": lambda: self.set_mode("G"),
            "B": lambda: self.set_mode("B"), "A": lambda: self.set_mode("A"),
            "C": lambda: self.set_mode("rgb"), "N": self.toggle_normal,
            "1": self.view.fit, "0": self.view.reset_zoom,
            "Ctrl+0": self.view.reset_zoom, "H": self._toggle_controls,
        }
        for key, fn in binds.items():
            QShortcut(QKeySequence(key), self, activated=fn)

    def _build_controls_dock(self):
        self._dock = QDockWidget("Controls", self)
        self._dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        label = QLabel(_CONTROLS)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop)
        label.setContentsMargins(10, 10, 10, 10)
        self._dock.setWidget(label)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock)

    def _build_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        act_open = QAction("&Open…", self, shortcut="Ctrl+O", triggered=self.open_file)
        act_export = QAction("&Export…", self, shortcut="Ctrl+S", triggered=self.export)
        act_quit = QAction("&Quit", self, shortcut="Ctrl+Q", triggered=self.close)
        file_menu.addActions([act_open, act_export])
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

        img_menu = mb.addMenu("&Image")
        img_menu.addAction(QAction(
            "Flip &Horizontal", self, shortcut="F", triggered=self.flip_h))
        img_menu.addAction(QAction(
            "Flip &Vertical", self, shortcut="V", triggered=self.flip_v))
        img_menu.addAction(QAction(
            "&Invert Colors", self, shortcut="I", triggered=self.invert))
        img_menu.addSeparator()
        img_menu.addAction(QAction(
            "Rotate &Left 90°", self, shortcut=",", triggered=lambda: self.rotate_by(-90)))
        img_menu.addAction(QAction(
            "Rotate &Right 90°", self, shortcut=".", triggered=lambda: self.rotate_by(90)))
        img_menu.addAction(QAction(
            "Rotate by &Degrees…", self, shortcut="Ctrl+R", triggered=self.rotate_prompt))
        img_menu.addSeparator()
        img_menu.addAction(QAction(
            "Re&set Transforms", self, shortcut="T", triggered=self.reset_transforms))

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._dock.toggleViewAction())  # "Controls" show/hide

    def _toggle_controls(self):
        self._dock.setVisible(not self._dock.isVisible())

    def open_file(self):
        start = self._last_dir
        if not start and self._dds:
            start = os.path.dirname(self._dds.path)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DDS texture", start,
            "DDS textures (*.dds);;All files (*)")
        if path:
            self._last_dir = os.path.dirname(path)
            self.load_path(path)

    def load_path(self, path: str):
        try:
            self._dds = crydds.load_dds(path)
        except crydds.UnsupportedFormat as e:
            self._dds = None
            self.status.showMessage(f"{os.path.basename(path)} — {e}")
            return
        self._mode = "normal" if self._dds.is_normal else "rgb"
        self._rot = 0
        self._flip_h = self._flip_v = self._invert = False
        self.render(fit=True)

    def set_mode(self, mode: str):
        if self._dds is None:
            return
        self._mode = mode
        self.render(fit=False)

    def toggle_normal(self):
        if self._dds is None:
            return
        self._mode = "rgb" if self._mode == "normal" else "normal"
        self.render(fit=False)

    # --- transforms (baked into _display, so export includes them) ---
    def flip_h(self):
        if self._dds:
            self._flip_h = not self._flip_h
            self.render(fit=False)

    def flip_v(self):
        if self._dds:
            self._flip_v = not self._flip_v
            self.render(fit=False)

    def invert(self):
        if self._dds:
            self._invert = not self._invert
            self.render(fit=False)

    def rotate_by(self, deg: float):
        if self._dds:
            self._rot = (self._rot + deg) % 360
            self.render(fit=False)

    def rotate_prompt(self):
        if not self._dds:
            return
        deg, ok = QInputDialog.getDouble(
            self, "Rotate", "Degrees (clockwise):", 0.0, -360.0, 360.0, 1)
        if ok:
            self.rotate_by(deg)

    def reset_transforms(self):
        if self._dds:
            self._rot = 0
            self._flip_h = self._flip_v = self._invert = False
            self.render(fit=False)

    def _apply_transforms(self, img: Image.Image) -> Image.Image:
        img = img.convert("RGBA")
        if self._invert:                       # invert RGB, preserve alpha
            r, g, b, a = img.split()
            rgb = ImageOps.invert(Image.merge("RGB", (r, g, b)))
            img = Image.merge("RGBA", (*rgb.split(), a))
        if self._flip_h:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self._flip_v:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if self._rot % 360 != 0:               # PIL rotates CCW; negate for CW
            img = img.rotate(-self._rot, expand=True,
                             resample=Image.Resampling.BICUBIC)
        return img

    def render(self, fit: bool):
        d = self._dds
        if d is None:
            return
        if self._mode == "normal":
            base = channels.reconstruct_normal(d.image)
        elif self._mode in ("R", "G", "B", "A"):
            base = channels.isolate(d.image, self._mode)
        else:
            base = channels.full_rgb(d.image)
        self._display = self._apply_transforms(base)
        self.view.set_pixmap(pil_to_pixmap(self._display), fit=fit)

        tag = {"rgb": "RGB", "normal": "Normal"}.get(self._mode, f"{self._mode} only")
        self.setWindowTitle(f"DDS Viewer — {os.path.basename(d.path)}")
        self.status.showMessage(
            f"{os.path.basename(d.path)} · {d.width}×{d.height} · {d.format_name} · {tag}"
        )

    def export(self):
        if self._display is None or self._dds is None:
            self.status.showMessage("Nothing to export — open a texture first.")
            return
        # Default name = source filename + a mode suffix; default folder = last used,
        # else the texture's own folder.
        stem = os.path.splitext(os.path.basename(self._dds.path))[0] or "texture"
        suffix = "" if self._mode == "rgb" else f"_{self._mode.lower()}"
        start_dir = self._last_dir or os.path.dirname(self._dds.path)
        suggested = os.path.join(start_dir, f"{stem}{suffix}.png")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export image", suggested, _PNG_JPG_FILTER)
        if not path:
            return
        self._last_dir = os.path.dirname(path)
        img = self._display
        if path.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        try:
            img.save(path)
            self.status.showMessage(f"Exported → {path}")
        except Exception as e:
            self.status.showMessage(f"Export failed: {e}")
