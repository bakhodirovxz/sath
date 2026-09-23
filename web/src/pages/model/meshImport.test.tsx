import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, setToken, type MeshImportResult } from "../../api/client";
import MeshUnitCheck from "./MeshUnitCheck";
import { meshFollowUp } from "./meshImport";

/** CAD-03/04 (server): birlik/o'q avto aniqlanadi; y_up faqat foydalanuvchi tanlasa yuboriladi; units_uncertain → so'rov. */
const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { "Content-Type": "application/json" } }));
beforeEach(() => setToken("t"));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("mesh import klienti", () => {
  it("y_up berilmasa yuborilmaydi (glTF avto-o'girish), unit_override faqat true bo'lsa", async () => {
    const f = vi.fn((_u: string, _i?: RequestInit) => json({ id: 1 }));
    vi.stubGlobal("fetch", f);
    const file = new File(["x"], "a.glb");
    await api.importMeshVersion(5, file, { unit: "m", y_up: null });
    let fd = f.mock.calls[0][1]!.body as FormData;
    expect(fd.has("y_up")).toBe(false);
    expect(fd.has("unit_override")).toBe(false);
    await api.importMeshVersion(5, file, { unit: "mm", y_up: false, unit_override: true });
    fd = f.mock.calls[1][1]!.body as FormData;
    expect(fd.get("y_up")).toBe("false");
    expect(fd.get("unit_override")).toBe("true");
    expect(fd.get("unit")).toBe("mm");
  });

  it("javob: ogohlantirishlar birlashtiriladi, units_uncertain, tashlab ketilgan 2D", () => {
    const r = { id: 2, warnings: ["A"], units_uncertain: true, import_info: { unit: "m", scale: 1, unit_source: "", units_uncertain: true, unit_note: "", up_axis: null, axis_uncertain: true, y_up: false, dxf: { skipped_2d: 14 }, warnings: ["A", "B"] } } as unknown as MeshImportResult;
    expect(meshFollowUp(r)).toMatchObject({ warnings: ["A", "B"], uncertain: true, skipped2d: 14 });
    expect(meshFollowUp({ id: 3 } as MeshImportResult)).toMatchObject({ warnings: [], uncertain: false, skipped2d: 0 });
  });
});

describe("birlik tasdiqlash dialogi", () => {
  it("aniqlangan birlik va ogohlantirish ko'rsatiladi; tanlangan birlik bilan qayta import", () => {
    const onReimport = vi.fn(), onAccept = vi.fn();
    render(<MeshUnitCheck fileName="dam.dxf" info={{ unit: "m", scale: 1, unit_source: "aniqlanmadi", units_uncertain: true, unit_note: "", up_axis: null, axis_uncertain: true, y_up: false, warnings: [] }} warnings={["$INSUNITS yo'q"]} busy={false} onAccept={onAccept} onReimport={onReimport} />);
    expect(screen.getByTestId("mesh-unit-check")).toHaveTextContent("metr deb o'qildi");
    expect(screen.getByTestId("mesh-unit-check")).toHaveTextContent("$INSUNITS yo'q");
    fireEvent.change(screen.getByTestId("mesh-unit-select"), { target: { value: "mm" } });
    fireEvent.click(screen.getByTestId("mesh-reimport"));
    expect(onReimport).toHaveBeenCalledWith("mm");
    fireEvent.click(screen.getByRole("button", { name: /qabul qilish/ }));
    expect(onAccept).toHaveBeenCalled();
  });
});
