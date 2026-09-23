import { useEffect, useState } from "react";
import { api } from "../api/client";
import { annunciator, type AnnunciatorHealth } from "./annunciator";
import Icon from "./Icon";

const LABEL: Record<AnnunciatorHealth, string> = {
  ok: "ovoz ishlayapti",
  blocked: "ovoz bloklangan — bosing",
  silenced: "ovoz vaqtincha o'chirilgan",
  off: "ovoz o'chirilgan",
  unsupported: "ovoz qo'llanmaydi",
};

/** Annunciator sog'ligi va boshqaruvi (F6): ishlayapti / bloklangan (bosib yoqish) / o'chirilgan; silence
 * muddat bilan — auditga yoziladi (server). */
export default function AnnunciatorControl({ projectId, canOperate }: { projectId: number; canOperate: boolean }) {
  const [health, setHealth] = useState<AnnunciatorHealth>(() => annunciator.health());
  const [open, setOpen] = useState(false);
  useEffect(() => {
    annunciator.init();
    setHealth(annunciator.health());
    const off = annunciator.onChange(() => setHealth(annunciator.health()));
    const unlock = () => { void annunciator.unlock().then(setHealth); };
    window.addEventListener("pointerdown", unlock, { once: true });
    const t = window.setInterval(() => setHealth(annunciator.health()), 5000);
    return () => { off(); window.removeEventListener("pointerdown", unlock); window.clearInterval(t); };
  }, []);
  const silence = async (minutes: number) => {
    annunciator.silence(minutes);
    setOpen(false);
    try { await api.annunciatorSilence(projectId, minutes); } catch { /* audit yozilmasa ham ovoz o'chiriladi; server logida ko'rinadi */ }
  };
  const cls = health === "ok" ? "published" : health === "blocked" ? "rejected" : "archived";
  return (
    <span className="row gap-4 rel" data-testid="annunciator" data-health={health}>
      <button className={`btn sm ${health === "blocked" ? "danger" : ""}`} title={LABEL[health]} onClick={() => (health === "blocked" ? void annunciator.unlock().then(setHealth) : setOpen((v) => !v))}>
        <Icon name={health === "ok" ? "volume" : "volume-x"} size={12} /> <span className={`badge ${cls}`}>{health}</span>
      </button>
      {open && (
        <div className="menu-list menu-right" role="menu">
          <button className="menu-item" onClick={() => { annunciator.setMuted(!annunciator.muted); setOpen(false); }}>{annunciator.muted ? "Ovozni yoqish" : "Ovozni o'chirish (doimiy)"}</button>
          {canOperate && [5, 15, 30, 60].map((m) => <button key={m} className="menu-item" onClick={() => silence(m)}>Silence {m} daqiqa (auditga yoziladi)</button>)}
          {annunciator.silencedUntil && <button className="menu-item" onClick={() => silence(0)}>Silence ni bekor qilish</button>}
        </div>
      )}
    </span>
  );
}
