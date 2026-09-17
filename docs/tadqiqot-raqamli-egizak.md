# GES uchun raqamli egizak, BIM va SCADA: sanoat yechimlari tahlili va Sath yo'l xaritasi

*2026-09-15. Internet manbalari asosida (havolalar oxirida). Maqsad: sanoatda qanday funksiyalar bor, ular Sath da
qay darajada tayyor, nimani qo'shish va qanchalik avtomatlashtirish mumkin.*

## 1. Sanoat yechimlari nima qiladi

| Yechim | Asosiy funksiyalar |
|---|---|
| **ANDRITZ Metris Digital Twin** | Statsionar massa/energiya balansi, dinamik hisoblar, "nima bo'lsa" ssenariylari, virtual o'lchagichlar (hisoblangan kattaliklar), KPI monitoring, proaktiv maslahat (optimal setpoint), boshqaruv tizimi bilan ikki tomonlama almashuv; loyihalash → ishga tushirish → ekspluatatsiya bosqichlarida |
| **GE Vernova Hydro APM / SmartSignal** | AI/ML egizaklar bilan bashoratli tahlil, APM Health/Reliability/Strategy (sog'liq indeksi, ishonchlilik, strategiya), 3D egizakda ma'lumotlarni kontekstda ko'rsatish |
| **Voith OnCare.Health Hydro / HydroPocket** | Monitoring, tahlil va diagnostika, erta nosozlik aniqlash, holatga asoslangan texnik xizmat; bulutli kuzatuv |
| **ORNL/PNNL DTHS-OPF (AQSh DOE)** | Ochiq platforma: eski tizimlar + yangi sensorlar integratsiyasi; energiya ishlab chiqarishni optimallashtirish, bashoratli texnik xizmat, suv resurslarini boshqarish; Alder va Rocky Reach GESlarida sinalgan (Francis agregat egizagi) |
| **HEC-ResSim / HEC-RAS (USACE, bepul)** | Suv ombori tizimi rejimi (toshqin, suv ta'minoti), daryo gidravlikasi, yorilish to'lqini va suv bosish xaritalari |
| **ThingsBoard / Rapid SCADA (ochiq kod)** | Qurilma ulash, telemetriya, qoidalar, dashboard; 3D egizak ko'rinishi (tadqiqot bosqichida) |
| **Governor HIL simulyatorlar (IEEE 1207, IEC 61362)** | Turbina regulyatorini haqiqiy apparat bilan virtual stansiyada sinash — ishga tushirish vaqtini 95 % gacha qisqartiradi; operatorlarni o'qitish |

**Holat monitoringi (condition monitoring) standarti:** ISO 20816-5:2018 — gidroagregat podshipnik va val tebranishini
baholash (60–1000 ayl/min), A/B/C/D zonalar; podshipnik harorati va tebranish trendi nosozlikdan 30–90 kun oldin
ogohlantiradi; kavitatsiya tebranish trendi 3–6 oy oldin; FIK egri chizig'ida 1–2 % pasayish kavitatsiya belgisi.

## 2. Sath da nima bor (2026-09-15 holati)

| Funksiya | Holat |
|---|---|
| BIM: IFC versiyalar, tasdiqlash oqimi, farq, BCF, QTO, to'qnashuv | ✅ |
| Web 3D (Blender uslubi), element yaratish (Shift+A) va IFC ga commit | ✅ |
| SCADA: sensorlar (MQTT/OPC UA/Modbus), alarmlar, historian, dispetcher paneli, buyruqlar, jurnal | ✅ |
| Raqamli egizak: jonli sath/sarf ↔ model → kutilgan quvvat, og'ish, FIK; aktivlar; vaqt mashinasi | ✅ |
| Simulyatsiyalar: suv ombori/energiya, CFD, gidravlik zarba, minora, to'g'on barqarorligi, yorilish, filtratsiya, zilzila, toshqin/yorilish, ko'chki to'lqini, loyqa, to'g'on turi maslahatchisi, maxsus formulalar | ✅ |
| Maydon pasporti (yer, tuproq, seysmiklik, sathlar, materiallar) → simulyatsiyalar avtomatik | ✅ |
| **Holat monitoringi**: tebranish zonalari (ISO 20816-5), podshipnik harorati, sog'liq indeksi, anomaliya, qolgan resurs (RUL) | ✅ (2026-09-15) |
| **Kavitatsiya nazorati** (Toma σ jonli holatda) | ✅ (2026-09-15) |
| **Agregat-regulyator dinamikasi** (HYGOV, IEEE 1207): yuk tashlash/qabul, chastota, sozlamalarni oldindan sinash | ✅ (2026-09-15) |
| **Optimal yuk taqsimoti (dispatch)** — jonli holatdan "bugungi optimal rejim" | ✅ (2026-09-15) |
| **Mashq (training) rejimi** — «nima bo'lsa» sinovi (sath/sarf/quvvat o'zgartirib egizak, xavfsizlik, optimal rejim) — real ma'lumotga tegmasdan | ✅ (2026-09-15) |
| ML asosidagi bashorat (SmartSignal kabi) | integratsiya nuqtasi tayyor (`/ml/predictions` → ML.* sensorlar); kompaniyaning tayyor ML modeli keyin ulanadi |
| Yog'ingarchilik → toshqin (SCS-CN, qor erishi, GLOF) | ✅ (2026-09-15) |
| Toshqin prognozi (yog'in prognozi + jonli sath, oldindan tushirish tavsiyasi) | ✅ (2026-09-15) |
| CMMS: ish buyruqlari, MTTR/MTBF, avto buyruq sog'liqdan, ehtiyot qismlar | ✅ (2026-09-15) |
| Elektr qism: transformator yuklanishi/qarish (IEC 60076-7), generator | ✅ (2026-09-15) |

## 3. Avtomatlashtirish darajasi (nima qo'lda, nima o'zi)

1. **O'zi ishlaydi (fon)**: egizak har 30 s (kutilgan quvvat/og'ish), soatlik historian, aktiv ish soatlari, kunlik hisobot,
   stale nazorati, alarm bildirishnomalari, xavfsizlik ko'rsatkichlari (gerb zaxirasi, suv tashlagich, to'g'on sirpanishi).
2. **Bir tugma bilan**: barcha simulyatsiyalar pasport + model + jonli holatdan to'ldiriladi ("Modeldan", "Jonli holatdan");
   IFC yuklanganda QTO/to'qnashuv/fragments oldindan hisoblanadi.
3. **Qo'lda**: pasportni bir marta to'ldirish, sensorlarni sxemaga bog'lash, Pset_GES qiymatlari (desktop yoki web qoralama).

## 4. Yo'l xaritasi (tartib bilan)

1. Holat monitoringi va sog'liq indeksi (ISO 20816-5 zonalari, harorat chegaralari, FIK trendi, anomaliya z-score, RUL) — dispetcher panelida «Sog'liq».
2. Kavitatsiya: Toma σ (jonli quyi byef, napor, so'rish balandligi) — egizak agregat kartasida.
3. Agregat dinamikasi (HYGOV): regulyator sozlamalarini oldindan sinash, chastota/quvvat javobi.
4. Optimal yuk taqsimoti: FIK egri chiziqlari bo'yicha agregatlar orasida; kunlik jadval (sath chegaralari bilan).
5. Mashq rejimi: stsenariy in'eksiyasi, dispetcher javobini baholash (kvitlash vaqti, buyruqlar).
6. Keyin: ML bashorat (tarixdan), toshqin prognozi, CMMS ish buyruqlari, elektr qism (transformator yuklanishi).

## Manbalar

- ANDRITZ Metris Digital Twin — https://www.andritz.com/products-en/hydro/automation/metris-digital-twin
- GE Vernova Digital Hydro Plant / APM — https://www.gevernova.com/hydropower/digital-solutions/digital-hydro-plant ; https://www.gevernova.com/software/innovation/digital-twin-technology
- Voith digital hydropower solutions — https://www.voith.com/corp-en/products-services/hydropower-components/digital-hydropower-solutions.html
- ORNL/PNNL, "Modernizing US Hydropower: The Digital Twin for Hydropower Systems Project" (2024) — https://www.ornl.gov/sites/default/files/2025-01/Modernizing%20US%20Hydropower%20The%20Digital%20Twin%20for%20Hydropower%20Systems%20Project.pdf ; https://www.pnnl.gov/projects/digital-twins-hydropower
- International Water Power: digital twins for ageing plants — https://www.waterpowermagazine.com/analysis/hydropower-goes-data-driven-why-digital-twins-are-key-to-modernising-ageing-plants/ ; condition monitoring — https://www.waterpowermagazine.com/analysis/digitally-transforming-hydropower-condition-monitoring/
- POWER Magazine, "The Next Wave in Hydropower Condition Monitoring" — https://www.powermag.com/the-next-wave-in-hydropower-condition-monitoring/
- ISO 20816-5:2018 — https://www.iso.org/standard/67919.html
- Frontiers in Water (2025), hydropower digitalization mini-review — https://www.frontiersin.org/journals/water/articles/10.3389/frwa.2025.1681345/full
- Hydro turbine maintenance / cavitation monitoring — https://oxmaint.com/industries/power-plant/hydro-turbine-maintenance-cavitation-monitoring-repair
- Hydroelectric power unit simulator for turbine governor testing (HIL) — https://www.academia.edu/96129536/Hydroelectric_power_unit_simulator_for_turbine_governor_testing
- MDPI Energies (2026): digital-twin-based simulation training platforms — https://www.mdpi.com/1996-1073/19/17/4160
- HEC-ResSim — https://www.hec.usace.army.mil/software/hec-ressim/ ; HEC-RAS — https://www.hec.usace.army.mil/software/hec-ras/
- ThingsBoard — https://thingsboard.io/ ; Rapid SCADA — https://rapidscada.org/
