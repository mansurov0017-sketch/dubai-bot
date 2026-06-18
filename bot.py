"""
Dubai Real Estate Telegram Bot
- Claude API orqali avtomatik yangiliklar va post matni generatsiya qiladi
- Postni avval shaxsiy chatga (tasdiqlash uchun) yuboradi
- Tasdiqlangandan keyin kanalga joylaydi
- Kuniga belgilangan vaqtlarda avtomatik ishga tushadi (APScheduler orqali)
"""

import os
import logging
import asyncio
from datetime import datetime
import pytz

import anthropic
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------------------------------------------------------------------------
# Konfiguratsiya (Environment Variables orqali, Railway'da sozlanadi)
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
OWNER_CHAT_ID = os.environ["OWNER_CHAT_ID"]  # Sizning shaxsiy Telegram chat ID'ingiz
CHANNEL_USERNAME = os.environ["CHANNEL_USERNAME"]  # masalan: @dubai_realestate_uz

# Kunlik post mavzulari va vaqtlari (Dubai vaqti, Asia/Dubai)
# Har birini xohlagancha o'zgartirishingiz mumkin
POST_TIMES = [9, 14, 19]  # Dubai vaqti bo'yicha, har kuni shu 3 vaqtda post chiqadi

# Haftaning har kuni uchun 3 ta mavzu tartibi (0=Dushanba ... 6=Yakshanba)
# 5 mavzu rotatsiya qiladi, shunda har biri haftada bir necha marta chiqadi
WEEKLY_TOPIC_ROTATION = {
    0: ["real_estate", "markets", "political_economic"],          # Dushanba
    1: ["investment_insight", "real_estate", "sales_tips"],        # Seshanba
    2: ["markets", "political_economic", "real_estate"],           # Chorshanba
    3: ["sales_tips", "investment_insight", "markets"],            # Payshanba
    4: ["real_estate", "political_economic", "investment_insight"],# Juma
    5: ["markets", "sales_tips", "real_estate"],                   # Shanba
    6: ["investment_insight", "real_estate", "political_economic"],# Yakshanba
}

TOPIC_IMAGE_QUERIES = {
    "real_estate": "Dubai skyline luxury real estate",
    "markets": "stock market finance trading",
    "political_economic": "Dubai UAE government business",
    "investment_insight": "real estate investment growth",
    "sales_tips": "handshake real estate deal",
}


def get_unsplash_image(topic_key: str) -> str | None:
    """Unsplash API orqali mavzuga mos rasm URL'ini qaytaradi."""
    query = TOPIC_IMAGE_QUERIES.get(topic_key, "Dubai real estate")
    try:
        response = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data["urls"]["regular"]
    except Exception:
        logger.exception("Unsplash rasm olishda xato")
        return None


TOPIC_PROMPTS = {
    "real_estate": (
        "Dubai ko'chmas mulk bozori bo'yicha bugungi eng dolzarb va muhim yangilikni "
        "internetdan qidirib top. Yangi loyihalar, narxlar o'zgarishi, RERA/DLD "
        "statistikalari, yirik developerlar (Emaar, DAMAC, Sobha va boshqalar) yangiliklari, "
        "yoki investorlar uchun foydali tendentsiyalar haqida bo'lishi mumkin."
    ),
    "markets": (
        "Amerika fond bozori (S&P 500, Nasdaq, Dow Jones) bo'yicha bugungi eng muhim "
        "yangilikni va buning Dubai/UAE investorlariga, dollar kursiga yoki ko'chmas mulk "
        "bozoriga bo'lishi mumkin bo'lgan ta'sirini internetdan qidirib top."
    ),
    "political_economic": (
        "UAE va Dubai bilan bog'liq bugungi eng muhim siyosiy-iqtisodiy yangilikni "
        "(hukumat qarorlari, foiz stavkalari, vizalar, iqtisodiy siyosat, xalqaro "
        "munosabatlar) internetdan qidirib top va buning ko'chmas mulk bozoriga "
        "ta'sirini tushuntir."
    ),
    "investment_insight": (
        "Dubai ko'chmas mulkiga investitsiya qilish bo'yicha foydali, amaliy insight "
        "tayyorla. Internetdan eng so'nggi ROI ko'rsatkichlari, ijara daromadi (rental "
        "yield), eng istiqbolli rayonlar, yoki xalqaro investorlar uchun foydali "
        "soliq/qonunchilik yangiliklarini qidirib top. Maqsad - potensial investorga "
        "aniq raqamlar va amaliy maslahat berish."
    ),
    "sales_tips": (
        "Ko'chmas mulk sotish/sotib olish jarayoni haqida foydali, amaliy maslahat "
        "yoki insight tayyorla (masalan: muzokara strategiyalari, hujjatlashtirish "
        "bosqichlari, narx belgilash psixologiyasi, off-plan vs ready property "
        "tanlash mezonlari). Internetdan dolzarb Dubai bozor amaliyotlarini qidirib, "
        "shu asosda klientlar uchun foydali kontent yarat."
    ),
}

