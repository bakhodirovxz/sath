import { describe, expect, it } from "vitest";
import { adminCreds } from "../e2e/creds";

describe("e2e admin hisobi", () => {
  it("CI da E2E_PASS bo'lmasa xato — standart parolga tushib qolmaydi", () => {
    expect(() => adminCreds({ CI: "true" })).toThrow(/E2E_PASS/);
    expect(adminCreds({ CI: "true", E2E_PASS: "s3cret" })).toEqual({ username: "admin", password: "s3cret" });
  });
  it("lokal: hujjatlashtirilgan dev qiymati", () => {
    expect(adminCreds({})).toEqual({ username: "admin", password: "admin123" });
    expect(adminCreds({ E2E_USER: "root", E2E_PASS: "x" })).toEqual({ username: "root", password: "x" });
  });
});
