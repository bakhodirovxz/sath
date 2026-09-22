import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Sensor } from "../../api/client";
import { DialogHost, dialogs } from "../../ui/dialogs";
import ControlBlock, { validateSetpoint } from "./ControlBlock";

const mk = (o: Partial<Sensor> = {}): Sensor => ({ id: 5, project_id: 1, model_id: null, key: "GATE1.SP", name: "Zatvor", kind: "position", unit: "%", element_guid: null, protocol: "modbus", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 40, last_ts: null, alarm: "ok", stale: false, priority: "medium", writable: true, min_setpoint: 0, max_setpoint: 100, max_rate_per_min: 20, requires_dual_approval: false, ...o } as Sensor);

describe("boshqaruv validatsiyasi (F8, klient)", () => {
  it("diapazondan tashqari, chekli bo'lmagan, bo'sh — rad; tezlik — ogohlantirish", () => {
    const s = mk();
    expect(validateSetpoint(s, "5000")).toMatchObject({ ok: false, reason: expect.stringContaining("maksimum 100") });
    expect(validateSetpoint(s, "-1")).toMatchObject({ ok: false, reason: expect.stringContaining("minimum 0") });
    expect(validateSetpoint(s, "abc").ok).toBe(false);
    expect(validateSetpoint(s, "").ok).toBe(false);
    expect(validateSetpoint(s, "Infinity").ok).toBe(false);
    expect(validateSetpoint(s, "45")).toEqual({ ok: true });
    expect(validateSetpoint(s, "90")).toMatchObject({ ok: true, warn: expect.stringContaining("tezlik") });
    expect(validateSetpoint(mk({ min_setpoint: null, max_setpoint: null, max_rate_per_min: null }), "1e6")).toEqual({ ok: true });
  });
  it("ControlBlock: diapazondan tashqari qiymatda «Tanlash» o'chiq va rad matni; yozib bo'lmaydigan sensor — hech narsa", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })));
    const html = renderToStaticMarkup(<ControlBlock projectId={1} sensor={mk()} canCommand />);
    expect(html).toContain('data-testid="control-block"');
    expect(html).toContain("0 … 100 %");
    expect(html).toContain("1. Tanlash");
    expect(renderToStaticMarkup(<ControlBlock projectId={1} sensor={mk({ writable: false })} canCommand />)).toBe("");
    expect(renderToStaticMarkup(<ControlBlock projectId={1} sensor={mk()} canCommand={false} />)).toContain("operator huquqi kerak");
    vi.unstubAllGlobals();
  });
});

describe("dialogs host (F8: confirm/prompt/alert o'rniga)", () => {
  let root: Root;
  let el: HTMLDivElement;
  beforeEach(() => { el = document.createElement("div"); document.body.appendChild(el); root = createRoot(el); act(() => { root.render(<DialogHost />); }); });
  afterEach(() => { act(() => root.unmount()); el.remove(); });
  it("confirm → Ha/Bekor; prompt → matn; alert → OK; navbat", async () => {
    let p1!: Promise<boolean>;
    await act(async () => { p1 = dialogs.confirm("Savol?"); await Promise.resolve(); });
    expect(el.textContent).toContain("Savol?");
    act(() => { (el.querySelector("[data-testid=dlg-confirm]") as HTMLButtonElement).click(); });
    expect(await p1).toBe(true);
    let p2!: Promise<string | null>;
    await act(async () => { p2 = dialogs.prompt("Nom", "abc"); await Promise.resolve(); });
    const inp = el.querySelector("[data-testid=dlg-prompt]") as HTMLInputElement;
    expect(inp.value).toBe("abc");
    act(() => { (el.querySelector("[data-testid=dlg-confirm]") as HTMLButtonElement).click(); });
    expect(await p2).toBe("abc");
    let p3!: Promise<boolean>;
    let p4!: Promise<void>;
    await act(async () => { p3 = dialogs.confirm("Yana?"); p4 = dialogs.alert("Diqqat", "matn"); await Promise.resolve(); });
    expect(el.textContent).toContain("Yana?");
    act(() => { (el.querySelector(".btn:not(.primary)") as HTMLButtonElement).click(); }); // Bekor
    expect(await p3).toBe(false);
    await act(async () => { await Promise.resolve(); });
    expect(el.textContent).toContain("Diqqat");
    act(() => { (el.querySelector("[data-testid=dlg-confirm]") as HTMLButtonElement).click(); });
    await p4;
    expect(el.textContent).toBe("");
  });
});
