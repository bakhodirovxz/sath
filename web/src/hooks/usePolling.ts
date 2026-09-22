import { useEffect, useRef, useState } from "react";

/** Davriy so'rov (F12): `document.hidden` da to'xtaydi (ko'rinmas tabda tarmoq/CPU sarflamaydi), xatoda
 * eksponensial orqaga chekinadi (interval × 2^n, ≤ 8×), ko'rinish qaytganda darhol yangilaydi.
 * `key` o'zgarsa qayta boshlanadi (masalan `${projectId}:${hours}`). Qaytaradi: oxirgi xato va `refresh()`. */
export function usePolling(fn: () => Promise<unknown>, intervalMs: number, key = ""): { error: string | null; refresh: () => void } {
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let dead = false;
    let timer: number | undefined;
    let failures = 0;
    const schedule = (ms: number) => { if (!dead) timer = window.setTimeout(run, ms); };
    const run = async () => {
      if (dead) return;
      if (typeof document !== "undefined" && document.hidden) { schedule(intervalMs); return; }
      try {
        await fnRef.current();
        if (!dead) { failures = 0; setError(null); }
      } catch (e) {
        failures++;
        if (!dead) setError(e instanceof Error ? e.message : "Xato");
      }
      schedule(Math.min(intervalMs * Math.pow(2, failures), intervalMs * 8));
    };
    const onVisible = () => { if (!document.hidden) { window.clearTimeout(timer); void run(); } };
    document.addEventListener("visibilitychange", onVisible);
    void run();
    return () => { dead = true; window.clearTimeout(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [intervalMs, key, tick]);
  return { error, refresh: () => setTick((t) => t + 1) };
}
