import { expect, test } from "@playwright/test";
import { makeProject, uiLogin } from "./env";

/** WEB-01: ichki OT tarmoqda internet yo'q. Brauzer faqat ilova serveriga (localhost) chiqa oladi —
 * boshqa har qanday host (CDN, shriftlar, unpkg) rad etiladi. Login va model sahifasi (3D dvigatel,
 * web-ifc wasm, fragments worker) to'liq ochilishi kerak. */
test.describe("tarmoqsiz (internet yo'q) rejim", () => {
  let modelId = 0;
  let versionId = 0;
  let blocked: string[] = [];
  test.beforeAll(async ({ request }) => {
    const r = await makeProject(request, `E2E offline ${Date.now().toString(36)}`);
    modelId = r.modelId;
    versionId = r.versionId;
  });

  test.beforeEach(async ({ context }) => {
    blocked = [];
    await context.route("**/*", (route) => {
      const host = new URL(route.request().url()).hostname;
      if (host === "localhost" || host === "127.0.0.1" || host === "[::1]") return route.continue();
      blocked.push(route.request().url());
      return route.abort("internetdisconnected");
    });
  });

  test("login sahifasi va model (3D) tashqi tarmoqsiz ochiladi", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: /kirish/i })).toBeVisible();
    await uiLogin(page);
    await page.goto(`/models/${modelId}?v=${versionId}`);
    await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
    await expect(page.locator(".outliner")).toContainText("To'g'on");
    expect(blocked, `tashqi so'rovlar: ${blocked.join(", ")}`).toEqual([]);
  });
});
