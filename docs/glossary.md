# Sath — atamalar lug'ati (UX-09)

Web interfeysdagi yagona atamalar. Yangi matn yozishda shu jadvaldan foydalaning; lug'at kalitlari
`web/src/i18n/uz-Latn.ts` da. Kirill yozuvi (uz-Cyrl) lotin matndan avtomatik transliteratsiya qilinadi
(`web/src/i18n/translit.ts`), rus tili qisman (`ru.ts`, yetishmagan kalit — o'zbekcha).

Qoidalar:

- Inglizcha so'zni o'zbekcha qo'shimcha bilan aralashtirmang ("Issue lar", "Viewport Shading" — noto'g'ri).
- Standart qisqartmalar (SCADA, ISA-101, IFC, BCF, HH/LL, MW) o'zgarmaydi.
- Enum qiymatlari (critical, pending, power…) hech qachon xom ko'rsatilmaydi — `i18n/labels.ts` dagi yorliqlar.
- Vaqt: har doim stansiya vaqti (Asia/Tashkent), 24 soat, `kk.oo.yyyy ss:dd` (`ui/format.ts`).

## Dispetcherlik (SCADA / HMI)

| O'zbekcha (lotin) | Ўзбекча (кирилл) | Русский | English | Izoh |
|---|---|---|---|---|
| Alarm | Аларм | Авария / сигнализация | Alarm | ISA-18.2 hodisasi |
| Kvitlash | Квитлаш | Квитирование | Acknowledge | Operator alarmni ko'rganini tasdiqlaydi |
| Kvitlanmagan | Квитланмаган | Неквитированный | Unacknowledged | |
| Vaqtincha o'chirish (shelving) | Вақтинча ўчириш | Шельвинг | Shelve | Muddat + sabab bilan |
| Xizmatdan tashqari (OOS) | Хизматдан ташқари | Выведен из работы | Out of service | Faqat muhandis |
| Ustuvorlik: Kritik / Yuqori / O'rta / Past | Критик / Юқори / Ўрта / Паст | Критический / Высокий / Средний / Низкий | Critical / High / Medium / Low | Shakl: ◆ ▲ ■ ● |
| Aloqa yo'q | Алоқа йўқ | Нет связи | Stale / no communication | Sensor yoki jonli oqim uzilgan (yagona nom, "uzilgan" emas) |
| Eskirgan qiymat | Эскирган қиймат | Устаревшее значение | Stale value | Kulrang + shtrix |
| Jonli / Kechikmoqda | Жонли / Кечикмоқда | Онлайн / Задержка | Live / Stale | Jonli oqim holati |
| Toshqin (alarm toshqini) | Тошқин | Лавина аварий | Alarm flood | EEMUA-191: 10 daqiqada > 10 |
| Mimika (sxema) | Мимика | Мнемосхема | Mimic | L1/L2 ekranlari |
| Qiymat paneli (faceplate) | Қиймат панели | Фейсплейт | Faceplate | L3 |
| Buyruq, topshiriq qiymati | Буйруқ, топшириқ қиймати | Команда, уставка | Command, setpoint | |
| Tanlab bajarish | Танлаб бажариш | Выбор — исполнение | Select-before-operate | 2 qadam |
| Blokirovka | Блокировка | Блокировка | Interlock | |
| Izolyatsiya (LOTO) | Изоляция | Блокировка/маркировка | Lock-out tag-out | |
| Smena topshirish | Смена топшириш | Сдача смены | Shift handover | |
| Hodisalar ketma-ketligi (SOE) | Ҳодисалар кетма-кетлиги | Последовательность событий | Sequence of events | ms aniqlik |
| Yuqori / quyi byef | Юқори / қуйи бьеф | Верхний / нижний бьеф | Headwater / tailwater | |
| Agregat | Агрегат | Гидроагрегат | Unit | |

## BIM (model, versiya, tasdiqlash)

| O'zbekcha (lotin) | Ўзбекча (кирилл) | Русский | English | Izoh |
|---|---|---|---|---|
| Versiya | Версия | Версия | Version | Har IFC yuklash yoki commit |
| Tasdiqlash so'rovi | Тасдиқлаш сўрови | Запрос на утверждение | Change request (CR) | |
| Muammo | Муаммо | Замечание | Issue (BCF) | 3D ko'rinish bilan; "Issue" emas |
| Qoralama | Қоралама | Черновик | Draft | Web da qo'shilgan/tahrirlangan element |
| IFC ga qo'shish (commit) | IFC га қўшиш | Фиксация (commit) | Commit | Yangi versiya |
| Ko'rinish uslubi | Кўриниш услуби | Режим отображения | Viewport shading | Solid / Wireframe / X-ray / Rendered |
| Kesim | Кесим | Сечение | Section | |
| To'qnashuv | Тўқнашув | Коллизия | Clash | |
| Hajm-miqdor | Ҳажм-миқдор | Объёмы работ | QTO | |
| Farq | Фарқ | Сравнение | Diff | Qo'shilgan / o'zgargan / o'chirilgan |
| Federatsiya | Федерация | Сводная модель | Federation | |

## Rollar

| O'zbekcha | Русский | English |
|---|---|---|
| Ko'ruvchi | Наблюдатель | Viewer |
| Dispetcher | Диспетчер | Operator |
| Smena boshlig'i | Начальник смены | Shift supervisor |
| Muhandis | Инженер | Engineer |
| Tasdiqlovchi | Утверждающий | Approver |
| Administrator (tizim sozlamalari) | Администратор | Administrator |
