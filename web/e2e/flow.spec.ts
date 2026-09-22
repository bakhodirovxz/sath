import { expect, test, type APIRequestContext } from "@playwright/test";
import { createHmac } from "node:crypto";
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
    const eng = await (await request.post(`${API}/api/users`, { headers: h, data: { ...engineerCreds, full_name: "E2E muhandis", must_change_password: false } })).json();
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
    await panel.getByRole("button", { name: /ma'qullash/i }).first().click();
    await page.getByTestId("dlg-confirm").click(); // xavfsizlik tekshiruvi ogohlantirishi — Dialog (F8: confirm() emas)
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
    // IDS (G2): namuna barcha talablarni qanoatlantiradi — natija navbatda hisoblangan yoki qayta tekshirish
    await page.getByTestId("checks-ids").click();
    const status = page.getByTestId("ids-status");
    if (!(await status.isVisible().catch(() => false))) await page.locator(".checks button", { hasText: "Qayta tekshirish" }).click();
    await expect(status).toHaveText("O'TDI", { timeout: 60_000 });
    await expect(page.getByTestId("ids-panel")).toContainText("Georeferensiya");
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
    await page.getByTestId("dlg-text").fill("e2e kvitlash");  // Dialog (prompt emas, F5)
    await page.getByTestId("dlg-ok").click();
    await expect(page.locator(".dash-alarms")).toContainText("kvitlangan");
    await page.locator(".bell button").first().click();
    await expect(page.locator(".bell-menu")).toContainText("Alarm");
  });

  test("ISA-101 operator ekranlari: L1 → L2 → L3 faceplate → L4 (F2)", async ({ page, request }) => {
    const tok = await token(request);
    const h = { Authorization: `Bearer ${tok}` };
    await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "RES.H", name: "Yuqori byef", kind: "level", unit: "m", high_alarm: 905 } });
    await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "AGG1.P", name: "Agregat 1", kind: "power", unit: "MW", high_alarm: 30 } }); // 409 bo'lsa ham mayli
    await request.post(`${API}/api/projects/${projectId}/readings`, { headers: h, data: [{ key: "RES.H", value: 903.2 }, { key: "AGG1.P", value: 35 }] });
    await login(page);
    await page.goto(`/projects/${projectId}/ops`);
    // L1: KPI, agregat kartasi, uchastkalar, faol alarm (AGG1.P > 30)
    await expect(page.locator(".ops-nav .ops-level")).toHaveText("L1");
    await expect(page.getByTestId("l1-alarms")).toContainText("Faol alarmlar");
    await expect(page.locator(".l1-kpi")).toContainText("903.2");
    const unit = page.getByTestId("unit-card").first();
    await expect(unit).toContainText("Agregat 1");
    // L1 → L2 (uchastka)
    await page.locator("[data-testid=area-card]", { hasText: "Mashina zali" }).click();
    await expect(page.locator(".ops-nav .ops-level")).toHaveText("L2");
    await expect(page.locator("h2")).toContainText("Mashina zali");
    // L2 → L3 faceplate (qiymat kartasi)
    await page.locator("[data-testid=vcard][data-key='AGG1.P']").click();
    await expect(page.locator(".ops-nav .ops-level")).toHaveText("L3");
    const fp = page.getByTestId("faceplate");
    await expect(fp).toContainText("Agregat 1");
    await expect(fp).toContainText("AGG1.P");
    await expect(fp.locator(".fp-big")).toContainText("35");
    await expect(fp).toContainText("Ratsionalizatsiya");
    // L3 → L4 diagnostika → ota ekranga qaytish
    await fp.getByRole("link", { name: "L4 Diagnostika" }).click();
    await expect(page.locator(".ops-nav .ops-level")).toHaveText("L4");
    await expect(page.locator(".l4")).toContainText("Jonli oqim");
    await page.locator(".ops-nav button", { hasText: "L1 Umumiy" }).click();
    await expect(page.locator(".ops-nav .ops-level")).toHaveText("L1");
    // F8: faceplate boshqaruv bloki — diapazondan tashqari qiymat klientda rad, select → execute
    await request.post(`${API}/api/projects/${projectId}/sensors`, { headers: h, data: { key: "GATE1.SP", name: "Zatvor 1 SP", kind: "position", unit: "%", writable: true, min_setpoint: 0, max_setpoint: 100 } });
    await request.post(`${API}/api/projects/${projectId}/readings`, { headers: h, data: [{ key: "GATE1.SP", value: 40 }] });
    await page.goto(`/projects/${projectId}/ops`);
    await page.locator("[data-testid=area-card]", { hasText: "Gidrotexnik" }).click();
    await page.locator("[data-testid=vcard][data-key='GATE1.SP']").click();
    const ctl = page.getByTestId("control-block");
    await expect(ctl).toContainText("0 … 100 %");
    await ctl.getByTestId("ctl-value").fill("500");
    await ctl.getByTestId("ctl-note").fill("e2e sinov");
    await expect(ctl.getByTestId("ctl-invalid")).toContainText("maksimum 100");
    await expect(ctl.getByTestId("ctl-select")).toBeDisabled();
    await ctl.getByTestId("ctl-value").fill("55");
    await ctl.getByTestId("ctl-select").click();
    await expect(ctl.getByTestId("ctl-selected")).toContainText("55");
    await ctl.getByTestId("ctl-execute").click();
    await expect(ctl.getByTestId("ctl-status")).toContainText("navbatda");
    await page.getByTestId("nav-alarms").click();
    await expect(page).toHaveURL(/\/ops\/alarms$/);
    // Alarm sahifasi (F5): filtr, hammasini kvitlash — tasdiqlash dialogi, faqat filtrlangan to'plam
    await request.post(`${API}/api/projects/${projectId}/readings`, { headers: h, data: [{ key: "RES.H", value: 906 }] }); // yangi kvitlanmagan alarm (H > 905)
    await expect(page.getByTestId("alarm-table")).toBeVisible();
    await page.getByTestId("alarm-search").fill("RES.H");
    await expect(page.locator("[data-testid=alarm-row]")).toHaveCount(1);
    const before = Number(await page.getByTestId("cnt-unacked").locator(".tile-v").innerText());
    await page.getByTestId("ack-all").click();
    await expect(page.getByRole("dialog")).toContainText("1");
    await page.getByTestId("ack-all-ok").click();
    await expect(page.getByTestId("cnt-unacked").locator(".tile-v")).toHaveText(String(before - 1)); // faqat filtrlangan bittasi
    // F9: smena topshirish — yakunlanmagan ishlar ogohlantirishi, imzo; qabul qilinmagan banner
    await page.getByTestId("nav-shift").click();
    await expect(page.getByTestId("shift-snapshot")).toContainText("Topshirish varaqasi");
    await expect(page.getByTestId("shift-warnings")).toContainText("buyruq");
    await page.getByTestId("handover-btn").click();
    await expect(page.getByTestId("handover-ok")).toBeDisabled(); // ogohlantirishlar ko'rilmaguncha
    await page.getByTestId("ack-warn").check();
    await page.getByTestId("handover-notes").fill("e2e: zatvor buyrug'i navbatda");
    await page.getByTestId("handover-ok").click();
    await expect(page.getByTestId("handover-open")).toContainText("qabul qilinmagan");
    await page.goto(`/projects/${projectId}/ops`);
    await expect(page.getByTestId("handover-banner")).toContainText("qabul qilinmagan");
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
    await expect(page.locator(".verdict").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".sim")).toContainText("Ag'darilish zaxirasi");
    await expect(page.locator(".dam-profile")).toBeVisible();
    // Katalogga qaytib (Blender sarlavha: orqaga ikki marta) yog'ingarchilik
    await page.locator(".bhead button[title='Parametrlarga qaytish']").click();
    await page.locator(".bhead button[title='Katalogga qaytish']").click();
    await cat.locator(".blist-row", { hasText: "Yog'ingarchilik" }).click();
    await page.locator("form button", { hasText: "Hisoblash" }).click();
    await expect(page.locator(".verdict").first()).toContainText("CN", { timeout: 30_000 });
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
    await page.locator(".draft-list:not(.underlay-list) button", { hasText: "IFC ga qo'shish" }).click();
    await page.getByTestId("dlg-prompt").fill("e2e: web 3D element"); // Dialog (F8: prompt() emas)
    await page.getByTestId("dlg-confirm").click();
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

  test("Georeferensiya (G3): loyiha CRS, taklif, versiyani georeferensiyalash, global koordinata", async ({ page, request }) => {
    await login(page);
    await page.goto(`/projects/${projectId}`);
    await page.getByTestId("crs-settings").getByRole("button", { name: "Sozlash" }).click();
    await page.getByTestId("crs-epsg").selectOption("32642");
    await page.getByRole("button", { name: "Taklif" }).click();
    await expect(page.getByTestId("crs-settings").locator("input[type=number]").nth(0)).not.toHaveValue("500000");
    await page.getByTestId("crs-save").click();
    await expect(page.getByTestId("crs-settings")).toContainText("EPSG:32642");
    // API: lokal (0,0) → lat/lon ≈ taklif nuqtasi (41.62, 69.98)
    const tok = await token(request);
    const conv = await (await request.get(`${API}/api/projects/${projectId}/crs/convert?x=0&y=0`, { headers: { Authorization: `Bearer ${tok}` } })).json();
    expect(Math.abs(conv.latlon.lat - 41.62)).toBeLessThan(1e-4);
    // model: oxirgi versiyada IfcMapConversion yo'q → «Georeferensiyalash» → yangi versiya
    await page.goto(`/models/${modelId}?v=${versionId}&tab=versions`);
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    const list = page.locator(".dock-body");
    await list.locator(".blist-row").first().click(); // ro'yxat yangisi birinchi — Georeferensiyalash tugmasi oxirgi versiyada
    await page.getByTestId("georef-btn").click();
    await expect(list).toContainText("EPSG:32642", { timeout: 30_000 });
  });

  test("MFA (L1): profil orqali yoqish, kodsiz kirish rad, kod bilan kirish, o'chirish", async ({ page }) => {
    // Alohida foydalanuvchi — admin sessiyasi va boshqa testlar MFA talab qilmasin
    await page.goto("/login");
    await page.getByLabel(/login/i).fill(engineerCreds.username);
    await page.getByLabel(/parol/i).fill(engineerCreds.password);
    await page.getByRole("button", { name: /kirish/i }).click();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    await page.evaluate(() => localStorage.setItem("ges_help_seen", "1"));
    await page.getByTestId("profile-btn").click();
    await page.getByRole("button", { name: "MFA ni yoqish" }).click();
    const secret = (await page.getByTestId("mfa-secret").textContent())!.trim();
    expect(secret.length).toBeGreaterThan(16);
    await page.getByTestId("mfa-code").fill(totp(secret));
    await page.getByRole("button", { name: "Tasdiqlash va yoqish" }).click();
    await expect(page.getByRole("status")).toContainText("MFA yoqildi");
    await page.getByRole("button", { name: "Yopish" }).click();
    await page.getByRole("button", { name: "Chiqish" }).click();
    // kodsiz — OTP maydoni paydo bo'ladi; keyingi qadam kodi bilan kiradi (takror himoyasi: enable dagi kod ishlatilmaydi)
    await page.getByLabel(/login/i).fill(engineerCreds.username);
    await page.getByLabel(/parol/i).fill(engineerCreds.password);
    await page.getByRole("button", { name: /kirish/i }).click();
    await expect(page.getByTestId("login-otp")).toBeVisible();
    await page.getByTestId("login-otp").fill(totp(secret, 1));
    await page.getByRole("button", { name: /kirish/i }).click();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    // o'chirish (parol + kod): kirishda c+1 ishlatildi, server ±1 qadam oynasida takrorni rad etadi —
    // haqiqiy vaqt keyingi qadamga o'tguncha kutamiz (≤ 30 s), so'ng c'+1
    await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 200);
    await page.getByTestId("profile-btn").click();
    await page.getByPlaceholder("Parol").fill(engineerCreds.password);
    await page.getByPlaceholder("Kod").fill(totp(secret, 1));
    await page.getByRole("button", { name: "O'chirish" }).click();
    await expect(page.getByRole("status")).toContainText("MFA o'chirildi");
  });

  test("Sessiya (L2): majburiy parol almashtirish, sahifa qayta yuklanganda sessiya saqlanadi, chiqish", async ({ page, request }) => {
    const tok = await token(request);
    const creds = { username: `e2e_new_${stamp}`, password: "Fresh-pw-2026" };
    const r = await request.post(`${API}/api/users`, { headers: { Authorization: `Bearer ${tok}` }, data: { ...creds, full_name: "E2E yangi", must_change_password: true } });
    expect(r.status()).toBe(201);
    await page.goto("/login");
    await page.getByLabel(/login/i).fill(creds.username);
    await page.getByLabel(/parol/i).fill(creds.password);
    await page.getByRole("button", { name: /kirish/i }).click();
    // Boshqa amallar yopiq — profil dialogi majburiy
    await expect(page.getByTestId("must-change")).toBeVisible();
    await page.getByLabel("Joriy parol").fill(creds.password);
    await page.getByTestId("new-password").fill("Changed-pw-2026");
    await page.getByRole("button", { name: "O'zgartirish" }).click();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    // Qayta yuklash: access token xotirada yo'q — HttpOnly cookie orqali tiklanadi
    await page.reload();
    await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("ges_token"))).toBeNull();
    await page.getByRole("button", { name: "Chiqish" }).click();
    await page.goto("/");
    await expect(page.getByRole("button", { name: /kirish/i })).toBeVisible();
  });

  /** TOTP (RFC 6238, SHA1, 30 s, 6 raqam) — serverdagi bilan bir xil; `offset` — qadam siljishi. */
  function totp(secretB32: string, offset = 0): string {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let bits = "";
    for (const ch of secretB32.toUpperCase().replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
    const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((b) => parseInt(b, 2)));
    const counter = Math.floor(Date.now() / 1000 / 30) + offset;
    const msg = Buffer.alloc(8);
    msg.writeUInt32BE(Math.floor(counter / 2 ** 32), 0);
    msg.writeUInt32BE(counter >>> 0, 4);
    const h = createHmac("sha1", key).update(msg).digest();
    const o = h[h.length - 1]! & 0x0f;
    const code = (h.readUInt32BE(o) & 0x7fffffff) % 1_000_000;
    return code.toString().padStart(6, "0");
  }

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
