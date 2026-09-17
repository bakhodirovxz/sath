// Blender uslubidagi UI yordamchilari — sof funksiyalar (vitest bilan sinaladi).

export interface SearchItem {
  label: string;
  hint?: string;
  group?: string;
  run: () => void;
}

/** F3 qidiruv: har so'z alohida mos kelishi kerak (label, hint, group ichida), tartib: label boshida moslik birinchi. */
export function searchCommands(query: string, items: SearchItem[], limit = 12): SearchItem[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return items.slice(0, limit);
  const scored = items
    .map((it) => {
      const hay = `${it.label} ${it.hint ?? ""} ${it.group ?? ""}`.toLowerCase();
      if (!words.every((w) => hay.includes(w))) return null;
      const starts = it.label.toLowerCase().startsWith(words[0]) ? 0 : 1;
      return { it, key: `${starts}${it.label.toLowerCase()}` };
    })
    .filter((x): x is { it: SearchItem; key: string } => x !== null)
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return scored.slice(0, limit).map((x) => x.it);
}

/**
 * Pie menyu: kursor markazdan (dx, dy) ga siljigan; n ta bo'lak, 0-bo'lak yuqorida, soat yo'nalishida.
 * Markazga yaqin (dead zone) — null.
 */
export function pickPie(dx: number, dy: number, n: number, dead = 18): number | null {
  if (n <= 0 || Math.hypot(dx, dy) < dead) return null;
  const ang = Math.atan2(dx, -dy); // yuqori = 0, o'ng = +90°
  const step = (2 * Math.PI) / n;
  const idx = Math.round(ang / step);
  return ((idx % n) + n) % n;
}

/** Pie bo'lagining markaz nuqtasi (radius px), 0 yuqorida, soat yo'nalishida. */
export function piePosition(i: number, n: number, radius = 80): { x: number; y: number } {
  const ang = (2 * Math.PI * i) / n;
  return { x: Math.round(Math.sin(ang) * radius) + 0, y: Math.round(-Math.cos(ang) * radius) + 0 }; // +0: -0 emas
}
