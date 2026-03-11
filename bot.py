"""
OpenBudget.uz Ovoz Berish Telegram Boti
Bir vaqtda yuzlab foydalanuvchi uchun async ishlaydi
"""

import asyncio
import logging
import os
import re
import base64

import aiohttp
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ============================================================
# SOZLAMALAR
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

INITIATIVE_ID = "66b53e63-87bc-40b4-8fcc-e0f6da010ef9"
BOARD_ID = "53"
BASE_URL = "https://openbudget.uz"

API_BASE = f"{BASE_URL}/api/v1"
SEND_OTP_URL = f"{API_BASE}/initiatives/vote/send-otp"
VERIFY_OTP_URL = f"{API_BASE}/initiatives/vote/verify-otp"
CAPTCHA_URL = f"{API_BASE}/captcha"

INITIATIVE_LINK = (
    f"{BASE_URL}/boards/initiatives/initiative/{BOARD_ID}/{INITIATIVE_ID}"
)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================
# FSM STATES
# ============================================================
class VoteStates(StatesGroup):
    waiting_phone = State()
    waiting_captcha = State()
    waiting_otp = State()


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================
def format_phone(phone: str) -> str:
    """Telefon raqamni +998XXXXXXXXX formatiga keltirish"""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("8") and len(digits) == 11:
        return f"+99{digits[1:]}"
    if len(digits) == 9:
        return f"+998{digits}"
    return f"+{digits}"


def is_valid_phone(phone: str) -> bool:
    """O'zbek telefon raqamini tekshirish"""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("998") and len(digits) == 12:
        return True
    if len(digits) == 9 and digits[0] in "379456":
        return True
    return False


