# GES simulyatori — sinov stendi

Haqiqiy stansiyaga o'xshash dinamik model (`ges_sim` fizikasi: ombor balansi, suv tashlagich, quvur,
turbina/generator; agregat va zatvor kechikishlari; izolyatsiyalangan rejimda chastota 2H·dΔω/dt).
Modbus TCP (5020), OPC UA (4840) va IEC 60870-5-104 (2404, `c104` o'rnatilgan bo'lsa) server sifatida
ishlaydi — gateway haqiqiy protokol bilan ulanadi.

```
pip install ../../sim "pymodbus>=3.8,<3.10" asyncua
python ges_simulator.py --list
python ges_simulator.py --scenario unit_trip --modbus 0.0.0.0:5020 --opcua opc.tcp://0.0.0.0:4840/sath-sim/
python ges_simulator.py --scenario unit_trip --iec104 0.0.0.0:2404   # pip install c104 (GPLv3, alohida jarayon)
python ges_simulator.py --print-gateway-config --modbus 127.0.0.1:5020 > gw.json   # keyin kalitlarni to'ldiring
python ../gateway/ges_gateway.py gw.json
```

Docker: `docker compose --profile sim up -d` (`SIM_SCENARIO`, `SIM_SPEED`, gateway kalitlari `.env` da).

## Stsenariylar

| id | nima bo'ladi | kutilgan natija Sath da |
|---|---|---|
| normal | 2 agregat 35 MW, kiruvchi 150 m³/s | barqaror, alarm yo'q |
| load_rejection | 30 s izolyatsiya, 60 s yuk tashlash | GRID.F ortiqcha tezlik (statizm bilan cheklanadi), 120 s da tiklanadi |
| unit_trip | 40 s AGG1 himoya (trip), 300 s qayta ishga | AGG1.P → 0, AGG1.RUN 0; SOE: AGG1.PROT TRIP, AGG1.CB OPEN |
| gate_fault | zatvor 80 % ga buyruq, 25 s da qotadi | GATE1.POS o'zgarmaydi; SOE GATE1 STUCK; buyruq readback mismatch |
| flood (dt 60 s) | kiruvchi 150 → 2500 m³/s | RES.H > NPU, RES.QSPILL > 0, sath alarmi |
| comms_loss | 30–90 s aloqa yo'q | Modbus javob bermaydi / OPC UA Bad → quality=bad, keyin stale |
| sensor_stuck | RES.H qotadi, kiruvchi 400 | qiymat o'zgarmaydi (I2 ortiqchalik tekshiruvi buni topadi) |
| sensor_noisy | AGG1.VIB σ = 2 mm/s | alarm chatter (C1 deadband/kechikish sinovi) |
| chatter | AGG2.P 30 ↔ 31 MW har 10 s | chegara atrofida tebranish |

Teglar: `RES.H RES.QIN RES.QSPILL TW.H GATE1.SP GATE1.POS GRID.F TR1.OIL NET.H AGGn.P AGGn.Q AGGn.RUN
AGGn.SP AGGn.VIB AGGn.TEMP` (n = 1..3). Yoziladigan: `GATE1.SP`, `AGGn.SP` — Modbus holding
registrlari (float32, `--print-gateway-config` manzillarni beradi), OPC UA `ns=2;s=<KEY>` yoki IEC 104
IOA (o'lchovlar 100+ `M_ME_NC_1`, `*.RUN` — `M_SP_TB_1` vaqt tamg'ali → gateway SOE; setpointlar 200+ `C_SE_NC_1`).
Serverda shu kalitli sensorlar yarating (Monitoring → CSV import) — `GATE1.SP`, `AGGn.SP` `writable`.

SOE: trip/zatvor/uzgich hodisalari millisekundli tamg'a bilan `soe.jsonl` ga (D3 da serverga).
Yozib olish/qayta ijro: `--record run.jsonl`, `--replay run.jsonl` (operator mashqi, P8).
