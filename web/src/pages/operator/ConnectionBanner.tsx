import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { useLastLiveAt, useLiveLost, useLiveState } from "../../store/live";
import Icon from "../../ui/Icon";
import { fmtTime } from "../../ui/format";
import { fmtAge } from "./model";

function useNow(active: boolean, ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [active, ms]);
  return now;
}

/** UX-04: jonli ulanish uzilganda katta "ALOQA YO'Q" banneri — oxirgi ma'lumot yoshi va vaqti bilan
 * (qiymatlar ekranda qoladi, lekin kulrang/shtrixlangan — "hozirgi" deb o'qilmaydi). Kechikish (STALE) —
 * kichik ogohlantirish. Ulanish tiklansa — o'zi yo'qoladi. */
export default function ConnectionBanner({ pid }: { pid: number }) {
  const state = useLiveState(pid);
  const lastAt = useLastLiveAt(pid);
  const lost = useLiveLost(pid);
  const now = useNow(state !== "LIVE");
  if (state === "LIVE") return null;
  const age = lastAt != null ? fmtAge(Math.max(0, Math.round((now - lastAt) / 1000))) : null;
  if (state === "STALE") {
    return <div className="conn-banner stale" role="status" data-testid="conn-banner" data-state="STALE"><Icon name="wifi" size={14} /> {t("live.STALE")}: oxirgi xabar {age ?? "—"} oldin</div>;
  }
  if (!lost) return null;
  return (
    <div className="conn-banner offline" role="alert" data-testid="conn-banner" data-state="OFFLINE">
      <Icon name="wifi-off" size={20} />
      <div>
        <b className="conn-title">{t("live.lostBanner")}</b>
        <div className="small">{lastAt != null ? `${t("live.lostDetail", { age: age ?? "—" })} (${fmtTime(lastAt, true)})` : "Jonli ma'lumot hali kelmadi — server yoki tarmoqni tekshiring. Qayta ulanish avtomatik."}</div>
      </div>
    </div>
  );
}

/** Yuqori paneldagi jonli holat belgisi: matn (tarjima) + belgi; rang — faqat uzilishda. */
export function LiveBadge({ pid }: { pid: number }) {
  const state = useLiveState(pid);
  return (
    <span className={`live-dot ${state.toLowerCase()}`} title={t("live.title")} data-testid="live-state" data-state={state}>
      <Icon name={state === "OFFLINE" ? "wifi-off" : "wifi"} size={12} /> {t(`live.${state}`)}
    </span>
  );
}
