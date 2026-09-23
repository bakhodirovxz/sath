import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { afterEach, describe, expect, it } from "vitest";
import { DICTS, MESSAGE_KEYS, hasKey, setLocale, t, tEnum } from "./index";
import { alarmLabel, commandStatusLabel, priorityLabel, roleLabel, sensorKindLabel, stateLabel } from "./labels";
import { latnToCyrl } from "./translit";

afterEach(() => setLocale("uz-Latn"));

function walk(p: string, out: string[] = []): string[] {
  for (const f of readdirSync(p)) {
    const q = join(p, f);
    if (statSync(q).isDirectory()) walk(q, out);
    else if (/\.(ts|tsx)$/.test(f) && !/\.test\./.test(f)) out.push(q);
  }
  return out;
}

describe("i18n: kalitlar qamrovi (UX-09)", () => {
  const files = walk("src");
  const used = new Set<string>();
  for (const f of files) for (const m of readFileSync(f, "utf8").matchAll(/\bt\(\s*["'`]([a-zA-Z][\w.]*)["'`]/g)) used.add(m[1]);

  it("koddagi har bir t(\"…\") kaliti uz-Latn lug'atida bor", () => {
    expect(used.size).toBeGreaterThanOrEqual(35); // UX-07: navigatsiya, dispetcher zonalari, jonli holat — t() orqali
    expect([...used].filter((k) => !hasKey(k))).toEqual([]);
  });
  it("uz-Cyrl to'liq (transliteratsiya) va ru faqat ma'lum kalitlardan iborat", () => {
    const cyrl = DICTS["uz-Cyrl"]();
    expect(Object.keys(cyrl).sort()).toEqual([...MESSAGE_KEYS].sort());
    expect(Object.keys(DICTS.ru).filter((k) => !hasKey(k))).toEqual([]);
  });
  it("ru: barcha ustuvorlik, alarm holati va buyruq holati yorliqlari tarjima qilingan", () => {
    const need = MESSAGE_KEYS.filter((k) => /^enum\.(priority|alarm|cmd)\./.test(k));
    expect(need.filter((k) => !(k in DICTS.ru))).toEqual([]);
  });
  it("parametr almashtirish va til fallback", () => {
    expect(t("common.ago", { age: "12 s" })).toBe("12 s oldin");
    setLocale("ru");
    expect(t("live.OFFLINE")).toBe("Нет связи");
    expect(t("dash.tab.parts")).toBe("Ehtiyot qismlar"); // ru da yo'q — uz-Latn
    setLocale("uz-Cyrl");
    expect(t("live.OFFLINE")).toBe("Алоқа йўқ");
  });
});

describe("enum yorliqlari: xom inglizcha qiymat chiqmaydi", () => {
  it("ustuvorlik, alarm, buyruq, rol, sensor turi", () => {
    expect(priorityLabel("critical")).toBe("Kritik");
    expect(alarmLabel("stale")).toBe("aloqa yo'q"); // yagona nom ("uzilgan" emas)
    expect(commandStatusLabel("pending")).toBe("navbatda");
    expect(roleLabel("shift_supervisor")).toBe("Smena boshlig'i");
    expect(sensorKindLabel("power")).toBe("Quvvat");
    expect(stateLabel("changes_requested")).toBe("O'zgartirish so'ralgan");
    expect(tEnum("priority", undefined)).toBe("—");
    expect(tEnum("priority", "yangi_qiymat")).toBe("yangi_qiymat");
  });
});

describe("lotin → kirill", () => {
  it("o', g', sh, ch, yo, ye, tutuq belgisi, so'z boshidagi e", () => {
    expect(latnToCyrl("O'zbekiston")).toBe("Ўзбекистон");
    expect(latnToCyrl("yo'q")).toBe("йўқ");
    expect(latnToCyrl("shahar choy")).toBe("шаҳар чой");
    expect(latnToCyrl("Sog'liq")).toBe("Соғлиқ");
    expect(latnToCyrl("ma'lumot")).toBe("маълумот");
    expect(latnToCyrl("eski yangi yozuv")).toBe("эски янги ёзув");
    expect(latnToCyrl("ALOQA YO'Q")).toBe("АЛОҚА ЙЎҚ");
  });
  it("parametr va texnik qisqartmalar o'zgarmaydi", () => {
    expect(latnToCyrl("{age} oldin")).toBe("{age} олдин");
    expect(latnToCyrl("ISA-101 SCADA MW")).toBe("ISA-101 SCADA MW");
  });
});
