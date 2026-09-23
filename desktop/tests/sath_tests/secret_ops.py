"""CODE-05: parol Scene da emas (WindowManager, .blend ga yozilmaydi), xato logindan keyin ham tozalanadi."""

import tempfile
from pathlib import Path

import bpy

SECRET = "sinov-parol-9f3k2"


def run(ctx):
    from sath import prefs

    assert "password" not in bpy.context.scene.ges.bl_rna.properties
    sec = bpy.context.window_manager.sath_secret
    # .blend ga yozilmaydi
    sec.password = SECRET
    blend = Path(tempfile.mkdtemp(prefix="sath-sec-")) / "s.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=False)
    assert SECRET.encode() not in blend.read_bytes(), "parol .blend faylga yozildi"
    # xato login (server yo'q) — parol baribir tozalanadi
    p = prefs.prefs()
    p.server, p.username = "http://127.0.0.1:9", "admin"
    sec.password, sec.otp = SECRET, "123456"
    try:
        bpy.ops.sath.connect()
    except RuntimeError:
        pass  # operator xato bilan tugashi mumkin
    assert sec.password == "" and sec.otp == ""
