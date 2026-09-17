# Sath — foydalanuvchi qo'llanmasi

Sath — kompaniya ichidagi GES (gidroelektrostansiya) modellari bilan ishlash tizimi.
Brauzerda ko'rish, taqriz va tasdiqlash, simulyatsiya va monitoring; FreeCAD ichida — chizish va commit.

## 1. Kirish va rollar

Brauzerda server manzilini oching (masalan `http://ges-server:8000`), login/parolingizni kiriting.
Loyihada sizga rol beriladi:

| Rol | Nima qila oladi |
|---|---|
| **Ko'ruvchi** | modelni ko'rish, o'lchash, issue ochish, izoh, simulyatsiya ishga tushirish |
| **Dispetcher** | + alarmlarni kvitlash, boshqaruv buyruqlari (setpoint), smena jurnali, texnik xizmatni qayd etish |
| **Muhandis** | + yangi versiya yuklash (commit), tasdiqqa yuborish, sensor/aktiv sozlash, egizakni hisoblash |
| **Tasdiqlovchi** | + ma'qullash / rad etish / tasdiqlash (published), a'zolar rollari |
| **Administrator** | foydalanuvchilar, loyihalar yaratish, hamma loyihada tasdiqlovchi |

## 2. Loyihalar va modellar

**Loyihalar** — har bir GES. Ichida **modellar** (masalan «To'g'on», «Mashina zali»). Har modelda
**versiyalar** — har IFC yuklash bitta versiya (kim, qachon, nima o'zgardi).

Versiya holatlari: **Ishda** → **Tasdiqda** → **Tasdiqlangan** → **Arxiv**.
Model ochilganda avval *tasdiqlangan* versiya ko'rsatiladi (bo'lmasa oxirgisi).

## 3. 3D ish maydoni (Blender/3ds Max uslubi)

