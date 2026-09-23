import { useState } from "react";
import Dialog from "../../ui/Dialog";
import type { MeshImportInfo } from "../../api/client";
import { MESH_UNITS, unitLabel } from "./meshImport";

/** CAD-04: fayl birligi aniqlanmadi/shubhali — foydalanuvchi qabul qiladi yoki boshqa birlik bilan qayta import
 * qiladi (unit_override). Jimgina taxmin yo'q: aniqlangan birlik, manba va ogohlantirishlar ko'rsatiladi. */
export default function MeshUnitCheck({ fileName, info, warnings, busy, onAccept, onReimport }: {
  fileName: string;
  info: MeshImportInfo | null;
  warnings: string[];
  busy: boolean;
  onAccept: () => void;
  onReimport: (unit: string) => void;
}) {
  const detected = info?.unit ?? "m";
  const [unit, setUnit] = useState(detected === "m" ? "mm" : "m");
  return (
    <Dialog title="Fayl birligini tasdiqlang" onClose={onAccept}>
      <div data-testid="mesh-unit-check">
        <p>
          <b>{fileName}</b> — birlik aniq emas. Model <b>{unitLabel(detected)}</b> deb o'qildi
          {info?.unit_source ? <> (manba: {info.unit_source})</> : null}.
        </p>
        {info?.unit_note && <p className="muted small">{info.unit_note}</p>}
        {warnings.length > 0 && (
          <div className="verdict attention small"><ul className="warnings">{warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>
        )}
        <p className="small">Agar o'lchamlar noto'g'ri bo'lsa (masalan, to'g'on 1000 marta katta/kichik), to'g'ri birlikni tanlab qayta import qiling — yangi versiya yaratiladi, oldingi holat tarixda qoladi.</p>
        <label className="field w-200"><span>To'g'ri birlik</span>
          <select className="select" value={unit} onChange={(e) => setUnit(e.target.value)} data-testid="mesh-unit-select">
            {MESH_UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
          </select>
        </label>
        <div className="actions">
          <button type="button" className="btn" onClick={onAccept} disabled={busy}>{unitLabel(detected)} — to'g'ri, qabul qilish</button>
          <button type="button" className="btn primary" onClick={() => onReimport(unit)} disabled={busy || unit === detected} data-testid="mesh-reimport">{busy ? "Import qilinmoqda…" : `${unitLabel(unit)} bilan qayta import`}</button>
        </div>
      </div>
    </Dialog>
  );
}
