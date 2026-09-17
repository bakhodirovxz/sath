import { useEffect, useRef, useState } from "react";
import { Viewer, type SelectedItem, type Tool } from "./Viewer";

/** Viewer ni container ga bog'laydi; React holatiga tanlash/asbob/status ni uzatadi. */
export function useViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [ready, setReady] = useState(false);
  const [selection, setSelection] = useState<SelectedItem[]>([]);
  const [tool, setTool] = useState<Tool>("select");
  const [status, setStatus] = useState("");

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const v = new Viewer();
    viewerRef.current = v;
    if (import.meta.env.DEV) { (window as unknown as { __ges: Viewer }).__ges = v; void import("three").then((t) => { (window as unknown as { __THREE: unknown }).__THREE = t; }); } // dev konsolida tekshirish uchun
    let cancelled = false;
    const unsub: (() => void)[] = [];
    v.init(el)
      .then(() => {
        if (cancelled) return;
        unsub.push(v.subscribeSelection(setSelection), v.subscribeTool(setTool), v.subscribeStatus(setStatus));
        setReady(true);
      })
      .catch((e) => !cancelled && setStatus(`Viewer xatosi: ${e instanceof Error ? e.message : e}`));
    return () => {
      cancelled = true;
      unsub.forEach((u) => u());
      v.dispose();
      viewerRef.current = null;
      setReady(false);
    };
  }, []);

  return { containerRef, viewer: viewerRef, ready, selection, tool, status };
}
