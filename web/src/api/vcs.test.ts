import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, HEAD_MOVED_TEXT, api, isHeadMoved, setToken } from "./client";

/** VCS-01 (409 head_id) va OPS-03 (202 navbat → qayta so'rash). */
const json = (status: number, b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } }));
beforeEach(() => setToken("t"));
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("VCS-01: model boshqa versiya bilan yangilangan", () => {
  it("409 {head_id} → isHeadMoved, headId saqlanadi; oddiy 409 — yo'q", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(409, { detail: "Model yangilangan", head_id: 12 })));
    const e = await api.restoreVersion(3, 10).catch((x: unknown) => x);
    expect(isHeadMoved(e)).toBe(true);
    expect((e as ApiError).headId).toBe(12);
    expect(HEAD_MOVED_TEXT).toMatch(/yangilang/);
    vi.stubGlobal("fetch", vi.fn(() => json(409, { detail: "boshqa ziddiyat" })));
    expect(isHeadMoved(await api.restoreVersion(3).catch((x: unknown) => x))).toBe(false);
  });
});

describe("OPS-03: og'ir hisob navbatda (202)", () => {
  it("QTO: 202 → kutish holati → 200 natija (xato emas)", async () => {
    vi.useFakeTimers();
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(() => (++n < 3 ? json(202, { job_id: 7, status: "queued" }) : json(200, { element_count: 5 }))));
    const progress: number[] = [];
    const p = api.qto(1, (x) => progress.push(x.jobId ?? -1));
    await vi.advanceTimersByTimeAsync(5000);
    await expect(p).resolves.toMatchObject({ element_count: 5 });
    expect(progress).toEqual([7, 7]);
  });
  it("429 — kutib qayta so'raydi", async () => {
    vi.useFakeTimers();
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(() => (++n === 1 ? json(429, { detail: "Juda ko'p" }) : json(200, { clashes: [] }))));
    const p = api.clashes(1);
    await vi.advanceTimersByTimeAsync(2000);
    await expect(p).resolves.toMatchObject({ clashes: [] });
  });
  it("fragments 202/429 — null (IFC ochiladi)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 202 }))));
    await expect(api.versionFragments(1)).resolves.toBeNull();
  });
});
