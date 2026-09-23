import { useCallback, useEffect, useState } from "react";
import { api, type AuditStatus, type DeletedModel, type StorageGcReport } from "../../api/client";
import { dialogs } from "../../ui/dialogs";
import { fmtDate, fmtSize } from "../../ui/format";

/** Administrator: o'chirilgan modellar savati (VCS-06: yumshoq o'chirish → tiklash / butunlay o'chirish),
 * saqlash tozalash (GC: avval sinov hisobot, keyin ishga tushirish) va audit jurnali holati. */
export function DeletedModelsSection() {
  const [rows, setRows] = useState<DeletedModel[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => api.deletedModels().then(setRows).catch((e: Error) => { setRows([]); setError(e.message); }), []);
  useEffect(() => { void load(); }, [load]);
  const act = async (m: DeletedModel, kind: "restore" | "purge") => {
    const ok = kind === "restore"
      ? await dialogs.confirm("Modelni tiklash", { text: `«${m.name}» loyihaga qaytadi (versiyalar, tarix saqlangan).`, ok: "Tiklash" })
      : await dialogs.confirm("Butunlay o'chirish", { text: `«${m.name}»: ${m.version_count} ta versiya, tasdiqlash so'rovlari, muammolar va simulyatsiyalar qaytarib bo'lmaydigan tarzda o'chadi. Boshqa hech kim ishlatmaydigan fayllar ham o'chiriladi.`, ok: "Butunlay o'chirish", danger: true });
    if (!ok) return;
    setBusy(m.id); setError("");
    try {
      if (kind === "restore") await api.restoreDeletedModel(m.id); else await api.purgeDeletedModel(m.id);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Xato"); } finally { setBusy(null); }
  };
  return (
    <section aria-labelledby="deleted-models-h" data-testid="deleted-models">
      <h1 id="deleted-models-h" className="mt-24">O'chirilgan modellar</h1>
      <p className="muted small">Model o'chirilganda savatga tushadi — administrator tiklashi yoki butunlay o'chirishi mumkin.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {rows && rows.length === 0 && !error && <p className="dim">Savat bo'sh</p>}
      {rows && rows.length > 0 && (
        <table className="grid small">
          <thead><tr><th>Model</th><th>Loyiha</th><th>Versiyalar</th><th>O'chirilgan</th><th /></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td><b>{m.name}</b>{m.description && <div className="dim">{m.description}</div>}</td>
                <td>{m.project_id}</td>
                <td className="mono">{m.version_count}</td>
                <td className="mono">{fmtDate(m.deleted_at)}</td>
                <td className="row gap-6">
                  <button className="btn sm" disabled={busy === m.id} onClick={() => void act(m, "restore")}>Tiklash</button>
                  <button className="btn sm danger" disabled={busy === m.id} onClick={() => void act(m, "purge")}>Butunlay o'chirish</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function StorageSection() {
  const [rep, setRep] = useState<StorageGcReport | null>(null);
  const [status, setStatus] = useState<AuditStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.auditStatus().then(setStatus).catch(() => setStatus(null)); }, []);
  const gc = async (dryRun: boolean) => {
    if (!dryRun && !(await dialogs.confirm("Saqlashni tozalash", { text: `${rep ? `${rep.blobs + rep.derived + rep.temp} ta fayl (${fmtSize(rep.bytes)})` : "Murojaatsiz fayllar"} o'chiriladi. Oxirgi 24 soatda yozilganlar saqlanadi. Amal auditga yoziladi.`, ok: "Tozalash", danger: true }))) return;
    setBusy(true); setError("");
    try { setRep(await api.storageGc(dryRun)); } catch (e) { setError(e instanceof Error ? e.message : "Xato"); } finally { setBusy(false); }
  };
  return (
    <section aria-labelledby="storage-h" data-testid="storage">
      <h1 id="storage-h" className="mt-24">Saqlash va audit holati</h1>
      {status && (
        <p className={status.write_failures ? "verdict bad" : "verdict ok"} role="status" data-testid="audit-status">
          Audit jurnali: {status.write_failures ? `${status.write_failures} ta yozish xatosi, ${status.lost_entries} ta yozuv yo'qolgan (oxirgisi ${status.last_failure_at ? fmtDate(status.last_failure_at) : "—"}: ${status.last_error})` : "yozish xatosi yo'q"}{status.hash_alg ? ` · zanjir ${status.hash_alg}` : ""}
        </p>
      )}
      <div className="row wrap">
        <button className="btn" disabled={busy} onClick={() => void gc(true)} data-testid="gc-dry">Sinov (hisobot)</button>
        <button className="btn danger" disabled={busy || !rep || !rep.dry_run || rep.blobs + rep.derived + rep.temp === 0} onClick={() => void gc(false)} data-testid="gc-run" title="Avval sinov hisobotini ko'ring">Tozalash</button>
        {busy && <span className="muted small" role="status">tekshirilmoqda…</span>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {rep && (
        <p className="small" data-testid="gc-report">
          {rep.dry_run ? "Sinov: o'chiriladi" : "O'chirildi"} — {rep.blobs} ta fayl, {rep.derived} ta hosilaviy (kesh), {rep.temp} ta vaqtinchalik · {fmtSize(rep.bytes)}; yangi (saqlab qolindi): {rep.kept_recent}{rep.errors ? ` · xatolar: ${rep.errors}` : ""}
        </p>
      )}
    </section>
  );
}
