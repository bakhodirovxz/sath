import { alarmStyle, type AlarmStyle } from "./tokens";

/** Alarm indikatori (ISA-101 / HP-HMI, UX-01/02): ustuvorlik SHAKLI (◆ kritik, ▲ yuqori, ■ o'rta, ● past) +
 * ichida ustuvorlik raqami (1–4) + yonida holat kodi (HH, H, L, ROC…). Rang — uchinchi kanal: rang ko'rmaydigan
 * operator ham, kulrang bosma ham ajratadi. Kvitlanmagan alarm miltillaydi (1 Hz); reduced-motion da — statik
 * qo'sh kontur. Butun ilovada yagona komponent (jadval, karta, banner, mimika). */

const PATHS: Record<Exclude<AlarmStyle["shape"], "none">, string> = {
  // 16×16 maydon; kontur uchun 1 px chekka
  diamond: "M8 0.8 L15.2 8 L8 15.2 L0.8 8 Z",
  triangle: "M8 1 L15.4 14.6 L0.6 14.6 Z",
  square: "M1.5 1.5 H14.5 V14.5 H1.5 Z",
  circle: "M8 1 A7 7 0 1 1 7.99 1 Z",
};

export interface AlarmMarkProps {
  state: string;
  priority: string | null | undefined;
  /** Kvitlanmagan — miltillaydi */
  unacked?: boolean;
  /** Holat kodini (HH/H/L…) ko'rsatish */
  showCode?: boolean;
  /** Shakl o'lchami, px (matn — shunga mos) */
  size?: number;
  className?: string;
}

export function AlarmShapePath({ st }: { st: AlarmStyle }) {
  if (st.shape === "none") return null;
  return (
    <>
      <path d={PATHS[st.shape]} className={`am-shape prio-${st.priority}`} />
      <text x="8" y={st.shape === "triangle" ? 12.6 : 11.6} textAnchor="middle" className={`am-num prio-${st.priority}`}>{st.rank}</text>
    </>
  );
}

/** HTML ichida (jadval, karta, banner). ok — hech narsa; stale — "?" belgisi. */
export default function AlarmMark({ state, priority, unacked = false, showCode = true, size = 16, className = "" }: AlarmMarkProps) {
  const st = alarmStyle(state, priority ?? "medium");
  if (st.rank === 0) {
    if (state === "stale") return <span className={`alarm-mark stale ${className}`} title={st.label} aria-label={st.label}>?</span>;
    return null;
  }
  const label = `${st.rank}-ustuvorlik: ${st.label}${unacked ? " (kvitlanmagan)" : ""}`;
  return (
    <span className={`alarm-mark ${unacked ? "unacked" : ""} ${className}`} title={label} role="img" aria-label={label} data-prio={st.priority} data-shape={st.shape}>
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="am-svg">
        <AlarmShapePath st={st} />
      </svg>
      {showCode && st.code && <span className="am-code">{st.code}</span>}
    </span>
  );
}

/** SVG ichida (mimika): (x, y) — shakl markazi; o'lcham `size` viewBox birligida. */
export function AlarmMarkSvg({ x, y, state, priority, unacked = false, size = 20 }: { x: number; y: number; state: string; priority: string | null | undefined; unacked?: boolean; size?: number }) {
  const st = alarmStyle(state, priority ?? "medium");
  if (st.rank === 0) return null;
  const s = size / 16;
  return (
    <g className={`alarm-mark-svg ${unacked ? "unacked" : ""}`} transform={`translate(${x - size / 2} ${y - size / 2}) scale(${s})`} data-prio={st.priority} data-testid="mimic-alarm">
      <title>{`${st.rank}-ustuvorlik: ${st.label}${unacked ? " (kvitlanmagan)" : ""}`}</title>
      <AlarmShapePath st={st} />
    </g>
  );
}

/** Faqat ustuvorlik (holat kodisiz): filtr tugmalari, jamlanma qatori, sozlamalar jadvali. `muted` — son 0 bo'lganda
 * kulrang kontur (rang faqat faol alarm uchun). */
export function PriorityMark({ priority, size = 14, muted = false, title }: { priority: string | null | undefined; size?: number; muted?: boolean; title?: string }) {
  const st = alarmStyle("high", priority ?? "medium");
  const label = title ?? `${st.rank}-ustuvorlik`;
  return (
    <span className={`alarm-mark prio-only ${muted ? "muted" : ""}`} role="img" aria-label={label} title={label} data-prio={st.priority}>
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="am-svg"><AlarmShapePath st={st} /></svg>
    </span>
  );
}
