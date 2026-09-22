import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Sensor } from "../../api/client";
import { fmtValue } from "../../ui/format";
import { alarmStyle } from "../../ui/tokens";
import Mimic from "./Mimic";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import { loadScheme } from "./scheme";
import ValueCard from "./ValueCard";
import { AREAS, areaOf, pickKey, sortByAlarm, summarize, unitOf } from "./model";

/** Level 1 — stansiya umumiy ko'rinishi: barcha agregatlar, ombor, tashlama, chiqish quvvati, faol alarmlar
 * ustuvorlik bo'yicha. Operator bir qarashda normal/anomaliya ni ajratadi (ISA-101 §5.4: kam rang, ko'p kontekst). */
export default function L1Overview() {
  return (
    <OperatorShell level={1} crumbs={[{ label: "L1 Umumiy" }]}>
      <Body />
    </OperatorShell>
  );
}

function Body() {
  const { projectId: pid, sensors, dash, summary, events } = useOps();
  const nav = useNavigate();
  const scheme = useMemo(() => (dash ? loadScheme(dash.scheme, dash.mimic, Math.max(1, dash.units.length || 3)) : null), [dash]);
  const enabled = useMemo(() => sensors.filter((s) => s.enabled), [sensors]);
  const key = useMemo(() => ({
    level: pickKey(enabled, [/^RES\.H/, /^RES\./, /UPSTREAM|YUQORI/], "level"),
    inflow: pickKey(enabled, [/^RES\.QIN/, /INFLOW/, /QIN/]),
    spill: pickKey(enabled, [/^RES\.QSPILL/, /SPILL/]),
    tail: pickKey(enabled, [/^TW\./, /TAIL|QUYI/]),
    grid: pickKey(enabled, [/^GRID\.F/, /\.F$/]),
    total: pickKey(enabled, [/^(PLANT|STATION|SUM)\.P/, /TOTAL/]),
  }), [enabled]);
  const units = useMemo(() => {
    const m = new Map<number, Sensor[]>();
    for (const s of enabled) { const u = unitOf(s); if (u != null) m.set(u, [...(m.get(u) ?? []), s]); }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [enabled]);
  const totalPower = useMemo(() => {
    if (key.total?.last_value != null) return key.total.last_value;
    const ps = units.map(([, ss]) => ss.find((s) => s.kind === "power" && /\.P$/i.test(s.key))).filter((s): s is Sensor => !!s && !s.stale && s.last_value != null);
    return ps.length ? ps.reduce((a, s) => a + (s.last_value ?? 0), 0) : null;
  }, [key.total, units]);
  const powerUnit = units.flatMap(([, ss]) => ss).find((s) => s.kind === "power")?.unit ?? "MW";
  const areas = AREAS.map((a) => ({ ...a, sensors: enabled.filter((s) => areaOf(s) === a.id) })).filter((a) => a.sensors.length);
  const worst = sortByAlarm(enabled).filter((s) => alarmStyle(s.alarm, s.priority).rank).slice(0, 6);
  return (
    <div className="l1">
      <div className="dash-kpi l1-kpi">
        <div className={`tile ${summary.total ? "tile-alarm" : ""}`} data-testid="l1-alarms"><div className="tile-t">Faol alarmlar</div><div className="tile-v">{summary.total} <span className="tile-u">{summary.byPriority.critical ? `${summary.byPriority.critical} kritik` : ""}{summary.stale ? ` · ${summary.stale} aloqasiz` : ""}</span></div></div>
        <div className="tile"><div className="tile-t">Chiqish quvvati</div><div className="tile-v">{totalPower == null ? "—" : fmtValue(totalPower)} <span className="tile-u">{powerUnit}</span></div></div>
        <div className="tile"><div className="tile-t">Ombor sathi</div><div className="tile-v">{key.level?.last_value == null ? "—" : fmtValue(key.level.last_value)} <span className="tile-u">{key.level?.unit ?? "m"}</span></div></div>
        <div className="tile"><div className="tile-t">Kiruvchi / tashlama</div><div className="tile-v">{key.inflow?.last_value == null ? "—" : fmtValue(key.inflow.last_value)} / {key.spill?.last_value == null ? "—" : fmtValue(key.spill.last_value)} <span className="tile-u">{key.inflow?.unit ?? "m³/s"}</span></div></div>
        <div className="tile"><div className="tile-t">Agregatlar</div><div className="tile-v">{dash?.units.filter((u) => u.running).length ?? 0}/{dash?.units.length ?? units.length} <span className="tile-u">ishlayapti</span></div></div>
        {key.grid && <div className="tile"><div className="tile-t">Chastota</div><div className="tile-v">{key.grid.last_value == null ? "—" : fmtValue(key.grid.last_value)} <span className="tile-u">{key.grid.unit}</span></div></div>}
      </div>

      {scheme && <div className="panel l1-mimic"><Mimic scheme={scheme} sensors={sensors} onOpen={(sid) => nav(opsPath(pid, "sensor", sid))} /></div>}
      <div className="l1-grid">
        <section className="panel">
          <div className="row"><b>Agregatlar</b><span className="grow" /><Link className="btn sm" to={opsPath(pid, "area", "powerhouse")}>L2 Mashina zali →</Link></div>
          <div className="l1-units">
            {units.length === 0 && <p className="muted">Agregat sensorlari yo'q (kalit AGGn.*)</p>}
            {units.map(([n, ss]) => {
              const p = ss.find((s) => s.kind === "power");
              const run = ss.find((s) => /\.RUN$/i.test(s.key));
              const sm = summarize(ss);
              const st = sm.worst ? alarmStyle(sm.worst.alarm, sm.worst.priority) : null;
              const on = run ? (run.last_value ?? 0) >= 0.5 : !!p && (p.last_value ?? 0) > 0.05 && !p.stale;
              return (
                <Link key={n} to={opsPath(pid, "unit", n)} className={`unit-card ${sm.total ? "alarm" : ""}`} data-testid="unit-card" style={st ? { borderColor: st.color } : undefined}>
                  <div className="row"><b>Agregat {n}</b><span className="grow" />{st && <span className="alarm-mark" style={{ color: st.color }}>{st.glyph}{st.code}</span>}<span className={`badge ${on ? "published" : "archived"}`}>{on ? "ISHLAYAPTI" : "TO'XTAGAN"}</span></div>
                  <div className="tile-v">{p?.last_value == null ? "—" : fmtValue(p.last_value)} <span className="tile-u">{p?.unit ?? ""}</span></div>
                  <div className="dim small">{ss.length} sensor{sm.total ? ` · ${sm.total} alarm` : ""}{sm.stale ? ` · ${sm.stale} aloqasiz` : ""}</div>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="row"><b>Uchastkalar</b></div>
          <div className="l1-areas">
            {areas.map((a) => {
              const sm = summarize(a.sensors);
              const st = sm.worst ? alarmStyle(sm.worst.alarm, sm.worst.priority) : null;
              return (
                <Link key={a.id} to={opsPath(pid, "area", a.id)} className={`area-card ${sm.total ? "alarm" : ""}`} data-testid="area-card" style={st ? { borderColor: st.color } : undefined}>
                  <div className="row"><b>{a.title}</b><span className="grow" />{st ? <span className="alarm-mark" style={{ color: st.color }}>{st.glyph}{sm.total}</span> : <span className="badge published">normal</span>}</div>
                  <div className="dim small">{a.sensors.length} sensor{sm.stale ? ` · ${sm.stale} aloqasiz` : ""}</div>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="row"><b>Eng muhim alarmlar</b><span className="grow" /><Link className="btn sm" to={opsPath(pid, "alarms")}>Alarm sahifasi ({events.filter((e) => !e.acked_at).length} kvitlanmagan) →</Link></div>
          {worst.length === 0 ? <p className="muted">Faol alarm yo'q</p> : (
            <div className="vgrid">{worst.map((s) => <ValueCard key={s.id} s={s} pid={pid} compact />)}</div>
          )}
        </section>
      </div>
    </div>
  );
}
