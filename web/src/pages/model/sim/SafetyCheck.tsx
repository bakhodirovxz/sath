import { useState } from "react";
import { api, type SafetyCheck as Safety, type Version } from "../../../api/client";
import Icon from "../../../ui/Icon";
import type { Viewer } from "../../../viewer/Viewer";

/* Xavfsizlik tekshiruvi — standart ssenariylar (toshqinlar, N−1, zilzila, barqarorlik, filtratsiya, yoriq,
   gidrozarba, ko'chki) bir bosishda; ok/warn/fail jadvali, umumiy ball, natijani ochish, issue, chop etish. */

const STATUS: Record<string, { label: string; color: string; icon: string }> = {
  ok: { label: "bajarildi", color: "var(--ok)", icon: "check-circle" },
  warn: { label: "ogohlantirish", color: "var(--warn, #b98626)", icon: "alert-circle" },
  fail: { label: "bajarilmadi", color: "var(--danger)", icon: "alert-triangle" },
  skip: { label: "hisoblanmadi", color: "var(--muted)", icon: "info" },
};

const fmt = (v: unknown) => (typeof v === "number" ? (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)) : String(v ?? "—"));

export default function SafetyCheck({ modelId, current, viewer, onOpenJob, onDone }: { modelId: number; current: Version | null; viewer: Viewer | null; onOpenJob: (kind: string, jobId: number) => void; onDone: () => void }) {
  const [res, setRes] = useState<Safety | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  async function run() {
    setBusy(true); setErr("");
    try { setRes(await api.safetyCheck(modelId, current?.id ?? null)); setOpen(true); onDone(); } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  async function issue() {
    if (!res) return;
    const bad = res.rows.filter((r) => r.status === "fail" || r.status === "warn");
    if (!bad.length) return;
    try {
      const vp = viewer ? await viewer.getViewpoint() : { camera: null, selected_guids: [], section: [] };
      const lines = bad.map((r) => `• ${r.title} — ${STATUS[r.status].label}: ${r.message}`);
      const is = await api.createIssue(modelId, { title: `Xavfsizlik tekshiruvi: ${res.counts.fail} ta mezon bajarilmadi, ${res.counts.warn} ogohlantirish (ball ${res.score})`, description: `Standart ssenariylar to'plami (${current ? `v${current.number}` : ""}):\n${lines.join("\n")}`, version_id: current?.id ?? null, priority: res.counts.fail ? "high" : "normal", viewpoint: vp as never });
      setErr(`Issue #${is.id} yaratildi`);
    } catch (e) { setErr(e instanceof Error ? e.message : "Issue yaratilmadi"); }
  }
  function print() {
    if (!res) return;
    const esc = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
    const rows = res.rows.map((r) => `<tr class="${r.status}"><td>${esc(r.title)}<div class="dim">${esc(r.why)}</div></td><td><b>${esc(STATUS[r.status].label)}</b></td><td>${esc(r.message)}</td><td class="mono">${Object.entries(r.metrics).map(([k, v]) => `${esc(k)} = ${esc(fmt(v))}`).join("<br>")}</td></tr>`).join("");
    const html = `<!doctype html><html lang="uz"><head><meta charset="utf-8"><title>Xavfsizlik tekshiruvi</title><style>body{font:13px/1.45 system-ui,sans-serif;color:#111;margin:28px;max-width:960px}h1{font-size:20px;margin:0 0 4px}.meta{color:#555;margin-bottom:10px}.score{font-size:28px;font-weight:700}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid #e3e3e3;padding:5px 6px;text-align:left;vertical-align:top}.dim{color:#777;font-size:11px}.mono{font-family:ui-monospace,monospace;font-size:11px}tr.fail td:nth-child(2){color:#c0392b}tr.warn td:nth-child(2){color:#b98626}tr.ok td:nth-child(2){color:#27ae60}footer{margin-top:16px;color:#777;font-size:11px}@media print{body{margin:10mm}}</style></head><body><h1>Xavfsizlik tekshiruvi — standart ssenariylar</h1><div class="meta">${current ? `model versiyasi v${current.number} · ` : ""}${esc(new Date().toLocaleString("uz"))}</div><div class="score">${res.score} / 100 <span style="font-size:14px;font-weight:400">— ${esc(res.verdict)}</span></div><p>${res.counts.ok} bajarildi · ${res.counts.warn} ogohlantirish · ${res.counts.fail} bajarilmadi · ${res.counts.skip} hisoblanmadi</p><table><thead><tr><th>Ssenariy</th><th>Holat</th><th>Xulosa</th><th>Ko'rsatkichlar</th></tr></thead><tbody>${rows}</tbody></table><footer>Sath · mezonlar: KMK 2.06.05 / ICOLD amaliyoti (zaxira, K ≥ 1.5/1.3/1.1, suffoziya ≥ 1.5, quvur ≥ 1.5)</footer><script>window.addEventListener("load",()=>setTimeout(()=>window.print(),300))</script></body></html>`;
    const w = window.open("", "_blank");
    if (!w) { setErr("Brauzer yangi oynani bloklagan"); return; }
    w.document.write(html); w.document.close();
  }
  return (
    <div className="section-box small" style={{ marginBottom: 10 }}>
      <div className="row" style={{ alignItems: "center", gap: 8 }}>
        <Icon name="shield" size={16} />
        <b className="grow">Xavfsizlik tekshiruvi</b>
        {res && <span className="badge" style={{ background: res.counts.fail ? "var(--danger)" : res.counts.warn ? "var(--warn, #b98626)" : "var(--ok)", color: "#fff" }}>{res.score}/100</span>}
        <button className="btn sm primary" disabled={busy} onClick={() => void run()} title="Barcha ssenariylarni hisoblash (har biri «Oldingi hisoblar» ga saqlanadi)">{busy ? "Hisoblanmoqda…" : res ? "Qayta tekshirish" : "Tekshirish"}</button>
        {res && <button className="btn sm" onClick={() => setOpen(!open)}>{open ? "Yig'ish" : "Ko'rsatish"}</button>}
      </div>
      <div className="dim small">12 standart ssenariy (toshqinlar, N−1 darvoza, zilzila, barqarorlik, filtratsiya, yoriq, gidrozarba, ko'chki) — pasport + model bilan bir bosishda; har biri «Oldingi hisoblar» ga saqlanadi.</div>
      {err && <div className="small" style={{ marginTop: 4 }}>{err}</div>}
      {res && open && (
        <div style={{ marginTop: 6 }}>
          <div className={`verdict ${res.counts.fail ? "bad" : "ok"}`}><Icon name={res.counts.fail ? "alert-triangle" : "check-circle"} size={14} /> <span>{res.verdict} · {res.counts.ok} ok · {res.counts.warn} ogohlantirish · {res.counts.fail} bajarilmadi{res.counts.skip ? ` · ${res.counts.skip} hisoblanmadi` : ""}</span></div>
          <div className="safety-rows">
            {res.rows.map((r) => (
              <div key={r.id} className="node" style={{ display: "block", padding: "4px 6px", borderLeft: `3px solid ${STATUS[r.status].color}` }} title={r.why}>
                <div className="row" style={{ alignItems: "center", gap: 6 }}>
                  <span style={{ color: STATUS[r.status].color, display: "inline-flex" }}><Icon name={STATUS[r.status].icon} size={13} /></span>
                  <b className="grow">{r.title}</b>
                  {r.job_id && <button className="btn sm" title="Natijani ochish (grafiklar, 3D)" onClick={() => onOpenJob(r.kind, r.job_id!)}><Icon name="external-link" size={11} /></button>}
                </div>
                <div className="small" style={{ color: STATUS[r.status].color }}>{STATUS[r.status].label} — <span style={{ color: "var(--text)" }}>{r.message}</span></div>
                {Object.keys(r.metrics).length > 0 && <div className="dim small mono">{Object.entries(r.metrics).map(([k, v]) => `${k} = ${fmt(v)}`).join(" · ")}</div>}
              </div>
            ))}
          </div>
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <button className="btn sm" onClick={print}><Icon name="printer" size={11} /> Hisobot</button>
            {(res.counts.fail > 0 || res.counts.warn > 0) && <button className="btn sm" onClick={() => void issue()} title="Bajarilmagan mezonlar bo'yicha issue (tasdiqlash oqimiga)"><Icon name="flag" size={11} /> Issue ochish</button>}
          </div>
        </div>
      )}
    </div>
  );
}
