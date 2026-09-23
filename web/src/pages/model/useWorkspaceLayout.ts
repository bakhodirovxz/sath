import { useCallback, useState } from "react";

const HELP_KEY = "ges_help_seen";

/** Ish maydoni joylashuvi (FE-06: ModelPage dan ajratildi): o'ng dok va uning yorlig'i, asboblar paneli, outliner,
 * N-yon panel, yordam paneli (birinchi kirishda bir marta, UX-07/UX-10: yopiladigan, to'smaydi). */
export function useWorkspaceLayout<Tab extends string>(initialTab: Tab) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [dockOpen, setDockOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(true);
  const [outlinerOpen, setOutlinerOpen] = useState(true);
  const [sideOpen, setSideOpen] = useState(false);
  const [help, setHelp] = useState<boolean>(() => { try { return localStorage.getItem(HELP_KEY) !== "1"; } catch { return false; } });
  const closeHelp = useCallback(() => { setHelp(false); try { localStorage.setItem(HELP_KEY, "1"); } catch { /* saqlash bloklangan — faqat shu sessiya */ } }, []);
  /** Panelni ochish (dok yopiq bo'lsa ochiladi) */
  const openTab = useCallback((t: Tab) => { setTab(t); setDockOpen(true); }, []);
  return { tab, setTab, openTab, dockOpen, setDockOpen, toolsOpen, setToolsOpen, outlinerOpen, setOutlinerOpen, sideOpen, setSideOpen, help, setHelp, closeHelp };
}