# ============================================================
# OPENBUDGET API
# ============================================================
class OpenBudgetAPI:
    """openbudget.uz bilan ishlash uchun async API klient"""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Referer": INITIATIVE_LINK,
            "Origin": BASE_URL,
        }

    async def get_captcha(self) -> tuple:
        """Captcha olish — (captcha_id, image_bytes) yoki (None, None)"""
        try:
            async with self.session.get(
                CAPTCHA_URL,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    content_type = resp.content_type or ""
                    if "json" in content_type:
                        data = await resp.json()
                        captcha_id = (
                            data.get("id")
                            or data.get("captchaId")
                            or data.get("key")
                            or ""
                        )
                        img_data = (
                            data.get("image")
                            or data.get("captchaImage")
                            or data.get("img")
                            or ""
                        )
                        if img_data:
                            if img_data.startswith("data:image"):
                                img_data = img_data.split(",", 1)[1]
                            img_bytes = base64.b64decode(img_data)
                            return captcha_id, img_bytes
                    else:
                        # Binary rasm response
                        captcha_id = resp.headers.get("X-Captcha-Id", "")
                        img_bytes = await resp.read()
                        return captcha_id, img_bytes
        except Exception as e:
            logger.error(f"get_captcha xatosi: {e}")
        return None, None

    async def send_otp(
        self, phone: str, captcha_id: str, captcha_answer: str
    ) -> dict:
        """SMS OTP yuborish"""
        payload = {
            "phone": phone,
            "initiativeId": INITIATIVE_ID,
            "boardId": int(BOARD_ID),
            "captchaId": captcha_id,
            "captchaAnswer": captcha_answer,
        }
        try:
            async with self.session.post(
                SEND_OTP_URL,
                json=payload,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {}
                return {"status": resp.status, "data": data}
        except Exception as e:
            logger.error(f"send_otp xatosi: {e}")
            return {"status": 0, "data": {"error": str(e)}}

    async def verify_otp(
        self, phone: str, otp_code: str, session_token: str = ""
    ) -> dict:
        """OTP kodni tekshirish va ovoz berish"""
        payload = {
            "phone": phone,
            "initiativeId": INITIATIVE_ID,
            "boardId": int(BOARD_ID),
            "code": otp_code,
            "token": session_token,
        }
        try:
            async with self.session.post(
                VERIFY_OTP_URL,
                json=payload,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {}
                return {"status": resp.status, "data": data}
        except Exception as e:
            logger.error(f"verify_otp xatosi: {e}")
            return {"status": 0, "data": {"error": str(e)}}


# ============================================================
# ROUTER
# ============================================================
router = Router()

# Global HTTP session
http_session: aiohttp.ClientSession = None  # type: ignore


def get_api() -> OpenBudgetAPI:
    return OpenBudgetAPI(http_session)


# ============================================================
# HANDLERS
# ============================================================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Boshlash — loyiha haqida ma'lumot + telefon so'rash"""
    await state.clear()

    info_text = (
        "🗳️ <b>Ochiq Byudjet — Tashabbusli Loyiha</b>\n\n"
        "📌 <b>Loyiha:</b> Mahalla va ko'chalar obodonlashtirish\n"
        f"🔗 <b>Havola:</b> <a href='{INITIATIVE_LINK}'>Loyihani ko'rish</a>\n\n"
        "✅ Bu bot orqali siz <b>openbudget.uz</b> saytida "
        "ushbu loyihaga ovoz berishingiz mumkin.\n\n"
        "📋 <b>Jarayon:</b>\n"
        "1️⃣ Telefon raqamingizni yuboring\n"
        "2️⃣ Captcha rasmidagi kodni kiriting\n"
        "3️⃣ SMS orqali kelgan kodni kiriting\n"
        "4️⃣ Ovozingiz qabul qilinadi ✅\n\n"
        "<i>⚠️ Har bir fuqaro faqat 1 marta ovoz bera oladi</i>"
    )

    phone_btn = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(info_text, reply_markup=phone_btn)
    await message.answer(
        "👇 Tugmani bosing yoki raqamni qo'lda kiriting:\n"
        "<i>Misol: +998901234567 yoki 901234567</i>"
    )
    await state.set_state(VoteStates.waiting_phone)
    logger.info(
        f"User {message.from_user.id} ({message.from_user.username}) /start bosdi"
    )


@router.message(VoteStates.waiting_phone)
async def handle_phone(message: Message, state: FSMContext) -> None:
    """Telefon raqamini qabul qilish va captcha yuborish"""
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = f"+{phone}"
    else:
        raw = message.text.strip() if message.text else ""
        if not raw:
            await message.answer("❌ Iltimos, telefon raqamingizni yuboring!")
            return
        if not is_valid_phone(raw):
            await message.answer(
                "❌ <b>Noto'g'ri telefon raqam!</b>\n\n"
                "O'zbek raqamini kiriting:\n"
                "• <code>901234567</code>\n"
                "• <code>+998901234567</code>"
            )
            return
        phone = format_phone(raw)

    await state.update_data(phone=phone)
    await message.answer(
        f"📱 Raqam: <code>{phone}</code>\n\n⏳ Captcha yuklanmoqda...",
        reply_markup=ReplyKeyboardRemove(),
    )

    api = get_api()
    captcha_id, captcha_img = await api.get_captcha()

    if not captcha_img:
        await message.answer(
            "❌ Captcha yuklab bo'lmadi. Qayta urinib ko'ring: /start"
        )
        await state.clear()
        return

    await state.update_data(captcha_id=captcha_id)

    await message.answer_photo(
        BufferedInputFile(captcha_img, filename="captcha.png"),
        caption=(
            "🔐 <b>Captcha</b>\n\n"
            "Yuqoridagi rasmda ko'rsatilgan kodni kiriting:\n"
            "<i>(Harflar va raqamlarni diqqat bilan yozing)</i>"
        ),
    )
    await state.set_state(VoteStates.waiting_captcha)
    logger.info(
        f"Captcha yuborildi: user={message.from_user.id}, phone={phone}"
    )


@router.message(VoteStates.waiting_captcha)
async def handle_captcha(message: Message, state: FSMContext) -> None:
    """Captcha javobini qabul qilib OTP yuborish"""
    if not message.text:
        await message.answer("❌ Captcha kodni matn ko'rinishida yuboring!")
        return

    captcha_answer = message.text.strip()
    data = await state.get_data()
    phone = data.get("phone", "")
    captcha_id = data.get("captcha_id", "")

    await message.answer("⏳ Tekshirilmoqda...")

    api = get_api()
    result = await api.send_otp(phone, captcha_id, captcha_answer)

    status = result.get("status", 0)
    resp_data = result.get("data", {})

    logger.info(
        f"send_otp natija: user={message.from_user.id}, "
        f"status={status}, data={resp_data}"
    )

    if status in (200, 201):
        session_token = (
            resp_data.get("token")
            or resp_data.get("sessionId")
            or resp_data.get("session")
            or ""
        )
        await state.update_data(session_token=session_token)
        await message.answer(
            f"✅ <b>SMS yuborildi!</b>\n\n"
            f"📱 <code>{phone}</code> raqamiga 4–6 xonali kod yuborildi.\n\n"
            "👇 Kodni quyida kiriting:"
        )
        await state.set_state(VoteStates.waiting_otp)

    elif status == 400:
        error_msg = (
            resp_data.get("message")
            or resp_data.get("error")
            or "Noto'g'ri captcha"
        )
        if "captcha" in str(error_msg).lower():
            captcha_id_new, captcha_img_new = await api.get_captcha()
            if captcha_img_new:
                await state.update_data(captcha_id=captcha_id_new)
                await message.answer_photo(
                    BufferedInputFile(captcha_img_new, filename="captcha.png"),
                    caption=(
                        "❌ <b>Captcha noto'g'ri!</b>\n\n"
                        "Yangi captcha yuborildi. Qayta kiriting:"
                    ),
                )
            else:
                await message.answer(
                    "❌ Captcha noto'g'ri. Qayta boshlang: /start"
                )
                await state.clear()
        else:
            await message.answer(
                f"❌ <b>Xatolik:</b> {error_msg}\n\nQayta boshlash: /start"
            )
            await state.clear()

    elif status == 409:
        await message.answer(
            "⚠️ <b>Siz allaqachon ovoz bergansiz!</b>\n\n"
            "Har bir fuqaro faqat 1 marta ovoz bera oladi."
        )
        await state.clear()

    elif status == 429:
        await message.answer(
            "⏰ <b>Juda ko'p urinish!</b>\n\nBir oz kutib, qayta urinib ko'ring."
        )
        await state.clear()

    else:
        await message.answer(
            f"❌ Server xatosi ({status}). Keyinroq urinib ko'ring: /start"
        )
        await state.clear()


@router.message(VoteStates.waiting_otp)
async def handle_otp(message: Message, state: FSMContext) -> None:
    """OTP kodni qabul qilib ovoz berish"""
    if not message.text:
        await message.answer("❌ SMS kodini raqam ko'rinishida yuboring!")
        return

    otp_code = re.sub(r"\D", "", message.text.strip())
    if len(otp_code) < 4:
        await message.answer(
            "❌ Kod kamida 4 ta raqamdan iborat bo'lishi kerak!"
        )
        return

    data = await state.get_data()
    phone = data.get("phone", "")
    session_token = data.get("session_token", "")

    await message.answer("⏳ Ovoz berilmoqda...")

    api = get_api()
    result = await api.verify_otp(phone, otp_code, session_token)

    status = result.get("status", 0)
    resp_data = result.get("data", {})

    logger.info(
        f"verify_otp natija: user={message.from_user.id}, "
        f"status={status}, data={resp_data}"
    )

    if status in (200, 201):
        await message.answer(
            "🎉 <b>OVOZINGIZ QABUL QILINDI!</b>\n\n"
            "✅ Siz muvaffaqiyatli ovoz berdingiz!\n\n"
            "🗳️ Loyiha: Mahalla va ko'chalar obodonlashtirish\n"
            f"🔗 <a href='{INITIATIVE_LINK}'>Natijalarni ko'rish</a>\n\n"
            "🙏 Ishtirokingiz uchun rahmat!\n"
            "<i>Sizning ovozingiz shahar rivojiga hissa qo'shadi.</i>"
        )
        await state.clear()

    elif status == 400:
        error_msg = (
            resp_data.get("message")
            or resp_data.get("error")
            or "Noto'g'ri kod"
        )
        err_lower = str(error_msg).lower()
        if "expired" in err_lower or "eskirgan" in err_lower or "timeout" in err_lower:
            await message.answer(
                "⏰ <b>Kod muddati o'tgan!</b>\n\nQayta boshlang: /start"
            )
            await state.clear()
        else:
            await message.answer(
                f"❌ <b>Noto'g'ri kod!</b>\n\n{error_msg}\n\nQayta kiriting:"
            )
            # State saqlanadi — foydalanuvchi qayta kiritadi

    elif status == 409:
        await message.answer(
            "⚠️ <b>Ovoz allaqachon berilgan!</b>\n\n"
            "Bu raqam bilan avval ovoz berilgan."
        )
        await state.clear()

    elif status == 410:
        await message.answer(
            "⏰ <b>Sessiya tugagan!</b>\n\nQayta boshlang: /start"
        )
        await state.clear()

    else:
        unknown_err = resp_data.get("message") or "Noma'lum xatolik"
        await message.answer(
            f"❌ <b>Ovoz qabul qilinmadi</b> (xato: {status})\n\n"
            f"Sabab: {unknown_err}\n\n"
            "Qayta urinish: /start"
        )
        await state.clear()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Yordam</b>\n\n"
        "Bu bot openbudget.uz saytida loyihaga ovoz berish uchun.\n\n"
        "📋 <b>Buyruqlar:</b>\n"
        "/start — Ovoz berishni boshlash\n"
        "/help — Yordam\n\n"
        "❓ <b>Muammo bo'lsa:</b>\n"
        "• /start bosib qayta boshlang\n"
        "• SMS kelmasa, bir necha daqiqa kutib qayta urinib ko'ring\n"
        "• Har bir raqam faqat 1 marta ovoz bera oladi"
    )


@router.message()
async def handle_unknown(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("👋 Ovoz berish uchun /start bosing!")


# ============================================================
# MAIN
# ============================================================
async def main() -> None:
    global http_session

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    connector = aiohttp.TCPConnector(
        limit=200,
        limit_per_host=50,
        ssl=False,
    )
    http_session = aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=20),
    )

    logger.info("Bot ishga tushdi...")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        await http_session.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
