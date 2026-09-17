import type { AlarmState, Sensor } from "../../api/client";
import { fmtValue } from "../../ui/format";

/** GES texnologik sxemasi (mimik diagramma, SCADA HMI uslubi): suv ombori → to'g'on/suv tashlagich →
 * bosimli quvur → mashina zali (agregatlar) → quyi byef. Slotlarga sensorlar bog'lanadi. */

const COLOR: Record<AlarmState, string> = { ok: "var(--ok)", low: "var(--warn)", high: "var(--danger)", stale: "var(--text-dim)" };

// Slot joylashuvi (viewBox 900x380): x,y — qiymat katakchasi markazi
const POS: Record<string, { x: number; y: number; w?: number; short?: string }> = {
  inflow: { x: 70, y: 48 },
  upstream_level: { x: 130, y: 128 },
  spillway_flow: { x: 330, y: 40 },
  penstock_flow: { x: 420, y: 208 },
  penstock_pressure: { x: 420, y: 250 },
  unit1_power: { x: 575, y: 322, w: 64, short: "G1" },
  unit2_power: { x: 645, y: 322, w: 64, short: "G2" },
  unit3_power: { x: 715, y: 322, w: 64, short: "G3" },
  total_power: { x: 645, y: 178 },
  downstream_level: { x: 835, y: 345 },
  bearing_temp: { x: 590, y: 372 },
  vibration: { x: 700, y: 372 },
};

interface Props {
  sensors: Sensor[];
  mimic: Record<string, number>;
  labels: Record<string, string>;
  onSlotClick?: (slot: string) => void;
  editing?: boolean;
}

export default function Mimic({ sensors, mimic, labels, onSlotClick, editing }: Props) {
  const byId = new Map(sensors.map((s) => [s.id, s]));
  const anyAlarm = sensors.some((s) => s.alarm === "high" || s.alarm === "low");
  const power = ["unit1_power", "unit2_power", "unit3_power"].map((k) => byId.get(mimic[k]));
  return (
    <svg className="mimic" viewBox="0 0 900 400" role="img" aria-label="GES sxemasi">
      {/* Suv ombori */}
      <path d="M0 140 Q60 128 120 140 T240 140 L240 300 L0 300 Z" fill="#1d3f55" opacity="0.9" />
      <path d="M0 140 Q60 128 120 140 T240 140" fill="none" stroke="var(--accent-2)" strokeWidth="2" />
      <text x="20" y="290" className="mimic-cap">SUV OMBORI</text>
      {/* Kiruvchi oqim strelkasi */}
      <path d="M10 80 H60" stroke="var(--accent-2)" strokeWidth="2" markerEnd="url(#arr)" />
      {/* To'g'on */}
      <path d="M240 90 L290 90 L330 300 L240 300 Z" fill="#5b616b" stroke="#8b9098" strokeWidth="1.5" />
      <text x="244" y="316" className="mimic-cap">TO'G'ON</text>
      {/* Suv tashlagich — to'g'on ustidan oqim */}
      <path d="M235 88 Q290 55 345 100" fill="none" stroke="var(--accent-2)" strokeWidth="2" strokeDasharray="5 4" markerEnd="url(#arr)" />
      {/* Bosimli quvur */}
      <path d="M300 250 L470 250 L520 300" fill="none" stroke="#9aa0a8" strokeWidth="10" strokeLinejoin="round" />
      <path d="M300 250 L470 250 L520 300" fill="none" stroke="var(--accent-2)" strokeWidth="4" strokeLinejoin="round" strokeDasharray="14 10" className="mimic-flow" />
      <text x="340" y="272" className="mimic-cap">BOSIMLI QUVUR</text>
      {/* Mashina zali */}
      <rect x="520" y="200" width="250" height="140" fill="#2b2f36" stroke={anyAlarm ? "var(--danger)" : "#8b9098"} strokeWidth="1.5" />
      <text x="530" y="216" className="mimic-cap">MASHINA ZALI</text>
      {[575, 645, 715].map((cx, i) => {
        const s = power[i];
        const on = s && s.last_value != null && s.last_value > 0.05 && s.alarm !== "stale";
        return (
          <g key={cx}>
            <circle cx={cx} cy={272} r={24} fill={on ? "#1f3b2c" : "#26282c"} stroke={s ? COLOR[s.alarm] : "#4a4e57"} strokeWidth="2" strokeDasharray={s ? undefined : "3 3"} />
            <path d={`M${cx - 12} ${272} h24 M${cx} ${260} v24 M${cx - 8} ${264} l16 16 M${cx + 8} ${264} l-16 16`} stroke={on ? "var(--ok)" : "#6a6e76"} strokeWidth="2" className={on ? "mimic-spin" : undefined} style={{ transformOrigin: `${cx}px 272px` }} />
            
          </g>
        );
      })}
      {/* Transformator / liniya */}
      <path d="M770 240 H820 M820 240 V120 H890" fill="none" stroke="var(--warn)" strokeWidth="2" />
      <circle cx="820" cy="240" r="9" fill="none" stroke="var(--warn)" strokeWidth="2" />
      <circle cx="830" cy="240" r="9" fill="none" stroke="var(--warn)" strokeWidth="2" />
      <text x="838" y="112" className="mimic-cap">TARMOQ</text>
      {/* Quyi byef */}
      <path d="M770 310 Q800 300 830 310 T900 310 L900 400 L770 400 Z" fill="#1d3f55" opacity="0.9" />
      <text x="778" y="395" className="mimic-cap">QUYI BYEF</text>
      <defs>
        <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="var(--accent-2)" /></marker>
      </defs>
      {/* Slotlar */}
      {Object.entries(POS).map(([slot, p]) => {
        let s = byId.get(mimic[slot]);
        if (!s && slot === "total_power" && power.some(Boolean)) {
          // sensor yo'q — agregatlar yig'indisi (sintetik)
          const live = power.filter((u): u is Sensor => !!u && u.alarm !== "stale" && u.last_value != null);
          const worst = power.some((u) => u && (u.alarm === "high" || u.alarm === "low")) ? "high" : live.length ? "ok" : "stale";
          s = { ...(power.find(Boolean) as Sensor), id: -1, name: "Σ agregatlar", last_value: live.length ? live.reduce((a, u) => a + (u.last_value ?? 0), 0) : null, alarm: worst as AlarmState };
        }
        const w = p.w ?? 96;
        const bound = !!s;
        if (!bound && !editing) return null;
        const col = s ? COLOR[s.alarm] : "#4a4e57";
        return (
          <g key={slot} className={onSlotClick ? "mimic-slot clickable" : "mimic-slot"} onClick={() => onSlotClick?.(slot)}>
            <rect x={p.x - w / 2} y={p.y - 16} width={w} height={32} rx="2" fill="var(--panel)" stroke={col} strokeWidth={s && s.alarm !== "ok" ? 2 : 1} strokeDasharray={bound ? undefined : "3 3"} />
            <text x={p.x} y={p.y - 4} textAnchor="middle" className="mimic-lbl">{p.short ?? labels[slot] ?? slot}</text>
            <text x={p.x} y={p.y + 11} textAnchor="middle" className="mimic-val" fill={s && s.alarm === "stale" ? "var(--text-dim)" : "var(--text)"}>
              {s ? `${s.last_value == null ? "—" : fmtValue(s.last_value)} ${s.unit}` : "bog'lash…"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
