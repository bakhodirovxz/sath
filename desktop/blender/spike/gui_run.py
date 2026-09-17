"""SPIKE: GUI rejimida fc_bridge sinovi — natijani .blend ga saqlab 3 soniyadan keyin yopadi.
  blender --python gui_run.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import fc_bridge

fc_bridge.main()
out = os.path.join(os.environ.get("TEMP", "."), "ges_spike_gui.blend")
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAQLANDI:", out, "obyektlar:", len(bpy.data.objects), flush=True)
if os.environ.get("GES_SPIKE_KEEP_OPEN") != "1":
    bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=3.0)
