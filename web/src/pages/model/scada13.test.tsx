import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setToken } from "../../api/client";
import { configureLive, resetLive } from "../../store/live";
import { DialogHost } from "../../ui/dialogs";
import MonitoringRedirect from "../MonitoringRedirect";
import MonitoringPanel from "./MonitoringPanel";
import SafetyCheck from "./sim/SafetyCheck";

/** Server o'zgarishlariga moslash: SCADA-13 (GUID tekshiruvi, force, bog'lanmagan sensorlar), SIM (ko'ruvchi hisoblamaydi). */

type Reply = { status?: number; body: unknown };
let routes: Record<string, (init: RequestInit) => Reply>;
const calls: string[] = [];
beforeEach(() => {
  calls.length = 0;
  setToken("t");
  resetLive();
  configureLive({ socket: () => ({ close() { /* */ } }) as unknown as WebSocket });
  vi.stubGlobal("fetch", vi.fn((u: string, init: RequestInit = {}) => {
    const url = String(u);
    calls.push(`${init.method ?? "GET"} ${url}`);
    const path = url.split("?")[0];
    const h = routes[`${init.method ?? "GET"} ${url}`] ?? routes[`${init.method ?? "GET"} ${path}`];
    const r = h ? h(init) : { body: [] };
    return Promise.resolve(new Response(JSON.stringify(r.body), { status: r.status ?? 200, headers: { "Content-Type": "application/json" } }));
  }));
});
afterEach(() => { resetLive(); vi.unstubAllGlobals(); });

describe("SCADA-13: sensor GUID tekshiruvi", () => {
  it("422 (element topilmadi) → tasdiq dialogi → «Baribir saqlash» force=true bilan", async () => {
    routes = {
      "GET /api/projects/1/sensors": () => ({ body: [] }),
      "GET /api/projects/1/dashboard": () => ({ body: { mimic: {} } }),
      "GET /api/projects/1/sensors/unlinked": () => ({ body: { version_id: 7, checked: 0, count: 0, sensors: [] } }),
      "POST /api/projects/1/sensors": () => ({ status: 422, body: { detail: "element_guid «X» joriy model versiyasida (id 7) topilmadi — force=true bilan saqlang" } }),
      "POST /api/projects/1/sensors?force=true": () => ({ status: 201, body: { id: 9 } }),
    };
    render(<><DialogHost /><MonitoringPanel projectId={1} modelId={2} versionId={7} role="engineer" viewer={null} selection={[]} /></>);
    fireEvent.click(await screen.findByRole("button", { name: /Sensor/ }));
    fireEvent.change(screen.getByLabelText(/Kalit/), { target: { value: "AGG9.P" } });
    fireEvent.change(screen.getByLabelText(/^Nomi/), { target: { value: "Yangi agregat" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Saqlash" })); });
    fireEvent.click(await screen.findByTestId("dlg-confirm"));
    await waitFor(() => expect(calls).toContain("POST /api/projects/1/sensors?force=true"));
  });

  it("bog'lanmagan sensorlar ro'yxati ochiq versiya bo'yicha ko'rsatiladi", async () => {
    routes = {
      "GET /api/projects/1/sensors": () => ({ body: [] }),
      "GET /api/projects/1/dashboard": () => ({ body: { mimic: {} } }),
      "GET /api/projects/1/sensors/unlinked?version_id=7": () => ({ body: { version_id: 7, checked: 3, count: 1, sensors: [{ id: 4, key: "TR1.T", name: "Transformator", element_guid: "2abc", model_id: 2 }] } }),
    };
    render(<MonitoringPanel projectId={1} modelId={2} versionId={7} role="engineer" viewer={null} selection={[]} />);
    expect(await screen.findByTestId("unlinked-sensors")).toHaveTextContent("Bog'lanmagan sensorlar: 1 ta");
    expect(screen.getByTestId("unlinked-sensors")).toHaveTextContent("TR1.T");
  });

  it("bildirishnoma havolasi /projects/1/monitoring?unlinked=7 → model monitoring paneli", async () => {
    routes = { "GET /api/versions/7": () => ({ body: { id: 7, model_id: 3 } }) };
    function Where() { const l = useLocation(); return <span data-testid="loc">{l.pathname}{l.search}</span>; }
    render(<MemoryRouter initialEntries={["/projects/1/monitoring?unlinked=7"]}><Routes>
      <Route path="/projects/:projectId/monitoring" element={<MonitoringRedirect />} />
      <Route path="/models/:modelId" element={<Where />} />
    </Routes></MemoryRouter>);
    expect(await screen.findByTestId("loc")).toHaveTextContent("/models/3?v=7&tab=mon");
  });
});

describe("SIM: ko'ruvchi hisoblamaydi (server 403)", () => {
  it("xavfsizlik tekshiruvi tugmasi o'chiq va sababi yozilgan", () => {
    render(<SafetyCheck modelId={1} current={null} viewer={null} onOpenJob={() => undefined} onDone={() => undefined} canRun={false} />);
    const b = screen.getAllByRole("button").find((x) => /Tekshir|Hisobla/.test(x.textContent ?? ""))!;
    expect(b).toBeDisabled();
    expect(b.title).toMatch(/muhandis/);
  });
});
