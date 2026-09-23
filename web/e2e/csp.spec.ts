import { expect, test } from "@playwright/test";
import { makeProject, uiLogin } from "./env";

/** CSP (OPS-01): server `script-src 'self' 'wasm-unsafe-eval'`, `connect-src 'self'` + ws, `worker-src 'self' blob:`
 * yuborganda ilova (3D dvigatel, web-ifc wasm, fragments worker, jonli soket) buzilishsiz ishlaydi.
 * Vite dev (CSP yo'q) da ham o'tadi; to'liq tekshiruv — server web build ni tarqatganda (GES_WEB_DIST). */
test("CSP buzilishi yo'q: login, model (3D), dispetcher, operator ekranlari", async ({ page, request }) => {
  const { projectId, modelId, versionId } = await makeProject(request, `E2E csp ${Date.now().toString(36)}`);
  const violations: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp ??= [];
      (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  page.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(m.text()); });
  await uiLogin(page);
  await page.goto(`/models/${modelId}?v=${versionId}`);
  await expect(page.locator(".ws-status .msg")).toContainText("Yuklandi", { timeout: 90_000 });
  const collect = async () => violations.push(...((await page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? [])) as string[]));
  await collect();
  await page.goto(`/projects/${projectId}/dashboard`);
  await expect(page.locator(".dash-kpi")).toBeVisible();
  await collect();
  await page.goto(`/projects/${projectId}/ops`);
  await expect(page.getByTestId("live-state")).toBeVisible();
  await page.waitForTimeout(1500); // jonli soket ulanishi (connect-src ws)
  await collect();
  expect(violations, violations.join("\n")).toEqual([]);
});
