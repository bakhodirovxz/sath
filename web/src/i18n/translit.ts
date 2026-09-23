/** O'zbek lotin → kirill transliteratsiyasi (UX-09): uz-Cyrl lug'ati uz-Latn dan avtomatik olinadi, alohida
 * tarjima kerak emas. Qoidalar (1995 imlo): o'→ў, g'→ғ, sh→ш, ch→ч, yo→ё, yu→ю, ya→я, ye→е, so'z boshidagi e→э,
 * tutuq belgisi → ъ, h→ҳ, q→қ, x→х. `{param}` va texnik qisqartmalar (SCADA, ISA-101, MW…) o'zgarmaydi. */

const SINGLE: Record<string, string> = {
  a: "а", b: "б", d: "д", e: "е", f: "ф", g: "г", h: "ҳ", i: "и", j: "ж", k: "к", l: "л", m: "м", n: "н", o: "о",
  p: "п", q: "қ", r: "р", s: "с", t: "т", u: "у", v: "в", x: "х", y: "й", z: "з", c: "ц", w: "в",
};
const APOS = new Set(["'", "ʼ", "ʻ", "’", "‘", "`"]);

/** O'zgarmaydigan texnik qisqartmalar va birliklar (katta/kichik harf farqi bilan). */
const KEEP = new Set([
  "ISA", "ISA-101", "ISA-18.2", "SCADA", "IFC", "BIM", "HMI", "OOS", "LOTO", "SOE", "CSV", "CR", "BCF", "QTO", "IDS", "KKS",
  "HH", "LL", "ROC", "DEV", "MW", "MWh", "kW", "CFD", "GES", "MQTT", "OPC", "UA", "HTTP", "TCP", "EEMUA", "MFA", "L1", "L2",
  "L3", "L4", "OK", "SVG", "JSON", "Modbus", "ingest", "command", "shelved", "push", "heartbeat", "SVG", "ISO",
]);

function translitWord(w: string): string {
  if (KEEP.has(w) || /^[A-Z0-9][A-Z0-9.-]*[0-9]/.test(w)) return w;
  let out = "";
  for (let i = 0; i < w.length; i++) {
    const c = w[i];
    const lc = c.toLowerCase();
    const upper = c !== lc;
    const next = w[i + 1]?.toLowerCase() ?? "";
    const next2 = w[i + 2] ?? "";
    const up = (s: string) => (upper ? (w.length > 1 && w === w.toUpperCase() ? s.toUpperCase() : s[0].toUpperCase() + s.slice(1)) : s);
    if ((lc === "o" || lc === "g") && APOS.has(w[i + 1] ?? "")) { out += up(lc === "o" ? "ў" : "ғ"); i++; continue; }
    if (lc === "s" && next === "h") { out += up("ш"); i++; continue; }
    if (lc === "c" && next === "h") { out += up("ч"); i++; continue; }
    if (lc === "y" && (next === "o" || next === "u" || next === "a" || next === "e") && !APOS.has(next2)) {
      out += up(next === "o" ? "ё" : next === "u" ? "ю" : next === "a" ? "я" : "е");
      i++;
      continue;
    }
    if (lc === "e" && i === 0) { out += up("э"); continue; }
    if (APOS.has(c)) { out += "ъ"; continue; }
    const m = SINGLE[lc];
    out += m ? up(m) : c;
  }
  return out;
}

export function latnToCyrl(text: string): string {
  // {param} va so'zlar alohida; so'z — harf/raqam/tutuq belgisi/chiziqcha ketma-ketligi
  return text.split(/(\{[^}]*\}|[A-Za-z0-9'ʼʻ’‘`.-]+)/g).map((part) => {
    if (!part || part.startsWith("{")) return part;
    if (!/[A-Za-z]/.test(part)) return part;
    // oxirgi nuqta/chiziqcha so'zga kirmaydi
    const m = /^(.*?)([.-]*)$/.exec(part)!;
    return translitWord(m[1]) + m[2];
  }).join("");
}
