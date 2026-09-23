import { useSyncExternalStore } from "react";
import Icon from "./Icon";
import { dismiss, getNotices, subscribeNotices, type NoticeKind } from "./notice";

const ICON: Record<NoticeKind, string> = { success: "check-circle", info: "info", warning: "alert-triangle", error: "alert-triangle" };
const LABEL: Record<NoticeKind, string> = { success: "Bajarildi", info: "Ma'lumot", warning: "Diqqat", error: "Xato" };

/** Bildirishnomalar joyi (App da bitta). Xato — role=alert (darhol o'qiladi), boshqalari — role=status. */
export default function NoticeHost() {
  const items = useSyncExternalStore(subscribeNotices, getNotices, getNotices);
  return (
    <div className="notice-host" aria-live="polite">
      {items.map((n) => (
        <div key={n.id} className={`notice ${n.kind}`} role={n.kind === "error" || n.kind === "warning" ? "alert" : "status"} data-testid="notice" data-kind={n.kind}>
          <Icon name={ICON[n.kind]} size={14} />
          <span className="notice-text"><span className="sr-only">{LABEL[n.kind]}: </span>{n.text}</span>
          <button type="button" className="notice-close" aria-label="Yopish" onClick={() => dismiss(n.id)}>×</button>
        </div>
      ))}
    </div>
  );
}
