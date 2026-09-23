import { useEffect, useId, useRef } from "react";
import { initialFocusTarget, trapTab } from "./focus";

/** Modal dialoglar steki (UX-10): faqat eng yuqoridagi dialog Esc/Tab ga javob beradi — ustma-ust ochilgan
 * dialoglardan ikkalasi bir Esc bilan yopilmaydi. Global tezkor tugmalar `isModalOpen()` ni tekshiradi. */
const stack: symbol[] = [];
const listeners = new Set<() => void>();

export function isModalOpen(): boolean {
  return stack.length > 0;
}
/** Modal ochilish/yopilishini kuzatish (masalan fon kontentini `inert` qilish). */
export function onModalChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
const notify = () => listeners.forEach((f) => f());

export interface DialogProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Qo'shimcha sinf (masalan `wide`) */
  className?: string;
  /** Tavsif elementi id si (aria-describedby) */
  describedBy?: string;
}

/** Modal dialog: `role=dialog` + `aria-modal`, sarlavha bilan nomlangan, fokus ichida ushlanadi (Tab aylanadi),
 * ochilganda birinchi maydon (yoki `[data-autofocus]`) fokuslanadi, yopilganda fokus chaqirgan elementga qaytadi. */
export default function Dialog({ title, onClose, children, className, describedBy }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const token = Symbol("dialog");
    stack.push(token);
    notify();
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = ref.current!;
    initialFocusTarget(root).focus();
    const onKey = (e: KeyboardEvent) => {
      if (stack[stack.length - 1] !== token) return; // ustida boshqa dialog bor
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeRef.current();
      } else if (trapTab(root, e)) {
        e.stopPropagation();
      }
    };
    // Fokus dialogdan tashqariga (sichqoncha bilan) chiqsa — qaytariladi
    const onFocusIn = (e: FocusEvent) => {
      if (stack[stack.length - 1] !== token) return;
      if (e.target instanceof Node && !root.contains(e.target)) initialFocusTarget(root).focus();
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("focusin", onFocusIn);
      const i = stack.indexOf(token);
      if (i >= 0) stack.splice(i, 1);
      notify();
      if (opener && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} className={`dialog ${className ?? ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={describedBy} tabIndex={-1}>
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  );
}
