import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import type { Sensor } from "../../api/client";
import ValueCard from "./ValueCard";

const mk = (o: Partial<Sensor> = {}): Sensor => ({ id: 1, project_id: 1, model_id: null, key: "RES.H", name: "Yuqori byef", kind: "level", unit: "m", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: 905, stale_after_s: 600, enabled: true, last_value: 903.2, last_ts: new Date().toISOString(), alarm: "ok", stale: false, priority: "critical", writable: false, alarm_mode: "normal", ...o } as Sensor);

/** Sifat/eskirish ko'rsatilishi (F4) — @testing-library/react bilan (F10). */
describe("ValueCard sifat ko'rsatilishi", () => {
  afterEach(cleanup);
  const r = (s: Sensor) => render(<MemoryRouter><ValueCard s={s} pid={1} /></MemoryRouter>);
  it("yaxshi sifat: qiymat, kod yo'q", () => {
    r(mk());
    const card = screen.getByTestId("vcard");
    expect(card).toHaveTextContent("903.2");
    expect(card.className).not.toContain("bad");
    expect(card.className).not.toContain("stale");
  });
  it("bad sifat: ✕ kodi va chizilgan qiymat; eskirgan: ? va ESKIRGAN", () => {
    r(mk({ last_quality: "bad" }));
    expect(screen.getByTitle(/yaroqsiz/)).toHaveTextContent("✕");
    expect(screen.getByTestId("vcard").className).toContain("bad");
    cleanup();
    r(mk({ stale: true }));
    expect(screen.getByTestId("vcard").className).toContain("stale");
    expect(screen.getByTestId("vcard")).toHaveTextContent("ESKIRGAN");
    cleanup();
    r(mk({ last_ts: new Date(Date.now() - 3600_000).toISOString() })); // yosh > stale_after_s
    expect(screen.getByTestId("vcard")).toHaveTextContent("ESKIRGAN");
  });
  it("alarm: shakl + kod (rangdan mustaqil), shelved rejimi belgisi", () => {
    r(mk({ alarm: "highhigh" }));
    const mark = screen.getByRole("img", { name: /1-ustuvorlik: juda yuqori/ });
    expect(mark).toHaveTextContent("HH"); // kod matn sifatida
    expect(mark.dataset.prio).toBe("critical");
    expect(mark.dataset.shape).toBe("diamond"); // shakl — rangdan mustaqil kanal
    expect(mark.className).not.toContain("unacked");
    expect(screen.getByTestId("vcard").className).toContain("prio-critical");
    expect(screen.getByTestId("vcard").getAttribute("style")).toBeNull(); // inline rang yo'q
    cleanup();
    render(<MemoryRouter><ValueCard s={mk({ alarm: "high", priority: "low" })} pid={1} unacked /></MemoryRouter>);
    const m2 = screen.getByRole("img", { name: /kvitlanmagan/ });
    expect(m2.className).toContain("unacked");
    expect(m2.dataset.shape).toBe("circle");
    cleanup();
    r(mk({ alarm: "high", alarm_mode: "shelved" }));
    expect(screen.getByTestId("vcard")).toHaveTextContent("shelved");
  });
});
