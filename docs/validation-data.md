# Haqiqiy GES ma'lumotlari bilan validatsiya (SIM-09)

Holat: **qisman** — validatsiya to'plami (yuklagich, tekshiruvlar, qabul mezonlari) tayyor, lekin
haqiqiy stansiya ma'lumoti hali yo'q. Hozirgi `ges_sim` testlari qo'lda hisob, analitik yechim va
nashr etilgan benchmarklarga tayanadi (`sim/tests/test_benchmarks.py`); bu hujjat stansiyadan qaysi
ma'lumot kerakligini va uni qanday ulashni tavsiflaydi.

## Ishga tushirish

```
SATH_VALIDATION_DATA=/yo'l/ges-a;/yo'l/ges-b  pytest sim/tests/validation -rs
```

`SATH_VALIDATION_DATA` berilmasa `sim/tests/validation/data/<to'plam>/` qidiriladi. Ma'lumot
bo'lmasa haqiqiy testlar **SKIP** bo'ladi (CI yiqilmaydi); yuklagichning o'zi sintetik to'plam bilan
doim sinaladi. Ma'lumot tijorat siri bo'lishi mumkin — repozitoriyga qo'shmang, alohida saqlang.

## To'plam formati

Har stansiya — bitta papka, ikki fayl.

### `plant.json` — pasport

```json
{
  "name": "Namuna GES",
  "units": [
    {"name": "GA-1", "type": "Francis", "rated_power_mw": 25, "rated_head_m": 45,
     "rated_flow_m3s": 62, "max_efficiency": 0.92, "generator_eta_max": 0.985}
  ],
  "penstock": {"length_m": 180, "diameter_m": 4.0, "roughness_mm": 0.1, "minor_loss_k": 0.6},
  "storage_curve": {"elevations_m": [880, 890, 900, 910], "volumes_mcm": [0, 40, 120, 260]},
  "acceptance": {"power_mape_pct": 5, "power_bias_pct": 3, "level_rmse_m": 0.15, "level_window_h": 24}
}
```

- `units` — `ges_sim.turbine.TurbineSpec` maydonlari (`type`: Francis / Kaplan / Pelton ...), tartib
  `timeseries.csv` dagi `u1`, `u2`, ... bilan bir xil.
- `penstock` — ixtiyoriy; berilmasa sof napor = yuqori − quyi byef.
- `storage_curve` — ixtiyoriy; suv balansi tekshiruvi uchun (batimetriya, abs. sath → mln m³).
- `acceptance` — ixtiyoriy; yuqoridagilar default qiymatlar.

### `timeseries.csv` — ekspluatatsiya jurnali

| Ustun | Birlik | Majburiy | Izoh |
|---|---|---|---|
| `ts` | ISO 8601 | ha | qat'iy o'suvchi; qadam doimiy bo'lishi shart emas (1 soat tavsiya) |
| `headwater_m` | m (abs) | ha | yuqori byef sathi |
| `tailwater_m` | m (abs) | ha | quyi byef sathi |
| `u<N>_flow_m3s` | m³/s | ha | N-agregat sarfi (o'lchangan: ultratovush / Winter–Kennedy / indeks) |
| `u<N>_power_mw` | MW | ha | N-agregat generator klemmasidagi faol quvvat |
| `inflow_m3s` | m³/s | yo'q | omborga kiruvchi sarf (gidropost yoki balansdan) |
| `spill_m3s` | m³/s | yo'q | suv tashlagich / salt tashlama |
| `other_outflow_m3s` | m³/s | yo'q | sug'orish, ekologik sarf, filtratsiya |

Bo'sh katak — o'lchov yo'q (hisobga olinmaydi). O'nlik ajratgich nuqta yoki vergul.

## Tekshiruvlar

1. **Agregat quvvati** — o'lchangan sarf va sof napor bo'yicha `TurbineSpec.power_mw` (turbina hill-
   chart + generator yo'qotishlari) o'lchangan quvvat bilan solishtiriladi: MAPE ≤ `power_mape_pct`,
   |o'rtacha siljish| ≤ `power_bias_pct`.
2. **Suv balansi** — `reservoir.step` (modified Puls) o'lchangan kiruvchi / turbina / tashlama sarflari
   bilan sathni marshrutlaydi; har `level_window_h` oynada o'lchangan sathdan qayta boshlanadi, oyna
   oxiridagi sath xatosi RMSE ≤ `level_rmse_m`.

## Stansiyadan kerakli ma'lumotlar

- **Pasport**: har agregat uchun nominal quvvat, napor, sarf, turbina turi; zavod model sinovi
  (hill-chart) yoki qabul sinovi (IEC 60041) natijalari — FIK egri chizig'i; generator FIK (zavod
  protokoli).
- **Quvur**: uzunlik, diametr(lar), material / g'adir-budirlik, mahalliy yo'qotishlar (yoki o'lchangan
  napor yo'qotishi — sarf juftliklari).
- **Ombor**: sath–hajm egri chizig'i (so'nggi batimetriya), o'lik va normal sath.
- **SCADA arxivi**: kamida 1 yil, 1 soatlik (yoki 10–15 daqiqalik) o'rtacha qiymatlar — yuqori/quyi
  byef sathlari, har agregat sarfi va faol quvvati, tashlama, kiruvchi sarf (gidropost).
- **O'lchov metama'lumoti**: sarf o'lchash usuli va aniqligi, datchiklar kalibrlash sanalari, ta'mir /
  ishdan chiqish davrlari (bu davrlar bo'sh katak sifatida qoldiriladi).
- Imkon bo'lsa: gidrozarba sinovi (yuk tashlash) yozuvi — zadvijka oldidagi bosim va yopilish vaqti
  (`water_hammer` moduli uchun), zilzila / toshqin hodisalari yozuvlari.
