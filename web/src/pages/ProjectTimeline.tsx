import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type HistoryItem, type HistoryKind, type ProjectHistory } from "../api/client";
import AlarmMark from "../ui/AlarmMark";
import { fmtDay, fmtTime } from "../ui/format";

const KIND_LABEL: Record<HistoryKind, string> = {
  version: "Versiya",
  cr: "Tasdiqlash so'rovi",
  publish: "Nashr",
  cr_rejected: "Rad etildi",
  issue: "Muammo",
  work_order: "Ish buyrug'i",
  alarm: "Alarm",
};
const FILTERS: { id: "all" | "bim" | "ops"; label: string; kinds: HistoryKind[] }[] = [
  { id: "all", label: "Hammasi", kinds: ["version", "cr", "publish", "cr_rejected", "issue", "work_order", "alarm"] },
  { id: "bim", label: "Model", kinds: ["version", "cr", "publish", "cr_rejected", "issue"] },
  { id: "ops", label: "Ekspluatatsiya", kinds: ["alarm", "work_order"] },
];

function linkOf(pid: number, i: HistoryItem): string | null {
  if (i.model_id && i.version_id && (i.kind === "version" || i.kind === "publish" || i.kind === "cr" || i.kind === "cr_rejected")) return `/models/${i.model_id}?v=${i.version_id}${i.kind === "version" ? "" : "&tab=review"}`;
  if (i.kind === "issue" && i.model_id) return `/models/${i.model_id}?tab=issues`;
  if (i.kind === "work_order") return `/projects/${pid}/dashboard?tab=workorders`;
  if (i.kind === "alarm" && i.sensor_id) return `/projects/${pid}/ops/sensor/${i.sensor_id}`;
  return null;
}

/** Loyiha vaqt chizig'i (UX-12): versiyalar, tasdiqlash so'rovlari, nashrlar, muammolar, ish buyruqlari va muhim
 * alarmlar bitta o'qda — kun bo'yicha guruhlangan, eng yangisi tepada. BIM va SCADA hodisalari yonma-yon. */
export default function ProjectTimeline({ pid }: { pid: number }) {
  const [days, setDays] = useState(30);
  const [filter, setFilter] = useState<"all" | "bim" | "ops">("all");
  const [data, setData] = useState<ProjectHistory | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let dead = false;
    setError("");
    api.projectHistory(pid, days).then((d) => { if (!dead) setData(d); }).catch((e: Error) => { if (!dead) setError(e.message); });
    return () => { dead = true; };
  }, [pid, days]);
  const groups = useMemo(() => {
    const kinds = new Set(FILTERS.find((f) => f.id === filter)!.kinds);
    const out: { day: string; items: HistoryItem[] }[] = [];
    for (const i of data?.items ?? []) {
      if (!kinds.has(i.kind)) continue;
      const day = fmtDay(i.ts);
      if (out.at(-1)?.day !== day) out.push({ day, items: [] });
      out.at(-1)!.items.push(i);
    }
    return out;
  }, [data, filter]);
  return (
    <section className="timeline" aria-labelledby="timeline-h" data-testid="project-timeline">
      <div className="row wrap">
        <h2 id="timeline-h" className="m-0">Vaqt chizig'i</h2>
        <span className="grow" />
        <div className="row gap-4" role="group" aria-label="Hodisa turi">
          {FILTERS.map((f) => <button key={f.id} type="button" className={`btn sm ${filter === f.id ? "active" : ""}`} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>)}
        </div>
        <select className="select w-120" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Davr">
          {[7, 30, 90, 365].map((d) => <option key={d} value={d}>{d} kun</option>)}
        </select>
      </div>
      {error && <p className="error small" role="alert">{error}</p>}
      {data && groups.length === 0 && <p className="muted">Bu davrda hodisa yo'q.</p>}
      {groups.map((g) => (
        <div key={g.day} className="tl-day">
          <h3 className="tl-date">{g.day}</h3>
          <ol className="tl-list">
            {g.items.map((i, n) => {
              const to = linkOf(pid, i);
              return (
                <li key={`${i.kind}-${i.ts}-${n}`} className={`tl-item k-${i.kind}`} data-kind={i.kind}>
                  <span className="tl-time mono">{fmtTime(i.ts)}</span>
                  <span className="tl-kind">{i.kind === "alarm" ? <AlarmMark state="high" priority={i.severity} showCode={false} size={14} /> : null}{KIND_LABEL[i.kind]}</span>
                  <span className="tl-title">{to ? <Link to={to}>{i.title}</Link> : i.title}{i.detail && <span className="dim"> — {i.detail}</span>}</span>
                  {i.actor && <span className="tl-actor dim">{i.actor}</span>}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
      {data?.truncated && <p className="dim small">Faqat oxirgi {data.items.length} ta hodisa ko'rsatildi — davrni qisqartiring.</p>}
    </section>
  );
}
