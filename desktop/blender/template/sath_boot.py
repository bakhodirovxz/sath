# Sath bundle: Blender argumentsiz ochilsa ham «Sath» app template ga o'tadi (Blender template ni prefs da
# saqlamaydi). portable/scripts/startup/ da yotadi — har ishga tushishda avtomatik yuklanadi.

import bpy

TEMPLATE = "Sath"


def _boot():
    if bpy.app.background or bpy.context.preferences.app_template == TEMPLATE:
        return None
    if bpy.data.filepath:  # fayl ochib ishga tushirilgan — tegmaymiz
        return None
    wm = bpy.context.window_manager
    win = wm.windows[0] if wm.windows else None
    if win is None:
        return 0.1
    with bpy.context.temp_override(window=win):
        bpy.ops.wm.read_homefile(app_template=TEMPLATE)
    if bpy.context.preferences.view.show_splash:
        win = bpy.context.window_manager.windows[0]  # homefile dan keyin oyna obyekti yangilanadi
        with bpy.context.temp_override(window=win):
            bpy.ops.wm.splash("INVOKE_DEFAULT")
    return None


def register():
    bpy.app.timers.register(_boot, first_interval=0.0)


def unregister():
    pass
