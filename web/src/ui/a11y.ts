/** Klaviatura yordamchilari (UX-10). */

/** `role="button"` elementi uchun Enter/Space → faollashtirish (ichki tugma/havoladan kelgan hodisa emas). */
export function onActivateKey(fn: () => void) {
  return (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };
}
