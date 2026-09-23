// WEB-01: matndan tashqi (tarmoqdan) yuklanadigan import/skript/stil havolalarini topadi.
// Minifikatsiyalangan kod ham qamrab olinadi: `from"https://…"`, `import("https://…")`, `import "//cdn…"`,
// HTML dagi `<script src="https://…">`, `<link href="https://…">`, CSS dagi `@import url(https://…)`.
const PATTERNS = [
  /\bfrom\s*["'`]((?:https?:)?\/\/[^"'`\s]+)["'`]/g,
  /\bimport\s*\(?\s*["'`]((?:https?:)?\/\/[^"'`\s]+)["'`]/g,
  /\bimportScripts\s*\(\s*["'`]((?:https?:)?\/\/[^"'`\s]+)["'`]/g,
  /<script\b[^>]*\bsrc\s*=\s*["']((?:https?:)?\/\/[^"']+)["']/gi,
  /<link\b[^>]*\bhref\s*=\s*["']((?:https?:)?\/\/[^"']+)["']/gi,
  /@import\s+(?:url\()?\s*["']?((?:https?:)?\/\/[^"')\s]+)/gi,
];

/** Topilgan tashqi URL lar (takrorsiz). */
export function findRemoteImports(src) {
  const hits = new Set();
  for (const re of PATTERNS) for (const m of src.matchAll(re)) hits.add(m[1]);
  return [...hits];
}
