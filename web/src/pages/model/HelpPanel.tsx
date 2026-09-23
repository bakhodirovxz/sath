import { useEffect, useId, useRef } from "react";

/** Qisqa yo'riqnoma — yopib qo'yiladigan yon panel (UX-07): viewportni to'smaydi (modal emas), birinchi
 * kirishda o'ng tomonda ochiladi; «Yordam → Qisqa yo'riqnoma» yoki `?` bilan qayta ochiladi. */
export default function HelpPanel({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const ref = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  // Esc — fokus panel ichida bo'lsa yopadi (panel modal emas, fokusni ushlamaydi)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && ref.current?.contains(document.activeElement)) { e.stopPropagation(); close.current(); }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, []);
  return (
    <aside ref={ref} className="help-panel help-card" aria-labelledby={titleId}>
      <div className="help-panel-head">
        <h2 id={titleId}>Sath — qisqa yo'riqnoma</h2>
        <button type="button" className="btn sm icon-text" onClick={onClose} aria-label="Yo'riqnomani yopish">✕</button>
      </div>
      <div className="help-grid">
        <section><h3>1 · Ko'rish</h3><p>Chap tugma — tanlash, o'rta — surish, g'ildirak — masshtab, Shift+o'rta — aylantirish. Yuqorida shading (Solid/Wire/X-ray/Rendered), o'ngda Outliner va xususiyatlar.</p></section>
        <section><h3>Element qo'shish / tahrirlash</h3><p>Shift+A yoki «Qo'shish» menyusi: primitiv yoki GES inshooti (to'g'on, quvur, turbina…) — model/yer ustiga bosib joylashtiring, G/R/S bilan sozlang, o'ng panelda o'lchamlar va Pset_GES. Mavjud elementni tanlab <kbd>Tab</kbd> — tahrirlash, <kbd>X</kbd> — o'chirish. «IFC ga qo'shish» — yangi versiya (commit), GUID lar saqlanadi.</p></section>
        <section><h3>2 · Versiyalar va tasdiqlash</h3><p>Har IFC yuklash — versiya. Muhandis «Tasdiqqa yuboradi», tasdiqlovchi farqni ko'rib ma'qullaydi/merge qiladi. Muammo (issue) — 3D ko'rinish bilan.</p></section>
        <section><h3>3 · Tekshiruv va simulyatsiya</h3><p>To'qnashuvlar, hajm-miqdor (Tekshiruv); suv ombori/turbina rejimi va CFD (Simulyatsiya); jonli SCADA va raqamli egizak (Monitoring, Dispetcher paneli).</p></section>
        <section><h3>Tezkor tugmalar</h3><p>3D ko'rinish fokusda bo'lganda ishlaydi (bir marta bosing): Shift+A qo'shish · G/R/S · X o'chirish · Shift+D nusxa · H yashir · Alt+H hammasi · / ajrat · Home moslash · . tanlanganga · 1/3/7 ko'rinish · 5 orto · Z shading · B kesim qutisi · N yon panel · T asboblar · A hammasi · <kbd>:</kbd> yoki Ctrl+K — buyruqlar qatori. Istalgan joyda: F3 qidiruv · F2 ko'rinishni saqlash · F12 render · Ctrl+Space maksimal.</p></section>
      </div>
      <div className="actions"><button type="button" className="btn primary" onClick={onClose}>Tushunarli</button></div>
    </aside>
  );
}
