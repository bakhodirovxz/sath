# Sath — tijoriy BIM / SCADA / APM platformalari bilan solishtirish

Sana: 2026-09-22 · Holat: H3 (`4c0459d`) dan keyingi kod · Yozuvchi: ichki texnik baho

Bu hujjat **savdo materiali emas** — u Sath nimani haqiqatan qiladi, nimani qilmaydi va bozordagi
platformalarga nisbatan qayerda turishini ko'rsatadi. Har bir da'vo kod va testlar bilan tekshirilgan;
yo'q narsa «yo'q» deb yozilgan. Tijoriy mahsulotlarning imkoniyatlari nashr etilgan hujjatlar va
umumiy sanoat amaliyoti asosida **kategoriya darajasida** tasvirlangan (versiya va litsenziyaga qarab
farq qiladi) — bu yerda ularning aniq funksiyalari sinovdan o'tkazilmagan.

## 1. Sath nima (o'lchamlar)

| Qism | Hajm | Izoh |
|---|---|---|
| `server/` | ~25 700 qator Python | FastAPI, SQLAlchemy 2.0, 235 endpoint, Alembic 29 migratsiya |
| `sim/ges_sim` | ~9 400 qator | 27 muhandislik moduli (gidravlika, to'g'on, seysmika, transformator) |
| `web/` | ~15 700 qator TS/TSX | React 18, ISA-101 operator ekranlari, IFC 3D ko'ruvchi |
| Testlar | 54 server + 11 sim fayl; 463 test + 18 e2e | to'liq to'plam ~11 daqiqa |

Pozitsiya: **Purdue L3/3.5 — zavod axborot va raqamli egizak qatlami**. Sath stansiya boshqaruv
tizimi (PLC/RTU, himoya) o'rnini bosmaydi va bosmasligi kerak; u SCADA dan ma'lumot oladi, uni BIM
modeli, muhandislik hisoblari va aktiv boshqaruvi bilan bog'laydi.

## 2. Qiyosiy jadval

Belgilar: ✅ bor va sinalgan · ⚠️ qisman · ❌ yo'q · ⛔ ataylab qilinmaydi (O bo'limi)

