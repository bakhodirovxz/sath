import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canCommandRole, setToken, type Command, type Sensor } from "../../api/client";
import { can } from "../../api/permissions";
import GatewayKeys from "../../ui/GatewayKeys";
import { setpointRangeError } from "../model/MonitoringPanel";
import ControlBlock from "./ControlBlock";

/** SCADA-01/02/04: rollar (loyihalash rollari buyruq bermaydi), boshqaruv chegaralari, kalit bir marta ko'rsatiladi,
 * noma'lum buyruq natijasi ko'zga tashlanadi. */

const json = (b: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } }));
beforeEach(() => setToken("t"));
afterEach(() => vi.unstubAllGlobals());

describe("ruxsatlar (server ROLE_PERMISSIONS bilan bir xil)", () => {
  it("buyruq — faqat operator va smena boshlig'i; tasdiq/chetlab o'tish/qo'lda kiritish — smena boshlig'i", () => {
    expect(["viewer", "operator", "shift_supervisor", "engineer", "approver"].filter((r) => canCommandRole(r as never))).toEqual(["operator", "shift_supervisor"]);
    expect(can("approver", "scada.command")).toBe(false);
    expect(can("shift_supervisor", "scada.command.approve")).toBe(true);
    expect(can("operator", "scada.manual_entry")).toBe(false);
    expect(can("engineer", "scada.ack")).toBe(true); // server: kvitlash hozircha operator+ ierarxiyasi
    expect(can("shift_supervisor", "sensor.oos")).toBe(false);
    expect(can(null, "scada.ack")).toBe(false);
  });
});

describe("SCADA-02: yoziladigan nuqta chegaralari", () => {
  it("min va maks majburiy, chekli, min ≤ max", () => {
    expect(setpointRangeError(null, 10)).toMatch(/majburiy/);
    expect(setpointRangeError(0, Infinity)).toMatch(/majburiy/);
    expect(setpointRangeError(20, 10)).toMatch(/katta/);
    expect(setpointRangeError(0, 100)).toBeNull();
  });
});

describe("SCADA-04: gateway kaliti bir marta ko'rsatiladi", () => {
  it("GET — faqat prefiks; «Almashtirish» — kalit bir marta, keyin yashirin", async () => {
    const base = { header: "X-Ingest-Key", url: "/api/projects/1/readings", expires_at: null, days_left: null, last_used_at: null };
    vi.stubGlobal("fetch", vi.fn((u: string, init: RequestInit = {}) => {
      const kind = String(u).includes("/command") ? "command" : "ingest";
      if ((init.method ?? "GET") === "POST") return json({ ...base, kind, key: "sk_live_SECRET", key_prefix: "sk_live", shown_once: true, exists: true });
      return json({ ...base, kind, key: null, key_prefix: "sk_li", shown_once: false, exists: kind === "ingest" });
    }));
    render(<GatewayKeys projectId={1} canManage />);
    expect((await screen.findAllByText("sk_li…", { exact: false })).length).toBeGreaterThan(0);
    expect(screen.queryByText(/sk_live_SECRET/)).toBeNull();
    expect(screen.getByTestId("key-rotate-command")).toHaveTextContent("Yaratish"); // GET kalit yaratmaydi
    fireEvent.click(screen.getByTestId("key-rotate-ingest"));
    await waitFor(() => expect(screen.getByTestId("key-shown-ingest")).toHaveTextContent("sk_live_SECRET"));
  });
  it("ruxsat yo'q — hech narsa so'ralmaydi", () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    const { container } = render(<GatewayKeys projectId={1} canManage={false} />);
    expect(container.textContent).toBe("");
    expect(f).not.toHaveBeenCalled();
  });
});

describe("noma'lum buyruq natijasi (watchdog)", () => {
  it("ControlBlock: ogohlantirish (role=alert) va takrorlamaslik haqida matn", async () => {
    const sensor = { id: 5, key: "GATE1.SP", name: "Zatvor", unit: "%", writable: true, min_setpoint: 0, max_setpoint: 100, last_value: 40 } as unknown as Sensor;
    const cmd: Command = { id: 77, sensor_id: 5, sensor_key: "GATE1.SP", sensor_name: "Zatvor", unit: "%", value: 55, note: "", status: "unknown", result: "", author_username: "op", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
    vi.stubGlobal("fetch", vi.fn((u: string) => json(String(u).includes("/commands") ? [cmd] : [])));
    render(<ControlBlock projectId={1} sensor={sensor} canCommand />);
    expect(await screen.findByTestId("ctl-unknown")).toHaveTextContent("natijasi noma'lum");
    expect(screen.getByRole("alert")).toHaveTextContent("takrorlamang");
  });
});
