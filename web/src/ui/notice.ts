/** Bildirishnomalar (UX-02): muvaffaqiyat / ma'lumot / ogohlantirish — xatodan ALOHIDA kanal.
 * Muvaffaqiyat qizil xato matni sifatida chiqmaydi; operator ekranida ham alarm rangini egallamaydi
 * (neytral panel + belgi). Xato — `role=alert`, qolganlari — `role=status` (NoticeHost). */

export type NoticeKind = "success" | "info" | "warning" | "error";

export interface Notice {
  id: number;
  kind: NoticeKind;
  text: string;
  /** Avtomatik yopilish, ms (0 — faqat qo'lda) */
  ttl: number;
}

const TTL: Record<NoticeKind, number> = { success: 6000, info: 6000, warning: 12000, error: 0 };
const MAX = 4;

let items: Notice[] = [];
let seq = 0;
const subs = new Set<() => void>();
const timers = new Map<number, ReturnType<typeof setTimeout>>();

function emit() {
  for (const f of subs) f();
}

export function notify(text: string, kind: NoticeKind = "success", opts: { ttl?: number } = {}): number {
  const id = ++seq;
  const ttl = opts.ttl ?? TTL[kind];
  // Bir xil matn takrorlansa — yangisi eskisining o'rnini egallaydi (spam yo'q)
  const dup = items.find((n) => n.text === text && n.kind === kind);
  if (dup) dismiss(dup.id, false);
  items = [...items, { id, kind, text, ttl }].slice(-MAX);
  if (ttl > 0) timers.set(id, setTimeout(() => dismiss(id), ttl));
  emit();
  return id;
}

export function dismiss(id: number, notify = true): void {
  const t = timers.get(id);
  if (t) clearTimeout(t);
  timers.delete(id);
  const next = items.filter((n) => n.id !== id);
  if (next.length === items.length) return;
  items = next;
  if (notify) emit();
}

export function clearNotices(): void {
  for (const t of timers.values()) clearTimeout(t);
  timers.clear();
  items = [];
  emit();
}

export function subscribeNotices(f: () => void): () => void {
  subs.add(f);
  return () => { subs.delete(f); };
}

export function getNotices(): Notice[] {
  return items;
}