- **Yuqori satr**: menyular (Fayl · Tahrir · Ko'rinish · Tanlash · Tekshiruv · Simulyatsiya · Yordam) va
  **ish maydonlari** (Ko'rish · Tasdiqlash · Simulyatsiya · Monitoring · Tekshiruv) — Blender dagi kabi.
- **Viewport sarlavhasi**: kamera rejimi (aylantirish / yurish WASD / plan), shading (● Solid, ◯ Wireframe,
  ◐ X-ray, ◈ Rendered — ambient occlusion + konturlar), grid, Persp/Ortho, rang sxemasi (material / IFC turi /
  qavat — legenda bilan), **kesim qutisi** (tanlangan atrofida, `B`), **render** (rasm PNG, `F12`), ko'rinishlar.
- Kursor ostidagi element nomi ko'rinadi (tooltip); xususiyatlarda o'lchamlar (X×Y×Z) va markaz.
- **Outliner**: qidiruv (nom/tur), har element yonida ko'z — yashirish/ko'rsatish (shoxni butunlay).
- **O'ngda**: **Outliner** (model daraxti) va **xususiyatlar muharriri** — vertikal ikonkalar:
  ▣ element xususiyatlari · ≣ qatlamlar/ko'rinishlar · ⑂ versiyalar · ✓ tasdiqlash · ⚑ issue lar ·
  ≈ simulyatsiya/CFD · ◉ monitoring · ⊠ tekshiruv (to'qnashuv, hajm-miqdor).
- **Navigatsiya gizmosi** (o'ng yuqorida): X/Y/Z o'qlari kamera bilan aylanadi, o'qni bosing — shu tomondan ko'rinish.
- Tanlangan element **to'q sariq** (Blender kabi).

### Yangi element yaratish (Blender/3ds Max kabi)
`Shift+A` yoki **Qo'shish** menyusi: primitivlar (kub, silindr, sfera, konus, plita) va **GES inshootlari**
(to'g'on — trapetsiya profil, bosimli quvur, turbina agregati, suv tashlagich, mashina zali, transformator,
suv qabul qilgich). Tanlagach sharpa kursor ostida model yuzasi/yer bo'ylab yuradi — **chap tugma** bilan qo'ying
(`Esc` — bekor). Keyin: `G` surish · `R` burish (vertikal o'q) · `S` masshtab (gizmo), `Shift+D` nusxa, `X` o'chirish.
O'ng panelda **Qoralama obyekt**: nom, o'lchamlar (geometriya qayta quriladi), joylashuv (IFC koordinatalar),
`Pset_GES_*` (balandlik, gerb belgisi, **beton klassi**, po'lat markasi, quvvat…). Outliner da «Qoralama» ro'yxati
(ko'z, o'chirish). Qoralamalar serverda saqlanadi (muhandis/tasdiqlovchi) va **«IFC ga qo'shish»** tugmasi bilan
IFC ga yoziladi — yangi versiya (commit) yaratiladi, tarix saqlanadi; elementlar IfcWall/IfcPipeSegment/
IfcFlowMovingDevice/IfcSlab… sifatida Pset lar bilan kiradi va keyingi simulyatsiyalarga («Modeldan») uzatiladi.

### Mavjud elementni tahrirlash / o'chirish
Modeldagi istalgan elementni (to'g'on, agregat, relyef…) tanlab **`Tab`** (yoki Xususiyatlar → **Tahrirlash**,
Tahrir menyusi) — element **tahrirlanadigan qoralamaga** aylanadi (Blender «edit mode» kabi): geometriyasi
modeldan olinadi, asli yashiriladi, so'ng `G`/`R`/`S` bilan surish/burish/masshtab, o'ng panelda nom va **barcha
Pset lari** erkin tahrirlanadi. **`X`** — o'chirish belgisi (element darhol yashiriladi, Outliner da ustidan
chizilgan holda turadi). Bir nechta element tanlab `Tab`/`X` — hammasi. **«IFC ga qo'shish»** (commit) yangi
versiya yaratadi: tahrirlangan element **xuddi shu GUID**, IFC klassi, konteyneri (qavat/maydon), turi va
asl Pset lari (web dagilar ustidan) hamda rangi bilan yoziladi — versiyalar farqida «o'zgargan», o'chirilganlar
«o'chgan» bo'lib chiqadi. Qoralama ro'yxatidagi ↻ (yoki paneldagi «Bekor qilish») — tahrir/o'chirish bekor,
asl element qaytadi. Tahrirlanayotgan obyekt sariq-jigarrang tusda; tanlangan qoralama to'q sariq tusda.
`Ctrl` bosib turib gizmo bilan ishlasangiz — qadam bilan (1 m, 15°, 0.1). **Massiv** (qoralama panelida) — n ta
nusxa qadam bilan X/Y o'qi bo'ylab (masalan `4, 20, x` — 4 agregat 20 m oralig'ida). **Guruh**: `Shift`+bosish
(3D da yoki Qoralama ro'yxatida) — bir nechta obyekt gizmo bilan birga suriladi/buriladi (asosiy obyekt atrofida).
**`Ctrl+Z` / `Ctrl+Shift+Z`** — bekor qilish / qaytarish (surish, o'lchamlar, nom, Pset, o'chirish, qo'shish;
guruh amali bitta qadam). **`L`** — element nomlari 3D da (yorliqlar).

### Tezkor tugmalar
`Tab` elementni tahrirlash · `X` elementni o'chirish · `Ctrl`+gizmo qadam bilan ·
`H` yashirish · `Alt+H` hammasini ko'rsatish · `/` ajratish (local view) · `Home` hammasiga moslash ·
`.` tanlanganga moslash · `1` `3` `7` old/o'ng/tepa (`Ctrl` bilan qarama-qarshi) · `5` perspektiva/orto ·
`Z` shading almashtirish · `B` kesim qutisi · `N` yon panel · `T` asboblar · `F2` ko'rinishni saqlash ·
`F12` render · `?` qisqa yo'riqnoma · `Esc` bekor.

### Sichqoncha (AutoCAD kabi)
- **Chap tugma** — elementni tanlash (Xususiyatlar panelida Pset lar ko'rinadi); **ikki marta bosish** —
  aylantirish markazi shu nuqtaga (Blender «orbit around selection»); **chap tugma bilan tortish** — to'rtburchak
  tanlash (AutoCAD: chapdan o'ngga — to'liq ichidagilar, o'ngdan chapga — kesib o'tganlar ham; `Shift` — qo'shish)
- **O'rta tugma** — surish (pan); **Shift + o'rta** — aylantirish (orbit); **O'ng tugma** — aylantirish
- **G'ildirak** — masshtab (kursor tomon)

### Buyruqlar qatori (pastda)
Yozishni boshlasangiz fokus avtomatik buyruqlar qatoriga o'tadi. Enter — bajarish, bo'sh Enter — oxirgisini takrorlash, ↑/↓ — tarix, Tab — to'ldirish, Esc — bekor.

| Buyruq | Qisqa | Vazifa |
|---|---|---|
| `ZOOM E` / `ZOOM S` | `Z` | hammasi / tanlangan |
| `HIDE` | `H` | tanlanganni yashirish |
| `ISOLATE` | `ISO`, `I` | faqat tanlanganni qoldirish |
| `SHOWALL` | `SA` | hammasini ko'rsatish |
| `MEASURE` | `DIST`, `DI` | masofa o'lchash (ikki nuqta) |
| `SECTION` | `SEC` | kesim tekisligi (yuzaga bosing) |
| `FIND matn` | `F` | nomi bo'yicha qidirib tanlash |
| `SELECT guid` | `SEL` | GUID bo'yicha tanlash |
| `VIEW TOP/FRONT/ISO/…` | `V` | standart ko'rinish |
| `VSAVE nom` / `VIEW nom` | `VS` | ko'rinishni saqlash / ochish |
| `PROJ` | `P` | perspektiva ⇄ ortografik |
| `CLEAR` | `CL` | o'lchov va kesimlarni tozalash |
| `LAYER`, `PROPS`, `TREE` | `LA`, `PR`, `T` | panellar |
| `DIFF` | `D` | oldingi versiya bilan farq |
| `ISSUE` | `IS` | joriy ko'rinishdan issue |
| `SIM`, `CFD`, `MON` | | simulyatsiya / CFD / monitoring |
| `CLASH`, `QTO` | `CHECK`, `BOQ` | to'qnashuvlar / hajm-miqdor (Tekshiruv paneli) |
| `HELP` | `?` | ro'yxat |

### Qatlamlar
IFC kategoriyalari (Devor, Plita, Quvur, Turbina…) — yoqish/o'chirish. Shu tabda **saqlangan ko'rinishlar**.

### Tayyor raqamli egizak (haqiqiy GES presetlari)
Loyiha sahifasida **«Tayyor egizak…»** → Chorvoq GES (O'zbekiston) yoki Hoover Dam (AQSh): bir bosishda model
(vodiy relyefi, to'g'on kesimi va bermalari, suv qabul minorasi, bosimli tunnellar, mashina zali, agregatlar,
generatorlar, transformatorlar, suv tashlagich va darvozalar, OPU) — har element IFC klass va `Pset_GES_*` bilan,
**maydon pasporti** ochiq manbalardagi ma'lumotlar bilan to'ldiriladi (NPU/FPU/o'lik sath, sig'im egri chizig'i,
toshqin sarflari, seysmiklik…), Chorvoq uchun Wikimedia Commons fotosi (CC BY-SA) fon sifatida. Shundan keyin
barcha simulyatsiyalar «Modeldan» va «pasport» bilan tayyor: to'liq suv (viewport «Suv» tugmasi — NPU sathi),
toshqin, zilzila, gidrozarba, yoriq va h.k. Manbalar versiya izohida.
**«Namunaviy GES maketi»** — o'quv sxemasi («GES ichki ko'rinishi») bo'yicha ixcham stansiya: 1 suv ombori,
2 suv qabul qilish inshooti, 3 egri bosh quvur, 4 turbina, 5 generator, 6 chiqarish quvuri, 7 transformatorlar
va OPU, 8 boshqaruv xonasi, 9 daryo oqimi (tailrace), ko'prik kran, darvozali suv tashlagich; mashina zali yarim
shaffof (kesim ko'rinishi). Sinov ssenariylari: «Zilzila ta'siri» (MSK-64 9 ball → PGA 0.4 g) → «To'g'on
barqarorligi» (k_h zilziladan), «Suv toshqini» (boshlang'ich sath FPU, tekshiruv toshqini, darvozalar 0–100 %).

### Suv — relyefga moslashadi
Suv yuzasi tekis to'rtburchak emas: server model ustki yuzasining **balandlik xaritasini** hisoblaydi
(relyef + to'g'on + binolar), web esa suvni faqat sathdan past, **bog'langan** kataklarga chizadi (Blender
«shrinkwrap» kabi): ombor qirg'og'i tabiiy, to'g'on to'sadi, sath gerbdan oshsa suv o'zi quyi byefga o'tadi va
relyef bo'ylab yoyiladi; rang chuqurlikka qarab; to'lqinlar (ko'chki — o'sish balandligiga, toshqin — kuchliroq);
gerb/suv tashlagichdan **oqim pardasi** (harakatlanuvchi chiziqlar). Viewport «Suv» tugmasi — NPU sathida ombor.

### Jonli suv (sayoz suv gidrodinamikasi)
Toshqin, yog'ingarchilik va ko'chki natijalarida **«Jonli suv (oqim)»**: relyef + inshootlar balandlik xaritasida
sayoz suv modeli (virtual quvurlar usuli, Mei 2007) real vaqtda hisoblanadi — toshqin to'lqini vodiy bo'ylab
yuradi, suv gerbdan oshadi, **yorilish** bo'lsa to'g'on kesilib suv otilib chiqadi va quyi byefni bosadi, ko'chki
impulsi to'lqin bo'lib to'g'onga uriladi va qaytadi. Ombor sathi Puls hisobi (level) bo'yicha boshqariladi
(modeldagi vodiy haqiqiy omborning bir qismi), inshoot chiqimi (suv tashlagich/turbina) quyi byefga o'tkaziladi,
quyi chegara ochiq. 1 soat = 3 s (toshqin), ko'chki — 4× tezlashtirilgan. Bu ko'rgazmali gidrodinamika: chuqurlik
va oqim yo'nalishi sayoz suv taxminida, CFD emas.

**Toshqin xaritasi.** Jonli suv ishlayotganda (yoki to'xtatilgach) **«Toshqin xaritasi»**: har katakda yig'ilgan
maksimal chuqurlik, tezlik va **h·v** (chuqurlik × tezlik) bo'yicha relyef ustida rangli qatlam — xavf sinflari
AIDR (2017)/NZ ko'rsatmalari: sariq — past (h·v < 0.3), to'q sariq — o'rtacha (odam yiqiladi), qizil — yuqori
(mashina oqadi), to'q qizil — o'ta yuqori (binolar buziladi). Xulosa: ombor tashqarisida suv bosgan maydon (ga),
maks. chuqurlik/tezlik, suvning quyi chegaraga yetib kelish vaqti, sinflar bo'yicha maydonlar va **suv bosgan
inshootlar** ro'yxati (chuqurlik, kelish vaqti, xavf; bosilsa 3D da tanlanadi) — **CSV** ga yuklab olinadi,
**Issue** — suv bosgan inshootlar bo'yicha BCF issue (joriy ko'rinish + elementlar, tavsifda ro'yxat) tasdiqlash
oqimiga kiradi.

### Yerga o'tqazish (shrinkwrap)
Qoralama obyekt xususiyatlarida **«Yerga»** — obyekt tubi balandlik xaritasi bo'yicha relyef/inshoot yuzasiga
tushadi (Blender «shrinkwrap»/«snap to surface» kabi).

### Haqiqiy relyef (DEM)
Versiyalar → **«Relyef (DEM)»**: markaz lat/lon, maydon (X — to'g'on gerbi yo'nalishi, Y — daryo), burilish, zoom
(12 ≈ 30 m, 13 ≈ 15 m, 14 ≈ 7 m) → AWS Terrain Tiles (SRTM/ASTER) dan relyef yuzasi, parametrik «Relyef (vodiy)»
o'rniga yangi versiya (internet kerak, plitkalar keshlanadi). Haqiqiy to'g'on o'rniga moslash — markaz va burilishni
DEM ga qarab tanlang (Chorvoq ≈ 41.622, 69.981).

### Rasm asosi (foto/chizma ustidan chizish)
Outliner → **Rasm asosi → Rasm qo'shish**: foto, skanerlangan chizma yoki sun'iy yo'ldosh surati 3D da tekislik
bo'lib qo'yiladi (AutoCAD «Attach image» kabi). Kengligini haqiqiy o'lchamga (masalan to'g'on uzunligi)
moslang, joylashuv (X, Y, Z), burish, shaffoflik; «vertikal» — fasad/kesim rasmi. So'ng ustidan **Shift+A**
bilan elementlar (to'g'on, quvur, mashina zali…) qo'yiladi — rasmdan raqamli egizak. Bir modelda bir nechta
rasm bo'lishi mumkin (plan + kesimlar); ko'rinishni ko'z belgisi bilan o'chirasiz.

### Boshqa dasturlardan fayllar (Blender, 3ds Max, AutoCAD)
«Yangi versiya yuklash» IFC dan tashqari quyidagilarni qabul qiladi (server IFC ga aylantiradi, yangi versiya):

| Format | Qanday |
|---|---|
| OBJ (+MTL rang — ZIP qilib), STL, PLY, glTF/GLB, DAE, 3MF, OFF, DXF (3D yuzalar), ZIP | to'g'ridan-to'g'ri |
| FBX, 3DS, LWO/LWS, X, ASE, AC, MS3D, COB, OGEX, B3D, MD2/3/5, SMD, NFF, AMF, IRRMESH, X3D | Assimp (serverda `assimp-py`, konverter shart emas): obyekt nomlari (Blender/3ds Max tugun daraxti), materiallar rangi; FBX/X/DAE Y-up avto |
| STEP, IGES, BREP (SolidWorks, Inventor, Catia, FreeCAD) | OpenCASCADE (`cadquery-ocp`, Docker obrazida bor): har jism alohida, yig'ma nomi/rangi (XCAF), mm |
| Rasm: PNG/JPG/TIFF | **Rasmdan raqamli egizak** — rejimlar: *chizma* (skanerlangan plan/kesim: qora chiziqlar konturlarga ajratilib berilgan balandlikka ko'tariladi — devor/to'g'on konturi, har kontur alohida element), *balandlik xaritasi* (DEM/kulrang: yorug'lik → balandlik, relyef yuzasi), *foto* (taxminiy relyef). Masshtab — rasm kengligi metrda |
| DWG, DXF | DWG uchun serverda LibreDWG `dwg2dxf` yoki ODA File Converter kerak (Docker obrazida bor; Windows — `~/Tools/libredwg`, admin qo'llanmasi). 3D yuzalar (3DFACE/MESH) element bo'ladi. **Oddiy 2D chizma** (plan/kesim) AutoCAD dagidek chiqadi: bloklar, o'lchamlar, chiqish yozuvlari, matn (harf konturlari), shtrixlar, ranglar — qatlam (va rang) bo'yicha elementlar, varaq avtomatik yuqoridan (plan) ko'rinadi; birlik: `$INSUNITS`=mm bo'lsa-yu chizma 200 mm dan kichik bo'lsa metr deb olinadi; geodezik koordinatalar (0,0) ga ko'chiriladi (asl siljish `Pset_GES_Import`). Yopiq konturlarni «balandlikka ko'tarish, m» bilan devor/plita qilish mumkin; 3DSOLID jismlar o'qilmaydi — MESH ga aylantiring yoki FBX/OBJ; varaq maketlari (layout) va rasm/OLE kirmaydi |
| .blend | serverda Blender bo'lsa (`WITH_BLENDER=1` bilan qurilgan obraz) yoki **Blender addoni** orqali |
| .max | yopiq format — 3ds Max dan FBX/glTF/OBJ ga eksport qiling |

Har obyekt — alohida element: **nomi va rangi saqlanadi**; obyekt nomida `togon/dam`, `penstock/quvur`, `turbina`,
`spillway`, `transformator`, `mashina/powerhouse`, `wall/devor`, `slab/plita`, `column/ustun`, `beam/balka`
bo'lsa GES turi (IFC klass + `Pset_GES_*`, o'lchamlardan balandlik/uzunlik) avtomatik. Birlik glTF (metr) va DXF
(`$INSUNITS`) dan avto aniqlanadi, boshqalarida siz ko'rsatasiz; «Y yuqoriga», «bitta elementga birlashtirish»,
«joriy model ustiga qo'shish». **Teskari yo'l**: versiya yonidagi «glb» — Blender/3ds Max da ochish uchun
(nom va GUID saqlanadi). **Blender addoni** (`desktop/blender/`): «Sath ga yuborish / dan olish» tugmalari.
Desktop Sath (FreeCAD yadrosi): DWG uchun paket ichida LibreDWG (`tools/libredwg/dwg2dxf.exe`) keladi va dastur
ochilganda o'zi sozlanadi (Edit → Preferences → Import/Export → DWG). Bo'lmasa `~/Tools/libredwg` ga LibreDWG yoki ODA
File Converter o'rnating — qayta ochganda o'zi topadi. DWG/DXF **AutoCAD dagidek va tahrirlanadigan** holda ochiladi
(sukut — «tahrirlash» rejimi): har element alohida obyekt — chiziq/polilinya/yoy/aylana (Draft), ellips/spline (Part
egri), **matn** (Draft Text — matni, balandligi, burilishi tahrirlanadi), **o'lchamlar** (Draft Dimension — qiymati
AutoCAD dagidek, `Override` da; nuqtalarini siljitsangiz qayta hisoblatish uchun Override ni bo'shating), chiqish
yozuvlari, shtrixlar (bitta obyekt), bloklar (portlatilgan, obyekt nomida blok nomi), qatlamlar (Draft Layer — rang,
chiziq turi, ko'rinishni o'chirish), har element o'z rangida. Menyu Sath → «DWG/DXF ochish rejimi» bilan «ko'rish»
rejimiga o'tish mumkin (qatlam+rang bo'yicha bitta shakl — 50 000+ elementli chizmalar uchun tez, tahrirlanmaydi).
Kirmaydi: rasm/OLE, varaq maketlari (layout — faqat model fazosi). Ko'rinish: View → Top (2), Fit (V, F).

## 4. Versiyalar va tasdiqlash

1. **Muhandis**: Versiyalar → «Yangi versiya yuklash» → IFC fayl + izoh («nima o'zgardi»).
2. Versiyani ochib, **Tasdiqlash** tabida «vN ni tasdiqqa yuborish» — sarlavha, tavsif.
3. **Tasdiqlovchi**: so'rovni ochadi, «Ota bilan farq» (Versiyalar tabida) — yashil qo'shilgan, sariq o'zgargan, qizil o'chirilgan; issue ochadi; keyin **Ma'qullash** yoki **O'zgartirish so'rash**.
4. O'zgartirish so'ralsa muhandis yangi versiya yuklab, so'rovga bog'laydi («Yangi versiyani bog'lash»).
5. Ma'qullangach tasdiqlovchi **Tasdiqlash (published)** — versiya joriy bo'ladi, avvalgisi arxivga.

Har qadam audit jurnaliga yoziladi; tasdiqlovchi/muallifga qo'ng'iroq (va email) xabari boradi.

- **Qayta tiklash** — eski versiyani ochib «Qayta tiklash»: uning fayli bilan yangi (oxirgi) versiya
  yaratiladi (git revert kabi), tarix o'chmaydi.
- **Izoh/yorliq** — izohni muallif/tasdiqlovchi o'zgartiradi; **yorliq** (teg, masalan `EKSPERTIZA-1`)
  tasdiqlovchi qo'yadi — ro'yxatda 🏷 bilan ko'rinadi.
- Istalgan ikki versiyani solishtirish — «Solishtirish…» ro'yxati.

Tasdiqlash so'rovi kartasida **Xavfsizlik** qatori: shu versiya uchun standart ssenariylar bali (yoki «Tekshirish»
tugmasi); ma'qullashda tekshirilmagan yoki mezon bajarilmagan versiya uchun ogohlantirish so'raladi.

## 5. Issue lar (BCF)

Elementni tanlab, kamerani sozlab **Issue** → «Issue ochish». Kamera, tanlangan elementlar va kesimlar
saqlanadi — «Ko'rinishga o'tish» bilan hamma xuddi shu holatga qaytadi. Ijrochi, muhimlik, holat, izohlar.
**BCF eksport/import** — Revit, ArchiCAD, BIMcollab, Solibri bilan almashish (`.bcfzip`).

### Tekshiruv (BIM nazorati)
**To'qnashuvlar (clash detection)** — versiyadagi barcha elementlar juftliklari: *to'qnashuv* (sirtlar
kesishadi, masalan quvur devorni teshib o'tadi), *ehtimoliy* (ichma-ich), *tegib turadi* (normal).
Ro'yxatdan tanlang — ikkalasi 3D da qizil/sariq ajratiladi; «Issue ochish» shu ko'rinish bilan issue yaratadi.
**Hajm-miqdor (QTO)** — har element hajmi (m³), sirti, o'lchamlari; tur va qavat bo'yicha jamlanma; CSV.
Ikkalasi yuklashdan keyin fonda hisoblanadi (katta modelda birinchi ochilishda kutish mumkin).

## 6. Simulyatsiya

Simulyatsiya paneli — **katalog** (guruhlar bo'yicha kartochkalar). Katalog tepasida **Xavfsizlik tekshiruvi**:
«Tekshirish» — 12 standart ssenariy bir bosishda (loyihaviy va tekshiruv toshqini, N−1 darvoza, darvozalar yopiq,
zilzila, to'g'on barqarorligi statik/zilzila/FPU, filtratsiya, yoriq, gidrozarba, ko'chki) pasport + model
qiymatlari bilan; har ssenariy ok / ogohlantirish / bajarilmadi (mezonlar: zaxira ≥ 1 m loyihaviy, gerbdan
oshmaslik, K ≥ 1.5 / 1.3 / 1.1, suffoziya ≥ 1.5, quvur ≥ 1.5), umumiy ball, natijani ochish (hisob «Oldingi
hisoblar» ga saqlanadi), **Hisobot** (chop etish), **Issue ochish** (bajarilmagan mezonlar bo'yicha). Har simulyatsiya formasi
**maydon pasportidan** avtomatik to'ldiriladi (`pasport` belgisi), «Modeldan» (IFC Pset_GES + 3D qoralamalar)
va «Jonli holatdan» (SCADA: sath, sarf, quvvat) tugmalari bilan yangilanadi. Natija: xulosa (yashil/qizil),
asosiy ko'rsatkichlar, grafiklar, kitob ikonkasi — formulalar va manbalar. Forma ostida **Sezgirlik tahlili** — bitta parametrni oraliqda (n nuqta) o'zgartirib, xulosa ko'rsatkichlari grafigi
(masalan yuqori byef sathi → ag'darilish/sirpanish zaxirasi) va mezon buziladigan chegara; ish saqlanmaydi.
**Hisobot** — chop etish/PDF (xulosa, ko'rsatkichlar, kirish parametrlari manbasi bilan, grafiklar, formulalar). **Solishtirish…** — shu turdagi
boshqa hisobni tanlang: ko'rsatkichlar jadvali (ikkalasi va farqi), qaysi parametrlar farq qilgani, grafiklarda
ikkinchi ssenariy punktir chiziq bilan. **3D vizual** (natija ochilganda):
suv sathi tekisligi (vaqt kursori bilan), elementlar yashil/qizil; **yoriq xavfi xaritasi** to'g'on yuzasida
(ko'k → sariq → qizil: balandlik bo'yicha cho'zilish, abutment/gerb konsentratsiyasi, issiqlik); **gidrozarba
to'lqini** — quvur bo'ylab napor kadrlari rangli tasma bo'lib aylanadi («Gidrozarba to'lqini» tugmasi);
**zilzila** — «Zilzilani ko'rsatish»: model PGA va davr bo'yicha silkitiladi (ko'rinish uchun kattalashtirilgan);
**to'g'on barqarorligi** — «Kuchlar sxemasi»: to'g'on kesimida hisob profili (to'q sariq), kuchlar strelkalar va
yorliqlar bilan (og'irlik W, gidrostatik P, filtratsion U, loyqa, muz, zilzila), h₁/h₂ sathlari; **filtratsiya** —
«Depressiya egri chizig'i»: Dyupyui egri chizig'i to'g'on tanasida ko'k yuza; **loyqa bosishi** — yil kursori
bilan ombor tubidagi cho'kindi qatlami (jigarrang, relyefga moslashgan; yo'qotilgan sig'im pasport sath–hajm
egri chizig'i orqali belgiga aylantiriladi), ustida NPU suvi;
**toshqin** — quyi byef suv tekisligi (Manning chuqurligi) yuqori byef bilan birga vaqt bo'yicha;
**dispetcherlik** — agregatlar yuklanish foiziga qarab bo'yaladi.

| Guruh | Simulyatsiya | Nima hisoblaydi (asosiy formulalar) |
|---|---|---|
| Gidrologiya | **Suv ombori rejimi va energiya** | balans, quvur, turbinalar, ish rejimlari (quyida) |
| Gidravlika | **Gidravlik zarba** | MOC (Wylie–Streeter), Jukovskiy/Misho, Korteweg to'lqin tezligi, halqa kuchlanish σ=pD/2e, kavitatsiya |
| Gidravlika | **Bosim tenglashtiruvchi minora** | massa tebranishi (RK4), Toma sharti, toshish/havo tortish |
| Gidravlika | **Agregat–regulyator dinamikasi** | HYGOV (IEEE 1207): yuk qadam / yuk tashlash / setpoint — chastota, gate, barqarorlik, Hovey tavsiyasi |
| Gidravlika | **CFD (OpenFOAM)** | quyida |
| Mustahkamlik | **To'g'on barqarorligi** | og'irlik, gidrostatik, filtratsion (USACE drenaj), loyqa, muz, Westergaard → K_ag'darilish, K_sirpanish, tag kuchlanishlari; sath va k_h bo'yicha skan |
| Mustahkamlik | **Yorilish xavfi** | gravitatsion usul (balandlik bo'yicha σ), cho'zilish/yoriq zonalari, toe ezilishi, issiqlik yorilishi indeksi (ΔT_ad = q·C, σ_T = K_R·E·α·ΔT), tuproq to'g'onda gidravlik yorilish va cho'kish yoriqlari, **moyil joylar ro'yxati**, beton klassi tavsiyasi |
| Mustahkamlik | **Filtratsiya / suffoziya** | Darsi, Lane C_w, Xosla chiqish gradiyenti, Dyupyui depressiya, K_suffoziya |
| Mustahkamlik | **Qaysi to'g'on turi mos?** | asos, dara L/H, balandlik, seysmiklik, materiallar → 6 tur reytingi, qachon yaxshi/yomon, yoriqlarga moyil joylar |
| Favqulodda | **Zilzila ta'siri** | KMK 2.01.03 ball → PGA, EC8 spektr, Chopra davri, k_h = A·β·K₁, Westergaard |
| Favqulodda | **Yog'ingarchilik → toshqin** | SCS-CN oqim (yer qoplami, grunt guruhi, AMC), Kirpich t_c, SCS birlik gidrografi, qor erishi, **GLOF** → ombor orqali o'tkazish |
| Favqulodda | **Suv toshqini / yorilish** | Puls routing, suv tashlagich/darvoza, gerbdan oshish, Froehlich yorilish, Muskingum, Manning chuqurlik |
| Favqulodda | **Tog' ko'chishi → to'lqin** | Heller–Hager impuls to'lqin, tarqalish, to'g'onga chiqish R, gerbdan oshish |
| Ekspluatatsiya | **Loyqa bosishi** | Brune/Gill ushlab qolish, o'lik hajm to'lish yili |
| Ekspluatatsiya | **Optimal yuk taqsimoti** | DP (FIK egri chiziqlari): minimal suv sarfi, kunlik jadval |
| Maxsus | **Formulali simulyatsiya** | o'z tenglamalaringiz (kirishlar, holat, qadam, chiqishlar, tekshiruvlar), shablon sifatida saqlash |

**Maxsus simulyatsiya**: ifodalar Python sintaksisida (`+ − * / **`, `a if shart else b`, `min max sqrt exp log
interp clip mean sum last`), o'zgaruvchilar `t dt i g rho pi`; «Sinov» — saqlamasdan, «Shablonni saqlash» —
loyiha uchun (muhandis), «Hisoblash» — natija versiyaga bog'lanadi.

**Suv ombori / energiya**: kiruvchi gidrograf (doimiy yoki qadamma-qadam qiymatlar) → suv ombori balansi
(sath–hajm jadvali, o'lik sath, NPU, FPU, suv tashlagich, bug'lanish) → quvur yo'qotishlari → agregatlar
(Francis/Kaplan/Pelton, FIK egri chizig'i, avtomatik agregat soni). Ish rejimlari: sathni ushlab turish,
maksimal quvvat, oqim bo'yicha, doimiy sarf, berilgan quvvat.
«Modeldan olish» — agregat/quvur/suv tashlagich parametrlari IFC dagi `Pset_GES_*` dan.
Natija: energiya (MWh), o'rtacha quvvat, foydalanish koeffitsienti, sath/sarf/quvvat grafiklari,
vaqt slayderi bilan **3D da suv sathi** («Model 0 belgisi» — IFC z=0 ning absolyut belgisi).

**CFD oqim (OpenFOAM)**: bosimli quvur (napor yo'qotishi, tezlik profili), suv tashlagich
(erkin sirt, ostona ustidagi chuqurlik) yoki **model geometriyasi** — 3D da tanlangan element(lar)
atrofida suv oqimi (snappyHexMesh + simpleFoam): gidrodinamik kuch, sirtdagi bosim, tezlik maydoni.
3D da elementni tanlab «Modeldan olish», «Hisoblash».
Natija: xulosa, grafiklar, 2D maydon xaritasi va 3D da elementga qo'yilgan maydon tekisligi.
Aniqlik 1 — daqiqalar; 2 — o'n daqiqalar.

## 7. Monitoring (digital twin)

3D da «qiymatlar 3D da» — sensor bog'langan elementlar ustida jonli qiymat yorliqlari (nom, qiymat, alarm rangi);
«sog'liq rangi» — aktivlar sog'liq indeksi bo'yicha bo'yash. **«animatsiya»** — 3D HMI: `position` (darvoza/zatvor
ochilishi, %) sensori bog'langan element ochilish foizi bo'yicha ko'tariladi; `status`/`power` — agregat ustida
aylanuvchi halqa (ishlayapti — yashil); `flow` — quvur/kanal bo'ylab harakatlanuvchi punktir (yo'nalish va tezlik
sarfga qarab); `level` — suv tekisligi (yuqori byef). **«vaqt mashinasi»** — tarixdagi istalgan vaqt (6 soat … 30 kun)
slayder bilan: yorliqlar, ranglar, suv sathi, darvozalar, agregatlar o'sha vaqtdagi o'qishlar bo'yicha (hodisa
tahlili). **CSV import** — SCADA teglar ro'yxati (`key;name;kind;unit;protocol;address;element;low;high`): sensorlar
yaratiladi/yangilanadi, `element` (IFC nomi yoki GUID) bo'yicha 3D ga avtomatik bog'lanadi.
**BIM ⇄ SCADA**: 3D da sensor bog'langan elementni bossangiz — uning sensori ochiladi (trend, alarm chegaralari)
va `writable` bo'lsa **boshqaruv**: darvoza ochilishi slayder / agregat ishga tushirish–to'xtatish / qiymat →
«Buyruq yuborish» (supervisory control: pending → sent → acked, audit). Dispetcher panelidagi alarm jurnalida
**«3D»** havolasi — modelni shu element tanlangan va Monitoring paneli ochiq holda ochadi
(`/models/{id}?sel=<GUID>&tab=mon`).
**Sensor qo'shish** — SCADA teg nomi (kalit), turi, birlik, alarm chegaralari; 3D da elementni tanlab
bog'lang. Qiymatlar jonli keladi (WebSocket), elementlar rangi: yashil normal, qizil alarm, kulrang uzilgan.
Sensorni bosing — tarix grafigi (1 soat … 1 oy), «Qo'lda yuborish», CSV import.
Tasdiqlovchi «Ulanish kaliti» beradi — SCADA tomonidagi gateway (`deploy/gateway`) shu kalit bilan yuboradi.

### Dispetcher paneli (SCADA)
Loyiha sahifasida **«Dispetcher paneli»** (yoki menyu Fayl → Dispetcher paneli):
- **Mimik sxema** — suv ombori → to'g'on/suv tashlagich → bosimli quvur → mashina zali (agregatlar) →
  quyi byef; slotlarga sensorlar avtomatik (nom/kalit bo'yicha) bog'lanadi, «Sxemani sozlash» bilan qo'lda.
  Agregat aylanadi (quvvat > 0), alarm — qizil/sariq ramka.
- **KPI**: faol alarmlar, 24 soatlik energiya (quvvat sensorlaridan), umumiy quvvat, sensorlar holati.
- **Trendlar** — bir nechta sensor, 1 soat … 30 kun (uzoq davr soatlik agregatdan), CSV.
- **Alarm jurnali** — har hodisa (past/yuqori/aloqa yo'q) boshlanish–tugash vaqti bilan; **Kvitlash**
  (muhandis/tasdiqlovchi, izoh bilan), «Hammasini kvitlash», 7 kunlik tarix.
- **Hisobot** — kun/hafta/oy: har sensor o'rtacha/min/max, energiya MWh, alarmlar; CSV (Excel).
- Yangi alarm — ekranda qizil chiziq, **qo'ng'iroq** (yuqori o'ngda) va email (sozlangan bo'lsa).

Panel bo'limlari: **Sxema** · **Trendlar / Hisobot** · **Raqamli egizak** · **Aktivlar** · **Boshqaruv** · **Smena jurnali**.
Alarm ustuvorligi (sensor sozlamasida): *muhim* va *kritik* — ekranda belgi va **ovoz** (🔔 tugmasi o'chiradi).

### Raqamli egizak (digital twin)
Jonli SCADA holati BIM modeli bilan solishtiriladi: yuqori/quyi byef sathi → brutto napor, quvur sarfi →
agregatlar, tasdiqlangan versiyadagi `Pset_GES_Turbine`/`Pset_GES_Penstock` (turbina FIK egri chizig'i,
quvur yo'qotishi) → **kutilgan quvvat**; o'lchangan quvvat bilan **og'ish %** va **haqiqiy FIK**.
Natijalar virtual sensorlarga yoziladi (`TWIN.*.P_EXP`, `.DEV`, `.EFF`) — og'ish ±10 % dan oshsa alarm,
tarix va trendlar oddiy sensor kabi. 3D da: Monitoring panelida **jonli suv sathi** tekisligi (yuqori byef
sensoridan); Simulyatsiya panelida **«Jonli holatdan»** — joriy sath/sarf bilan «nima bo'lsa» ssenariysi.

### Holat monitoringi (Sog'liq)
Dispetcher panelida **Sog'liq** bo'limi: har agregat uchun **sog'liq indeksi 0–100** — tebranish zonasi
(ISO 20816-5: A/B/C/D, mashina guruhi bo'yicha 1.6/2.5/4.0 yoki 2.5/4.0/6.4 mm/s), podshipnik harorati
(ogohlantirish/alarm), **30 kunlik trend** → C/D zonaga yoki alarm chegarasiga qolgan kunlar (RUL), **anomaliya**
(z-score > 3), egizakdan FIK og'ishi va trendi, **kavitatsiya** (Toma σ_plant vs σ_kritik — rpm va runner belgisi
kiritilganda), texnik xizmat muddati; muammolar va tavsiyalar. Sozlamalar — kartadagi tishli tugma (sensorlar,
guruh, chegaralar). Indeks har soat `HEALTH.<aktiv>` virtual sensoriga yoziladi (trend, alarm < 60).

### Optimal rejim va «nima bo'lsa»
**Bugungi optimal rejim** — jonli napor va joriy umumiy quvvat uchun agregatlar yuk taqsimoti (minimal suv
sarfi; model `Pset_GES_Turbine` kerak). **«Nima bo'lsa»** — sath/sarf/quvvatni o'zgartirib egizakni,
xavfsizlik ko'rsatkichlarini va optimal taqsimotni qayta hisoblash — jonli ma'lumotga tegilmaydi (dispetcher
mashqi, rejalashtirish, buyruqni oldindan sinash).

### Toshqin prognozi
**Toshqin prognozi** bo'limi: ob-havo prognozidagi yog'in (mm, davomiylik, oldingi namlik, qor erishi, GLOF,
darvozalar holati) + jonli sath/sarf + pasport (havza CN, ombor, suv tashlagich) → 3–5 kunlik sath prognozi,
gerbdan oshish vaqti va **oldindan sath tushirish tavsiyasi** (qaysi sathga tushirilsa xavfsiz).

### Ish buyruqlari (CMMS)
**Ish buyruqlari** bo'limi: texnik xizmat/ta'mirlash vazifalari — sarlavha, aktiv, ustuvorlik, ijrochi (muhandis
tayinlaydi), muddat; holatlar *ochiq → bajarilmoqda → bajarildi/bekor*; yopishda natija, to'xtab turish soati,
xarajat. KPI: faol/muddati o'tgan, 90 kunda bajarilgan, **MTTR**, **MTBF**, to'xtab turish, xarajat.
Manbalar: qo'lda (dispetcher), **sog'liq kartasidan** (tishli/kalit tugma) va **avtomatik** — sog'liq indeksi
«yomon/kritik» bo'lsa har soat fonda buyruq yaratiladi (takrorlanmaydi), muhandislarga bildirishnoma.
3D da (Monitoring paneli, «sog'liq rangi») aktiv elementlari yashil/sariq/qizil.

### Ehtiyot qismlar
**Ehtiyot qismlar** bo'limi: ombor qoldig'i, minimal zaxira (kam bo'lsa belgi va muhandislarga bildirishnoma),
joylashuv, narx; **kirim** (muhandis) / **sarf** (dispetcher) — sarf ish buyrug'iga bog'lansa xarajat unga
avtomatik yoziladi; harakatlar tarixi.

### Elektr qism
Simulyatsiya katalogida **Transformator yuklanishi (IEC 60076-7)**: kunlik yuk va havo harorati → yuqori moy va
issiq nuqta harorati (dinamik, τ_o/τ_w), izolyatsiya qarish tezligi va umr sarfi, ortiqcha yuk chegaralari
(120/140 °C, K ≤ 1.5); generator yuklanishi (cos φ, stator harorati, reaktiv quvvat). Aktiv sozlamasida
`S_nom, cos φ` kiritilsa **Sog'liq** kartasida jonli quvvatdan transformator yuklanishi va issiq nuqta ko'rinadi.

### Tashqi ML modeli (integratsiya nuqtasi)
Tayyor ML modeli natijalarini `POST /api/projects/{id}/ml/predictions` ga yuboradi
(`{"model": "rul-v1", "predictions": [{"key": "AGG1.RUL", "name": "…", "value": 42, "unit": "kun",
"low_alarm": 30}]}`, muhandis tokeni). Har kalit `ML.<key>` **virtual sensor** (protocol `ml`) bo'ladi — oddiy
sensor kabi trend, alarm chegaralari, dashboard plitkalari, bildirishnomalar, egizak va 3D bog'lash
(`element_guid`). Shunday qilib ML alohida servis sifatida ishlaydi, Sath esa uni ko'rsatadi va nazorat qiladi.

### Maydon pasporti
Loyiha sahifasida **Maydon pasporti**: seysmiklik va grunt, asos tuprog'i, suv ombori (sathlar, hajm, sath–hajm,
toshqinlar, havza: maydon, uzunlik, nishab, yer qoplami, grunt guruhi, loyihaviy jala, muzlik ko'llari),
to'g'on (tur, o'lchamlar, beton klassi, sement), suv tashlagich, bosimli quvur (po'lat markasi), quyi byef va daryo
o'zani, **inshootlarning belgilari** (mashina zali poli, OPU, boshqaruv binosi — suv sathidan balandlik),
yonbag'irlar (ko'chki). Bir marta kiritiladi — barcha simulyatsiyalar va xavfsizlik ko'rsatkichlari shundan.
**Materiallar ma'lumotnomasi** — beton klasslari (KMK 2.03.01: R_b, R_bt, E), zonalar bo'yicha tavsiya, po'lat, grunt.

### Aktivlar
Agregat = quvvat sensori + IFC element: ish soatlari (jami/30 kun), ishga tushishlar, energiya,
mavjudlik %, texnik xizmat oralig'i (soat) → holat *normal / xizmat yaqin / muddati o'tgan*;
dispetcher «Xizmat bajarildi» (izoh bilan) — hisoblagich noldan.

### Boshqaruv (supervisory control)
Sensor sozlamasida **«Yozish mumkin (setpoint)»** belgilangan nuqtaga dispetcher buyruq yuboradi
(qiymat + sabab, tasdiqlash so'raladi). Holat: kutmoqda → yuborildi → bajarildi / xato (gateway SCADA ga
yozadi va natijani qaytaradi). Bekor qilish — faqat kutayotgan buyruq. Hammasi audit jurnalida,
tasdiqlovchiga bildirishnoma.

### Smena jurnali
Dispetcher yozuvlari: «Smena qabul», «Smena topshirish», hodisa, oddiy yozuv — vaqt va muallif bilan.

### Vaqt mashinasi
Yuqoridagi sana/vaqt maydoni — tanlangan vaqtdagi holat (sxema qiymatlari, alarm holatlari) ko'rsatiladi
(TARIX REJIMI); «Jonli» — qaytish. Kunlik hisobot email bilan ham keladi (admin sozlagan bo'lsa).

### Bildirishnomalar
Qo'ng'iroq belgisi: tasdiqlash so'rovlari va qarorlar, sizga tayinlangan issue lar, alarmlar.
Bosganda tegishli sahifaga o'tadi. Desktop da: GES → Bildirishnomalar.

## 8. Desktop — chizish

«Loyihalar» sahifasidagi **Sath x.y.z o'rnatish ↓** tugmasi bilan installer ni yuklab olib ishga
tushiring (admin huquqi shart emas — «faqat men uchun» rejimi). Portable variant: **zip ↓** — ochib
`Sath.bat`. Dastur Sath nomi bilan, qora tema, metr birliklari va **Sath** workbench bilan ochiladi:
- **Serverga ulanish** — manzil, login, parol
- **Modelni ochish** — loyiha → model → versiya (IFC yuklanib ochiladi)
- Chizish: BIM/Draft/Part workbench lar; **GES obyektlari** — To'g'on, Bosimli quvur, Turbina agregati,
  Suv tashlagich, Mashina zali, Transformator, Suv qabul qilgich (parametrlari xususiyatlar panelida; IFC ga
  `Pset_GES_*` bo'lib chiqadi — web dagi qoralama turlari bilan bir xil nomlar, simulyatsiyalar ikkalasini
  bir xil o'qiydi)
- **Commit** — IFC eksport + serverga yangi versiya (+ «Darhol tasdiqqa yuborish»)
- **Tasdiqlash so'rovlari** — ro'yxat, tafsilot; tasdiqlovchi: ma'qullash / o'zgartirish so'rash /
  tasdiqlash (merge) / rad etish — webdagi oqim bilan bir xil
- **Issue lar** — ro'yxat, ko'rinishga o'tish, yangi issue joriy kamera bilan
- **Simulyatsiya** — parametrlar «Modeldan olish» (Pset_GES), hisob serverda, natija jadvali va grafik,
  «3D: suv sathi tekisligi» — hujjatda `GES_SuvSathi` obyekti
- **Versiyalar va farq** — model versiyalari tarixi (git kabi): istalgan versiyani ochish, **ota bilan farq**
  3D da (qo'shilgan — yashil, o'zgargan — sariq, o'chirilganlar ro'yxatda), «Webda ochish»
- **Simulyatsiya katalogi** — webdagi barcha 15 simulyatsiya turi (forma maydonlari serverdan, «Pasportdan» /
  «Modeldan» to'ldirish, hisob serverda, xulosa + ko'rsatkichlar + grafik, «3D: suv sathi»), **Xavfsizlik
  tekshiruvi** (12 ssenariy, ball) — natijalar webdagi «Oldingi hisoblar» bilan umumiy
- **Monitoring (SCADA)** — jonli o'lchovlar jadvali (5 s), bog'langan obyektlar alarm rangi (yashil/qizil/kulrang),
  suv sathi sensoridan 3D tekislik, «3D da ko'rsatish» (sensor → obyekt); HMI animatsiya, vaqt mashinasi va
  boshqaruv — webda («Webda» tugmasi)
- **Webda ochish** — joriy model (tanlangan element bilan) brauzerda: `/models/{id}?v=&sel=<GUID>`
- **Bildirishnomalar** — kirishda o'qilmaganlar soni konsolda, dialogda ro'yxat
- **AutoCAD uslubi sozlamalari** — qora tema, CAD navigatsiya (o'rta tugma — pan), metr birliklar
  (o'rnatishda avtomatik qo'llangan; buzilsa shu tugma bilan qaytariladi)

FreeCAD ning barcha workbench lari (Part, PartDesign, Sketcher, Draft, BIM, FEM, TechDraw, Mesh…) to'liq mavjud —
Sath ularning ustidagi qatlam: chizilgan har qanday geometriya «Commit» da IFC ga (NativeIFC, GUID lar
saqlanadi) va serverga versiya bo'lib ketadi; webda ochilganda tahrirlangan elementlar «o'zgargan» bo'lib chiqadi.
Server yangi versiyani tarqatsa, kirishda xabar chiqadi — installer ni eskisi ustiga o'rnatasiz.
Boshqa dasturlardan fayllar: OBJ/STL/PLY/glTF/DAE/3DS/3MF (Blender, 3ds Max eksporti), STEP/IGES/DXF —
Файл → Импорт; FBX/.blend/.max ochilmaydi (glTF yoki OBJ qilib eksport qiling).
