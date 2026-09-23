import { useEffect, useState } from "react";
import { api, type GatewayKey, type GatewayKeyKind } from "../api/client";
import { keyKindLabel } from "../i18n/labels";
import { fmtDate, fmtDay } from "./format";

/** Gateway kalitlari (SCADA-04): kalit serverda faqat xesh sifatida saqlanadi — qiymati FAQAT yaratilganda/
 * almashtirilganda bir marta ko'rsatiladi; keyin prefiks. GET kalit yaratmaydi — «Yaratish» aniq amal.
 * Monitoring paneli va L4 diagnostikada bir xil. */
export default function GatewayKeys({ projectId, canManage, compact = false }: { projectId: number; canManage: boolean; compact?: boolean }) {
  const [keys, setKeys] = useState<GatewayKey[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<GatewayKeyKind | null>(null);
  useEffect(() => {
    if (!canManage) return;
    Promise.all([api.projectKey(projectId, "ingest"), api.projectKey(projectId, "command")]).then(setKeys).catch((e) => setErr(e instanceof Error ? e.message : "Xato"));
  }, [projectId, canManage]);
  if (!canManage) return null;
  const rotate = async (kind: GatewayKeyKind) => {
    setBusy(kind); setErr("");
    try {
      const nk = await api.rotateProjectKey(projectId, kind);
      setKeys((p) => (p ?? []).map((x) => (x.kind === nk.kind ? nk : x)));
    } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); } finally { setBusy(null); }
  };
  return (
    <div className="gw-keys" data-testid="gateway-keys">
      {err && <p className="error small">{err}</p>}
      {(keys ?? []).map((k) => {
        const exists = k.exists !== false;
        const shown = k.key ?? null;
        return (
          <div key={k.kind} className="gw-key">
            <div className="row wrap gap-6">
              <b>{keyKindLabel(k.kind)}</b>
              {exists ? <span className={k.days_left != null && k.days_left <= 14 ? "error" : "dim"}>{k.expires_at ? `muddat: ${fmtDay(k.expires_at)} (${k.days_left} kun)` : "muddatsiz"}</span> : <span className="dim">yaratilmagan</span>}
              {exists && <span className="dim">· oxirgi ishlatilgan: {k.last_used_at ? fmtDate(k.last_used_at) : "hali yo'q"}</span>}
              <button className={`btn sm ${exists ? "danger" : "primary"}`} disabled={busy === k.kind} onClick={() => void rotate(k.kind)} data-testid={`key-rotate-${k.kind}`}>{exists ? "Almashtirish (365 kun)" : "Yaratish"}</button>
            </div>
            {shown
              ? <div className="verdict warn small" role="status" data-testid={`key-shown-${k.kind}`}>Kalit FAQAT hozir ko'rsatiladi — nusxalab gateway hostiga saqlang (serverda faqat xeshi turadi): <code className="mono selectable">{shown}</code></div>
              : exists && <div className="dim small">Kalit yashirin (prefiks <span className="mono">{k.key_prefix ?? "—"}…</span>); yo'qolgan bo'lsa — almashtiring.</div>}
            {!compact && exists && (
              <pre className="mono code-sample">{k.kind === "ingest"
                ? `curl -X POST ${location.origin}${k.url} \\\n  -H "${k.header}: ${shown ?? `${k.key_prefix ?? ""}…`}" -H "Content-Type: application/json" \\\n  -d '[{"key":"AGG1.P","value":24.3},{"key":"RES.LEVEL","value":903.2}]'`
                : `curl -X POST ${location.origin}${k.url} -H "${k.header}: ${shown ?? `${k.key_prefix ?? ""}…`}"`}</pre>
            )}
          </div>
        );
      })}
    </div>
  );
}
