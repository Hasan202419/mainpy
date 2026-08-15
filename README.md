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

## Real hisobga ulanish (trading.try2bfunded.com)

Try2BFunded'ning ochiq/hujjatlashtirilgan API'si topilmadi (izlab ko'rdim —
faqat o'zining veb-interfeysi bor ko'rinadi). Shuning uchun `web_broker.py`
va `live_trade.py` shu veb-saytni **brauzer avtomatlashtiruvi (Playwright)**
orqali boshqaradi.

**Diqqat:** bu fayllar `trading.try2bfunded.com` sahifasini hech qachon
ko'rmasdan yozilgan — chunki bu repo tayyorlangan sandbox'da o'sha domenga
tarmoq kirishi bloklangan. `web_broker.py`dagi `SELECTORS` lug'atidagi
barcha qiymatlar **PLACEHOLDER** (taxminiy) — haqiqiy sahifa HTML'iga
qarab tasdiqlanmaguncha, order joylashtirish funksiyasi ishlamaydi (ataylab
`SelectorsNotConfirmed` xatosini chiqaradi).

### Ishga tushirish tartibi (o'z kompyuteringizda, tarmoq bloklanmagan joyda)

1. `pip install -r requirements.txt` va `playwright install chromium`
   (agar Chromium alohida o'rnatilmagan bo'lsa).
2. `cp .env.example .env` va login/parolingizni shu yerga yozing. **`.env`
   hech qachon git'ga commit qilinmaydi** (`.gitignore`'da).
3. Avval faqat **o'qish** rejimida ishga tushiring:
   ```bash
   python3 live_trade.py inspect GRMN --exchange NYSE
   ```
   Bu login qiladi, `/profile/NYSE-GRMN` sahifasini ochadi va uning HTML'i
   bilan skrinshotini `inspect_dump/` papkasiga saqlaydi — hech qanday order
   bosilmaydi.
4. Saqlangan HTML'dan haqiqiy selektorlarni (login maydonlari, order forma
   tugmalari va h.k.) toping va `web_broker.py`dagi `SELECTORS` lug'atiga
   yozing, so'ng `SELECTORS["confirmed"] = True` qiling.
5. Sinab ko'ring — standart holat **doim dry-run**:
   ```bash
   python3 live_trade.py scan bars.json
   ```
   Bu haqiqiy narxlarni o'qiydi, signal va risk-gate'ni tekshiradi, lekin
   order o'rniga faqat "would place order" deb konsolga chiqaradi.
6. Faqat shundan keyin, ongli ravishda:
   ```bash
   python3 live_trade.py scan bars.json --live
   ```
   Bu **haqiqiy order** yuboradi. Skript qo'shimcha ravishda
   `PLACE REAL ORDERS` deb aniq yozishingizni so'raydi — tasodifiy
   ishga tushirilishini oldini olish uchun.

### Xavfsizlik va ehtiyot chegaralari

- **Login/parol hech qachon kodga yoki repo'ga yozilmaydi** — faqat
  `.env` (git'dan tashqarida) orqali. Bu repo **ochiq (public)**.
- `place_order()` standart holatda `dry_run=True` — real tugma bosilmaydi.
- Order joylashtirish `SELECTORS["confirmed"] == True` bo'lmaguncha ishlamaydi.
- **Try2BFunded'ning challenge/foydalanish shartlarini o'zingiz tekshiring**
  — ko'p prop-firmalar bot/avtomatik savdoni taqiqlaydi yoki cheklaydi;
  agar shunday bo'lsa, bu skriptni ishlatish challenge'ingizni bekor
  qilishga olib kelishi mumkin. Men bu saytning shartlarini sandbox'dan
  tekshira olmadim (domen bloklangan).
- Risk qoidalari (`portfolio.py`: 2% kunlik zarar, 4% max drawdown, guruh
  slot limiti) `live_trade.py`da ham xuddi shu tarzda ishlaydi — lekin bu
  endi **haqiqiy pul/challenge natijasiga** ta'sir qiladi, paper emas.

## Muhim: `run_scan.py` / `portfolio.py` / `scanner.py` hali ham real broker bilan ishlamaydi

Ushbu paketda hech qanday broker klienti import qilinmagan — ya'ni bu kod
orqali hech qachon haqiqiy order yuborilishi **mumkin emas**. Bar
ma'lumotlari alohida (masalan, IBKR market-data vositalari orqali) olinadi va
oddiy JSON fayl sifatida shu skriptlarga uzatiladi. Bu "bozor ma'lumotini
o'qish" (xavfsiz, faqat o'qish) bilan "buyurtma yuborish" o'rtasida qattiq
devor qo'yadi — real hisobda tugmani bosish har doim odam (Hasan) qo'lida
qoladi.

## Pine Script strategiyasi (TradingView)

`buy_only_strategy.pine` — "Comprehensive 'Buy-only' Trading Strategy
Analysis" hisobotidagi 3 ta long-only strategiyani bitta konfiguratsiya-
lanadigan TradingView `strategy()` skriptiga jamlaydi:

- **Scalping** — RSI(14) < 30 (oversold) da BUY, ~3-5 bar (1m grafikda
  taxminan 3-5 daqiqa) ushlab chiqish. TSLA 1m grafik uchun mo'ljallangan.
- **Day Trading** — 8-davrli SMA 21-davrli SMA'dan yuqoriga kesib
  o'tganda BUY, qarama-qarshi crossover'da chiqish. TSLA 15m grafik uchun.
- **Swing Trading** — Golden Cross: 50-kunlik SMA 200-kunlik SMA'dan
  yuqoriga o'tganda BUY, Death Cross'da chiqish. AAPL kunlik (1D) grafik
  uchun.

Uchala rejim ham bitta umumiy risk-yadrodan foydalanadi (repo'dagi
`portfolio.py`ning risk-mantig'iga izchil): stop-loss oldingi shamning
low'ida, pozitsiya hajmi ATR asosida hisoblanadi (har savdo tengdek % risk
qiladi), va kunlik drawdown limitiga (standart 2%) yetilgach shu kun uchun
yangi kirishlar to'xtatiladi (ochiq pozitsiya majburan yopilmaydi).

### Ishga tushirish

1. TradingView'da mos grafikni oching (masalan Scalping uchun TSLA, 1m
   timeframe).
2. Pine Editor'ni oching (pastki panel) → yangi skript → shu faylning
   tarkibini joylashtiring → **Add to Chart**.
3. Skript sozlamalaridan (⚙️) **Strategy Mode**'ni tanlang (Scalping /
   Day Trading / Swing Trading) — grafikdagi ticker/timeframe'ga mos
   rejimni tanlash kerak.
4. Natijalarni **Strategy Tester** panelida (Total Return, Win Rate va h.k.)
   ko'ring.

Bu skript shu muhitda (TradingView'siz) kompilyatsiya qilib ko'rilmadi —
Pine v6 grammatikasiga diqqat bilan qarab yozilgan, lekin agar Pine
Editor xato chiqarsa, xato matnini menga yuboring — darhol tuzataman.
