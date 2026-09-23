import { expect, test, type APIRequestContext, type WebSocketRoute } from "@playwright/test";
import { API, apiToken, makeProject, uiLogin } from "./env";

/** FE-07: SCADA oqimlari alohida (mustaqil) testlarda — har test o'z loyihasi, dispetcher (operator) foydalanuvchisi
 * va gateway ingest kaliti bilan: alarm banneri va sahifa ichida kvitlash, buyruq select → execute, jonli ulanish
 * uzilishi va qayta ulanish (UX-03, UX-04, SCADA-01/07). */

const stamp = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

async function scadaProject(request: APIRequestContext) {
  const s = stamp();
  const { projectId, modelId, h } = await makeProject(request, `E2E scada ${s}`);
  const op = { username: `e2e_op_${s}`, password: "pass1234" };
  const u = await (await request.post(`${API}/api/users`, { headers: h, data: { ...op, full_name: "E2E dispetcher", must_change_password: false } })).json();
  expect((await request.put(`${API}/api/projects/${projectId}/members`, { headers: h, data: { user_id: u.id, role: "operator" } })).ok()).toBeTruthy();
  const k = await (await request.post(`${API}/api/projects/${projectId}/keys/ingest`, { headers: h })).json();
  const ingest = { [k.header ?? "X-Ingest-Key"]: k.key as string };
  const read = async (key: string, value: number) => {
    const r = await request.post(`${API}/api/projects/${projectId}/readings`, { headers: ingest, data: [{ key, value }] });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  return { projectId, modelId, h, op, read };
}

test("alarm banneri har sahifada; dispetcher sahifa ichida izoh bilan kvitlaydi", async ({ page, request }) => {
  const { projectId, modelId, h, op, read } = await scadaProject(request);
  const s = await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "RES.H", name: "Yuqori byef sathi", kind: "level", unit: "m", high_alarm: 905, priority: "critical" } });
  expect(s.ok(), await s.text()).toBeTruthy();
  await read("RES.H", 906.4);
  await uiLogin(page, op);
  // Loyiha sahifasi (BIM) — banner ko'rinadi
  await page.goto(`/projects/${projectId}`);
  const banner = page.getByTestId("alarm-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toHaveClass(/prio-critical/);
  await expect(page.getByTestId("alarm-banner-item").first()).toContainText("Yuqori byef sathi");
  // 3D model sahifasi — ham
  await page.goto(`/models/${modelId}`);
  await expect(page.getByTestId("alarm-banner")).toBeVisible({ timeout: 60_000 }); // 3D bo'lagi (dev) birinchi marta sekin
  // Sahifa ichida kvitlash (prompt() emas)
  await page.getByTestId("alarm-banner-ack").first().click();
  await expect(page.getByRole("dialog")).toContainText("Kvitlash: Yuqori byef sathi");
  await page.getByTestId("dlg-text").fill("e2e: tekshirildi");
  await page.getByTestId("dlg-ok").click();
  await expect(page.getByTestId("alarm-banner")).toHaveCount(0);
  await expect(page.getByTestId("notice").first()).toContainText("Kvitlandi");
  // server tomonida izoh bilan kvitlangan
  const ev = await (await request.get(`${API}/api/projects/${projectId}/alarm-events?active=false`, { headers: h })).json();
  const list = Array.isArray(ev) ? ev : ev.items ?? [];
  expect(list.some((e: { acked_at: string | null; comment: string }) => e.acked_at && e.comment === "e2e: tekshirildi")).toBeTruthy();
});

test("buyruq: select → execute faceplate dan (dispetcher), diapazon tekshiruvi", async ({ page, request }) => {
  const { projectId, h, op, read } = await scadaProject(request);
  const r = await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "GATE1.SP", name: "Zatvor 1 SP", kind: "position", unit: "%", writable: true, min_setpoint: 0, max_setpoint: 100 } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const sid = (await r.json()).id as number;
  await read("GATE1.SP", 40);
  await uiLogin(page, op);
  await page.goto(`/projects/${projectId}/ops/sensor/${sid}`);
  const ctl = page.getByTestId("control-block");
  await expect(ctl).toContainText("0 … 100 %");
  await ctl.getByTestId("ctl-value").fill("150");
  await ctl.getByTestId("ctl-note").fill("e2e");
  await expect(ctl.getByTestId("ctl-select")).toBeDisabled();
  await ctl.getByTestId("ctl-value").fill("62");
  await ctl.getByTestId("ctl-select").click();
  await expect(ctl.getByTestId("ctl-selected")).toContainText("62");
  await ctl.getByTestId("ctl-execute").click();
  await expect(ctl.getByTestId("ctl-status")).toContainText("navbatda");
  const cmds = await (await request.get(`${API}/api/projects/${projectId}/commands`, { headers: h })).json();
  const list = Array.isArray(cmds) ? cmds : cmds.items ?? [];
  expect(list.some((c: { value: number; status: string }) => c.value === 62 && c.status === "pending")).toBeTruthy();
});

test("jonli ulanish uzilsa — ALOQA YO'Q banneri va eskirgan qiymatlar; qayta ulanganda yo'qoladi", async ({ page, request }) => {
  const { projectId, op, read } = await scadaProject(request);
  const h = { Authorization: `Bearer ${await apiToken(request)}` };
  await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "AGG1.P", name: "Agregat 1 quvvati", kind: "power", unit: "MW" } });
  await read("AGG1.P", 31.5);
  let block = false;
  const open: WebSocketRoute[] = [];
  await page.routeWebSocket(/\/api\/projects\/\d+\/live/, (ws) => {
    if (block) { void ws.close({ code: 1006 }); return; }
    ws.connectToServer();
    open.push(ws);
  });
  await uiLogin(page, op);
  await page.goto(`/projects/${projectId}/ops/area/powerhouse`);
  await expect(page.getByTestId("live-state")).toHaveAttribute("data-state", "LIVE", { timeout: 20_000 });
  await expect(page.getByTestId("conn-banner")).toHaveCount(0);
  // uzilish: joriy soket yopiladi, qayta ulanishlar rad etiladi
  block = true;
  for (const ws of open.splice(0)) await ws.close({ code: 1006 });
  const b = page.getByTestId("conn-banner");
  await expect(b).toHaveAttribute("data-state", "OFFLINE", { timeout: 15_000 });
  await expect(b).toContainText("ALOQA YO'Q");
  await expect(b).toContainText("oldin");
  await expect(page.locator("[data-testid=vcard][data-key='AGG1.P']")).toHaveClass(/stale/);
  // tiklanish: keyingi urinish (eksponensial kutish) serverga ulanadi
  block = false;
  await expect(page.getByTestId("live-state")).toHaveAttribute("data-state", "LIVE", { timeout: 45_000 });
  await expect(page.getByTestId("conn-banner")).toHaveCount(0);
});
