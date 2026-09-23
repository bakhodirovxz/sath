import { tEnum } from "./index";

/** Barcha enum lar uchun yorliqlar (UX-09): xom inglizcha qiymat (critical, power, pending…) UI ga chiqmaydi. */
export const priorityLabel = (p: string | null | undefined) => tEnum("priority", p);
export const alarmLabel = (s: string | null | undefined) => tEnum("alarm", s);
export const isaStateLabel = (s: string | null | undefined) => tEnum("isa", s);
export const alarmModeLabel = (s: string | null | undefined) => tEnum("alarmMode", s);
export const qualityLabel = (s: string | null | undefined) => tEnum("quality", s);
export const sensorKindLabel = (s: string | null | undefined) => tEnum("sensorKind", s);
export const commandStatusLabel = (s: string | null | undefined) => tEnum("cmd", s);
export const roleLabel = (s: string | null | undefined) => tEnum("role", s);
export const workOrderStatusLabel = (s: string | null | undefined) => tEnum("wo", s);
export const permitLabel = (s: string | null | undefined) => tEnum("permit", s);
export const journalKindLabel = (s: string | null | undefined) => tEnum("journal", s);
export const soeTypeLabel = (s: string | null | undefined) => tEnum("soe", s);
export const periodLabel = (s: string | null | undefined) => tEnum("period", s);
export const simStatusLabel = (s: string | null | undefined) => tEnum("sim", s);
export const cmStateLabel = (s: string | null | undefined) => tEnum("cm", s);
export const keyKindLabel = (s: string | null | undefined) => tEnum("keyKind", s);
export const protocolLabel = (s: string | null | undefined) => tEnum("protocol", s);
export const handoverLabel = (s: string | null | undefined) => tEnum("handover", s);
export const assetStatusLabel = (s: string | null | undefined) => tEnum("assetStatus", s);

const LABEL_GROUPS = ["version", "cr", "issue", "priority", "role", "wo"];
/** Umumiy holat yorlig'i (versiya, tasdiqlash so'rovi, muammo, ustuvorlik, rol) — eski `label()` o'rnida. */
export function stateLabel(s: string | null | undefined): string {
  if (s == null || s === "") return "—";
  for (const g of LABEL_GROUPS) {
    const v = tEnum(g, s);
    if (v !== s) return v;
  }
  return s;
}
