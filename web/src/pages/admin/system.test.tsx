import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setToken } from "../../api/client";
import { DialogHost } from "../../ui/dialogs";
import { DeletedModelsSection, StorageSection } from "./SystemSections";

/** VCS-06 / SRV-05: savat (tiklash/butunlay o'chirish), saqlash GC (avval sinov), audit holati. */
const json = (b: unknown, status = 200) => Promise.resolve(new Response(b === null ? null : JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } }));
const calls: string[] = [];
beforeEach(() => { setToken("t"); calls.length = 0; });
afterEach(() => vi.unstubAllGlobals());

describe("administrator: tizim bo'limlari", () => {
  it("o'chirilgan model: butunlay o'chirish — tasdiq dialogidan keyin DELETE", async () => {
    vi.stubGlobal("fetch", vi.fn((u: string, init: RequestInit = {}) => {
      calls.push(`${init.method ?? "GET"} ${u}`);
      if (String(u).includes("/purge")) return Promise.resolve(new Response(null, { status: 204 }));
      return json([{ id: 4, project_id: 1, name: "Eski to'g'on", description: "", version_count: 3, latest_version_id: 1, published_version_id: null, deleted_at: "2026-09-01T10:00:00Z", deleted_by: 1 }]);
    }));
    render(<><DialogHost /><DeletedModelsSection /></>);
    fireEvent.click(await screen.findByRole("button", { name: "Butunlay o'chirish" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("qaytarib bo'lmaydigan");
    fireEvent.click(screen.getByTestId("dlg-confirm"));
    await waitFor(() => expect(calls).toContain("DELETE /api/admin/models/4/purge"));
  });
  it("GC: «Tozalash» faqat sinov hisobotidan keyin; audit holati ko'rinadi", async () => {
    vi.stubGlobal("fetch", vi.fn((u: string, init: RequestInit = {}) => {
      calls.push(`${init.method ?? "GET"} ${u} ${init.body ?? ""}`);
      if (String(u).includes("/audit/status")) return json({ write_failures: 0, lost_entries: 0, last_failure_at: null, last_error: "", hash_alg: "sha256" });
      const dry = JSON.parse(String(init.body)).dry_run;
      return json({ dry_run: dry, grace_s: 86400, blobs: 2, derived: 1, temp: 0, bytes: 4096, kept_recent: 1, errors: 0, paths: [] });
    }));
    render(<><DialogHost /><StorageSection /></>);
    expect(await screen.findByTestId("audit-status")).toHaveTextContent("yozish xatosi yo'q");
    expect(screen.getByTestId("gc-run")).toBeDisabled();
    fireEvent.click(screen.getByTestId("gc-dry"));
    expect(await screen.findByTestId("gc-report")).toHaveTextContent("Sinov: o'chiriladi — 2 ta fayl");
    fireEvent.click(screen.getByTestId("gc-run"));
    fireEvent.click(await screen.findByTestId("dlg-confirm"));
    await waitFor(() => expect(screen.getByTestId("gc-report")).toHaveTextContent("O'chirildi"));
    expect(calls.some((c) => c.includes('"dry_run":false'))).toBe(true);
  });
});
