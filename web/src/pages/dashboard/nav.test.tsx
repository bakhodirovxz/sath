import { describe, expect, it } from "vitest";
import { ZONES, sectionFromQuery } from "../DashboardPage";
import { t } from "../../i18n";

/** UX-07: dispetcher bo'limlari ikki zonada, tanlangan bo'lim URL da (?tab=). */
describe("dispetcher navigatsiyasi", () => {
  it("operator zonasi — sxema, boshqaruv, smena jurnali; muhandislik — egizak, sog'liq, texnik xizmat", () => {
    expect(ZONES.map((z) => z.id)).toEqual(["operator", "engineering"]);
    expect(ZONES[0].sections).toEqual(expect.arrayContaining(["scheme", "control", "journal"]));
    expect(ZONES[1].sections).toEqual(expect.arrayContaining(["twin", "health", "workorders", "parts", "assets"]));
    const all = ZONES.flatMap((z) => z.sections);
    expect(new Set(all).size).toBe(all.length); // bo'lim bitta zonada
    for (const id of all) expect(t(`dash.tab.${id}`)).not.toBe(`dash.tab.${id}`);
  });
  it("?tab= qiymati: to'g'ri — shu bo'lim, noto'g'ri/yo'q — sxema", () => {
    expect(sectionFromQuery("workorders")).toBe("workorders");
    expect(sectionFromQuery("nope")).toBe("scheme");
    expect(sectionFromQuery(null)).toBe("scheme");
  });
  it("admin havolasi 'Boshqaruv' (boshqaruv bo'limi bilan chalkash) emas", () => {
    expect(t("nav.admin")).toBe("Sozlamalar");
    expect(t("dash.tab.control")).toBe("Boshqaruv");
  });
});