SYSTEM_PROMPT = """Sen Dubayda ishlaydigan tajribali realtor uchun Telegram kanal kontentini yozadigan yordamchisan. Kanal auditoriyasi - potensial va mavjud klientlar, ko'chmas mulkka qiziqqan investorlar.

Vazifang: berilgan mavzu bo'yicha internetdan eng so'nggi va dolzarb ma'lumotni qidirib topish, so'ngra O'ZBEK TILIDA professional, ishonchli va vizual jihatdan jozibali Telegram post matnini yozish.

Post talablari:
- Faqat o'zbek tilida (lotin alifbosida)
- Professional, ishonchli ohang - murakkab moliyaviy terminlarni oddiy so'zlar bilan tushuntir
- Aniq raqamlar va faktlarga asoslangan (sana, foiz, summalar)
- Boshida mavzuga mos 1 ta sarlavha emoji bilan boshlanadigan qisqa, diqqatni tortuvchi sarlavha qatori (masalan: "🏙️ Dubai Real Estate Pulse" yoki "📊 Bozor Tahlili")
- Matn ichida har bir asosiy fikr/band oldida mos emoji ishlatilsin (📈 📉 💰 🏗️ 🔑 ⚡️ kabi), lekin ortiqcha ishlatmasdan - har bandda bittadan yetarli
- Qisqa paragraflar, oson o'qiladigan struktura
- Uzunligi: 80-150 so'z atrofida (Telegram'da o'qilishi oson bo'lishi uchun)
- Manba havolasi yoki nomini oxirida kichik shrift kabi ko'rsat (masalan: "Manba: Bloomberg")
- HECH QANDAY "Mana post:" kabi metaizoh yozmang - faqat tayyor post matnini ber
- Faktlarni ixtiro qilma - agar aniq ma'lumot topa olmasang, buni ayt va eng yaqin ishonchli ma'lumotni ber

Javobing FAQAT tayyor Telegram post matni bo'lishi kerak, boshqa hech narsa qo'shma."""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Claude API orqali post generatsiya qilish
# ---------------------------------------------------------------------------

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Vaqtinchalik xotirada tasdiqlanmagan postlarni saqlash (oddiy holat uchun yetarli)
pending_posts = {}


def generate_post(topic_key: str, custom_topic: str = None) -> str:
    """Claude API orqali web search bilan post matnini generatsiya qiladi."""

    if custom_topic:
        user_prompt = (
            f"Quyidagi mavzu/havola bo'yicha internetdan qidirib, post yoz: {custom_topic}"
        )
    else:
        user_prompt = TOPIC_PROMPTS.get(topic_key, TOPIC_PROMPTS["real_estate"])

    response = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    # Javobdagi barcha text bloklarni birlashtiramiz
    text_parts = [block.text for block in response.content if block.type == "text"]
    post_text = "\n".join(text_parts).strip()

    return post_text


# ---------------------------------------------------------------------------
# Telegram handler funksiyalari
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Salom! Bot ishga tushdi.\n\nSizning chat ID'ingiz: {chat_id}\n\n"
        "Buni Railway environment variable'ga OWNER_CHAT_ID sifatida kiriting.\n\n"
        "Buyruqlar:\n"
        "/post <mavzu> - shu mavzuda hozir post generatsiya qil\n"
        "/test - test posti generatsiya qil (real estate mavzusida)"
    )


