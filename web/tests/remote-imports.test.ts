import { describe, expect, it } from "vitest";
// @ts-expect-error — oddiy JS modul (build skripti), tiplar yo'q
import { findRemoteImports } from "../scripts/remote-imports.mjs";

/** WEB-01: build natijasida tashqi import qolsa check-bundle yiqiladi. */
describe("findRemoteImports (WEB-01)", () => {
  it("minifikatsiyalangan statik/dinamik import va HTML/CSS havolalarini topadi", () => {
    const src = [
      'import a from"https://cdn.jsdelivr.net/npm/opentype.js@1.3.4/+esm";',
      'const m=await import("https://esm.sh/x");',
      'import "//cdn.example.com/y.js";',
      '<script type="module" src="https://unpkg.com/z"></script>',
      '<link rel="stylesheet" href="https://fonts.googleapis.com/css">',
      '@import url(https://fonts.example.com/a.css);',
      'importScripts("https://w.example.com/w.js")',
    ].join("\n");
    expect(findRemoteImports(src).sort()).toEqual([
      "//cdn.example.com/y.js",
      "https://cdn.jsdelivr.net/npm/opentype.js@1.3.4/+esm",
      "https://esm.sh/x",
      "https://fonts.example.com/a.css",
      "https://fonts.googleapis.com/css",
      "https://unpkg.com/z",
      "https://w.example.com/w.js",
    ]);
  });
  it("oddiy satrlar va lokal importlar xato emas", () => {
    const src = 'import x from"./three-abc.js";const u="https://github.com/x";fetch("https://api");<a href="https://doc">';
    expect(findRemoteImports(src)).toEqual([]);
  });
});
