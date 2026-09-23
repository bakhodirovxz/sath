import * as THREE from "three";
import { PAL } from "./palette";

/** Ekran o'lchamidagi matnli sprite (yorliq): matn, rang, fon (FE-06: Viewer.ts dan ajratildi). */
export function makeTextSprite(text: string, color: string = PAL.labelText, bg: string = PAL.labelBg, scale = 0.055): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 56;
  const ctx = c.getContext("2d")!;
  ctx.font = "600 24px system-ui, sans-serif";
  const w = Math.min(500, ctx.measureText(text).width + 20);
  ctx.fillStyle = bg; ctx.fillRect(0, 0, w, 56);
  ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, 10, 28, 490);
  const tex = new THREE.CanvasTexture(c);
  tex.repeat.x = w / 512;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true, sizeAttenuation: false }));
  sp.scale.set(scale * (w / 56), scale, 1);
  sp.center.set(0.5, 0);
  sp.renderOrder = 30;
  return sp;
}
