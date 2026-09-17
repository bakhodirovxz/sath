# Sath gateway

SCADA tarmog'ida ishlaydigan kichik Python skript: Modbus TCP, OPC UA yoki CSV dan o'qib,
Sath serverga HTTP orqali yuboradi. Serverga faqat HTTP kirish kifoya.

```
pip install requests pymodbus asyncua
cp gateway_config.example.json config.json   # server manzili, project_id, ingest_key, teglar
python ges_gateway.py config.json
```

- `ingest_key` — webda Monitoring → «Ulanish kaliti» (tasdiqlovchi).
- Har teg `key` serverdagi sensor kaliti bilan bir xil bo'lishi kerak (Monitoring → Sensor qo'shish).
- Tarmoq uzilsa o'lchovlar buferda saqlanib, keyin yuboriladi.
- `sim` manbasi — sinov uchun (haqiqiy qurilma kerak emas).

Windows da doimiy ishlashi uchun Task Scheduler («At startup», «Run whether user is logged on») yoki NSSM.

## Buyruqlar (supervisory control)

Serverda `writable` belgilangan sensor (setpoint/rele) uchun dispetcher **Dispetcher paneli → Buyruq**
yuboradi. Gateway har siklda `GET /api/projects/{id}/commands/pending` (X-Ingest-Key) dan navbatni oladi va
teg konfiguratsiyasi bo'yicha yozadi: Modbus — `write_registers` (address/type/scale), OPC UA — `write_value`,
sim — simulyator qiymati. Natija `POST /api/commands/{id}/ack` (`acked`/`failed` + matn) — dispetcher
panelida va audit jurnalida ko'rinadi. O'chirish: konfiguratsiyada `"commands": false`.


## OPC UA teglarini avtomatik topish (browse)

```
pip install asyncua
python ges_gateway.py browse opc.tcp://scada-host:4840 tags.csv 4 [user] [parol]
```

`tags.csv` — Sath «Monitoring → CSV import» formati (`key;name;kind;unit;protocol;address;element;low;high`):
`kind` nomdan taxmin qilinadi (sath/sarf/quvvat/bosim/harorat/tebranish/holat/ochilish), `address` — OPC UA
node id. Faylni ochib `element` ustuniga IFC element nomini (yoki GUID) yozing — import 3D ga avtomatik bog'laydi;
`gateway_config.json` ning `tags` ro'yxatiga ham xuddi shu `key`/`node_id` lar kiradi.
