import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type MyTasks } from "../api/client";
import { t } from "../i18n";
import { priorityLabel } from "../i18n/labels";
import { fmtDate, fmtValue } from "../ui/format";
import TopBar from "../ui/TopBar";

/** "Mening vazifalarim" (UX-12): meni kutayotgan tasdiqlash so'rovlari, o'zgartirish so'ralgan CR larim,
 * menga biriktirilgan muammolar va ish buyruqlari, ikki kishi qoidasida tasdiq kutayotgan buyruqlar. Bo'sh
 * bo'limlar ko'rsatilmaydi; hammasi bo'sh — "vazifa yo'q". */
export default function MyTasksPage() {
  const [data, setData] = useState<MyTasks | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.myTasks().then(setData).catch((e: Error) => setError(e.message)); }, []);
  return (
    <div className="page">
      <TopBar crumbs={[{ label: t("nav.projects"), to: "/" }, { label: t("nav.myTasks") }]} />
      <div className="page-body page-narrow" data-testid="my-tasks">
        <h1>{t("nav.myTasks")}</h1>
        {error && <p className="error" role="alert">{error}</p>}
        {!data && !error && <p className="muted">{t("common.loading")}</p>}
        {data && data.total === 0 && <p className="muted" data-testid="tasks-empty">Sizni kutayotgan vazifa yo'q.</p>}
        {data && data.command_approvals.length > 0 && (
          <section className="task-section" aria-labelledby="t-cmd">
            <h2 id="t-cmd">Buyruq tasdig'i (ikki kishi qoidasi) <span className="count-pill">{data.command_approvals.length}</span></h2>
            <table className="grid">
              <thead><tr><th>Loyiha</th><th>Nuqta</th><th>Qiymat</th><th>Muallif</th><th>Vaqt</th><th /></tr></thead>
              <tbody>{data.command_approvals.map((c) => (
                <tr key={c.id} data-testid="task-command">
                  <td>{c.project_name}</td><td><b>{c.sensor_name}</b> <span className="dim mono">{c.sensor_key}</span></td>
                  <td className="mono">{fmtValue(c.value)} {c.unit}</td><td>{c.author}</td><td className="mono">{fmtDate(c.created_at)}</td>
                  <td><Link className="btn sm" to={`/projects/${c.project_id}/dashboard?tab=control`}>Ko'rib chiqish</Link></td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        )}
        {data && data.reviews.length > 0 && (
          <section className="task-section" aria-labelledby="t-rev">
            <h2 id="t-rev">Tasdiqlash so'rovlari <span className="count-pill">{data.reviews.length}</span></h2>
            <table className="grid">
              <thead><tr><th>So'rov</th><th>Model</th><th>Muallif</th><th>Ochilgan</th></tr></thead>
              <tbody>{data.reviews.map((c) => (
                <tr key={c.id} data-testid="task-review">
                  <td><Link to={`/models/${c.model_id}?v=${c.version_id}&tab=review`}>#{c.id} {c.title}</Link></td>
                  <td>{c.project_name} › {c.model_name} v{c.version_number}</td><td>{c.author}</td><td className="mono">{fmtDate(c.created_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        )}
        {data && data.my_change_requests.length > 0 && (
          <section className="task-section" aria-labelledby="t-mine">
            <h2 id="t-mine">O'zgartirish so'ralgan so'rovlarim <span className="count-pill">{data.my_change_requests.length}</span></h2>
            <ul className="task-list">{data.my_change_requests.map((c) => (
              <li key={c.id}><Link to={`/models/${c.model_id}?v=${c.version_id}&tab=review`}>#{c.id} {c.title}</Link> <span className="dim">— {c.project_name} › {c.model_name} v{c.version_number}</span></li>
            ))}</ul>
          </section>
        )}
        {data && data.issues.length > 0 && (
          <section className="task-section" aria-labelledby="t-iss">
            <h2 id="t-iss">Menga biriktirilgan muammolar <span className="count-pill">{data.issues.length}</span></h2>
            <table className="grid">
              <thead><tr><th>Muammo</th><th>Model</th><th>Ustuvorlik</th><th>Yangilangan</th></tr></thead>
              <tbody>{data.issues.map((i) => (
                <tr key={i.id} data-testid="task-issue">
                  <td><Link to={`/models/${i.model_id}?tab=issues`}>#{i.id} {i.title}</Link></td>
                  <td>{i.project_name} › {i.model_name}</td><td>{i.priority}</td><td className="mono">{fmtDate(i.updated_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        )}
        {data && data.work_orders.length > 0 && (
          <section className="task-section" aria-labelledby="t-wo">
            <h2 id="t-wo">Menga biriktirilgan ish buyruqlari <span className="count-pill">{data.work_orders.length}</span></h2>
            <table className="grid">
              <thead><tr><th>Ish buyrug'i</th><th>Loyiha</th><th>Ustuvorlik</th><th>Muddat</th></tr></thead>
              <tbody>{data.work_orders.map((w) => (
                <tr key={w.id} data-testid="task-wo">
                  <td><Link to={`/projects/${w.project_id}/dashboard?tab=workorders`}>#{w.id} {w.title}</Link>{w.loto_active && <span className="badge rejected ml-4">LOTO</span>}</td>
                  <td>{w.project_name}</td><td>{priorityLabel(w.priority)}</td><td className="mono">{w.due_at ? fmtDate(w.due_at) : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        )}
      </div>
    </div>
  );
}
