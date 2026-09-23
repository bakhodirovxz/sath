import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";
import { ApiError, DEFAULT_TIMEOUT_MS, api, apiErrorMessage, setToken } from "./client";

/** FE-05: vaqt chegarasi, o'zbekcha xato matnlari, CSV yuklash (401 refresh + kechiktirilgan revoke). */

type Handler = (url: string, init: RequestInit) => Promise<Response>;
function mockFetch(h: Handler) {
  const fn = vi.fn((url: string | URL | Request, init: RequestInit = {}) => h(String(url), init));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => setToken("t0"));
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("apiErrorMessage", () => {
  it("FastAPI 422 massivi → maydon + o'zbekcha sabab (xom JSON emas)", () => {
    const detail = [
      { loc: ["body", "name"], msg: "Field required", type: "missing" },
      { loc: ["body", "high_alarm"], msg: "Input should be greater than or equal to 0", type: "greater_than_equal", ctx: { ge: 0 } },
      { loc: ["body", "items", 0, "value"], msg: "Input should be a valid number", type: "float_parsing" },
      { loc: ["query", "hours"], msg: "x", type: "int_parsing" },
    ];
    const m = apiErrorMessage(422, detail);
    expect(m).toBe("Ma'lumot noto'g'ri: «name» — to'ldirilishi shart; «high_alarm» — 0 yoki undan katta bo'lishi kerak; «items[1].value» — son bo'lishi kerak; «hours» — butun son bo'lishi kerak");
    expect(m).not.toContain("{");
  });
  it("value_error prefiksi olib tashlanadi; 5 tadan ko'p — qisqartiriladi", () => {
    expect(apiErrorMessage(422, [{ loc: ["body"], msg: "Value error, chegara noto'g'ri", type: "value_error" }])).toBe("Ma'lumot noto'g'ri: chegara noto'g'ri");
    const many = Array.from({ length: 7 }, (_, i) => ({ loc: ["body", `f${i}`], type: "missing" }));
    expect(apiErrorMessage(422, many)).toMatch(/\(yana 2 ta\)$/);
  });
  it("matn detail o'zgarishsiz; obyekt — message; bo'sh — holat bo'yicha", () => {
    expect(apiErrorMessage(409, "Versiya eskirgan")).toBe("Versiya eskirgan");
    expect(apiErrorMessage(409, { message: "LOTO faol", code: "loto" })).toBe("LOTO faol");
    expect(apiErrorMessage(403, undefined)).toBe("Bu amal uchun ruxsat yo'q");
    expect(apiErrorMessage(502, null)).toMatch(/vaqtincha/);
    expect(apiErrorMessage(418, null, "I'm a teapot")).toBe("I'm a teapot");
  });
});

describe("request: vaqt chegarasi va tarmoq xatolari", () => {
  it("server javob bermasa DEFAULT_TIMEOUT_MS dan keyin ApiError(timeout)", async () => {
    vi.useFakeTimers();
    mockFetch((_u, init) => new Promise((_res, rej) => {
      init.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
    }));
    const p = api.projects();
    const check = expect(p).rejects.toMatchObject({ code: "timeout", status: 0 });
    await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS + 10);
    await check;
    await expect(p).rejects.toBeInstanceOf(ApiError);
  });
  it("tarmoq uzilgan — ApiError(network), o'zbekcha matn", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(api.projects()).rejects.toMatchObject({ code: "network", message: expect.stringMatching(/aloqa yo'q/) });
  });
  it("422 javobi — xatoda detail saqlanadi, matn tushunarli", async () => {
    mockFetch(() => Promise.resolve(json(422, { detail: [{ loc: ["body", "name"], type: "missing", msg: "Field required" }] })));
    const e = await api.createProject({ name: "", description: "", location: "" }).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).message).toBe("Ma'lumot noto'g'ri: «name» — to'ldirilishi shart");
    expect(Array.isArray((e as ApiError).detail)).toBe(true);
  });
});

describe("downloadCsv", () => {
  it("401 da refresh qilib takrorlaydi; URL darhol emas, keyinroq bo'shatiladi", async () => {
    vi.useFakeTimers();
    const calls: string[] = [];
    mockFetch((url, init) => {
      calls.push(`${init.method ?? "GET"} ${url} ${new Headers(init.headers).get("Authorization") ?? ""}`);
      if (url === "/api/auth/refresh") return Promise.resolve(json(200, { access_token: "t1", expires_in: 900 }));
      if (new Headers(init.headers).get("Authorization") === "Bearer t0") return Promise.resolve(new Response("", { status: 401 }));
      return Promise.resolve(new Response("a;b\n1;2", { status: 200 }));
    });
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    const orig = { c: URL.createObjectURL, r: URL.revokeObjectURL };
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    onTestFinished(() => { Object.assign(URL, { createObjectURL: orig.c, revokeObjectURL: orig.r }); });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await api.downloadCsv("/api/sensors/1/export.csv", "s.csv");
    expect(calls).toEqual(["GET /api/sensors/1/export.csv Bearer t0", "POST /api/auth/refresh ", "GET /api/sensors/1/export.csv Bearer t1"]);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revoke).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(revoke).toHaveBeenCalledWith("blob:x");
  });
  it("xato holati — o'zbekcha ApiError (sessiya tugagan)", async () => {
    mockFetch((url) => Promise.resolve(url === "/api/auth/refresh" ? new Response("", { status: 401 }) : new Response("", { status: 404 })));
    await expect(api.downloadCsv("/api/x.csv", "x.csv")).rejects.toMatchObject({ status: 404, message: "Topilmadi" });
  });
});
