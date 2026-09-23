import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { adminCreds } from "./creds";

/** E2E muhiti: E2E_API_URL (default http://localhost:8000), E2E_USER, E2E_PASS (creds.ts — CI da majburiy). */
export const API = process.env.E2E_API_URL ?? "http://localhost:8000";

export const ADMIN = adminCreds(process.env);

export const SAMPLE_IFC = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/samples/namuna_ges_v2.ifc");

export async function apiToken(req: APIRequestContext, creds = ADMIN): Promise<string> {
  const r = await req.post(`${API}/api/auth/login`, { form: creds });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

/** Loyiha + model + namuna IFC versiyasi (API orqali). */
export async function makeProject(req: APIRequestContext, name: string): Promise<{ projectId: number; modelId: number; versionId: number; h: Record<string, string> }> {
  const h = { Authorization: `Bearer ${await apiToken(req)}` };
  const p = await (await req.post(`${API}/api/projects`, { headers: h, data: { name } })).json();
  const m = await (await req.post(`${API}/api/projects/${p.id}/models`, { headers: h, data: { name: "Namuna" } })).json();
  const up = await req.post(`${API}/api/models/${m.id}/versions`, {
    headers: h,
    multipart: { message: "e2e v1", file: { name: "namuna.ifc", mimeType: "application/octet-stream", buffer: readFileSync(SAMPLE_IFC) } },
  });
  expect(up.status()).toBe(201);
  return { projectId: p.id, modelId: m.id, versionId: (await up.json()).id, h };
}

/** Web orqali kirish (admin); yo'riqnoma paneli yopiladi. */
export async function uiLogin(page: Page, creds = ADMIN): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/login/i).fill(creds.username);
  await page.getByLabel(/parol/i).fill(creds.password);
  await page.getByRole("button", { name: /kirish/i }).click();
  await expect(page.getByRole("heading", { name: "Loyihalar" })).toBeVisible();
  await page.evaluate(() => localStorage.setItem("ges_help_seen", "1"));
}
