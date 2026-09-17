// AutoCAD uslubidagi buyruqlar qatori: "ZOOM E", "HIDE", "SEC", "VIEW TOP" ...
// Viewer dan mustaqil — bu yerda faqat tahlil (parse) va ro'yxat; bajarish ModelPage da.

export interface CommandDef {
  name: string;
  aliases: string[];
  description: string;
  usage?: string;
}

export const COMMANDS: CommandDef[] = [
  { name: "ZOOM", aliases: ["Z"], description: "Kamerani moslash", usage: "ZOOM [E|S] — E: hammasi, S: tanlangan" },
  { name: "HIDE", aliases: ["H"], description: "Tanlangan elementlarni yashirish" },
  { name: "ISOLATE", aliases: ["ISO", "I"], description: "Faqat tanlanganlarni qoldirish" },
  { name: "SHOWALL", aliases: ["SHOW", "SA", "UNHIDE"], description: "Hamma elementni ko'rsatish" },
  { name: "MEASURE", aliases: ["DIST", "DI", "M"], description: "Masofa o'lchash (ikki nuqta)" },
  { name: "SECTION", aliases: ["SEC", "CLIP"], description: "Kesim tekisligi (yuzaga bosing)" },
  { name: "SELECT", aliases: ["SEL"], description: "GUID bo'yicha tanlash", usage: "SELECT <guid> [guid...]" },
  { name: "FIND", aliases: ["F"], description: "Nomi bo'yicha qidirish", usage: "FIND <matn>" },
  { name: "VIEW", aliases: ["V"], description: "Standart yoki saqlangan ko'rinish", usage: "VIEW TOP|FRONT|ISO… yoki VIEW <saqlangan nom>" },
  { name: "VSAVE", aliases: ["VS"], description: "Joriy ko'rinishni nom bilan saqlash", usage: "VSAVE <nom>" },
  { name: "PROJ", aliases: ["PROJECTION", "P"], description: "Perspektiva/ortografik almashtirish" },
  { name: "CLEAR", aliases: ["CL"], description: "O'lchov va kesimlarni o'chirish" },
  { name: "LAYER", aliases: ["LA"], description: "Qatlamlar (kategoriyalar) paneli" },
  { name: "PROPS", aliases: ["PR", "PROPERTIES"], description: "Xususiyatlar paneli" },
  { name: "TREE", aliases: ["T"], description: "Model daraxti" },
  { name: "DIFF", aliases: ["D"], description: "Oldingi versiya bilan farq" },
  { name: "ISSUE", aliases: ["IS", "BCF"], description: "Joriy ko'rinishdan issue ochish" },
  { name: "SIM", aliases: ["SIMULATE", "HYDRO"], description: "Simulyatsiya paneli" },
  { name: "MON", aliases: ["MONITOR", "SCADA"], description: "Monitoring paneli (jonli o'lchovlar)" },
  { name: "CFD", aliases: ["FOAM", "FLOW"], description: "CFD oqim hisobi (simulyatsiya paneli)" },
  { name: "CLASH", aliases: ["CHECK", "INTERFERE"], description: "To'qnashuvlarni aniqlash (Tekshiruv paneli)" },
  { name: "QTO", aliases: ["QUANTITY", "BOQ"], description: "Hajm-miqdor hisobi (Tekshiruv paneli)" },
  { name: "ESC", aliases: ["ESCAPE", "CANCEL"], description: "Joriy asbobni bekor qilish" },
  { name: "HELP", aliases: ["?"], description: "Buyruqlar ro'yxati" },
];

const INDEX = new Map<string, CommandDef>();
for (const c of COMMANDS) {
  INDEX.set(c.name, c);
  c.aliases.forEach((a) => INDEX.set(a, c));
}

export interface ParsedCommand {
  name: string;
  args: string[];
  raw: string;
}

export function parseCommand(input: string): ParsedCommand | null {
  const raw = input.trim();
  if (!raw) return null;
  const [head, ...args] = raw.split(/\s+/);
  const def = INDEX.get(head.toUpperCase());
  if (!def) return { name: "UNKNOWN", args: [head, ...args], raw };
  return { name: def.name, args, raw };
}

/** Avtoto'ldirish uchun: prefiksga mos buyruqlar (nom yoki alias). */
export function suggest(prefix: string): CommandDef[] {
  const p = prefix.trim().toUpperCase();
  if (!p) return [];
  const out = new Set<CommandDef>();
  for (const c of COMMANDS) {
    if (c.name.startsWith(p) || c.aliases.some((a) => a.startsWith(p))) out.add(c);
  }
  return [...out];
}

/** Buyruqlar tarixi (yuqoriga/pastga strelka). */
export class CommandHistory {
  private items: string[] = [];
  private pos = 0;
  push(cmd: string) {
    if (cmd && this.items[this.items.length - 1] !== cmd) this.items.push(cmd);
    if (this.items.length > 100) this.items.shift();
    this.pos = this.items.length;
  }
  prev(): string | null {
    if (this.pos > 0) this.pos--;
    return this.items[this.pos] ?? null;
  }
  next(): string | null {
    if (this.pos < this.items.length) this.pos++;
    return this.items[this.pos] ?? null;
  }
  get last(): string | null {
    return this.items[this.items.length - 1] ?? null;
  }
}
