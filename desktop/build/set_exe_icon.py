"""Windows exe ichidagi ikonkani almashtirish (kompilyatsiyasiz, faqat Windows API — ctypes).

Fork build ida ikonka src/Main/icon.ico dan kompilyatsiya qilinadi; tayyor FreeCAD binariga
overlay qo'llanganda esa Sath.exe Blender ikonkasi bilan qoladi — shu skript
RT_GROUP_ICON va RT_ICON resurslarini .ico faylidagi bilan almashtiradi.

    python set_exe_icon.py <exe> <ico>
"""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes
from pathlib import Path

RT_ICON = 3
RT_GROUP_ICON = 14
LANG_NEUTRAL = 0  # MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL)


def read_ico(path: Path) -> list[tuple[bytes, bytes]]:
    """[(ICONDIRENTRY 16 bayt (offsetsiz), rasm baytlari)]"""
    data = path.read_bytes()
    _res, typ, count = struct.unpack_from("<HHH", data, 0)
    if typ != 1:
        raise SystemExit("ICO fayl emas")
    out = []
    for i in range(count):
        off = 6 + 16 * i
        w, h, colors, res, planes, bpp, size, img_off = struct.unpack_from("<BBBBHHII", data, off)
        entry = struct.pack("<BBBBHHI", w, h, colors, res, planes, bpp, size)
        out.append((entry, data[img_off : img_off + size]))
    return out


def existing_group_ids(exe: Path) -> list:
    """Exe dagi mavjud RT_GROUP_ICON nomlari (ID lar) — birinchisini almashtiramiz."""
    k32 = ctypes.windll.kernel32
    LOAD_LIBRARY_AS_DATAFILE = 0x2
    h = k32.LoadLibraryExW(str(exe), None, LOAD_LIBRARY_AS_DATAFILE)
    if not h:
        raise ctypes.WinError()
    names: list = []
    ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPARAM)

    def cb(_h, _type, name, _param):
        v = ctypes.cast(name, ctypes.c_void_p).value
        names.append(v if v >> 16 == 0 else ctypes.wstring_at(name))
        return True

    k32.EnumResourceNamesW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, ENUMPROC, wintypes.LPARAM]
    k32.EnumResourceNamesW(h, ctypes.cast(ctypes.c_void_p(RT_GROUP_ICON), wintypes.LPCWSTR), ENUMPROC(cb), 0)
    k32.FreeLibrary(h)
    return names


def set_icon(exe: Path, ico: Path) -> None:
    """Resurs yangilash vaqtinchalik papkadagi nusxada bajariladi (ba'zi papkalarda — masalan
    himoyalangan Desktop — EndUpdateResource "ruxsat yo'q" beradi), so'ng baytlar qaytariladi."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ges-ico-") as td:
        tmp = Path(td) / exe.name
        shutil.copyfile(exe, tmp)
        _set_icon_inplace(tmp, ico)
        shutil.copyfile(tmp, exe)
    print(f"ikonka almashtirildi: {exe.name}")


def _set_icon_inplace(exe: Path, ico: Path) -> None:
    images = read_ico(ico)
    groups = existing_group_ids(exe)
    group_id = groups[0] if groups and isinstance(groups[0], int) else 1
    k32 = ctypes.windll.kernel32
    k32.BeginUpdateResourceW.restype = wintypes.HANDLE
    k32.UpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    h = k32.BeginUpdateResourceW(str(exe), False)
    if not h:
        raise ctypes.WinError()

    def upd(typ: int, name: int, data: bytes | None):
        buf = ctypes.create_string_buffer(data) if data is not None else None
        ok = k32.UpdateResourceW(
            h,
            ctypes.cast(ctypes.c_void_p(typ), wintypes.LPCWSTR),
            ctypes.cast(ctypes.c_void_p(name), wintypes.LPCWSTR),
            LANG_NEUTRAL,
            ctypes.cast(buf, ctypes.c_void_p) if buf is not None else None,
            len(data) if data is not None else 0,
        )
        if not ok:
            raise ctypes.WinError()

    # Yangi RT_ICON lar: ID 1..n (FreeCAD niki ham 1..n dan boshlanadi — ustiga yoziladi)
    group = struct.pack("<HHH", 0, 1, len(images))
    for i, (entry, img) in enumerate(images, start=1):
        upd(RT_ICON, i, img)
        group += entry + struct.pack("<H", i)
    # Eski gruppadagi ortiqcha RT_ICON lar (n dan katta ID) qolsa ham zarar qilmaydi
    upd(RT_GROUP_ICON, group_id, group)
    if not k32.EndUpdateResourceW(h, False):
        raise ctypes.WinError()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    set_icon(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
