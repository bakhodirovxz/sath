/** Chop etish hisobotlari (simulyatsiya, xavfsizlik tekshiruvi): qog'oz uchun yorug' palitra — token fayli
 * (hex faqat token fayllarida: tokens.ts, tokens.css, viewer/palette.ts, shu fayl).
 *
 * CSP (`script-src 'self'`): yangi oynaga inline `<script>` yozilmaydi — chop etish ochgan oynadan chaqiriladi. */

export const PRINT_INK = { text: "#111111", muted: "#555555", dim: "#777777", rule: "#cccccc", hair: "#e3e3e3", tint: "#f6f7f8", ok: "#1c6b3f", warn: "#8a5a00", bad: "#b3261e" } as const;

export const PRINT_BASE_CSS = `body{font:13px/1.45 system-ui,"Segoe UI",sans-serif;color:${PRINT_INK.text};margin:28px;max-width:960px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:18px 0 6px;border-bottom:1px solid ${PRINT_INK.rule}}
.meta{color:${PRINT_INK.muted};margin-bottom:10px}.dim{color:${PRINT_INK.dim}}
.verdict{padding:8px 12px;border-left:4px solid ${PRINT_INK.ok};background:${PRINT_INK.tint};margin:10px 0}.verdict.bad{border-left-color:${PRINT_INK.bad}}.verdict.warn{border-left-color:${PRINT_INK.warn}}
.tiles{display:flex;flex-wrap:wrap;gap:8px}.tile{border:1px solid ${PRINT_INK.rule};border-radius:6px;padding:8px 12px;min-width:140px}.tile b{font-size:18px}.tile div{color:${PRINT_INK.muted};font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid ${PRINT_INK.hair};padding:4px 6px;text-align:left;vertical-align:top}td.n{text-align:right;font-family:ui-monospace,monospace}
tr.fail td:nth-child(2){color:${PRINT_INK.bad}}tr.warn td:nth-child(2){color:${PRINT_INK.warn}}tr.ok td:nth-child(2){color:${PRINT_INK.ok}}
.chart{margin:10px 0;page-break-inside:avoid;max-width:520px}.ct{font-weight:600;margin-bottom:2px}svg{width:100%;height:auto;background:#ffffff}
.chart-grid{stroke:${PRINT_INK.hair}}.chart-tick{fill:${PRINT_INK.muted};font-size:10px;font-family:ui-monospace,monospace}.chart-ref{stroke:${PRINT_INK.dim};stroke-dasharray:4 3}.chart-cursor{display:none}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:${PRINT_INK.text}}.score{font-size:28px;font-weight:700}.score small{font-size:14px;font-weight:400}
footer{margin-top:20px;color:${PRINT_INK.dim};font-size:11px}@media print{body{margin:10mm}}`;

/** Hisobot oynasini ochib, chop etish dialogini chaqiradi. Qaytaradi: oyna ochildimi (popup bloklangan bo'lsa — false). */
export function openPrintWindow(title: string, bodyHtml: string, lang = "uz"): boolean {
  const w = window.open("", "_blank");
  if (!w) return false;
  const esc = (v: string) => v.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
  w.document.write(`<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${PRINT_BASE_CSS}</style></head><body>${bodyHtml}</body></html>`);
  w.document.close();
  w.setTimeout(() => w.print(), 300);
  return true;
}
