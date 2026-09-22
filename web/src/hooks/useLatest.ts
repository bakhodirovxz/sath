import { useRef } from "react";

/** Eng so'nggi qiymatga ref (F10): effekt ichida o'qish uchun, lekin effektni qayta ishga tushirmaydi —
 * `react-hooks/exhaustive-deps` ni bostirish o'rniga aniq niyat: "o'zgarsa qayta ishga tushma, o'qiganda yangi bo'l". */
export function useLatest<T>(value: T): { readonly current: T } {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
