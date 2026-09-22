import { Link } from "react-router-dom";
import type { Sensor } from "../../api/client";
import { fmtValue } from "../../ui/format";
import { alarmStyle, qualityStyle } from "../../ui/tokens";
import { ageSeconds, fmtAge } from "./model";
import { opsPath } from "./OperatorShell";

/** Qiymat kartasi (ISA-101): qiymat + birlik, alarm belgisi (shakl + kod), sifat kodi, yosh.
 * Eskirgan/yaroqsiz qiymat hech qachon "normal" ko'rinmaydi: `?`/`✕` belgisi va yosh matni. */
export default function ValueCard({ s, pid, compact = false, now }: { s: Sensor; pid: number; compact?: boolean; now?: number }) {
  const st = alarmStyle(s.alarm, s.priority);
  const q = qualityStyle(s.last_quality);
  const age = ageSeconds(s.last_ts, now);
  const stale = !!s.stale || (age != null && age > s.stale_after_s);
  const bad = s.last_quality === "bad";
  const mode = s.alarm_mode && s.alarm_mode !== "normal" ? s.alarm_mode : s.suppressed ? "suppressed" : null;
  return (
    <Link to={opsPath(pid, "sensor", s.id)} className={`vcard ${st.rank ? "alarm" : ""} ${stale ? "stale" : ""} ${bad ? "bad" : ""} ${compact ? "compact" : ""}`} data-testid="vcard" data-key={s.key} style={st.rank && !mode ? { borderColor: st.color } : undefined}>
      <div className="vcard-t">
        <span className="vcard-name">{s.name}</span>
        {st.code && <span className="alarm-mark" style={{ color: st.color }} title={st.label}>{st.glyph}{st.code}</span>}
        {mode && <span className="badge archived" title={`Alarm rejimi: ${mode}`}>{mode === "shelved" ? "shelved" : mode === "out_of_service" ? "OOS" : "bostirilgan"}</span>}
      </div>
      <div className="vcard-v">
        {s.last_value == null ? "—" : fmtValue(s.last_value)} <span className="vcard-u">{s.unit}</span>
        {q.code && <span className="alarm-mark" style={{ color: q.color }} title={`Sifat: ${q.label}`}>{q.code}</span>}
        {stale && <span className="alarm-mark" style={{ color: "var(--alarm-stale)" }} title="aloqa yo'q / eskirgan">?</span>}
      </div>
      {!compact && <div className="vcard-age dim">{s.key} · {fmtAge(age)}{stale ? " · ESKIRGAN" : ""}</div>}
    </Link>
  );
}
