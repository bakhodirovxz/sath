import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { useNavigate } from "react-router-dom";
import { api, type Notification } from "../api/client";
import { fmtDate } from "./format";

const KIND: Record<Notification["kind"], string> = { review: "tasdiqlash", issue: "issue", alarm: "alarm", system: "tizim" };

/** Qo'ng'iroq: o'qilmaganlar soni (30 s da yangilanadi), ro'yxat, bosganda havolaga o'tish. */
export default function NotificationsBell() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const tick = () => api.notificationCount().then((r) => alive && setCount(r.unread)).catch(() => undefined);
    tick();
    const t = window.setInterval(tick, 30000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  useEffect(() => {
    if (!open) return;
    api.notifications(false, 40).then(setItems).catch(() => undefined);
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  async function pick(n: Notification) {
    if (!n.read_at) {
      await api.markRead([n.id]).catch(() => undefined);
      setCount((c) => Math.max(0, c - 1));
    }
    setOpen(false);
    if (n.link) nav(n.link);
  }
  async function readAll() {
    await api.markRead(null).catch(() => undefined);
    setCount(0);
    setItems((it) => it.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
  }

  return (
    <div className="bell" ref={ref}>
      <button className="btn sm" onClick={() => setOpen((o) => !o)} title="Bildirishnomalar" aria-label={`Bildirishnomalar, ${count} o'qilmagan`}>
        <Icon name="bell" size={17} />{count > 0 && <span className="bell-count">{count > 99 ? "99+" : count}</span>}
      </button>
      {open && (
        <div className="bell-menu">
          <div className="row" style={{ padding: "6px 10px" }}><b>Bildirishnomalar</b><span className="grow" />{count > 0 && <button className="btn sm" onClick={readAll}>Hammasi o'qildi</button>}</div>
          {items.length === 0 && <p className="muted" style={{ padding: 10 }}>Hozircha yo'q</p>}
          {items.map((n) => (
            <button key={n.id} className={`bell-item ${n.read_at ? "" : "unread"}`} onClick={() => pick(n)}>
              <div className={`k ${n.kind}`}>{KIND[n.kind]} · {fmtDate(n.created_at)}</div>
              <div>{n.title}</div>
              {n.body && <div className="muted small">{n.body}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
