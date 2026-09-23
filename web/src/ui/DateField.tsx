import { useEffect, useId, useState } from "react";
import { t } from "../i18n";
import { fmtDate, isoDayToText, parseDateTime, parseDay } from "./format";

/** Sana maydonlari (UX-09): brauzerning `<input type=date>` i foydalanuvchi tiliga qarab mm/dd/yyyy ko'rsatadi —
 * o'rniga yagona kk.oo.yyyy format (stansiya vaqti Asia/Tashkent). Enter/blur da tekshiriladi; xato — aria-invalid. */

interface Common {
  className?: string;
  title?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}

/** Kun: qiymat "yyyy-mm-dd" yoki "" (bo'sh — joriy/ixtiyoriy). */
export function DateField({ value, onChange, ...rest }: Common & { value: string; onChange: (isoDay: string) => void }) {
  const [text, setText] = useState(isoDayToText(value));
  const [bad, setBad] = useState(false);
  const errId = useId();
  useEffect(() => { setText(isoDayToText(value)); setBad(false); }, [value]);
  const commit = () => {
    if (!text.trim()) { setBad(false); if (value) onChange(""); return; }
    const d = parseDay(text);
    setBad(!d);
    if (d && d !== value) onChange(d);
  };
  return (
    <span className="date-field">
      <input className={`input ${rest.className ?? ""}`} inputMode="numeric" placeholder={t("date.placeholder")} value={text} title={rest.title ?? t("date.invalid")}
        aria-label={rest["aria-label"]} aria-invalid={bad} aria-describedby={bad ? errId : undefined} data-testid={rest["data-testid"]}
        onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />
      {bad && <span id={errId} className="field-error">{t("date.invalid")}</span>}
    </span>
  );
}

/** Sana va vaqt: qiymat ISO (UTC) yoki "" — ko'rsatish stansiya vaqtida "kk.oo.yyyy ss:dd". */
export function DateTimeField({ value, onChange, ...rest }: Common & { value: string; onChange: (iso: string) => void }) {
  const show = (v: string) => (v ? fmtDate(v) : "");
  const [text, setText] = useState(show(value));
  const [bad, setBad] = useState(false);
  const errId = useId();
  useEffect(() => { setText(show(value)); setBad(false); }, [value]);
  const commit = () => {
    if (!text.trim()) { setBad(false); if (value) onChange(""); return; }
    const iso = parseDateTime(text);
    setBad(!iso);
    if (iso && iso !== value) onChange(iso);
  };
  return (
    <span className="date-field">
      <input className={`input ${rest.className ?? ""}`} placeholder={t("date.placeholderTime")} value={text} title={rest.title ?? t("date.placeholderTime")}
        aria-label={rest["aria-label"]} aria-invalid={bad} aria-describedby={bad ? errId : undefined} data-testid={rest["data-testid"]}
        onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />
      {bad && <span id={errId} className="field-error">{t("date.invalid")}</span>}
    </span>
  );
}