| Imkoniyat | Sath | Tijoriy BIM egizak (Autodesk Tandem, Bentley iTwin, Trimble) | SCADA/HMI (Ignition, AVEVA System Platform, Siemens Spectrum) | APM / CM (GE Vernova APM, Voith OnCare, ANDRITZ Metris, SKF) |
|---|---|---|---|---|
| IFC4.3 (ISO 16739-1) import va 3D | ✅ IFC4X3_ADD2 sxemasi, web-ifc ko'ruvchi | ✅ (kuchli) | ❌ odatda yo'q | ❌ |
| IDS (axborot talablari) tekshiruvi | ✅ ifctester, tasdiqlashni bloklaydi | ⚠️ (yangi mahsulotlarda) | ❌ | ❌ |
| ISO 19650 yaroqlilik/reviziya, CDE oqimi | ✅ S0–S7, P/C, nomlash shabloni, EIR/BEP | ✅ | ❌ | ❌ |
| Federatsiya va to'qnashuv tahlili | ✅ grid broad-phase, birlashtirilgan IFC | ✅ (kuchliroq: 4D, katta modellar) | ❌ | ❌ |
| Georeferensiya (IfcMapConversion, EPSG) | ✅ Krüger TM / Pulkovo GK, Helmert | ✅ | ⚠️ | ❌ |
| Klassifikatsiya (Uniclass, ichki KSI) | ✅ | ✅ | ❌ | ⚠️ |
| Aktiv topshiruvi (COBie uslubida) | ✅ registr, CSV/zip, hujjatlar | ✅ | ❌ | ⚠️ |
| 4D (jadval) / 5D (xarajat) | ❌ → P11 | ✅ (Synchro, Navisworks) | ❌ | ❌ |
| BCF izohlari (BIMcollab, Revit bilan) | ❌ → P12 | ✅ | ❌ | ❌ |
| Nuqtalar buluti / skanerni model bilan solishtirish | ❌ (vendor ishi) | ✅ | ❌ | ❌ |
| O'lchov yig'ish (Modbus, IEC 60870-5-104, MQTT) | ✅ gateway + spool, sifat bayrog'i | ❌ | ✅ (kengroq protokol to'plami) | ⚠️ |
| IEC 61850 (MMS, SCL/SCD, GOOSE) | ⛔ O bo'limi (sertifikatlangan stek kerak) | ❌ | ✅ | ⚠️ |
| OPC UA server (L3 → L2 chiqish) | ❌ → P1 (rejada) | ⚠️ | ✅ | ✅ |
| ICCP/TASE.2 (dispetcher markazi) | ⛔ O bo'limi | ❌ | ✅ | ❌ |
| Historian (retention, agregat, Timescale) | ✅ 1m/10m/soatlik, siqish, PG+Timescale | ⚠️ | ✅ (katta ko'lamda kuchliroq) | ✅ |
| Alarm boshqaruvi (ISA-18.2, EEMUA-191) | ✅ kechikish, shelving, bostirish, toshqin, KPI | ❌ | ✅ | ⚠️ |
| SOE (hodisalar ketma-ketligi) | ✅ | ❌ | ✅ | ⚠️ |
| Operator ekranlari (ISA-101 L1–L4) | ✅ | ❌ | ✅ | ⚠️ |
| Boshqaruv: select-before-operate, ikki tasdiq | ✅ token bilan, readback, watchdog | ❌ | ✅ | ❌ |
| Blokirovkalar (interlock) va LOTO taqiqi | ✅ B4 + H2 (chetlab o'tilmaydi) | ❌ | ✅ (PLC darajasida) | ❌ |
| Issiq rezerv, soniyadan kam failover | ⛔ O bo'limi (rol/leader va replika bor) | ❌ | ✅ | ❌ |
| Sog'liq indeksi va holat monitoringi | ✅ ISO 13374 bloklari (DA→AG) | ⚠️ | ⚠️ | ✅ (kuchli) |
| Tebranish: zona (ISO 20816-5), spektr, podshipnik chastotalari | ✅ zona, envelope/BPFO tahlili, saqlash | ❌ | ⚠️ | ✅ (datchik + apparat bilan) |
| Tashqi CM tizimi natijasini qabul qilish | ✅ SD/HA/PA darajasida, `valid_hours` | ❌ | ⚠️ | ✅ |
| Prognoz (RUL) | ⚠️ chiziqli trend + tashqi RUL | ❌ | ❌ | ✅ (model kutubxonasi bilan) |
| Ko'p o'zgaruvchili anomaliya (PCA/AE) | ❌ → P10 (hozir z-score va egizak og'ishi) | ❌ | ⚠️ | ✅ |
| FMEA / RCM kutubxonasi | ❌ → P15 | ❌ | ❌ | ✅ |
| CMMS: reja, mehnat, qism, PTW/LOTO, ISO 14224 | ✅ H2 | ⚠️ (integratsiya orqali) | ⚠️ | ✅ |
| Uskuna kodlash KKS / RDS-PP | ✅ H1 grammatika + ierarxiya | ⚠️ | ⚠️ | ✅ |
| Muhandislik hisoblari (to'g'on, gidravlika, seysmika) | ✅ 27 modul, normalarga havola bilan | ❌ | ❌ | ❌ |
| Gidravlik zarba, surge tank, regulyator (HYGOV) | ✅ | ❌ | ❌ | ❌ |
| Toshqin yo'naltirish, to'g'on yorilishi (Froehlich) | ✅ (1D/Puls; Sen-Venan — vendor) | ❌ | ❌ | ❌ |
| Audit zanjiri (hash), MFA, sessiya rotatsiyasi | ✅ | ⚠️ | ⚠️ | ⚠️ |
| SSO (OIDC/SAML), LDAP/AD | ❌ → P9 | ✅ | ✅ | ✅ |
| SIEM ga jurnal eksporti (syslog/CEF) | ❌ → P9 | ⚠️ | ✅ | ⚠️ |
| Mobil / dala rejimi (oflayn) | ❌ → P14 | ✅ | ⚠️ | ✅ |
| GIS qatlami (WMS/WFS, GeoJSON) | ❌ → P13 (georef bor) | ✅ | ⚠️ | ❌ |
| Hisobotlar (IEEE 762 EAF/FOR, oylik) | ❌ → P2 (rejada) | ❌ | ⚠️ | ✅ |
| Ko'p stansiya (fleet) ko'rinishi | ❌ → P6 | ✅ | ✅ | ✅ |
| Narx | o'z kodi, litsenziya to'lovisiz | yuqori (obuna, foydalanuvchi boshiga) | yuqori (teg boshiga yoki server) | juda yuqori (aktiv boshiga + apparat) |

## 3. Sath kuchli bo'lgan joylar

1. **BIM ↔ ekspluatatsiya bog'lanishi bitta tizimda.** Tijoriy dunyoda bu odatda uchta mahsulot
   (BIM egizak + SCADA/historian + APM/CMMS) va ular orasidagi integratsiya loyihasi. Sath da model
   versiyasi, IDS tekshiruvi, KKS kodi, sensor, alarm, ish buyrug'i va spektr bitta ma'lumotlar
   bazasida va bitta ruxsat modelida.
2. **Gidroenergetika muhandisligi ichkarida.** To'g'on barqarorligi, sizish, suv tashlagich,
   gidravlik zarba, regulyator, transformator issiqligi, toshqin va yorilish — hammasi normaga
   havola bilan (USACE, USBR, SNiP/SP, IEC, EN 1998). Tijoriy SCADA/APM bularni bermaydi; ular uchun
   alohida muhandislik dasturlari (HEC-RAS, SEEP/W, Slide2) ishlatiladi va natija qo'lda ko'chiriladi.
3. **Xavfsizlik qoidalari kodda majburlangan.** Select-before-operate, ikki tasdiq, blokirovkalar,
   LOTO (chetlab o'tib bo'lmaydigan), audit hash zanjiri, MFA, sessiya rotatsiyasi — bularning
   har biri test bilan qopqoqlangan.
4. **Ochiq standartlarga tayanish.** IFC4.3, IDS, ISO 19650, KKS/RDS-PP, ISO 14224, ISO 13374,
   ISO 20816-5, ISA-101/18.2, EEMUA-191 — vendor qulfi yo'q, ma'lumot ko'chiriladi.
5. **Hajmi va o'qilishi.** ~51 000 qator kod va 481 test — bitta muhandis jamoasi saqlab tura oladigan
   ko'lam; tijoriy platformalarda bitta konnektor shuncha bo'lishi mumkin.

## 4. Sath ortda qolgan joylar (halol ro'yxat)

| Kamchilik | Ta'siri | Yo'l |
|---|---|---|
| OPC UA serveri yo'q | Sath hisoblagan teglarni tashqi HMI/SCADA o'qiy olmaydi | P1 (rejada) |
| Ekspluatatsiya hisobotlari (IEEE 762) yo'q | Oylik/yillik hisobot qo'lda tayyorlanadi | P2 (rejada) |
| SSO/LDAP yo'q | Korxona hisoblari alohida boshqariladi | **P9 (yangi)** |
| Ko'p o'zgaruvchili anomaliya modeli yo'q | Sekin rivojlanayotgan murakkab nosozlik kech ko'rinadi | **P10 (yangi)** |
| 4D/5D yo'q | Ta'mirlash jadvali va byudjeti modelga bog'lanmagan | **P11 (yangi)** |
| BCF yo'q | Taqriz izohlari Revit/Navisworks bilan almashinmaydi | **P12 (yangi)** |
| GIS qatlami yo'q | Havza, kommunikatsiya, yer uchastkasi ko'rinmaydi | **P13 (yangi)** |
| Mobil/oflayn rejim yo'q | Dala xodimi ish buyrug'ini joyida yopa olmaydi | **P14 (yangi)** |
| FMEA/RCM kutubxonasi yo'q | Nosozlik rejimi va monitoring kanali bog'lanmagan | **P15 (yangi)** |
| Prognoz sodda (chiziqli trend) | RUL taxminiy; tijoriy APM model kutubxonasiga yutqazadi | P10 bilan birga |
| Katta ko'lam sinovi yo'q | 10 000+ teg va 10+ yillik arxivda yuk sinovi o'tkazilmagan | M bo'limi (yuk testi) |
| Sertifikatlar yo'q | IEC 62443 bo'yicha rasmiy baho, o'lchov sertifikati | ⛔ O bo'limi (vendor/laboratoriya) |

## 5. Xulosa

Sath **gidroelektrostansiya uchun BIM asosidagi ekspluatatsiya platformasi** sifatida o'z sinfida
kuchli: model, monitoring, muhandislik va aktiv boshqaruvini bitta ochiq tizimda birlashtiradi.
U **SCADA emas** (va bo'lmasligi kerak): real vaqt boshqaruvi, himoya va soniyadan kam rezerv
L1/L2 uskunasining ishi.

Tijoriy platformalar bilan solishtirganda asosiy farq **qamrov chuqurligida emas, integratsiyada**:
Tandem + Ignition + GE APM to'plami har bir yo'nalishda chuqurroq, lekin ularni bog'lash alohida
loyiha va yillik litsenziya. Sath bu bog'lanishni tug'ma beradi, evaziga har bir yo'nalishda
tijoriy mahsulotning eng chuqur imkoniyatlarini emas, muhandislik uchun yetarli qismini beradi.

Keyingi bosqichda eng katta qiymat: **P1 (OPC UA)** — tashqi tizimlar bilan ikki tomonlama
ekosistemaga kirish, **P2 (hisobotlar)** — kundalik ekspluatatsiya ehtiyoji, **P10 (anomaliya
modellari)** — APM bilan farqni kamaytiradi, va **P14 (mobil)** — CMMS dan amalda foydalanish uchun.
