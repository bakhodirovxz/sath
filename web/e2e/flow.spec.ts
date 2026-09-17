import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** To'liq oqim (reja «Tekshirish»): login → loyiha → model (viewer yuklanadi) → tasdiqlash so'rovi →
 * ma'qullash/merge (webdan) → dispetcher paneli → bildirishnoma. Ma'lumotlar API orqali tayyorlanadi. */

const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const ADMIN = { username: process.env.E2E_USER ?? "admin", password: process.env.E2E_PASS ?? "admin123" };
const SAMPLE = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/samples/namuna_ges_v2.ifc");
const stamp = Date.now().toString(36);

async function token(req: APIRequestContext): Promise<string> {
  const r = await req.post(`${API}/api/auth/login`, { form: ADMIN });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

test.describe.serial("Sath web oqimi", () => {
  let projectId = 0;
  let modelId = 0;
  let versionId = 0;
  const engineerCreds = { username: `e2e_eng_${stamp}`, password: "pass1234" };

  test.beforeAll(async ({ request }) => {
    const tok = await token(request);
    const h = { Authorization: `Bearer ${tok}` };
    const p = await (await request.post(`${API}/api/projects`, { headers: h, data: { name: `E2E ${stamp}` } })).json();
    projectId = p.id;
    const eng = await (await request.post(`${API}/api/users`, { headers: h, data: { ...engineerCreds, full_name: "E2E muhandis" } })).json();
    await request.put(`${API}/api/projects/${projectId}/members`, { headers: h, data: { user_id: eng.id, role: "engineer" } });
    const m = await (await request.post(`${API}/api/projects/${projectId}/models`, { headers: h, data: { name: "Namuna" } })).json();
    modelId = m.id;
    const up = await request.post(`${API}/api/models/${modelId}/versions`, {
      headers: h,
      multipart: { message: "e2e v1", file: { name: "namuna.ifc", mimeType: "application/octet-stream", buffer: readFileSync(SAMPLE) } },
    });
    expect(up.status()).toBe(201);
    versionId = (await up.json()).id;
    // muhandis tasdiqqa yuboradi (webda admin tasdiqlaydi)
    const et = (await (await request.post(`${API}/api/auth/login`, { form: engineerCreds })).json()).access_token;
    const cr = await request.post(`${API}/api/models/${modelId}/change-requests`, { headers: { Authorization: `Bearer ${et}` }, data: { version_id: versionId, title: `E2E so'rov ${stamp}` } });
    expect(cr.status()).toBe(201);
  });

  test("login va loyihalar", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/login/i).fill(ADMIN.username);
    await page.getByLabel(/parol/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /kirish/i }).click();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    await expect(page.getByText(`E2E ${stamp}`)).toBeVisible();
  });

  test("model: viewer yuklanadi, outliner, tasdiqlash oqimi", async ({ page }) => {
    await login(page);
    await page.evaluate(() => localStorage.removeItem("ges_help_seen"));
    await page.goto(`/models/${modelId}?v=${versionId}`);
    // Birinchi kirishda yo'riqnoma
    await expect(page.locator(".help-card")).toContainText("qisqa yo'riqnoma");
    await page.getByRole("button", { name: "Tushunarli" }).click();
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    // Outliner da elementlar
    await expect(page.locator(".outliner")).toContainText("Namuna GES");
    await expect(page.locator(".outliner")).toContainText("To'g'on");
    // Tasdiqlash ish maydoni: so'rov ko'rinadi, ma'qullash → merge
    await page.locator(".ws-tabs button", { hasText: "Tasdiqlash" }).click();
    const panel = page.locator(".dock-body");
    await expect(panel).toContainText(`E2E so'rov ${stamp}`);
    page.on("dialog", (d) => d.accept()); // xavfsizlik tekshiruvi ogohlantirishi (versiya tekshirilmagan)
    await panel.getByRole("button", { name: /ma'qullash/i }).first().click();
    await expect(panel).toContainText(/ma'qullangan/i);
    await panel.getByRole("button", { name: /tasdiqlash \(published\)/i }).first().click();
    await expect(panel).toContainText(/tasdiqlangan/i);
    // Shading: header tugmasi va Z pie menyu (Blender: Z → bo'lak raqami)
    await page.locator(".vp-group button[title^='X-ray']").click();
    await expect(page.locator(".vp-info")).toContainText("X-ray");
    await page.mouse.move(600, 450);
    await page.keyboard.press("z");
    await expect(page.locator(".pie-item")).toHaveCount(4);
    await page.keyboard.press("3"); // Rendered
    await expect(page.locator(".vp-info")).toContainText("Rendered");
    // N-panel (viewport yon paneli) va F3 qidiruv
    await page.keyboard.press("n");
    await expect(page.locator(".vp-sidebar")).toBeVisible();
    await page.keyboard.press("n");
    await page.keyboard.press("F3");
    await page.locator(".search-input").fill("grid");
    await expect(page.locator(".search-item").first()).toContainText("Grid");
    await page.keyboard.press("Escape");
    // Outliner: qidiruv va ko'z (yashirish)
    await page.getByPlaceholder("Qidirish…").fill("to'g'on");
    await expect(page.locator(".outliner .node:visible")).toHaveCount(3); // Project › Maydon › To'g'on
    await page.locator(".outliner .node", { hasText: "To'g'on" }).locator(".eye").click();
    await expect(page.locator(".outliner .node.hidden")).toHaveCount(1);
  });

  test("tekshiruv: to'qnashuvlar va QTO", async ({ page }) => {
    await login(page);
    await page.goto(`/models/${modelId}?v=${versionId}`);
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    await page.locator(".ws-tabs button", { hasText: "Tekshiruv" }).click();
    await expect(page.locator(".checks .tile").first()).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".checks")).toContainText("juftlik tekshirildi");
    await page.locator(".checks button", { hasText: "Hajm-miqdor" }).click();
    await expect(page.locator(".checks")).toContainText("jami hajm");
  });

  test("dispetcher paneli va bildirishnomalar", async ({ page, request }) => {
    const tok = await token(request);
    const h = { Authorization: `Bearer ${tok}` };
    await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "AGG1.P", name: "Agregat 1", kind: "power", unit: "MW", high_alarm: 30 } });
    await request.post(`${API}/api/projects/${projectId}/readings`, { headers: h, data: [{ key: "AGG1.P", value: 35 }] });
    await login(page);
    await page.goto(`/projects/${projectId}/dashboard`);
    await expect(page.locator(".dash-kpi")).toContainText("Faol alarmlar");
    await expect(page.locator(".dash-alarms")).toContainText("Agregat 1");
    await expect(page.locator(".mimic")).toBeVisible();
    await page.locator(".dash-alarms button", { hasText: "Kvitlash" }).first().click();
    await expect(page.locator(".dash-alarms")).toContainText("kvitlangan");
    await page.locator(".bell button").first().click();
    await expect(page.locator(".bell-menu")).toContainText("Alarm");
  });

  test("simulyatsiya katalogi: to'g'on barqarorligi va yog'ingarchilik", async ({ page }) => {
    await login(page);
    await page.goto(`/models/${modelId}?v=${versionId}`);
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    await page.locator(".ws-tabs button", { hasText: "Simulyatsiya" }).click();
    const cat = page.locator(".sim-catalog");
    await expect(cat).toContainText("Gidravlik zarba");
    await expect(cat).toContainText("Yog'ingarchilik");
    await cat.locator(".blist-row", { hasText: "To'g'on barqarorligi" }).click();
    await expect(page.locator(".simform")).toContainText("Profil");
    await page.locator("form button", { hasText: "Hisoblash" }).click();
    await expect(page.locator(".verdict")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".sim")).toContainText("Ag'darilish zaxirasi");
    await expect(page.locator(".dam-profile")).toBeVisible();
    // Katalogga qaytib (Blender sarlavha: orqaga ikki marta) yog'ingarchilik
    await page.locator(".bhead button[title='Parametrlarga qaytish']").click();
    await page.locator(".bhead button[title='Katalogga qaytish']").click();
    await cat.locator(".blist-row", { hasText: "Yog'ingarchilik" }).click();
    await page.locator("form button", { hasText: "Hisoblash" }).click();
    await expect(page.locator(".verdict")).toContainText("CN", { timeout: 30_000 });
  });

  test("3D da element qo'shish va IFC ga commit", async ({ page }) => {
    await login(page);
    await page.goto(`/models/${modelId}?v=${versionId}`);
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    await page.locator(".menubar .menu-title", { hasText: "Qo'shish" }).click();
    await page.locator(".menu-item", { hasText: "Transformator" }).click();
    await expect(page.locator(".ws-status .msg")).toContainText("Joylashtirish");
    const canvas = page.locator(".ws-canvas canvas");
    const box = await canvas.boundingBox();
    await page.mouse.move(box!.x + box!.width * 0.5, box!.y + box!.height * 0.6);
    await page.mouse.click(box!.x + box!.width * 0.5, box!.y + box!.height * 0.6);
    await expect(page.locator(".draft-list:not(.underlay-list)")).toContainText("Transformator 1");
    await expect(page.locator(".draft-props")).toContainText("Joylashuv");
    // G/R/S rejimlari, nom o'zgartirish
    await page.keyboard.press("r");
    await expect(page.locator(".draft-props .btn.active[title^='Burish']")).toBeVisible();
    await page.locator(".draft-props input").first().fill("E2E transformator");
    await expect(page.locator(".draft-list:not(.underlay-list)")).toContainText("E2E transformator");
    // Commit → yangi versiya
    page.once("dialog", (d) => d.accept("e2e: web 3D element"));
    await page.locator(".draft-list:not(.underlay-list) button", { hasText: "IFC ga qo'shish" }).click();
    await expect(page.locator(".ws-status .msg")).toContainText("Namuna v2", { timeout: 90_000 });
    await expect(page.locator(".ws-status")).toContainText("Elementlar: 21");
    await expect(page.locator(".draft-list:not(.underlay-list)")).toHaveCount(0);
  });

  test("maydon pasporti va sog'liq bo'limi", async ({ page }) => {
    await login(page);
    await page.goto(`/projects/${projectId}/site`);
    await expect(page.getByRole("heading", { name: "Maydon pasporti" })).toBeVisible();
    await page.locator(".simform input[type=number]").first().fill("111");
    await page.getByRole("button", { name: "Saqlash" }).click();
    await expect(page.locator(".page-body")).toContainText("Saqlandi");
    await expect(page.locator(".page-body")).toContainText("Tezkor xavf ko'rsatkichlari");
    await page.goto(`/projects/${projectId}/dashboard`);
    await page.locator("button", { hasText: "Sog'liq" }).click();
    await expect(page.locator(".dash-block")).toContainText("Holat monitoringi");
    await page.locator("button", { hasText: "Optimal rejim" }).click();
    await expect(page.locator(".dash-block")).toContainText("Nima bo'lsa");
  });

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByLabel(/login/i).fill(ADMIN.username);
    await page.getByLabel(/parol/i).fill(ADMIN.password);
    await page.getByRole("button", { name: /kirish/i }).click();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    // Loyiha kartochkasi va tezkor amallar
    await expect(page.locator(".card", { hasText: `E2E ${stamp}` }).getByRole("button", { name: "Dispetcher paneli" })).toBeVisible();
    await page.evaluate(() => localStorage.setItem("ges_help_seen", "1")); // yo'riqnoma overlay ni yopamiz
  }
});
