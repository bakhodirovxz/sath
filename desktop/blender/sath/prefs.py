"""Addon sozlamalari: server manzili, login, yangilanish kaliti. Parol saqlanmaydi (faqat sessiya)."""

from __future__ import annotations

import os

import bpy

PKG = __package__  # "bl_ext.user_default.sath" yoki headless da "sath"


class GesPrefs(bpy.types.AddonPreferences):
    bl_idname = PKG
    # HTTPS default (SEC-03): parol va yangilanish paketlari ochiq kanalda uzatilmasin; lokal dev — http://localhost:8000
    server: bpy.props.StringProperty(name="Server", default="https://ges-server")
    username: bpy.props.StringProperty(name="Login", default="")
    # SEC-03: desktop paketlari imzosini tekshirish uchun nashr qiluvchining Ed25519 ochiq kaliti (base64);
    # berilsa imzosiz/noto'g'ri imzoli paket o'rnatilmaydi
    update_public_key: bpy.props.StringProperty(
        name="Yangilanish kaliti",
        default=os.environ.get("SATH_UPDATE_PUBLIC_KEY", ""),
        description="Paket imzosini tekshirish uchun ochiq kalit (base64, administrator beradi)",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "server")
        col.prop(self, "username")
        col.prop(self, "update_public_key")


def prefs() -> GesPrefs:
    a = bpy.context.preferences.addons.get(PKG)
    if a is None:  # headless test: addon ro'yxatda yo'q
        a = bpy.context.preferences.addons.new()
        a.module = PKG
    return a.preferences


def register():
    bpy.utils.register_class(GesPrefs)


def unregister():
    bpy.utils.unregister_class(GesPrefs)
