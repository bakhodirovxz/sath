# Sath web — UI yo'nalishi (reference lock va qarorlar daftari)

Holat: 2026-09 audit (WEB/FE/UX) bo'yicha qayta ishlash. Bu hujjat — dizayn qarorlarining yagona manbasi:
yangi ekran yoki komponent shu qoidalarga tayanadi, og'ish bo'lsa — shu yerda yoziladi.

## 0. Tadqiqot asosi

Refero MCP (styles/screens) bu sessiyada mavjud emas edi; tadqiqot manbalari:

| Manba | Nima olindi |
|---|---|
| ANSI/ISA-101.01-2015 *HMI for Process Automation Systems* | Ekranlar ierarxiyasi L1–L4, neytral fon, rang faqat holat uchun, animatsiya faqat anomaliyada |
| Hollifield, Oliver, Nimmo, Habibi — *The High Performance HMI Handbook* (PAS, 2008) | Kulrang kanva, jihoz — kontur (ishlayotgan — to'q kulrang to'ldirilgan, to'xtagan — bo'sh), alarm indikatori = rangli shakl + ustuvorlik raqami, "normal" uchun yashil ishlatilmaydi, qiymat matni katta va to'q |
| EEMUA 191 (3-nashr, 2013) | Alarm toshqini (10 daq > 10), kvitlanmagan alarm annunsiyasi kvitlangunga qadar davom etadi, top-N ko'rinish |
| ANSI/ISA-18.2-2016 | Alarm holatlari (unack/acked/rtn_unack), shelving/OOS, ratsionalizatsiya maydonlari |
| WCAG 2.2 AA | Matn 4.5:1, katta matn/grafika 3:1, fokus ko'rinadi (2.4.11/2.4.13), rang yagona kanal emas (1.4.1), harakatni kamaytirish (2.3.3) |
| Blender 4.x "Blender Dark" temasi | Muhandis temasining neytrallari, zich 12–13 px UI, 26–30 px sarlavha satrlari, faol ko'k #4772b3, tanlov #334d80 |
| refero-design craft: color.md, typography.md, craft-details.md, motion.md, anti-ai-slop.md | Token nomlash (vazifa bo'yicha), ≤ 8 o'lcham shkalasi, tabular raqamlar, `:focus-visible`, harakat 90–240 ms, "AI-slop" belgilari |

## 1. Reference lock

### Operator temasi (dispetcher: `/ops/*`, `/projects/:id/dashboard`)

```text
Primary reference/direction: ISA-101 / High Performance HMI (Hollifield) — kulrang, kam rangli, holatga yo'naltirilgan
Preserve:
  - neytral kulrang kanva (L≈86 %), kartalar/soyalar yo'q — uchastkalar ingichka chiziq bilan
  - jihozlar — faqat kontur; holat — kulrang to'ldirish (ishlayapti/yopiq = to'q kulrang, to'xtagan/ochiq = bo'sh)
  - rang FAQAT anomaliya/alarm uchun; alarm = rangli shakl + ustuvorlik raqami + kod (◆1 kritik, ▲2 yuqori, ■3 o'rta, ●4 past)
  - katta o'qiladigan qiymatlar: mimika qiymati ≥ 18 px, yorliq ≥ 14 px, KPI 28 px; tana matni 14 px
  - animatsiya faqat anormal holatda (kvitlanmagan alarm miltillashi 1 Hz); reduced-motion — butunlay o'chadi
Borrow only:
  - EEMUA 191: doimiy top-3 alarm banneri, toshqin rejimi
  - WCAG: har rangli belgi yonida shakl/matn; fokus halqasi ikki qavatli (qora + oq)
Role rules:
  - alarm ranglari (qizil/to'q sariq/sariq/ko'k) boshqa hech narsaga ishlatilmaydi (tugma, havola, "normal", suv)
  - "ok"/"normal" rangsiz (matn kulrang); yashil yo'q
  - eskirgan/yaroqsiz qiymat — rang emas: shtrix fon + "?"/"✕" + yosh matni
  - navigatsiya aktiv holati — to'q kulrang (#2F343B), ko'k emas (ko'k P4 alarmga band)
Media strategy: code-native SVG mimika (jihoz sxemasi); rasm/illyustratsiya yo'q
Reject: yashil "normal", ko'k suv, amber shina/transformator, oqim chizig'i animatsiyasi, aylanayotgan turbina,
  qorong'i operator temasi, gradient, soyali kartalar, emoji
Token commitments: § 2
```

### Muhandis temasi (BIM: loyihalar, model, admin)

```text
Primary reference/direction: Blender 4.x "Blender Dark" (ish maydoni: outliner, properties, viewport)
Preserve:
  - neytral to'q kulranglar (#303030 panel, #282828 sarlavha, #3d3d3d viewport, #545454 vidjet)
  - faol/tanlov ko'ki (#4772b3, #334d80); brend teal (#39b7c9) faqat logo/kirish
  - zich UI (12–13 px), 26–30 px sarlavha satrlari, vertikal properties yorliqlari
Fix (identitetni o'zgartirmasdan): kontrast (to'ldirilgan xavf belgilari — oq matn 1.7:1 edi), o'lcham shkalasi
  (12.5 px tana → 13 px), 4 px ritm, bir xil komponentlar (btn/input/badge balandligi), dublikat CSS
Reject: yangi aksent rang (indigo/violet), yorug' muhandis temasi, kartalar/soyalar ko'paytirish
```

## 2. Tokenlar

Manba: `web/src/ui/tokens.ts` (JS, kontrast testlari) ↔ `web/src/ui/tokens.css` (CSS, test bilan sinxron).
Komponentlarda hex yo'q (lint + test), faqat `var(--…)`.

### Ranglar (vazifa bo'yicha)

| Token | Operator | Operator (kunduzgi) | Muhandis | Vazifa |
|---|---|---|---|---|
| `--canvas` | #DCDDDF | #F2F2F2 | #3D3D3D | mimika/viewport foni |
| `--panel` | #E4E5E7 | #FFFFFF | #303030 | sahifa/panel |
| `--chrome` | #CDD0D4 | #E6E6E6 | #282828 | sarlavha, navigatsiya |
| `--text` | #16181B | #000000 | #E6E6E6 | qiymat, asosiy matn |
| `--text-muted` | #3F444B | #26292D | #B3B3B3 | yorliqlar |
| `--mimic-outline` | #5C626B | #333333 | #8B9098 | jihoz konturi (≥ 3:1) |
| `--mimic-on` | #5C626B | #333333 | #9AA0A8 | ishlayapti/yopiq to'ldirish |
| `--accent` | #2F343B | #111111 | #4772B3 | faol navigatsiya/tanlov |
| `--alarm-critical` | #D6211A | #D6211A | #FF6262 | ◆ 1, siyoh oq |
| `--alarm-high` | #EC8A1C | #EC8A1C | #F29A38 | ▲ 2, siyoh qora |
| `--alarm-medium` | #F2C200 | #F2C200 | #F2C94C | ■ 3, siyoh qora |
| `--alarm-low` | #2E6FD8 | #2E6FD8 | #5B8FF0 | ● 4, siyoh oq |
| `--alarm-outline` | #1B1D20 | #000000 | #111111 | alarm shakli konturi (grafik kontrast) |
| `--attention` | #3F444B | #26292D | #C9B27A | NEYTRAL "e'tibor" (muddati o'tgan ish, kam qism) — alarm emas |
| `--danger-strong` | #B3261E | #B3261E | #C0392B | to'ldirilgan xavf belgisi (oq matn ≥ 4.5:1) |

### Tipografiya

Bitta oila (`Inter`, `Segoe UI`, tizim sans), raqamlar `tabular-nums`; kalit/teg — mono.

| Token | Muhandis | Operator | Ishlatilishi |
|---|---|---|---|
| `--fs-xs` | 11 px | 12 px | izoh, birlik (eng kichik) |
| `--fs-sm` | 12 px | 13 px | jadval, vidjet |
| `--fs-body` | 13 px | 14 px | tana |
| `--fs-md` | 15 px | 16 px | bo'lim sarlavhasi |
| `--fs-lg` | 20 px | 20 px | sahifa sarlavhasi |
| `--fs-value` | 16 px | 18 px | jonli qiymat (mimika/kartochka) |
| `--fs-kpi` | 22 px | 28 px | KPI |
| mimika yorlig'i | — | 14 px (viewBox birligi = px, minimal kenglikda) | |

### Oraliq, radius, harakat

- Oraliq: 4 px asos — `--sp-1` 4, `--sp-2` 8, `--sp-3` 12, `--sp-4` 16, `--sp-6` 24, `--sp-8` 32 (+ 2/6 zich UI uchun).
- Radius: muhandis 4 px (Blender), operator 2 px (sanoat, aniq qirra).
- Harakat: hover/press 120 ms, panel 200 ms; alarm miltillashi 1 Hz `steps(2)`; `prefers-reduced-motion` — barcha
  animatsiya va o'tishlar o'chadi (miltillash o'rniga statik qo'sh kontur).

## 3. Qarorlar daftari

| Qaror | Manba | Qoida / rol | Sabab |
|---|---|---|---|
| Operator fon — neytral kulrang, kartalar yo'q | ISA-101 §5, HP-HMI ch.6 | fon ≠ ma'lumot | ko'z charchashi va rangli signallar ajralishi |
| "Normal" rangsiz, yashil yo'q | HP-HMI "no green for normal" | rang = anomaliya | yashil ekran fonga aylanib, alarm ko'rinishini susaytiradi |
| Jihoz kontur, holat — kulrang to'ldirish | HP-HMI | on=to'q, off=bo'sh | rang ishlatmasdan holat, rang ko'rmaydiganlarga ham |
| Alarm shakli + raqam + kod | ISA-18.2, WCAG 1.4.1 | ◆1 ▲2 ■3 ●4 | rang yagona kanal emas; kulrang bosmada ham o'qiladi |
| Sariq/to'q sariq shakllarga qora kontur | WCAG 1.4.11 (3:1) | kontur tokeni | sariq kulrangda 1.2:1 — kontur 12:1 |
| Animatsiya faqat kvitlanmagan alarm | ISA-101 §6, motion.md | 1 Hz | doimiy harakat e'tiborni o'g'irlaydi |
| Oqim/aylanish animatsiyasi olib tashlandi | ISA-101 | — | normal holatda harakat yo'q |
| Qiymat ≥ 18 px, yorliq ≥ 14 px | HP-HMI, dispetcher masofasi 1–2 m | tipografiya shkalasi | audit: 9–10 px o'qilmasdi |
| Mimika tor ekranda gorizontal suriladi (kichraymaydi) | yuqoridagi qoida | viewBox birligi ≥ 1 px | 390 px da 0.35× kichrayish matnni 3 px qilardi |
| Eskirgan qiymat — shtrix + "?" + yosh | ISA-101 sifat ko'rsatkichi | rangsiz | eski qiymat "normal" ko'rinmasin |
| "ALOQA YO'Q" katta banner | EEMUA 191 | — | badge yetarli emas edi |
| Doimiy alarm banneri (top-3, har sahifa) | EEMUA 191 | ustuvorlik bo'yicha | 6 s flash yo'qolardi |
| Neytral "e'tibor" uslubi | audit UX-02 | alarm-row faqat alarm | muddati o'tgan ish buyrug'i alarm emas |
| Muvaffaqiyat — bildirishnoma (toast), xato — qizil matn | craft-details §6 | role=status / role=alert | "saqlandi" qizil ko'rinardi |
| Kunduzgi (yuqori kontrast) variant | WCAG, yorug' boshqaruv xonasi | tugma bilan | quyosh/yorug' xonada kontrast |
| Muhandis — Blender Dark saqlanadi | foydalanuvchi talabi | identitet | BIM foydalanuvchilari uchun tanish |
| Operator navigatsiya aktiv — to'q kulrang | HP-HMI | ko'k — P4 alarm | ko'k tugma bilan past alarm chalkashmasin |
| Dispetcher tablari ikki zonaga | audit UX-07 | Operator / Muhandislik | 12 tekis yorliq — yo'qolish |
| Hex faqat token fayllarida | color.md "no random hex" | test + stylelint | tema almashishi va kontrast nazorati |

## 4. Rad etilganlar

- Indigo/violet aksent, gradientlar (Blender viewport gradientidan tashqari), glassmorphism.
- Har narsani kartaga o'rash, dekorativ yon chiziqlar (chap chiziq faqat holat uchun).
- Emoji ikonlar (◆▲■● — semantik shakllar, emoji emas).
- Operator ekranlarida qorong'i tema (ISA-101 kulrang talabiga zid; muhandis temasi faqat BIM).
- Suvni ko'k bilan bo'yash (operator) — kulrang to'ldirish, sath chizig'i to'q.

## 5. Tekshiruv (validatsiya)

`web/src/ui/tokens.test.ts` — barcha tema juftliklari kontrasti; `design.test.ts` — hex/inline-style cheklovi.
Skrinshotlar (oldin/keyin, 1440 va 390 px, ikkala tema): hisobot ilovasi. Og'ish topilsa — shu hujjat yangilanadi.
