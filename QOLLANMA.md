# Dubai Real Estate Telegram Bot — Sozlash Qo'llanmasi

## 1-QADAM: Fayllarni GitHub'ga yuklash

1. github.com saytida ro'yxatdan o'ting (agar hisobingiz yo'q bo'lsa)
2. "New repository" tugmasini bosing, nom bering (masalan `dubai-bot`), **Private** qilib qo'ying
3. Repository ichida "uploading an existing file" havolasini bosing
4. Quyidagi 3 faylni yuklang: `bot.py`, `requirements.txt`, `Procfile`
5. "Commit changes" tugmasini bosing

## 2-QADAM: Railway'da loyiha yaratish

1. railway.app saytiga kiring, GitHub orqali ro'yxatdan o'ting
2. "New Project" → "Deploy from GitHub repo" tanlang
3. Yaratgan `dubai-bot` repository'ni tanlang
4. Railway avtomatik ravishda `requirements.txt` va `Procfile`ni topib, kerakli kutubxonalarni o'rnatadi

## 3-QADAM: Environment Variables (maxfiy kalitlar) kiritish

Railway loyihangizda **"Variables"** bo'limiga o'ting va quyidagi 4 ta o'zgaruvchini qo'shing:

| Nomi | Qiymati |
|------|---------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan olgan tokeningiz |
| `ANTHROPIC_API_KEY` | Anthropic Console'dan olgan API key |
| `OWNER_CHAT_ID` | Sizning shaxsiy Telegram chat ID'ingiz (pastda qanday topish yozilgan) |
| `CHANNEL_USERNAME` | Kanalingiz username, masalan `@dubai_realestate_uz` |

### OWNER_CHAT_ID qanday topiladi?

Bot birinchi marta ishga tushgandan keyin, Telegram'da botingizga `/start` deb yozing. Bot sizga javoban chat ID'ingizni yuboradi. Shu raqamni nusxalab, Railway'dagi `OWNER_CHAT_ID` qiymatiga kiritib, qayta saqlang (Railway avtomatik qayta ishga tushiradi).

## 4-QADAM: Botni tekshirish

1. Railway'da "Deployments" bo'limida loglarni kuzating — "Bot polling boshlandi..." degan xabar chiqishi kerak
2. Telegram'da botingizga `/test` deb yozing — bu darhol test postini generatsiya qiladi
3. Bot sizga "✅ Kanalga joylash" va "❌ Bekor qilish" tugmalari bilan post yuboradi
4. "✅ Kanalga joylash" bossangiz — post avtomatik kanalga chiqadi

## Kunlik avtomatik jadval

Hozirgi sozlamada bot **kuniga 3 marta** (Dubai vaqti bo'yicha) avtomatik post tayyorlaydi va sizga tasdiqlash uchun yuboradi:

- **09:00** — Dubai ko'chmas mulk yangiliklari
- **14:00** — Amerika fond bozori tahlili
- **19:00** — UAE siyosiy-iqtisodiy yangiliklar

Bu vaqtlarni o'zgartirish uchun `bot.py` faylida `POST_SCHEDULE` qismini tahrirlash kifoya.

## Qo'shimcha buyruqlar

- `/test` — darhol test posti generatsiya qiladi (real estate mavzusida)
- `/post <mavzu yoki havola>` — siz bergan aniq mavzu bo'yicha post yozadi (masalan: `/post Eid al-Etihad Towers loyihasi haqida`)

## Xarajatlar haqida eslatma

- Railway: oyiga taxminan $5 atrofida (ishlatishga qarab)
- Anthropic API: har bir post taxminan $0.05-0.15 atrofida (web search + yozish), kuniga 3 post = oyiga ~$5-15

## Xavfsizlik eslatmasi

Hech qachon `TELEGRAM_BOT_TOKEN` yoki `ANTHROPIC_API_KEY` qiymatlarini boshqa odamlarga yoki ochiq joyga (masalan GitHub'ning public repository'siga) joylashtirmang. Shuning uchun repository **Private** qilib yaratilgan.
