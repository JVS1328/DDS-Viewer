"""CryEngine / War of Rights DDS decode.

The dropped .dds is only a header + tiny mip; the full-resolution pixels live in
sibling split files (name.dds.1 .. name.dds.N, highest number = mip 0). Pillow also
refuses several DX10/DXGI sRGB codes, so we rewrite the header to a legacy FourCC
(BC1-BC5 blocks are byte-identical). BC6H/BC7 keep their DX10 header.
"""

from __future__ import annotations

import glob
import io
import os
import struct
from dataclasses import dataclass

from PIL import Image

# DXGI format code -> (legacy FourCC, human name). BC1-BC5 are byte-compatible
# with the legacy compressed formats, so swapping the header is lossless.
_DXGI_LEGACY = {
    70: (b"DXT1", "BC1"), 71: (b"DXT1", "BC1"), 72: (b"DXT1", "BC1 sRGB"),
    73: (b"DXT3", "BC2"), 74: (b"DXT3", "BC2"), 75: (b"DXT3", "BC2 sRGB"),
    76: (b"DXT5", "BC3"), 77: (b"DXT5", "BC3"), 78: (b"DXT5", "BC3 sRGB"),
    79: (b"ATI1", "BC4"), 80: (b"ATI1", "BC4"), 81: (b"ATI1", "BC4s"),
    82: (b"ATI2", "BC5"), 83: (b"ATI2", "BC5"), 84: (b"ATI2", "BC5s"),
}
# DXGI codes that Pillow decodes via the DX10 header (keep it intact).
_DXGI_DX10_KEEP = {
    94: "BC6H", 95: "BC6H", 96: "BC6H",
    97: "BC7", 98: "BC7", 99: "BC7 sRGB",
}

_HDR_LEN_LEGACY = 128
_HDR_LEN_DX10 = 148


class UnsupportedFormat(Exception):
    def __init__(self, dxgi_code, name=""):
        self.dxgi_code = dxgi_code
        super().__init__(
            f"Can't decode this texture yet (DXGI format {dxgi_code}). {name}".strip()
        )


@dataclass
class DdsImage:
    image: Image.Image      # always RGBA
    width: int
    height: int
    format_name: str        # e.g. "BC1 sRGB"
    dxgi_code: int | None
    is_normal: bool
    path: str


def _top_split(path: str) -> str | None:
    """Highest-numbered .dds.N sibling (mip 0), or None for a plain DDS."""
    splits = [p for p in glob.glob(glob.escape(path) + ".*")
              if p[len(path) + 1:].isdigit()]
    if not splits:
        return None
    return max(splits, key=lambda p: int(p[len(path) + 1:]))


def load_dds(path: str) -> DdsImage:
    data = open(path, "rb").read()
    if data[:4] != b"DDS ":
        raise UnsupportedFormat(None, "Not a DDS file.")

    height, width = struct.unpack_from("<II", data, 12)
    mipcount = struct.unpack_from("<I", data, 28)[0] or 1
    is_dx10 = data[84:88] == b"DX10"
    dxgi = struct.unpack_from("<I", data, 128)[0] if is_dx10 else None

    top = _top_split(path)
    if top is not None:                       # CryEngine: use full-res mip 0
        pixels = open(top, "rb").read()
        out_mips = 1
    else:                                     # plain DDS: keep its own mip chain
        hdr_len = _HDR_LEN_DX10 if is_dx10 else _HDR_LEN_LEGACY
        pixels = data[hdr_len:]
        out_mips = mipcount

    if dxgi in _DXGI_LEGACY:
        fourcc, fmt_name = _DXGI_LEGACY[dxgi]
        hdr = bytearray(data[:_HDR_LEN_LEGACY])
        struct.pack_into("<I", hdr, 28, out_mips)   # dwMipMapCount
        struct.pack_into("<I", hdr, 80, 0x4)        # pixelformat flags = FOURCC
        hdr[84:88] = fourcc                          # dwFourCC
        blob = bytes(hdr) + pixels
    elif is_dx10:                                    # BC6H / BC7 / other DX10
        fmt_name = _DXGI_DX10_KEEP.get(dxgi, f"DXGI {dxgi}")
        hdr = bytearray(data[:_HDR_LEN_DX10])
        struct.pack_into("<I", hdr, 28, out_mips)
        blob = bytes(hdr) + pixels
    else:                                            # already legacy FourCC DDS
        fourcc = data[84:88]
        fmt_name = fourcc.decode("ascii", "replace").strip("\x00") or "RGBA"
        hdr = bytearray(data[:_HDR_LEN_LEGACY])
        struct.pack_into("<I", hdr, 28, out_mips)
        blob = bytes(hdr) + pixels

    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except NotImplementedError:
        raise UnsupportedFormat(dxgi, os.path.basename(path))
    except Exception as e:                           # corrupt / unexpected layout
        raise UnsupportedFormat(dxgi, f"{os.path.basename(path)}: {e}")

    return DdsImage(
        image=im.convert("RGBA"),
        width=width, height=height,
        format_name=fmt_name, dxgi_code=dxgi,
        is_normal="_ddna" in os.path.basename(path).lower(),
        path=path,
    )
