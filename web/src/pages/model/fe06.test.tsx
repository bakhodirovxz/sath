import { act, renderHook } from "@testing-library/react";
import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";
import { buildFieldPlane, buildSectionOverlay, disposeObject3D } from "../../viewer/analysisOverlays";
import type { Viewer } from "../../viewer/Viewer";
import { useViewportDisplay } from "./useViewportDisplay";
import { useWorkspaceLayout } from "./useWorkspaceLayout";

/** FE-06: ModelPage holati hook larga, Viewer.ts dan tahlil qatlamlari moduli — xatti-harakat o'zgarmagan. */
describe("useViewportDisplay", () => {
  it("React holati va Viewer sinxron: shading, grid, navigatsiya, rang sxemasi, yorliqlar", async () => {
    const vw = {
      setShading: vi.fn(), setGridVisible: vi.fn(), setNavMode: vi.fn(), setLabels: vi.fn(async () => undefined),
      colorScheme: vi.fn(async () => [{ name: "IfcWall", color: "#fff" }]),
      toggleProjection: vi.fn(async () => undefined), world: { camera: { projection: { current: "Orthographic" } } },
    };
    const ref = { current: vw as unknown as Viewer };
    const { result } = renderHook(() => useViewportDisplay(ref));
    act(() => result.current.setShading("xray"));
    expect(result.current.shading).toBe("xray");
    expect(vw.setShading).toHaveBeenCalledWith("xray");
    act(() => result.current.setGrid(false));
    expect(result.current.gridOn).toBe(false);
    expect(vw.setGridVisible).toHaveBeenCalledWith(false);
    act(() => result.current.pickNavMode("Plan"));
    expect(vw.setNavMode).toHaveBeenCalledWith("Plan");
    await act(async () => { await result.current.pickColorScheme("type"); });
    expect(result.current.legend).toEqual([{ name: "IfcWall", color: "#fff" }]);
    await act(async () => { await result.current.pickColorScheme("none"); });
    expect(result.current.legend).toBeNull();
    await act(async () => { await result.current.toggleLabels(); });
    expect(vw.setLabels).toHaveBeenCalledWith(true);
    expect(result.current.labelsOn).toBe(true);
    await act(async () => { await result.current.toggleProjection(); });
    expect(result.current.projection).toBe("Orthographic");
  });
});

describe("useWorkspaceLayout", () => {
  it("yordam birinchi kirishda bir marta; yopilgach eslab qolinadi; openTab dokni ochadi", () => {
    localStorage.removeItem("ges_help_seen");
    const { result } = renderHook(() => useWorkspaceLayout<"versions" | "mon">("versions"));
    expect(result.current.help).toBe(true);
    act(() => result.current.closeHelp());
    expect(result.current.help).toBe(false);
    expect(localStorage.getItem("ges_help_seen")).toBe("1");
    act(() => { result.current.setDockOpen(false); result.current.openTab("mon"); });
    expect(result.current.tab).toBe("mon");
    expect(result.current.dockOpen).toBe(true);
    expect(renderHook(() => useWorkspaceLayout("versions")).result.current.help).toBe(false);
  });
});

describe("tahlil qatlamlari (analysisOverlays)", () => {
  const box = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(10, 4, 2));
  it("maydon tekisligi: uzun o'q bo'ylab, bbox markazida, rang har tugunda", () => {
    const m = buildFieldPlane(box, { nx: 3, ny: 2, values: [0, 0.5, 1, 1, 0.5, 0] }, (t) => [t, 0, 1 - t]);
    expect(m.position.toArray()).toEqual([5, 2, 1]);
    expect(m.rotation.y).toBe(0); // X uzun o'q
    expect(m.geometry.getAttribute("color").count).toBe(6);
    const p = (m.geometry as THREE.PlaneGeometry).parameters;
    expect([p.width, p.height]).toEqual([10, 4]);
  });
  it("kesim sxemasi: hisob profili yopiq chiziq, bbox ga moslangan; bo'shatish xatosiz", () => {
    const g = buildSectionOverlay(box, { profile: [[0, 0], [2, 8], [4, 0]] });
    expect(g.name).toBe("section");
    const loop = g.children.find((c) => (c as THREE.LineLoop).isLineLoop) as THREE.LineLoop;
    expect(loop).toBeTruthy();
    const pos = loop.geometry.getAttribute("position");
    const ys = Array.from({ length: pos.count }, (_, i) => pos.getY(i));
    expect(Math.max(...ys)).toBeCloseTo(4); // profil balandligi 8 → element balandligi 4
    expect(() => disposeObject3D(g)).not.toThrow();
  });
});
