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
OWNER_CHAT_ID = os.environ["OWNER_CHAT_ID"]  # Sizning shaxsiy Telegram chat ID'ingiz
CHANNEL_USERNAME = os.environ["CHANNEL_USERNAME"]  # masalan: @dubai_realestate_uz

# Kunlik post mavzulari va vaqtlari (Dubai vaqti, Asia/Dubai)
# Har birini xohlagancha o'zgartirishingiz mumkin
POST_SCHEDULE = [
    {"hour": 9, "minute": 0, "topic": "real_estate"},
    {"hour": 14, "minute": 0, "topic": "markets"},
    {"hour": 19, "minute": 0, "topic": "political_economic"},
]

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
}

SYSTEM_PROMPT = """Sen Dubayda ishlaydigan tajribali realtor uchun Telegram kanal kontentini yozadigan yordamchisan. Kanal auditoriyasi - potensial va mavjud klientlar, ko'chmas mulkka qiziqqan investorlar.

Vazifang: berilgan mavzu bo'yicha internetdan eng so'nggi va dolzarb ma'lumotni qidirib topish, so'ngra O'ZBEK TILIDA professional, ishonchli va qiziqarli Telegram post matnini yozish.

Post talablari:
- Faqat o'zbek tilida (lotin alifbosida)
- Professional, lekin tushunarli til - murakkab moliyaviy terminlarni oddiy so'zlar bilan tushuntir
- Aniq raqamlar va faktlarga asoslangan (sana, foiz, summalar)
- Telegram uchun mos formatda: qisqa paragraflar, kerak bo'lsa emoji (lekin oshirib yubormasdan, 2-4 ta yetarli)
- Oxirida qisqa tahlil yoki "bu nima uchun muhim" degan amaliy xulosa (realtor nuqtai nazaridan)
- Uzunligi: 80-150 so'z atrofida (Telegram'da o'qilishi oson bo'lishi uchun)
- Manba havolasi yoki nomini oxirida kichik shrift kabi ko'rsat (masalan: "Manba: Bloomberg")
- HECH QANDAY sarlavha-prefiks yoki "Mana post:" kabi metaizoh yozmang - faqat tayyor post matnini ber
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
        await send_for_approval(context, post_text)
    except Exception as e:
        logger.exception("Post generatsiyasida xato")
        await update.message.reply_text(f"❌ Xato yuz berdi: {e}")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(OWNER_CHAT_ID):
        return
    await update.message.reply_text("⏳ Test posti tayyorlanmoqda...")
    try:
        post_text = generate_post(topic_key="real_estate")
        await send_for_approval(context, post_text)
    except Exception as e:
        logger.exception("Test postida xato")
        await update.message.reply_text(f"❌ Xato yuz berdi: {e}")


async def send_for_approval(context: ContextTypes.DEFAULT_TYPE, post_text: str):
    """Tayyor postni owner'ga tasdiqlash tugmalari bilan yuboradi."""
    post_id = str(datetime.now().timestamp())
    pending_posts[post_id] = post_text

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Kanalga joylash", callback_data=f"approve:{post_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject:{post_id}"),
            ]
        ]
    )

    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=f"📝 Yangi post tayyor:\n\n{post_text}",
        reply_markup=keyboard,
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, post_id = query.data.split(":", 1)
    post_text = pending_posts.get(post_id)

    if not post_text:
        await query.edit_message_text("⚠️ Bu post muddati o'tgan yoki allaqachon ishlov berilgan.")
        return

    if action == "approve":
        try:
            await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=post_text)
            await query.edit_message_text(f"✅ Kanalga joylandi:\n\n{post_text}")
        except Exception as e:
            logger.exception("Kanalga joylashda xato")
            await query.edit_message_text(f"❌ Kanalga joylashda xato: {e}")
        finally:
            pending_posts.pop(post_id, None)

    elif action == "reject":
        await query.edit_message_text("❌ Bekor qilindi.")
        pending_posts.pop(post_id, None)


# ---------------------------------------------------------------------------
# Rejalashtirilgan (scheduled) postlar
# ---------------------------------------------------------------------------

async def scheduled_post_job(application: Application, topic_key: str):
    logger.info(f"Rejalashtirilgan post boshlandi: {topic_key}")
    try:
        post_text = generate_post(topic_key=topic_key)
        await send_for_approval(application, post_text)
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

    for slot in POST_SCHEDULE:
        scheduler.add_job(
            scheduled_post_job,
            trigger=CronTrigger(hour=slot["hour"], minute=slot["minute"]),
            args=[application, slot["topic"]],
            id=f"post_{slot['topic']}_{slot['hour']}",
            misfire_grace_time=3600,
        )

    scheduler.start()
    logger.info("Scheduler ishga tushdi. Rejalashtirilgan postlar: %s", POST_SCHEDULE)
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
