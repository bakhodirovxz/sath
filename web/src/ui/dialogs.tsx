import { useEffect, useState } from "react";
import Dialog from "./Dialog";
import { t } from "../i18n";

/** Promise asosidagi tasdiqlash/kiritish dialoglari (F8): `confirm()`/`prompt()`/`alert()` o'rniga — asosiy
 * oqimni bloklamaydi, tema/klaviatura bilan ishlaydi. `<DialogHost />` ilovada bir marta o'rnatiladi. */

type Req =
  | { kind: "confirm"; title: string; text?: string; ok?: string; danger?: boolean; resolve: (v: boolean) => void }
  | { kind: "prompt"; title: string; text?: string; initial?: string; ok?: string; multiline?: boolean; resolve: (v: string | null) => void }
  | { kind: "alert"; title: string; text?: string | undefined; resolve: (v: void) => void };

let push: ((r: Req) => void) | null = null;
const queue: Req[] = [];

function enqueue(r: Req) {
  if (push) push(r); else queue.push(r);
}

export const dialogs = {
  confirm(title: string, opts: { text?: string; ok?: string; danger?: boolean } = {}): Promise<boolean> {
    return new Promise((resolve) => enqueue({ kind: "confirm", title, ...opts, resolve }));
  },
  prompt(title: string, initial = "", opts: { text?: string; ok?: string; multiline?: boolean } = {}): Promise<string | null> {
    return new Promise((resolve) => enqueue({ kind: "prompt", title, initial, ...opts, resolve }));
  },
  alert(title: string, text?: string): Promise<void> {
    return new Promise((resolve) => enqueue({ kind: "alert", title, text, resolve }));
  },
};

export function DialogHost() {
  const [cur, setCur] = useState<Req | null>(null);
  const [pending, setPending] = useState<Req[]>([]);
  const [value, setValue] = useState("");
  useEffect(() => {
    push = (r) => setPending((p) => [...p, r]);
    if (queue.length) { setPending((p) => [...p, ...queue]); queue.length = 0; }
    return () => { push = null; };
  }, []);
  useEffect(() => {
    if (!cur && pending.length) { const [n, ...rest] = pending; setCur(n); setPending(rest); setValue(n.kind === "prompt" ? (n.initial ?? "") : ""); }
  }, [cur, pending]);
  if (!cur) return null;
  const done = (v: boolean | string | null) => {
    if (cur.kind === "confirm") cur.resolve(!!v);
    else if (cur.kind === "prompt") cur.resolve(typeof v === "string" ? v : null);
    else cur.resolve();
    setCur(null);
  };
  return (
    <Dialog title={cur.title} onClose={() => done(cur.kind === "confirm" ? false : null)}>
      {cur.text && <p className="small" style={{ whiteSpace: "pre-wrap" }}>{cur.text}</p>}
      {cur.kind === "prompt" && (
        <form onSubmit={(e) => { e.preventDefault(); done(value); }}>
          {cur.multiline ? <textarea className="textarea" value={value} onChange={(e) => setValue(e.target.value)} data-autofocus data-testid="dlg-prompt" /> : <input className="input" value={value} onChange={(e) => setValue(e.target.value)} data-autofocus data-testid="dlg-prompt" />}
        </form>
      )}
      <div className="actions">
        {cur.kind !== "alert" && <button className="btn" onClick={() => done(cur.kind === "confirm" ? false : null)}>{t("common.cancel")}</button>}
        <button className={`btn primary ${cur.kind === "confirm" && cur.danger ? "danger" : ""}`} data-testid="dlg-confirm" onClick={() => done(cur.kind === "prompt" ? value : true)} data-autofocus={cur.kind !== "prompt" ? "" : undefined}>{cur.kind === "alert" ? t("common.ok") : (cur.ok ?? (cur.kind === "confirm" ? t("common.yes") : t("common.ok")))}</button>
      </div>
    </Dialog>
  );
}