async def manual_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi /post <mavzu> deb yozsa, shu mavzuda post yozadi."""
    if str(update.effective_chat.id) != str(OWNER_CHAT_ID):
        return

    custom_topic = " ".join(context.args) if context.args else None
    await update.message.reply_text("⏳ Post tayyorlanmoqda, biroz kuting...")

    try:
        post_text = generate_post(topic_key="real_estate", custom_topic=custom_topic)
        image_url = get_unsplash_image("real_estate")
        await send_for_approval(context, post_text, image_url)
    except Exception as e:
        logger.exception("Post generatsiyasida xato")
        await update.message.reply_text(f"❌ Xato yuz berdi: {e}")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(OWNER_CHAT_ID):
        return
    await update.message.reply_text("⏳ Test posti tayyorlanmoqda...")
    try:
        post_text = generate_post(topic_key="real_estate")
        image_url = get_unsplash_image("real_estate")
        await send_for_approval(context, post_text, image_url)
    except Exception as e:
        logger.exception("Test postida xato")
        await update.message.reply_text(f"❌ Xato yuz berdi: {e}")


async def send_for_approval(context: ContextTypes.DEFAULT_TYPE, post_text: str, image_url: str = None):
    """Tayyor postni owner'ga tasdiqlash tugmalari bilan yuboradi (rasm bilan, agar mavjud bo'lsa)."""
    post_id = str(datetime.now().timestamp())
    pending_posts[post_id] = {"text": post_text, "image_url": image_url}

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Kanalga joylash", callback_data=f"approve:{post_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject:{post_id}"),
            ]
        ]
    )

    caption = f"📝 Yangi post tayyor:\n\n{post_text}"

    if image_url:
        try:
            await context.bot.send_photo(
                chat_id=OWNER_CHAT_ID,
                photo=image_url,
                caption=caption,
                reply_markup=keyboard,
            )
            return
        except Exception:
            logger.exception("Rasm bilan yuborishda xato, faqat matn yuboriladi")

    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=caption,
        reply_markup=keyboard,
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, post_id = query.data.split(":", 1)
    post_data = pending_posts.get(post_id)

    if not post_data:
        await _safe_edit(query, "⚠️ Bu post muddati o'tgan yoki allaqachon ishlov berilgan.")
        return

    post_text = post_data["text"]
    image_url = post_data.get("image_url")

    if action == "approve":
        try:
            if image_url:
                try:
                    await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=image_url, caption=post_text)
                except Exception:
                    logger.exception("Kanalga rasm bilan joylashda xato, faqat matn yuboriladi")
                    await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=post_text)
            else:
                await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=post_text)
            await _safe_edit(query, f"✅ Kanalga joylandi:\n\n{post_text}")
        except Exception as e:
            logger.exception("Kanalga joylashda xato")
            await _safe_edit(query, f"❌ Kanalga joylashda xato: {e}")
        finally:
            pending_posts.pop(post_id, None)

    elif action == "reject":
        await _safe_edit(query, "❌ Bekor qilindi.")
        pending_posts.pop(post_id, None)


async def _safe_edit(query, new_text: str):
    """Xabar matn yoki rasm (caption) bo'lishidan qat'i nazar, to'g'ri tahrirlaydi."""
    try:
        if query.message.photo:
            await query.edit_message_caption(caption=new_text)
        else:
            await query.edit_message_text(new_text)
    except Exception:
        logger.exception("Xabarni tahrirlashda xato")


# ---------------------------------------------------------------------------
# Rejalashtirilgan (scheduled) postlar
# ---------------------------------------------------------------------------

async def scheduled_post_job(application: Application, slot_index: int):
    """slot_index: 0, 1 yoki 2 - kunlik 3 vaqtdan (09:00/14:00/19:00) qaysi biri ekanini bildiradi.
    Bugungi haftaning kuniga qarab to'g'ri mavzu WEEKLY_TOPIC_ROTATION'dan tanlanadi."""
    dubai_tz = pytz.timezone("Asia/Dubai")
    weekday = datetime.now(dubai_tz).weekday()  # 0=Dushanba ... 6=Yakshanba
    topic_key = WEEKLY_TOPIC_ROTATION[weekday][slot_index]

    logger.info(f"Rejalashtirilgan post boshlandi: kun={weekday}, slot={slot_index}, mavzu={topic_key}")
    try:
        post_text = generate_post(topic_key=topic_key)
        image_url = get_unsplash_image(topic_key)
        await send_for_approval(application, post_text, image_url)
    except Exception as e:
        logger.exception("Rejalashtirilgan postda xato")
        try:
            await application.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"❌ Rejalashtirilgan post ({topic_key}) generatsiyasida xato: {e}",
            )
        except Exception:
            pass


def setup_scheduler(application: Application):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Dubai"))

    for slot_index, hour in enumerate(POST_TIMES):
        scheduler.add_job(
            scheduled_post_job,
            trigger=CronTrigger(hour=hour, minute=0),
            args=[application, slot_index],
            id=f"post_slot_{slot_index}_{hour}",
            misfire_grace_time=3600,
        )

    scheduler.start()
    logger.info("Scheduler ishga tushdi. Kunlik vaqtlar: %s", POST_TIMES)
    return scheduler


# ---------------------------------------------------------------------------
# Asosiy ishga tushirish
# ---------------------------------------------------------------------------

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("post", manual_post_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Scheduler'ni ishga tushirish uchun post_init callback ishlatamiz
    async def on_startup(app: Application):
        setup_scheduler(app)
        logger.info("Bot to'liq ishga tushdi.")

    application.post_init = on_startup

    logger.info("Bot polling boshlandi...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
