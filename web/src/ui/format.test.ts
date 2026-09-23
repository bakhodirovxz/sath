import { describe, expect, it } from "vitest";
import { fmtDate, fmtDateMs, fmtDay, fmtShort, fmtTime, isoDayToText, parseDateTime, parseDay, zonedToIso } from "./format";
import { fmtTick } from "./trendMath";

/** UX-09: yagona vaqt formati — Asia/Tashkent (UTC+5), 24 soat, kk.oo.yyyy; brauzer soat mintaqasidan mustaqil. */
describe("format: stansiya vaqti", () => {
  const iso = "2026-01-05T19:30:05.042Z"; // Toshkentda 06.01.2026 00:30:05
  it("sana/vaqt kk.oo.yyyy ss:dd, yarim tun 00 (24 emas)", () => {
    expect(fmtDate(iso)).toBe("06.01.2026 00:30");
    expect(fmtDay(iso)).toBe("06.01.2026");
    expect(fmtTime(iso)).toBe("00:30");
    expect(fmtTime(iso, true)).toBe("00:30:05");
    expect(fmtShort(iso)).toBe("06.01 00:30");
    expect(fmtDateMs(iso)).toBe("06.01.2026 00:30:05.042");
    expect(fmtTick(Date.parse(iso), 5 * 86400_000)).toBe("06.01 00:30");
  });
  it("noto'g'ri qiymat — tire", () => {
    expect(fmtDate("")).toBe("—");
    expect(fmtDate("nimadir")).toBe("—");
    expect(fmtDate(null)).toBe("—");
  });
  it("kiritish: kk.oo.yyyy → yyyy-mm-dd, mavjud bo'lmagan sana rad", () => {
    expect(parseDay("5.1.2026")).toBe("2026-01-05");
    expect(parseDay("31.02.2026")).toBeNull();
    expect(parseDay("2026-01-05")).toBeNull();
    expect(isoDayToText("2026-01-05")).toBe("05.01.2026");
  });
  it("kk.oo.yyyy ss:dd (stansiya vaqti) → UTC ISO va qaytish", () => {
    const out = parseDateTime("06.01.2026 00:30");
    expect(out).toBe("2026-01-05T19:30:00.000Z");
    expect(fmtDate(out)).toBe("06.01.2026 00:30");
    expect(parseDateTime("06.01.2026 24:10")).toBeNull();
    expect(zonedToIso(2026, 7, 1, 12, 0)).toBe("2026-07-01T07:00:00.000Z");
  });
});
