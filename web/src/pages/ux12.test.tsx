import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setToken } from "../api/client";
import MyTasksPage from "./MyTasksPage";
import ProjectTimeline from "./ProjectTimeline";

/** UX-12: "Mening vazifalarim" va loyiha vaqt chizig'i. */
const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { "Content-Type": "application/json" } }));
beforeEach(() => setToken("t"));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const TASKS = {
  reviews: [{ id: 4, title: "Mashina zali v3", status: "open", project_id: 1, project_name: "Chorvoq", model_id: 2, model_name: "Zal", version_id: 9, version_number: 3, author: "Muhandis", created_at: "2026-09-20T08:00:00Z" }],
  my_change_requests: [],
  issues: [{ id: 7, title: "Devor", status: "open", priority: "high", project_id: 1, project_name: "Chorvoq", model_id: 2, model_name: "Zal", updated_at: "2026-09-21T08:00:00Z" }],
  work_orders: [],
  command_approvals: [{ id: 11, project_id: 1, project_name: "Chorvoq", sensor_id: 5, sensor_name: "Zatvor 1", sensor_key: "GATE1.SP", unit: "%", value: 55, author: "Operator", created_at: "2026-09-22T08:00:00Z" }],
  total: 3,
};

describe("Mening vazifalarim", () => {
  it("bo'limlar faqat vazifa bo'lsa; havolalar kerakli sahifaga", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(TASKS)));
    render(<MemoryRouter><MyTasksPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("task-review")).toBeTruthy());
    expect(screen.getByRole("link", { name: /#4 Mashina zali v3/ }).getAttribute("href")).toBe("/models/2?v=9&tab=review");
    expect(screen.getByTestId("task-command")).toHaveTextContent(/55(.0+)? %/);
    expect(screen.getByRole("link", { name: "Ko'rib chiqish" }).getAttribute("href")).toBe("/projects/1/dashboard?tab=control");
    expect(screen.getByTestId("task-issue")).toHaveTextContent("Devor");
    expect(screen.queryByTestId("task-wo")).toBeNull();
    expect(screen.queryByText(/O'zgartirish so'ralgan/)).toBeNull();
  });
  it("hammasi bo'sh — xabar", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ reviews: [], my_change_requests: [], issues: [], work_orders: [], command_approvals: [], total: 0 })));
    render(<MemoryRouter><MyTasksPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("tasks-empty")).toBeTruthy());
  });
});

describe("loyiha vaqt chizig'i", () => {
  const items = [
    { ts: "2026-09-22T10:00:00Z", kind: "alarm", title: "Sath: highhigh", detail: "905 m", actor: "", severity: "critical", model_id: null, version_id: null, change_request_id: null, issue_id: null, work_order_id: null, sensor_id: 3 },
    { ts: "2026-09-22T08:00:00Z", kind: "publish", title: "Zal v3 nashr qilindi", detail: "", actor: "", severity: null, model_id: 2, version_id: 9, change_request_id: 4, issue_id: null, work_order_id: null, sensor_id: null },
    { ts: "2026-09-20T08:00:00Z", kind: "version", title: "Zal: v3", detail: "devorlar", actor: "Muhandis", severity: null, model_id: 2, version_id: 9, change_request_id: null, issue_id: null, work_order_id: null, sensor_id: null },
  ];
  it("kun bo'yicha guruhlar, BIM va SCADA bitta o'qda, filtr, havolalar", async () => {
    const f = vi.fn((_u: string) => json({ project_id: 1, since: "2026-08-23T00:00:00Z", items, truncated: false }));
    vi.stubGlobal("fetch", f);
    render(<MemoryRouter><ProjectTimeline pid={1} /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["22.09.2026", "20.09.2026"]);
    expect(screen.getByRole("link", { name: "Zal v3 nashr qilindi" }).getAttribute("href")).toBe("/models/2?v=9&tab=review");
    expect(screen.getByRole("link", { name: "Sath: highhigh" }).getAttribute("href")).toBe("/projects/1/ops/sensor/3");
    fireEvent.click(screen.getByRole("button", { name: "Model" }));
    expect(screen.getAllByRole("listitem").map((li) => li.dataset.kind)).toEqual(["publish", "version"]);
    fireEvent.change(screen.getByRole("combobox", { name: "Davr" }), { target: { value: "90" } });
    await waitFor(() => expect(String(f.mock.calls.at(-1)?.[0])).toContain("days=90"));
  });
});
