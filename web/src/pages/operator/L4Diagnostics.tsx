import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ReadingPoint, type Sensor } from "../../api/client";
import { fmtDate, fmtValue } from "../../ui/format";
import { qualityStyle } from "../../ui/tokens";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import { ageSeconds, fmtAge } from "./model";
import GatewayKeys from "../../ui/GatewayKeys";
import { can } from "../../api/permissions";

/** Level 4 — diagnostika: sensor xom qiymatlari va sifat tarixi, aloqa holati (yosh, stale), gateway
 * diagnostika teglari (GW.*), kalit muddati, jonli oqim holati. Operator "nega qiymat yo'q" ga javob topadi. */
export default function L4Diagnostics() {
  const { projectId, sensorId } = useParams();
  const pid = Number(projectId);
  return (
    <OperatorShell level={4} crumbs={[{ label: "L1 Umumiy", to: opsPath(pid) }, { label: "L4 Diagnostika" }]}>
      <Body sensorId={sensorId ? Number(sensorId) : null} />
    </OperatorShell>
  );
}

function Body({ sensorId }: { sensorId: number | null }) {
  const { projectId: pid, sensors, live, project } = useOps();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [sel, setSel] = useState<number | null>(sensorId);
  const [raw, setRaw] = useState<ReadingPoint[]>([]);
  const now = Date.now();
  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);
  useEffect(() => { if (sel != null) api.readings(sel, 1, 200).then((r) => setRaw(r.points)).catch(() => setRaw([])); }, [sel]);
  const gw = useMemo(() => sensors.filter((s) => /^GW\./i.test(s.key)), [sensors]);
  const stale = useMemo(() => sensors.filter((s) => s.enabled && (s.stale || (ageSeconds(s.last_ts, now) ?? Infinity) > s.stale_after_s)), [sensors, now]);
  const bad = useMemo(() => sensors.filter((s) => s.enabled && s.last_quality && s.last_quality !== "good"), [sensors]);
  const s: Sensor | undefined = sensors.find((x) => x.id === sel);
  return (
    <div className="l4">
      <div className="dash-kpi">
        <div className={`tile ${live !== "LIVE" ? "tile-alarm" : ""}`}><div className="tile-t">Jonli oqim (WebSocket)</div><div className="tile-v">{live}</div></div>
        <div className="tile"><div className="tile-t">Server</div><div className="tile-v">{health ? String(health.status ?? "ok") : "—"} <span className="tile-u">{health && typeof health.version === "string" ? health.version : ""}</span></div></div>
        <div className={`tile ${stale.length ? "tile-alarm" : ""}`}><div className="tile-t">Aloqasiz sensorlar</div><div className="tile-v">{stale.length} <span className="tile-u">/ {sensors.filter((x) => x.enabled).length}</span></div></div>
        <div className={`tile ${bad.length ? "tile-alarm" : ""}`}><div className="tile-t">Sifati yaxshi emas</div><div className="tile-v">{bad.length}</div></div>
      </div>
      <div className="l3-grid">
        <section className="panel">
          <div className="row"><b>Gateway diagnostikasi</b><span className="dim small">GW.* teglari (spool, soat farqi)</span></div>
          {gw.length === 0 ? <p className="muted">GW.* diagnostika teglari yo'q — gateway konfiguratsiyasida <code>diag: true</code> va serverda shu kalitli sensorlar kerak.</p> : (
            <table className="grid small"><tbody>{gw.map((g) => <tr key={g.id}><td className="mono">{g.key}</td><td className="mono">{g.last_value == null ? "—" : fmtValue(g.last_value)}</td><td className="dim">{fmtAge(ageSeconds(g.last_ts, now))}</td></tr>)}</tbody></table>
          )}
          <GatewayKeys projectId={pid} canManage={can(project?.my_role, "gateway.keys")} compact />
        </section>
        <section className="panel">
          <div className="row"><b>Aloqa holati</b></div>
          {stale.length === 0 ? <p className="muted">Barcha sensorlar vaqtida ma'lumot beryapti</p> : (
            <table className="grid small"><thead><tr><th>Sensor</th><th>Oxirgi</th><th>Yosh</th><th>Chegara</th></tr></thead><tbody>
              {stale.map((x) => <tr key={x.id}><td><Link to={opsPath(pid, "sensor", x.id)}>{x.name}</Link> <span className="dim mono">{x.key}</span></td><td className="dim">{x.last_ts ? fmtDate(x.last_ts) : "—"}</td><td className="error mono">{fmtAge(ageSeconds(x.last_ts, now))}</td><td className="mono">{x.stale_after_s} s</td></tr>)}
            </tbody></table>
          )}
          {bad.length > 0 && (
            <>
              <div className="row mt-8"><b>Sifat</b></div>
              <table className="grid small"><tbody>{bad.map((x) => { const q = qualityStyle(x.last_quality); return <tr key={x.id}><td><Link to={opsPath(pid, "sensor", x.id)}>{x.name}</Link></td><td className="alarm-mark" style={{ color: q.color }}>{q.code} {q.label}</td></tr>; })}</tbody></table>
            </>
          )}
        </section>
        <section className="panel">
          <div className="row"><b>Xom qiymatlar (oxirgi 1 soat)</b><span className="grow" />
            <select className="select w-220" value={sel ?? ""} onChange={(e) => setSel(e.target.value ? Number(e.target.value) : null)}>
              <option value="">sensor tanlang…</option>{sensors.map((x) => <option key={x.id} value={x.id}>{x.key} — {x.name}</option>)}
            </select>
          </div>
          {s && <p className="small dim">{s.key} · protokol {s.protocol} · manzil {JSON.stringify(s.address)} · sifat {s.last_quality ?? "good"} · xom diapazon {s.min_raw ?? "—"}…{s.max_raw ?? "—"}</p>}
          {sel != null && (raw.length === 0 ? <p className="muted">Ma'lumot yo'q</p> : (
            <table className="grid small mono"><thead><tr><th>Vaqt</th><th>Qiymat</th></tr></thead><tbody>{raw.slice(-60).reverse().map((p, i) => <tr key={i}><td>{fmtDate(p.ts)}</td><td>{fmtValue(p.v)} {s?.unit}</td></tr>)}</tbody></table>
          ))}
        </section>
      </div>
    </div>
  );
}
