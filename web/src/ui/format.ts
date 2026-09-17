export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("uz-UZ", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
export const STATE_LABEL: Record<string, string> = {
  wip: "Ishda",
  shared: "Tasdiqda",
  published: "Tasdiqlangan",
  archived: "Arxiv",
  open: "Ochiq",
  changes_requested: "O'zgartirish so'ralgan",
  approved: "Ma'qullangan",
  rejected: "Rad etilgan",
  merged: "Tasdiqlangan",
  in_progress: "Jarayonda",
  resolved: "Hal qilingan",
  closed: "Yopilgan",
  low: "Past",
  normal: "Oddiy",
  high: "Yuqori",
  critical: "Kritik",
  viewer: "Ko'ruvchi",
  operator: "Dispetcher",
  engineer: "Muhandis",
  approver: "Tasdiqlovchi",
};
export const label = (s: string) => STATE_LABEL[s] ?? s;

const IFC_UZ: Record<string, string> = {
  WALL: "Devor", SLAB: "Plita", BEAM: "To'sin", COLUMN: "Ustun", DOOR: "Eshik", WINDOW: "Deraza",
  ROOF: "Tom", STAIR: "Zina", PIPESEGMENT: "Quvur", PIPEFITTING: "Quvur fitingi", FLOWMOVINGDEVICE: "Nasos/Turbina",
  ELECTRICGENERATOR: "Generator", TRANSFORMER: "Transformator", SITE: "Maydon", BUILDING: "Bino",
  BUILDINGSTOREY: "Qavat", SPACE: "Xona", FOOTING: "Poydevor", COVERING: "Qoplama", RAILING: "To'siq",
  MEMBER: "Element", PLATE: "Plastina", TANK: "Rezervuar", VALVE: "Zadvijka", DUCTSEGMENT: "Havo quvuri",
  BUILDINGELEMENTPROXY: "Element", FURNITURE: "Mebel", CURTAINWALL: "Vitraj", OPENINGELEMENT: "Ochiq joy",
};
/** IFCPIPESEGMENT / IfcPipeSegment → "Quvur" (yoki "Pipe Segment"). */
export function ifcLabel(category: string): string {
  const key = category.replace(/^Ifc/i, "").toUpperCase();
  if (IFC_UZ[key]) return IFC_UZ[key];
  // CamelCase bo'lsa so'zlarga ajratamiz, UPPER bo'lsa bosh harf
  const raw = category.replace(/^Ifc/i, "");
  return raw === raw.toUpperCase() ? raw.charAt(0) + raw.slice(1).toLowerCase() : raw.replace(/([a-z])([A-Z])/g, "$1 $2");
}

/** O'lchov qiymati: kattaligiga qarab 0–2 kasr. */
export function fmtValue(v: number): string {
  const a = Math.abs(v);
  return a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(1) : v.toFixed(2);
}
export const ALARM_LABEL: Record<string, string> = { ok: "normal", low: "past", high: "yuqori", stale: "aloqa yo'q" };
