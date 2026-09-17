# Web UI — Blender uslubi (4-bosqich) — dizayn

Sana: 2026-09-17. Manba: `web/` (React + three.js/@thatopen). Hozirgi holat allaqachon Blender ga yaqin: menyu, workspace
yorliqlari, viewport header + gizmo, chap asboblar, Outliner, vertikal ikonkali Properties, status bar, buyruqlar qatori.
Maqsad: uch yo'nalishda Blender ga yaqinlashtirish, mavjud funksiyalarni buzmasdan (vitest + playwright e2e o'tadi).

## A. Tema va o'lchamlar (`web/src/ui/theme.css`)

Blender Dark tokenlari `:root` da: fon `#303030` (editor), viewport `#3d3d3d→#2b2b2b` gradient (canvas), panel `#3d3d3d`,
header `#303030`, region chegarasi `#191919`, widget `#545454` (hover `#656565`), aksent `#4772b3` (tanlov/faol),
matn `#e6e6e6` / xira `#9a9a9a`, sarlavha balandligi 26px (top bar, viewport header, dock head), status 22px, asboblar
ustuni 40px, widget radius 4px, shrift 12px. Sath brendi: faqat logo/`Sath` matni `--brand` (#39b7c9). Eski Sath ranglari
tokenlar orqali almashadi — selektorlar o'zgarmaydi; `.btn` radius/hover Blender widget kabi; `.vp-select` Blender dropdown.

## B. Viewport N-panel va klaviatura

- `ViewportSidebar` (yangi, `pages/model/ViewportSidebar.tsx`): viewport o'ng chetida, `N` bilan ochiladi/yopiladi
  (dock o'zgarmaydi — u Blender «Properties editor»). Vertikal yorliqlar: **Element** (nom, klass, GUID, o'lchamlar,
  markaz — PropertiesPanel ma'lumotidan), **Ko'rinish** (proyeksiya, shading, grid, yorliqlar, ko'rinishlar 1/3/7,
  saqlangan ko'rinishlar), **Sath** (joriy versiya, tezkor: yangi versiya, tasdiqqa, issue, webda/desktopda ochish).
- Klaviatura qo'shimchalari (`ModelPage` onKey): `Z` — pie menyu (Wireframe/Solid/Material/Rendered, sichqoncha
  atrofida, tugmani qo'yib yuborganda/bosganda tanlanadi), `F3` — operator qidiruvi (COMMANDS + menyu bandlari, matn
  bilan filtrlanadi, Enter bajaradi), `Ctrl+Space` — viewportni maksimal (dock, outliner, asboblar yashiriladi/qaytadi),
  `A` — hammasini tanlash, `Alt+A` — bekor, `Shift+C` — hammasiga moslash + kursor. Mavjud tugmalar saqlanadi;
  `N` endi sidebar, dock uchun `Ctrl+N`? — yo'q: dock ochiq qoladi, faqat `N` sidebar. Yordam oynasi yangilanadi.

## C. Outliner va Properties

- Outliner (`TreePanel`): Blender ustunlari — chap: ochish/yopish, ikonka (IfcProject/Site/Building/Storey/element
  turi bo'yicha `Icon`), nom (faol — och rang, tanlangan — aksent fon), o'ng: ko'z (ko'rinish) + «ajratish» (local view)
  tugmasi; qatorlar 20px, hover fon; o'ng tugma kontekst menyu (Tanlash (ierarxiya), Yashirish, Ajratish, Hammasini
  ko'rsatish, Moslash); filtr: tur bo'yicha (select). Drag-drop bilan konteyner o'zgartirish — ko'lam tashqarisi
  (server IFC tahriri).
- Properties (`PropertiesPanel`): Blender panellari — yopiladigan bo'limlar sarlavha foni bilan («Element», «O'lchamlar»,
  «Atributlar», har Pset alohida panel), qatorlar label (40%) / maydon (60%) Blender maydoni ko'rinishida (o'qish uchun,
  `canEdit` bo'lsa «Tahrirlash» tugmasi saqlanadi). Bo'lim holati (ochiq/yopiq) localStorage da.

## Sinov

`npm run typecheck`, `npm test` (vitest), `npm run e2e` (playwright, server bilan) — mavjud; qo'shimcha vitest:
`ViewportSidebar` render (element ma'lumotisiz/bilan), `F3` qidiruv filtri (sof funksiya `searchCommands`), pie menyu
tanlovi (sof `pickPie(angle)`). Vizual tekshiruv: playwright skrinshot (model sahifasi, N-panel ochiq, F3, Z pie).
