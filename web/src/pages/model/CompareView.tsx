import { useEffect, useRef, useState } from "react";
import { api, type Diff, type Version } from "../../api/client";
import Dialog from "../../ui/Dialog";
import { Viewer } from "../../viewer/Viewer";

/** Versiya ochish: server tayyorlagan fragments bo'lsa — shu (tez), aks holda IFC. */
async function loadInto(vw: Viewer, v: Version, label: string) {
  const frag = await api.versionFragments(v.id).catch(() => null);
  if (frag) await vw.loadFragments(frag, label);
  else await vw.loadIfc(await api.versionFile(v.id), label);
}

type Mode = "side" | "slider";

/** Versiyalarni taqqoslash (UX-12): ikki viewport yonma-yon yoki bitta ekranda slayder bilan (chap — eski, o'ng —
 * yangi). Kameralar sinxron (IFC koordinatalarida); farq ranglari ikkala tomonda (qo'shilgan / o'zgargan / o'chgan). */
export default function CompareView({ modelName, from, to, diff, onClose }: { modelName: string; from: Version; to: Version; diff: Diff | null; onClose: () => void }) {
  const leftEl = useRef<HTMLDivElement>(null);
  const rightEl = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<Mode>("side");
  const [split, setSplit] = useState(50);
  const [status, setStatus] = useState("Yuklanmoqda…");
  useEffect(() => {
    const prev = (window as unknown as { __gesViewer?: Viewer | undefined }).__gesViewer; // e2e/diagnostika — asosiy viewer qaytariladi
    const a = new Viewer();
    const b = new Viewer();
    let dead = false;
    const offs: (() => void)[] = [];
    void (async () => {
      try {
        await Promise.all([a.init(leftEl.current!), b.init(rightEl.current!)]);
        if (dead) return;
        await Promise.all([loadInto(a, from, `${modelName} v${from.number}`), loadInto(b, to, `${modelName} v${to.number}`)]);
        if (dead) return;
        if (diff) await Promise.all([a.applyDiff(diff), b.applyDiff(diff)]);
        await a.fitAll(false);
        b.lookAtFrom(a);
        // Sinxron kamera: qaysi tomon harakatlansa — ikkinchisi ergashadi (aks-sado aylanmasin)
        let syncing = false;
        const follow = (src: Viewer, dst: Viewer) => () => { if (syncing) return; syncing = true; dst.lookAtFrom(src); syncing = false; };
        offs.push(a.onViewChange(follow(a, b)), b.onViewChange(follow(b, a)));
        setStatus(diff ? `+${diff.summary.added} qo'shilgan · ~${diff.summary.changed} o'zgargan · −${diff.summary.deleted} o'chgan` : "");
      } catch (e) {
        if (!dead) setStatus(e instanceof Error ? e.message : "Yuklanmadi");
      }
    })();
    return () => {
      dead = true;
      offs.forEach((f) => f());
      a.dispose();
      b.dispose();
      (window as unknown as { __gesViewer?: Viewer | undefined }).__gesViewer = prev;
    };
  }, [from, to, diff, modelName]);
  return (
    <Dialog title={`Taqqoslash: v${from.number} ↔ v${to.number}`} onClose={onClose} className="compare-dialog">
      <div className="row wrap cmp-bar">
        <div className="row gap-4" role="group" aria-label="Taqqoslash rejimi">
          <button type="button" className={`btn sm ${mode === "side" ? "active" : ""}`} aria-pressed={mode === "side"} onClick={() => setMode("side")}>Yonma-yon</button>
          <button type="button" className={`btn sm ${mode === "slider" ? "active" : ""}`} aria-pressed={mode === "slider"} onClick={() => setMode("slider")} data-testid="cmp-slider-mode">Slayder</button>
        </div>
        <span className="dim small" role="status">{status}</span>
        <span className="grow" />
        {diff && <span className="small cmp-legend"><i className="lg-added" /> qo'shilgan <i className="lg-changed" /> o'zgargan <i className="lg-deleted" /> o'chgan</span>}
        <button type="button" className="btn sm" onClick={onClose}>Yopish</button>
      </div>
      <div className={`cmp-stage ${mode}`} data-testid="compare-view" data-mode={mode}>
        <div className="cmp-pane cmp-left"><div ref={leftEl} className="cmp-canvas" /><span className="cmp-tag">v{from.number}</span></div>
        {/* slayder: o'ng (yangi) qatlam chap chegaradan kesiladi — dinamik qiymat, shuning uchun inline */}
        <div className="cmp-pane cmp-right" style={mode === "slider" ? { clipPath: `inset(0 0 0 ${split}%)` } : undefined}>
          <div ref={rightEl} className="cmp-canvas" />
          <span className="cmp-tag">v{to.number}</span>
        </div>
        {mode === "slider" && <div className="cmp-divider" style={{ left: `${split}%` }} aria-hidden="true" />}
        {mode === "slider" && (
          <input type="range" className="cmp-range" min={0} max={100} step={1} value={split} onChange={(e) => setSplit(Number(e.target.value))} aria-label="Slayder: chap — eski, o'ng — yangi versiya" data-testid="cmp-range" />
        )}
      </div>
    </Dialog>
  );
}
