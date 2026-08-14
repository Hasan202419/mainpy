# Savdo tizimi (paper/demo)

Bu repo — qoidalar asosida ishlaydigan, **faqat qog'ozda (paper/simulyatsiya)** savdo
qiladigan skaner + portfel tizimi. Har bir pozitsiya ochilishidan oldin
**stop-loss va take-profit (target) narxlari avtomatik hisoblanadi**, risklar
oldindan tekshiriladi, va tizimda haqiqiy brokerga ulanadigan hech qanday kod
yo'q — ya'ni real order hech qachon avtomatik yuborilmaydi.

## Tuzilishi

- `archetypes.py` — 29 ta tikerning guruhlanishi (A–G). Har bir guruh uchun:
  bir vaqtda nechta pozitsiya ochish mumkinligi (korrelyatsiya riski uchun
  limit), stop masofasi koeffitsienti (`stop_k`) va target reward multiple
  (`target_r`).
- `scanner.py` — signal qidirish logikasi, tarmoqqa chiqmaydi (faqat berilgan
  bar'lar ustida ishlaydi):
  - **ORB (Opening Range Breakout)** — sessiya ochilishidagi birinchi 30
    daqiqa (5 daqiqalik 6 ta bar) diapazonidan tashqariga chiqish.
  - **VWAP reclaim** — narx VWAP'ning bir tomonidan ikkinchi tomoniga o'tishi
    va ushlab turishi.
  Har ikkala signal ham `entry`, `stop` va `target` narxlarini ATR-proksi
  (bar range) asosida hisoblab qaytaradi.
- `portfolio.py` — to'liq simulyatsiya qilingan ("paper") hisob:
  - Boshlang'ich balans $30,000, Try2BFunded qoidalariga mos: kunlik zarar
    limiti 2%, maksimal drawdown 4%, har bir guruh uchun bitta (yoki
    belgilangan sonli) pozitsiya slot.
  - Har bir yangi pozitsiyadan oldin `can_open()` orqali barcha risk
    qoidalari tekshiriladi — limitdan oshib ketsa, savdo avtomatik rad
    etiladi.
  - Ochiq pozitsiyalar har skan siklida narxga qarab stop yoki target'ga
    tegib-tegmaganligi tekshiriladi (`mark_and_check_exits`) va avtomatik
    yopiladi.
  - Holat `state.json` fayliga saqlanadi (bu fayl repo'da saqlanmaydi —
    `.gitignore`'da, chunki u ishga tushirish paytida generatsiya bo'ladigan
    runtime holat).
- `run_scan.py` — bitta skan siklini ishga tushiruvchi orkestrator:
  1. Ochiq pozitsiyalarni stop/target bo'yicha tekshiradi,
  2. Har bir tiker uchun yangi signal qidiradi,
  3. Risk qoidalaridan o'tgan signal uchun pozitsiya ochadi (stop va target
     bilan birga, avtomatik hisoblangan holda),
  4. Portfel holatini (equity, kunlik P&L, ochiq pozitsiyalar) chop etadi.
- `build_bars.py` — IBKR'dan olingan xom bar ma'lumotlarini `bars.json`
  formatiga aylantiradigan bir martalik skript (tarmoqqa chiqmaydi, faqat
  oldindan olingan ma'lumotlarni qayta shakllantiradi).
- `bars.json` — demo uchun namunaviy bar ma'lumotlari (2026-08-14, 5 daqiqalik,
  RTH).

## Ishga tushirish

```bash
python3 run_scan.py bars.json
```

Bu buyruq `state.json`ni (agar mavjud bo'lmasa) $30,000 balans bilan yaratadi,
ochiq pozitsiyalarni tekshiradi, yangi signallarni qidiradi va natijani
konsolga chiqaradi.

## Muhim: bu real broker bilan ishlamaydi

Ushbu paketda hech qanday broker klienti import qilinmagan — ya'ni bu kod
orqali hech qachon haqiqiy order yuborilishi **mumkin emas**. Bar
ma'lumotlari alohida (masalan, IBKR market-data vositalari orqali) olinadi va
oddiy JSON fayl sifatida shu skriptlarga uzatiladi. Bu "bozor ma'lumotini
o'qish" (xavfsiz, faqat o'qish) bilan "buyurtma yuborish" o'rtasida qattiq
devor qo'yadi — real hisobda tugmani bosish har doim odam (Hasan) qo'lida
qoladi.
