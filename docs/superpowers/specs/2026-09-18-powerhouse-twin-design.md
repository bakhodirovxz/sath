# GES ichki egizagi (Blender desktop) — dizayn

**Maqsad.** Sath desktop (Blender) ilovasida GES ichki ko'rinishi rasmidagi 9 komponentli stansiyaning raqamli
egizagi bir tugma bilan quriladi va simulyatsiyalar shu egizak ustida timeline animatsiyasi sifatida ko'rinadi.

Komponentlar (rasm → GES obyekt turi):

| № | Rasm | Tur | IFC | Pset |
|---|---|---|---|---|
| 1 | Suv ombori | `GES_SuvSathi` tekislik (yuqori byef) | — | — |
| 2 | Suv qabul qilish | `GES_Intake` (bor) | IfcBuildingElementProxy | Pset_GES_Intake |
| 3 | Bosh quvur | `GES_Penstock` + **egri variant** (Inclination/BendAngle/BendRadius/OutletLength) | IfcPipeSegment | Pset_GES_Penstock |
| 4 | Turbina | `GES_Turbine` (bor) | IfcFlowMovingDevice | Pset_GES_Turbine |
| 5 | Generator | **`GES_Generator`** (yangi) | IfcElectricGenerator | Pset_GES_Generator |
| 6 | Chiqarish quvuri | **`GES_DraftTube`** (yangi) | IfcFlowSegment | Pset_GES_DraftTube |
| 7 | Transformatorlar | `GES_Transformer` (bor) | IfcTransformer | Pset_GES_Transformer |
| 8 | Boshqaruv xonasi | **`GES_ControlRoom`** (yangi) | IfcBuildingElementProxy | Pset_GES_ControlRoom |
| 9 | Daryo oqimi | **`GES_Tailrace`** (yangi) + `GES_QuyiByef` tekislik | IfcCivilElement | Pset_GES_Tailrace |
| — | To'g'on, tashlama, bino | `GES_Dam`, `GES_Spillway`, `GES_Powerhouse` (bor) | | |

## A. Yangi FreeCAD obyektlari (`desktop/GesWorkbench/ges_workbench/ges_objects.py` → sync `sath/wb/`)

- **Generator**: RatedPower (MVA, 30), Voltage (kV, 10.5), EfficiencyMax (0.985), IronLossFrac (0.4), Poles (24),
  Frequency (Hz, 50), StatorDiameter (m, 6), Height (m, 3.5). Shakl: stator silindr + qovurg'alar + qo'zg'atish qopqog'i +
  val. Pset: `Quvvat_MVA, Kuchlanish_kV, FIK, TemirUlushi, Qutblar, Chastota_Hz, Aylanish_rpm` (n = 120·f/p).
