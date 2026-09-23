import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { fmtDate } from "../../ui/format";
import { alarmStyle } from "../../ui/tokens";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import ValueCard from "./ValueCard";
import { AREAS, areaOf, sortByAlarm, summarize, unitOf, type AreaId } from "./model";
import AlarmMark from "../../ui/AlarmMark";
import { unackedSensorIds } from "../../store/live";

/** Level 2 — texnologik uchastka (gidrotexnik / mashina zali / elektr): uchastka sensorlari qiymat kartalari,
 * uchastka alarmlari; agregat bo'yicha guruhlash (mashina zali). Har karta → L3 faceplate. */
export default function L2Area() {
  const { area, projectId } = useParams();
  const a = AREAS.find((x) => x.id === area) ?? AREAS[0];
  return (
    <OperatorShell level={2} crumbs={[{ label: "L1 Umumiy", to: opsPath(Number(projectId)) }, { label: `L2 ${a.title}` }]}>
      <Body area={a.id} title={a.title} />
    </OperatorShell>
  );
}

function Body({ area, title }: { area: AreaId; title: string }) {
  const { projectId: pid, sensors, events } = useOps();
  const unacked = unackedSensorIds(events);
  const mine = useMemo(() => sortByAlarm(sensors.filter((s) => s.enabled && areaOf(s) === area)), [sensors, area]);
  const sm = summarize(mine);
  const ids = new Set(mine.map((s) => s.id));
  const myEvents = events.filter((e) => ids.has(e.sensor_id) && !e.ended_at);
  const groups = useMemo(() => {
    if (area !== "powerhouse") return [["", mine] as const];
    const m = new Map<string, typeof mine>();
    for (const s of mine) { const u = unitOf(s); const k = u != null ? `Agregat ${u}` : "Umumiy"; m.set(k, [...(m.get(k) ?? []), s]); }
    return [...m.entries()].sort((x, y) => x[0].localeCompare(y[0]));
  }, [mine, area]);
  return (
    <div className="l2">
      <div className="row mb-8">
        <h2 className="m-0">{title}</h2>
        <span className="grow" />
        {sm.worst ? <span className="row gap-6"><AlarmMark state={sm.worst.alarm} priority={sm.worst.priority} showCode={false} size={18} /><b>{sm.total} faol alarm</b></span> : <span className="state-tag">alarm yo'q</span>}
        {sm.stale > 0 && <span className="badge archived">{sm.stale} aloqasiz</span>}
      </div>
      {mine.length === 0 && <p className="muted">Bu uchastkada sensor yo'q. Sensor kaliti (masalan RES.H, AGG1.P, TR1.OIL) yoki turi bo'yicha tasniflanadi.</p>}
      {groups.map(([g, ss]) => (
        <section key={g || "all"} className="panel mb-8">
          {g && <div className="row"><b>{g}</b><span className="grow" />{/^Agregat (\d+)$/.test(g) && <Link className="btn sm" to={opsPath(pid, "unit", g.replace(/\D/g, ""))}>L3 Faceplate →</Link>}</div>}
          <div className="vgrid">{ss.map((s) => <ValueCard key={s.id} s={s} pid={pid} unacked={unacked.has(s.id)} />)}</div>
        </section>
      ))}
      <section className="panel">
        <div className="row"><b>Uchastka alarmlari</b><span className="grow" /><Link className="btn sm" to={opsPath(pid, "alarms")}>Alarm sahifasi →</Link></div>
        {myEvents.length === 0 ? <p className="muted">Faol alarm yo'q</p> : (
          <table className="grid small">
            <thead><tr><th>Vaqt</th><th>Sensor</th><th>Holat</th><th>Qiymat</th><th /></tr></thead>
            <tbody>
              {myEvents.map((e) => {
                const st = alarmStyle(e.state, e.priority ?? "medium");
                return (
                  <tr key={e.id} className="alarm-active">
                    <td className="mono">{fmtDate(e.started_at)}</td>
                    <td><Link to={opsPath(pid, "sensor", e.sensor_id)}>{e.sensor_name}</Link></td>
                    <td><AlarmMark state={e.state} priority={e.priority} unacked={!e.acked_at} /> {st.label}</td>
                    <td className="mono">{e.value == null ? "—" : `${e.value} ${e.unit}`}</td>
                    <td>{e.acked_at ? <span className="dim">kvitlangan</span> : <span className="badge rejected">UNACK</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
