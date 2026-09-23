import { useCallback, useState, type RefObject } from "react";
import type { NavMode, Shading, Viewer } from "../../viewer/Viewer";

export type ColorScheme = "none" | "type" | "storey";
export type Projection = "Perspective" | "Orthographic";

/** 3D ko'rinish sozlamalari (FE-06: ModelPage dan ajratildi) — React holati va Viewer bir joyda sinxron:
 * shading, grid, yorliqlar, proyeksiya, navigatsiya rejimi, rang sxemasi (+ legenda). Xatti-harakat o'zgarmagan. */
export function useViewportDisplay(viewer: RefObject<Viewer | null>) {
  const [shading, setShadingState] = useState<Shading>("solid");
  const [gridOn, setGridState] = useState(true);
  const [labelsOn, setLabelsOn] = useState(false);
  const [projection, setProjection] = useState<Projection>("Perspective");
  const [navMode, setNavMode] = useState<NavMode>("Orbit");
  const [colorScheme, setColorScheme] = useState<ColorScheme>("none");
  const [legend, setLegend] = useState<{ name: string; color: string }[] | null>(null);

  const setShading = useCallback((m: Shading) => { setShadingState(m); viewer.current?.setShading(m); }, [viewer]);
  const setGrid = useCallback((v: boolean) => { setGridState(v); viewer.current?.setGridVisible(v); }, [viewer]);
  const toggleLabels = useCallback(async () => {
    const vw = viewer.current;
    if (!vw) return;
    await vw.setLabels(!labelsOn);
    setLabelsOn(!labelsOn);
  }, [viewer, labelsOn]);
  const toggleProjection = useCallback(async () => {
    await viewer.current?.toggleProjection();
    setProjection(viewer.current?.world.camera.projection.current ?? "Perspective");
  }, [viewer]);
  const pickNavMode = useCallback((m: NavMode) => { setNavMode(m); viewer.current?.setNavMode(m); }, [viewer]);
  const pickColorScheme = useCallback(async (m: ColorScheme) => {
    setColorScheme(m);
    const lg = await viewer.current?.colorScheme(m);
    setLegend(m === "none" ? null : (lg ?? null));
  }, [viewer]);

  return { shading, setShading, gridOn, setGrid, labelsOn, toggleLabels, projection, toggleProjection, navMode, pickNavMode, colorScheme, pickColorScheme, legend };
}