- **DraftTube**: InletDiameter (3), ConeHeight (5), OutletWidth (8), OutletHeight (4), DiffuserLength (12), SuctionHead
  H_s (m, +2: ish g'ildiragi quyi byefdan yuqori). Shakl: konus pastga + tirsak + gorizontal kengayuvchi diffuzor (+Y).
  Pset: `KirishDiametr_m, KonusBalandligi_m, ChiqishKenglik_m, ChiqishBalandlik_m, DiffuzorUzunligi_m, SorishBalandligi_m`.
- **ControlRoom**: Length (12), Width (8), Height (4), FloorElevation, Operators (2), ScadaChannels (256). Shakl: quti,
  old tomonida oynalar kesilgan. Pset: `Uzunlik_m, Kenglik_m, Balandlik_m, PolBelgisi_m, Dispetcherlar, SCADA_Kanallar`.
- **Tailrace**: Width (20), Length (40), Depth (6), BedSlope (0.001), Manning (0.03), BedElevation (m abs). Shakl:
  U-kanal (+Y yo'nalishda ochiq). Pset: `Kenglik_m, Uzunlik_m, Chuqurlik_m, Nishab, Manning_n, TagBelgisi_m`.
- **Penstock (egri)**: yangi xususiyatlar Inclination (°, 0), BendAngle (°, 0), BendRadius (m, 8), OutletLength (m, 6).
  Ikkalasi 0 → eski Z bo'ylab silindr (moslik). Aks holda yo'l: kirish (0,0,0) → 1-qism u1=(0, cos α, −sin α) →
  yoy R → gorizontal +Y chiqish. `makePipeShell` bilan; xato bo'lsa silindrga qaytadi.

## B. «Namuna GES» yig'uvchi (`desktop/blender/sath/demo_plant.py`, operator `sath.build_demo_plant`)

Parametrlar: napor H (m, 45), agregatlar n (1–4, 2), model 0 belgisi (abs, m). Koordinata: Y — oqim, X — ko'ndalang,
mashina zali poli z=0, quyi byef z=−2, yuqori byef z_up = H − 2, gerb z_up+3.
Joylashuv: to'g'on (uzunlik n·14+60, asos z=−10) → suv qabul minorasi yuqori yuzada → har agregat uchun egri bosh quvur
(`solve_penstock`: Δz, Δy, R, L_out → α, L1 bisection) → turbina (y_t=20, z=−2) + generator (z=2) → chiqarish quvuri
(pastga, +Y) → daryo kanali (y_t+10, tag z=−8) → mashina zali (quti) → transformatorlar (y_t+W/2+6) → boshqaruv xonasi
(zal o'ng chetida, z=10 balkon) → tashlama (to'g'on o'ng qismida, ostona z_up). Ikki suv tekisligi:
`GES_SuvSathi` (yuqori byef, faqat to'g'ondan yuqorida) va `GES_QuyiByef` (kanal ustida). Yer plitasi `GES_Yer` (IFC emas).
Har obyekt `obj.ges.role` ("unit:1", "gen:1", "draft:1", "penstock:1", "tailrace", "dam", ...) va IFC joylashuvi
(`bim.edit_object_placement`) bilan. Suv tekisliklari `sath_region` xususiyati bilan mintaqaga bog'lanadi — keyingi
sath yangilanishlarida faqat z o'zgaradi.

## C. Simulyatsiyalar egizak ustida (`sim_anim.py`, `physics.py`, `ops_sim.py`)

`physics.py` (sof Python, formulalar manbasi bilan): `manning_depth(q, b, s, n)` (bisection), `thoma_sigma(h_s, h_net)`
(σ = (H_atm − H_v − H_s)/H_net, H_atm 10.1 m, H_v 0.24 m), `sigma_critical(type, n_s)` (Francis 0.0432·(n_s/100)²,
Kaplan 0.28+(n_s/380)³, Pelton 0), `specific_speed(n_rpm, p_kw, h)`, `synchronous_rpm(f, poles)`,
`penstock_path(params, n)` (FreeCAD bilan bir xil yo'l, markerlar uchun), `spectral_displacement(sa_g, t)`
(S_d = S_a·g·(T/2π)²), `envelope(t, rise, plateau, decay)`.

1. **Hydro** (kengaytma): agregat rangi (bor) + generator rangi yuklama, transformator rangi (S/S_nom), quyi byef
   tekisligi Manning bo'yicha (Q_turbina + tashlama), chiqarish quvuri: σ_plant < σ_c → qizil (kavitatsiya), aks holda ko'k.
2. **Gidrozarba** (`water_hammer`, `sath.sim_hammer`): `profile.frames` (≤60) → bosh quvur bo'ylab `GES_Bosim.NN` markerlar
   (rang ko'k→qizil, h nisbiy), kadr = frame. Kirish: quvur Pset + napor + agregat sarfi + yopilish vaqti.
3. **Regulyator** (`governor`, `sath.sim_governor`): chastota → generator+turbina `rotation_euler.z` (n = 120f/p),
   generator rangi chastota chetlanishi (±0.2 Hz yashil, ±1 sariq, undan ortiq qizil), bosh quvur rangi flow_pu. ≤600 kadr.
4. **Transformator** (`transformer`, `sath.sim_transformer`): hot_spot_c → transformator rangi (40 ko'k → 80 yashil →
   110 sariq → 140 qizil). ≤720 kadr.
5. **Zilzila** (`seismic`, `sath.sim_seismic`): har inshoot uchun S_a, T → u(t)=S_d·env(t)·sin(2πt/T) (×20 vizual
   ko'paytirgich), to'g'on/zal/quvur `location` keyframe; rang k_h bo'yicha (<0.1 yashil, <0.2 sariq, ≥ qizil). 16 s × 24 fps.

Operatorlar model Pset larini o'qib (obj.ges.params) parametrlarni to'ldiradi, serverda `create_sim(kind)`,
`_poll_factory(meta, job, done)` → animatsiya; natija xulosasi Sim panelida. UI: Sim panelida «Egizak» qutisi.

## Sinovlar

- `desktop/tests/test_physics.py` (pytest): Manning, Thoma, sinxron tezlik, penstock yo'l uzunligi, spektral siljish.
- Blender headless: `objects` (barcha turlar, yangi Pset tekshiruvi), `demo_plant` (9 rol, bog'lanish: quvur oxiri
  turbinaga ≤ 1 m, suv tekisliklari), `sim_twin` (server: namuna → commit → 4 sim → keyframelar), GUI skrinshot.
