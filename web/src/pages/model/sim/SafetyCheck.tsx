import { useState } from "react";
import { api, type SafetyCheck as Safety, type Version } from "../../../api/client";
import Icon from "../../../ui/Icon";
import type { Viewer } from "../../../viewer/Viewer";
import { openPrintWindow } from "../../../ui/print";
import { fmtDate } from "../../../ui/format";
import { notify } from "../../../ui/notice";

/* Xavfsizlik tekshiruvi — standart ssenariylar (toshqinlar, N−1, zilzila, barqarorlik, filtratsiya, yoriq,
   gidrozarba, ko'chki) bir bosishda; ok/warn/fail jadvali, umumiy ball, natijani ochish, issue, chop etish. */

/** Holat: yorliq, rang sinfi (theme.css), belgi — rang yagona kanal emas (belgi + matn). */
const STATUS: Record<string, { label: string; cls: string; icon: string }> = {
  ok: { label: "bajarildi", cls: "c-ok", icon: "check-circle" },
  warn: { label: "ogohlantirish", cls: "c-warn", icon: "alert-circle" },
  fail: { label: "bajarilmadi", cls: "c-danger", icon: "alert-triangle" },
  skip: { label: "hisoblanmadi", cls: "dim", icon: "info" },
};

const fmt = (v: unknown) => (typeof v === "number" ? (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)) : String(v ?? "—"));

export default function SafetyCheck({ modelId, current, viewer, onOpenJob, onDone, canRun = true }: { modelId: number; current: Version | null; viewer: Viewer | null; onOpenJob: (kind: string, jobId: number) => void; onDone: () => void; canRun?: boolean }) {
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
      const is = await api.createIssue(modelId, { title: `Xavfsizlik tekshiruvi: ${res.counts.fail} ta mezon bajarilmadi, ${res.counts.warn} ogohlantirish (ball ${res.score ?? "—"})`, description: `Standart ssenariylar to'plami (${current ? `v${current.number}` : ""}):\n${lines.join("\n")}`, version_id: current?.id ?? null, priority: res.counts.fail ? "high" : "normal", viewpoint: vp as never });
      notify(`Muammo #${is.id} yaratildi`);
    } catch (e) { setErr(e instanceof Error ? e.message : "Muammo yaratilmadi"); }
  }
  function print() {
    if (!res) return;
    const esc = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
    const rows = res.rows.map((r) => `<tr class="${r.status}"><td>${esc(r.title)}<div class="dim">${esc(r.why)}</div></td><td><b>${esc(STATUS[r.status].label)}</b></td><td>${esc(r.message)}${r.warnings?.length ? `<div class="dim">⚠ ${r.warnings.map(esc).join("; ")}</div>` : ""}</td><td class="mono">${Object.entries(r.metrics).map(([k, v]) => `${esc(k)} = ${esc(fmt(v))}`).join("<br>")}</td></tr>`).join("");
    const body = `<h1>Xavfsizlik tekshiruvi — standart ssenariylar</h1><div class="meta">${current ? `model versiyasi v${current.number} · ` : ""}${esc(fmtDate(Date.now()))}</div><div class="score">${res.score ?? "—"} / 100 <small>— ${esc(res.verdict)}</small></div><p>${res.counts.ok} bajarildi · ${res.counts.warn} ogohlantirish · ${res.counts.fail} bajarilmadi · ${res.counts.skip} hisoblanmadi</p><table><thead><tr><th>Ssenariy</th><th>Holat</th><th>Xulosa</th><th>Ko'rsatkichlar</th></tr></thead><tbody>${rows}</tbody></table><footer>Sath · mezonlar: KMK 2.06.05 / ICOLD amaliyoti (zaxira, K ≥ 1.5/1.3/1.1, suffoziya ≥ 1.5, quvur ≥ 1.5)</footer>`;
    if (!openPrintWindow("Xavfsizlik tekshiruvi", body)) setErr("Brauzer yangi oynani bloklagan");
  }
  return (
    <div className="section-box small mb-8">
      <div className="row items-center gap-8">
        <Icon name="shield" size={16} />
        <b className="grow">Xavfsizlik tekshiruvi</b>
        {res && <span className={`badge score-badge ${res.counts.fail ? "fail" : res.counts.skip ? "skip" : res.counts.warn ? "warn" : "ok"}`} title={res.overall === "incomplete" ? "Hisoblanmagan mezon bor — umumiy baho yo'q" : undefined}>{res.score ?? "—"}/100</span>}
        <button className="btn sm primary" disabled={busy || !canRun} onClick={() => void run()} title={canRun ? "Barcha ssenariylarni hisoblash (har biri «Oldingi hisoblar» ga saqlanadi)" : "Hisoblash — muhandis va tasdiqlovchi uchun (ko'ruvchi faqat natijalarni ko'radi)"}>{busy ? "Hisoblanmoqda…" : res ? "Qayta tekshirish" : "Tekshirish"}</button>
        {res && <button className="btn sm" onClick={() => setOpen(!open)}>{open ? "Yig'ish" : "Ko'rsatish"}</button>}
      </div>
      <div className="dim small">12 standart ssenariy (toshqinlar, N−1 darvoza, zilzila, barqarorlik, filtratsiya, yoriq, gidrozarba, ko'chki) — pasport + model bilan bir bosishda; har biri «Oldingi hisoblar» ga saqlanadi.</div>
      {err && <div className="small mt-4">{err}</div>}
      {res && open && (
        <div className="mt-6">
          <div className={`verdict ${res.counts.fail ? "bad" : "ok"}`}><Icon name={res.counts.fail ? "alert-triangle" : "check-circle"} size={14} /> <span>{res.verdict} · {res.counts.ok} ok · {res.counts.warn} ogohlantirish · {res.counts.fail} bajarilmadi{res.counts.skip ? ` · ${res.counts.skip} hisoblanmadi` : ""}</span></div>
          <div className="safety-rows">
            {res.rows.map((r) => (
              <div key={r.id} className={`safety-row st-${r.status}`} title={r.why}>
                <div className="row items-center gap-6">
                  <Icon name={STATUS[r.status].icon} size={13} className={STATUS[r.status].cls} />
                  <b className="grow">{r.title}</b>
                  {r.job_id && <button className="btn sm" title="Natijani ochish (grafiklar, 3D)" onClick={() => onOpenJob(r.kind, r.job_id!)}><Icon name="external-link" size={11} /></button>}
                </div>
                <div className={`small ${STATUS[r.status].cls}`}>{STATUS[r.status].label} — <span className="c-text">{r.message}</span></div>
                {r.warnings && r.warnings.length > 0 && <div className="small c-warn" title="Usul amal doirasi / ishonchlilik">⚠ {r.warnings.join("; ")}</div>}
                {Object.keys(r.metrics).length > 0 && <div className="dim small mono">{Object.entries(r.metrics).map(([k, v]) => `${k} = ${fmt(v)}`).join(" · ")}</div>}
              </div>
            ))}
          </div>
          <div className="row gap-6 mt-6">
            <button className="btn sm" onClick={print}><Icon name="printer" size={11} /> Hisobot</button>
            {(res.counts.fail > 0 || res.counts.warn > 0) && <button className="btn sm" onClick={() => void issue()} title="Bajarilmagan mezonlar bo'yicha muammo (tasdiqlash oqimiga)"><Icon name="flag" size={11} /> Issue ochish</button>}
          </div>
        </div>
      )}
    </div>
  );
}
