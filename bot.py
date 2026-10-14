import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
    CallbackQuery,
    Message
)

import config
import database as db

logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "images")
BOT_BANNER = os.path.join(STATIC_DIR, "bot_banner.png")
MENU_BANNER = os.path.join(STATIC_DIR, "menu_banner.png")
HELP_BANNER = os.path.join(STATIC_DIR, "help_banner.png")


# --- FSM States ---

class ApplicationState(StatesGroup):
    waiting_for_source = State()
    waiting_for_time = State()
    waiting_for_experience = State()


class PromoState(StatesGroup):
    waiting_for_promo = State()
    waiting_for_discount = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


class AliasState(StatesGroup):
    waiting_for_alias = State()


class SearchClientState(StatesGroup):
    waiting_for_query = State()


class AddProductState(StatesGroup):
    waiting_for_title = State()
    waiting_for_category = State()
    waiting_for_price = State()
    waiting_for_description = State()


class WalletState(StatesGroup):
    waiting_for_address = State()


class WithdrawState(StatesGroup):
    waiting_for_amount = State()


class TransferState(StatesGroup):
    waiting_for_recipient = State()
    waiting_for_amount = State()


class HelpQuestionState(StatesGroup):
    waiting_for_work_question = State()
    waiting_for_client_question = State()


class AdminReplyState(StatesGroup):
    waiting_for_reply_text = State()


class AdminRoleState(StatesGroup):
    waiting_for_user_query = State()
    waiting_for_role_selection = State()


class AdminLinkState(StatesGroup):
    waiting_for_chat_url = State()
    waiting_for_profits_url = State()
    waiting_for_shops_text = State()


class AdminBroadcastState(StatesGroup):
    waiting_for_broadcast_text = State()


class AdminBannerState(StatesGroup):
    waiting_for_media = State()


class AdminProfitChannelState(StatesGroup):
    waiting_for_channel_id = State()


# --- Keyboards ---

def get_persistent_reply_keyboard(worker: dict) -> ReplyKeyboardMarkup:
    role = worker.get("role", "worker")
    tg_id = worker.get("telegram_id", 0)
    is_admin = (role == "admin") or (tg_id in config.ADMIN_IDS)
    is_curator = (role == "curator") or (worker.get("is_mentor") == 1)

    keyboard = [
        [KeyboardButton(text="📦 Основное меню"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🛒 Marketplace")]
    ]
    admin_row = []
    if is_admin:
        admin_row.append(KeyboardButton(text="👑 Админ-панель"))
    if is_curator or is_admin:
        admin_row.append(KeyboardButton(text="🎓 Кабинет наставника"))

    if admin_row:
        keyboard.append(admin_row)

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_marketplace_keyboard(worker_promo: str):
    domains_btn = [InlineKeyboardButton(text="🌐 Открыть сайт", url=f"{config.DOMAINS[0]}?ref={worker_promo}")]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Управление клиентами", callback_data="nav_clients")],
            [InlineKeyboardButton(text="⚙️ Настройки сайта", callback_data="nav_settings")],
            domains_btn
        ]
    )


def get_settings_keyboard(worker: dict):
    logs_icon = "🟢" if worker.get("action_logs", 1) else "🔴"
    collateral_icon = "🟢" if worker.get("collateral_required", 0) else "🔴"
    deposit_icon = "🟢" if worker.get("deposit_via_support", 0) else "🔴"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"Логи действий: {logs_icon}", callback_data="toggle_action_logs"),
                InlineKeyboardButton(text=f"Залог при продаже: {collateral_icon}", callback_data="toggle_collateral")
            ],
            [
                InlineKeyboardButton(text=f"Пополнение через ТП: {deposit_icon}", callback_data="toggle_deposit_via_support")
            ],
            [
                InlineKeyboardButton(text="📦 Мои объявления", callback_data="worker_my_products")
            ],
            [
                InlineKeyboardButton(text="Массовое уведомление", callback_data="worker_broadcast")
            ],
            [
                InlineKeyboardButton(text="🔘 Изменить реферальный промокод", callback_data="worker_change_promo")
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в маркетплейс", callback_data="nav_marketplace")
            ]
        ]
    )


def get_clients_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Клиенты на сайте", callback_data="clients_list"),
                InlineKeyboardButton(text="Добавить клиента", callback_data="clients_add")
            ],
            [
                InlineKeyboardButton(text="Поиск клиента", callback_data="clients_search")
            ],
            [
                InlineKeyboardButton(text="👤 Имена для переписки", callback_data="clients_alias")
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в маркетплейс", callback_data="nav_marketplace")
            ]
        ]
    )


def get_profile_keyboard(worker: dict):
    kb = [
        [InlineKeyboardButton(text="💸 Оформить выплату", callback_data="wallet_withdraw")],
        [InlineKeyboardButton(text="💸 Перевод средств", callback_data="wallet_transfer")],
        [InlineKeyboardButton(text="⚙️ Настройка", callback_data="wallet_settings")]
    ]
    if worker.get("mentor_id"):
        kb.append([InlineKeyboardButton(text="🎓 Мой наставник", callback_data="my_mentor_info")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def get_main_menu_keyboard():
    chat_url = await db.get_bot_setting("chat_url", config.DEFAULT_CHAT_URL)
    profits_url = await db.get_bot_setting("profits_url", config.DEFAULT_PROFITS_URL)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💭 Общий чат", url=chat_url)],
            [InlineKeyboardButton(text="💳 Прямой перевод", callback_data="menu_direct_transfer")],
            [InlineKeyboardButton(text="🧾 Проверка чека", callback_data="menu_check_receipt")],
            [InlineKeyboardButton(text="💰 Профиты", url=profits_url)],
            [
                InlineKeyboardButton(text="🤝 Помощь в работе", callback_data="menu_help_work"),
                InlineKeyboardButton(text="🎓 Наставники", callback_data="menu_mentors")
            ],
            [InlineKeyboardButton(text="🌐 Полезное", callback_data="menu_useful")]
        ]
    )


def get_help_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Вопрос по работе", callback_data="help_work_question")],
            [InlineKeyboardButton(text="Помощь в обработке клиента", callback_data="help_client_question")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_menu_back")]
        ]
    )


# --- Media Banner Sender (Photo / Video / GIF / Animation) ---

async def send_media_screen(message_or_cb, section: str, caption: str, reply_markup=None, default_banner_path=None):
    if isinstance(message_or_cb, CallbackQuery):
        chat_id = message_or_cb.message.chat.id
        try:
            await message_or_cb.message.delete()
        except Exception:
            pass
    else:
        chat_id = message_or_cb.chat.id

    # Check custom banner in DB (or unified banner if active)
    banner = await db.get_banner(section)

    if banner:
        mtype = banner["media_type"]
        fid = banner["file_id"]
        try:
            if mtype == "video":
                return await bot.send_video(
                    chat_id=chat_id,
                    video=fid,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            elif mtype == "animation":
                return await bot.send_animation(
                    chat_id=chat_id,
                    animation=fid,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            else:  # photo
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=fid,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error sending custom banner for {section}: {e}")

    # Fallback to default local file
    if default_banner_path and os.path.exists(default_banner_path):
        return await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(default_banner_path),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        return await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )


# --- Notification Helpers ---

async def log_to_channel(text: str, reply_markup=None):
    try:
        await bot.send_message(
            chat_id=config.LOG_CHAT_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error sending log to channel: {e}")


async def notify_admins(text: str, reply_markup=None):
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception:
            pass


async def notify_worker(telegram_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error notifying worker {telegram_id}: {e}")


async def post_profit_to_channel(worker_name: str, profit_rub: float, total_order_rub: float = 0.0, order_number: str = "") -> tuple[bool, str]:
    """
    Publish a profit notification to the configured channel.
    Requirement: Worker nickname must be displayed strictly WITHOUT '@', along with the profit amount.
    """
    channel_target = await db.get_bot_setting("profits_channel_id", "")
    if not channel_target:
        channel_target = str(config.LOG_CHAT_ID)

    # Worker nickname strictly without '@'
    clean_name = (worker_name or "Воркер").replace("@", "").strip()
    if not clean_name:
        clean_name = "Воркер"

    profit_usd = round(profit_rub / config.USD_RUB_RATE, 1)

    text = (
        f"💸 <b>НОВЫЙ ПРОФИТ!</b>\n\n"
        f"👤 <b>Воркер:</b> {clean_name}\n"
        f"💰 <b>Сумма профита:</b> <b>{profit_rub:,.0f} ₽</b> (~{profit_usd}$)\n"
        f"🛍 <b>Сервис:</b> MODEVA"
    )

    try:
        target = int(channel_target) if (channel_target.startswith("-") or channel_target.lstrip("-").isdigit()) else channel_target
        await bot.send_message(
            chat_id=target,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return True, "Успешно опубликовано в канал"
    except Exception as e:
        logger.error(f"Error posting profit to channel '{channel_target}': {e}")
        return False, str(e)


# --- START & APPLICATIONS ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    worker = await db.get_worker_by_tg(user_id)

    if worker and worker.get("status") == "approved":
        reply_kb = get_persistent_reply_keyboard(worker)
        await message.answer(
            f"👋 Добро пожаловать, <b>{worker.get('first_name')}</b>!\n"
            f"Выберите нужный раздел в меню ниже:",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb
        )
        await show_main_menu(message)
        return

    # Check pending
    app = await db.get_application_by_tg(user_id)
    if app and app.get("status") == "pending":
        await message.answer(
            "⏳ <b>Ваша заявка находится на рассмотрении администрации.</b>\n\n"
            "Пожалуйста, ожидайте решения. Вы получите автоматическое уведомление после проверки.",
            parse_mode=ParseMode.HTML
        )
        return

    # New application
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📝 Заполнить заявку", callback_data="start_application")]]
    )
    await message.answer(
        "👋 <b>Добро пожаловать в закрытую команду MODEVA!</b>\n\n"
        "Чтобы получить доступ к платформе, заполните короткую анкету.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


@dp.callback_query(F.data == "start_application")
async def cb_start_application(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ApplicationState.waiting_for_source)
    await callback.message.answer("1️⃣ <b>Откуда вы узнали о нас?</b>", parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.message(ApplicationState.waiting_for_source)
async def process_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await state.set_state(ApplicationState.waiting_for_time)
    await message.answer("2️⃣ <b>Сколько времени в день вы готовы уделять работе?</b>", parse_mode=ParseMode.HTML)


@dp.message(ApplicationState.waiting_for_time)
async def process_time(message: Message, state: FSMContext):
    await state.update_data(time_commit=message.text.strip())
    await state.set_state(ApplicationState.waiting_for_experience)
    await message.answer("3️⃣ <b>Какой у вас опыт работы в данной сфере / продажах / трафике?</b>", parse_mode=ParseMode.HTML)


@dp.message(ApplicationState.waiting_for_experience)
async def process_experience(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    user = message.from_user

    app_id = await db.submit_application(
        telegram_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        source=data.get("source", "Не указано"),
        time_commit=data.get("time_commit", "Не указано"),
        experience=message.text.strip()
    )

    await message.answer(
        "✅ <b>Ваша заявка успешно отправлена на модерацию!</b> Ожидайте уведомления в этом диалоге.",
        parse_mode=ParseMode.HTML
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"app_approve_{app_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"app_reject_{app_id}")
            ]
        ]
    )
    user_str = f"@{user.username}" if user.username else f"ID: {user.id}"
    log_text = (
        f"📋 <b>НОВАЯ ЗАЯВКА НА ВОРКЕРА #{app_id}</b>\n\n"
        f"👤 <b>Кандидат:</b> {user.first_name} ({user_str})\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"1️⃣ <b>Откуда:</b> {data.get('source')}\n"
        f"2️⃣ <b>Время:</b> {data.get('time_commit')}\n"
        f"3️⃣ <b>Опыт:</b> {message.text.strip()}\n\n"
        f"Статус: 🟡 На рассмотрении"
    )
    await log_to_channel(log_text, reply_markup=admin_kb)


@dp.callback_query(F.data.startswith("app_approve_"))
async def cb_approve_app(callback: CallbackQuery):
    app_id = int(callback.data.replace("app_approve_", ""))
    app = await db.get_application_by_id(app_id)
    if not app:
        await callback.answer("Заявка не найдена!", show_alert=True)
        return

    worker = await db.approve_application(app_id)
    admin_str = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name

    await callback.message.edit_text(
        callback.message.text.replace("Статус: 🟡 На рассмотрении", f"Статус: ✅ ОДОБРЕНО ({admin_str})"),
        reply_markup=None,
        parse_mode=ParseMode.HTML
    )

    if worker:
        reply_kb = get_persistent_reply_keyboard(worker)
        await bot.send_message(
            chat_id=worker["telegram_id"],
            text=(
                f"🎉 <b>Поздравляем! Ваша заявка одобрена администрацией.</b>\n\n"
                f"Ваш промокод: <code>{worker['promo_code']}</code>\n"
                f"Добро пожаловать в команду!"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb
        )
    await callback.answer("Одобрено!")


@dp.callback_query(F.data.startswith("app_reject_"))
async def cb_reject_app(callback: CallbackQuery):
    app_id = int(callback.data.replace("app_reject_", ""))
    app = await db.get_application_by_id(app_id)
    if not app:
        await callback.answer("Заявка не найдена!", show_alert=True)
        return

    await db.reject_application(app_id)
    admin_str = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.message.edit_text(
        callback.message.text.replace("Статус: 🟡 На рассмотрении", f"Статус: ❌ ОТКЛОНЕНО ({admin_str})"),
        reply_markup=None,
        parse_mode=ParseMode.HTML
    )
    await notify_worker(app["telegram_id"], "❌ <b>К сожалению, ваша заявка была отклонена администрацией.</b>")
    await callback.answer("Отклонено!")


# Quick approve command
@dp.message(Command("approve"))
async def cmd_quick_approve(message: Message):
    parts = message.text.split()
    target_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else message.from_user.id
    worker = await db.create_worker(target_id, message.from_user.username, message.from_user.first_name)
    reply_kb = get_persistent_reply_keyboard(worker)
    await message.answer(f"✅ Воркер <code>{target_id}</code> моментально одобрен!", reply_markup=reply_kb, parse_mode=ParseMode.HTML)


# --- 📦 ОСНОВНОЕ МЕНЮ (Screenshot 3) ---

@dp.message(F.text == "📦 Основное меню")
async def msg_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)


async def show_main_menu(message_or_cb):
    kb = await get_main_menu_keyboard()
    caption = "<b>Выберите действие:</b>"
    await send_media_screen(message_or_cb, "menu", caption, kb, MENU_BANNER)
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.answer()


@dp.callback_query(F.data == "nav_menu_back")
async def cb_nav_menu_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback)


@dp.callback_query(F.data == "menu_direct_transfer")
async def cb_direct_transfer(callback: CallbackQuery):
    text = (
        "💳 <b>Прямой перевод / Пополнение</b>\n\n"
        "Для пополнения баланса или прямого перевода используйте наш сервис Crypto Bot или обратитесь в техническую поддержку.\n\n"
        f"Поддержка: {config.SUPPORT_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_menu_back")]])
    await callback.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "menu_check_receipt")
async def cb_check_receipt(callback: CallbackQuery):
    text = (
        "🧾 <b>Проверка чека / заказа</b>\n\n"
        "Для проверки статуса чека введите номер заказа (например: <code>BM-123456</code>) в чат с ботом или передайте клиенту ссылку на бутик."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_menu_back")]])
    await callback.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "menu_useful")
async def cb_useful(callback: CallbackQuery):
    shops_text = await db.get_bot_setting("shops_text", config.DEFAULT_SHOPS_TEXT)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_menu_back")]])
    await callback.message.edit_caption(caption=shops_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


# --- 🤝 ПОМОЩЬ В РАБОТЕ (Screenshot 4) ---

@dp.callback_query(F.data == "menu_help_work")
async def cb_help_work(callback: CallbackQuery):
    caption = (
        "Здесь вы можете задать любой интересующий Вас вопрос по ворку или по команде в целом, "
        "также получить консультацию по обработке вашего клиента!\n\n"
        "<b>Выберите нужное:</b>"
    )
    await send_media_screen(callback, "help", caption, get_help_keyboard(), HELP_BANNER)
    await callback.answer()


@dp.callback_query(F.data == "help_work_question")
async def cb_help_work_q(callback: CallbackQuery, state: FSMContext):
    await state.set_state(HelpQuestionState.waiting_for_work_question)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_help_work")]])
    await callback.message.answer("❓ <b>Вопрос по работе</b>\n\nНапишите ваш вопрос (он будет передан Администраторам):", parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.message(HelpQuestionState.waiting_for_work_question)
async def process_work_q(message: Message, state: FSMContext):
    question = message.text.strip()
    await state.clear()
    user = message.from_user

    # Notify admins
    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✍️ Ответить воркеру", callback_data=f"reply_to_worker_{user.id}")]]
    )
    user_str = f"@{user.username}" if user.username else f"ID: {user.id}"
    await notify_admins(
        f"❓ <b>ВОПРОС ПО РАБОТЕ от {user_str}:</b>\n\n{question}",
        reply_markup=admin_kb
    )
    await log_to_channel(
        f"❓ <b>ВОПРОС ПО РАБОТЕ от {user_str}:</b>\n\n{question}",
        reply_markup=admin_kb
    )
    await message.answer("✅ <b>Ваш вопрос передан администраторам!</b> Ожидайте ответа в этом диалоге.", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "help_client_question")
async def cb_help_client_q(callback: CallbackQuery, state: FSMContext):
    await state.set_state(HelpQuestionState.waiting_for_client_question)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_help_work")]])
    await callback.message.answer("🆘 <b>Помощь в обработке клиента</b>\n\nОпишите ситуацию с клиентом (вопрос будет передан Кураторам / Наставникам):", parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.message(HelpQuestionState.waiting_for_client_question)
async def process_client_q(message: Message, state: FSMContext):
    details = message.text.strip()
    await state.clear()
    user = message.from_user

    # Notify curators and channel
    curators = await db.get_all_mentors()
    reply_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✍️ Помочь воркеру", callback_data=f"reply_to_worker_{user.id}")]]
    )
    user_str = f"@{user.username}" if user.username else f"ID: {user.id}"
    msg_text = f"🆘 <b>ПОМОЩЬ В ОБРАБОТКЕ КЛИЕНТА от {user_str}:</b>\n\n{details}"

    for c in curators:
        try:
            await bot.send_message(c["telegram_id"], msg_text, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
        except Exception:
            pass
    await log_to_channel(msg_text, reply_markup=reply_kb)

    await message.answer("✅ <b>Запрос передан наставникам и кураторам!</b> Скоро вам ответят.", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("reply_to_worker_"))
async def cb_admin_reply_to_worker(callback: CallbackQuery, state: FSMContext):
    target_id = int(callback.data.replace("reply_to_worker_", ""))
    await state.set_state(AdminReplyState.waiting_for_reply_text)
    await state.update_data(target_worker_id=target_id)
    await callback.message.answer(f"✍️ Введите текст ответа для пользователя <code>{target_id}</code>:", parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.message(AdminReplyState.waiting_for_reply_text)
async def process_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_worker_id")
    await state.clear()

    reply_text = message.text.strip()
    sender_role = "Администратора"
    worker = await db.get_worker_by_tg(message.from_user.id)
    if worker and worker.get("role") == "curator":
        sender_role = "Наставника"

    await notify_worker(
        target_id,
        f"📩 <b>Ответ от {sender_role}:</b>\n\n{reply_text}"
    )
    await message.answer(f"✅ Ответ успешно доставлен пользователю <code>{target_id}</code>!", parse_mode=ParseMode.HTML)


# --- 👤 ПРОФИЛЬ (Screenshot 2) ---

@dp.message(F.text == "👤 Профиль")
async def msg_profile(message: Message, state: FSMContext):
    await state.clear()
    await show_profile(message)


async def show_profile(message_or_cb):
    user_id = message_or_cb.from_user.id
    worker = await db.get_worker_by_tg(user_id)
    if not worker:
        return

    stats = await db.get_worker_profit_stats(worker["id"])
    balance = worker.get("balance", 0.0)
    frozen = worker.get("frozen_balance", 0.0)

    username_str = f"@{worker.get('username')}" if worker.get('username') else worker.get('first_name', 'Воркер')

    # Exactly matching Screenshot 2 format (clean, without Fake tag or community)
    text = (
        f"🥷 <b>Профиль {username_str}</b>\n"
        f"💳 <b>ID:</b> <code>{worker['telegram_id']}</code>\n\n"
        f"<i>К сожалению, Вы до сих пор не попали в топ проекта...</i>\n\n"
        f"💳 <b>Ваш кошелёк</b>\n"
        f"├ Баланс: <b>{balance:,.1f}$</b>\n"
        f"└ Заморожено: <b>{frozen:,.1f}$</b>\n\n"
        f"💰 <b>Ваши профиты</b>\n"
        f"├ За день: <b>{stats['day_count']} профитов на сумму {stats['day_sum']:,.0f}₽</b>\n"
        f"├ За месяц: <b>{stats['month_count']} профитов на сумму {stats['month_sum']:,.0f}₽</b>\n"
        f"└ За все время: <b>{stats['all_count']} профитов на сумму {stats['all_sum']:,.0f}₽</b>"
    )

    kb = get_profile_keyboard(worker)
    await send_media_screen(message_or_cb, "profile", text, kb, MENU_BANNER)
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.answer()


# --- ВЫПЛАТЫ (CRYPTO BOT / TRC20, ОТ 20$) ---

@dp.callback_query(F.data == "wallet_withdraw")
async def cb_wallet_withdraw(callback: CallbackQuery, state: FSMContext):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker:
        return

    wallet = worker.get("trc20_wallet", "").strip()
    if not wallet:
        await state.set_state(WalletState.waiting_for_address)
        await callback.message.answer(
            "⚠️ <b>У вас не указан кошелёк TRC(20)!</b>\n\n"
            "Пожалуйста, введите ваш адрес кошелька USDT (TRC-20) для выплат через Crypto Bot:",
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return

    balance = worker.get("balance", 0.0)
    if balance < config.MIN_WITHDRAWAL_USD:
        await callback.answer(f"Минимальная сумма вывода: {config.MIN_WITHDRAWAL_USD}$. Ваш баланс: {balance}$", show_alert=True)
        return

    await state.set_state(WithdrawState.waiting_for_amount)
    await callback.message.answer(
        f"💸 <b>Оформление выплаты</b>\n\n"
        f"Доступно к выводу: <b>{balance:,.1f}$</b>\n"
        f"Минимум: <b>{config.MIN_WITHDRAWAL_USD}$</b>\n"
        f"Кошелек TRC(20): <code>{wallet}</code>\n\n"
        f"Введите сумму в долларах ($), которую хотите вывести:",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(WithdrawState.waiting_for_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    txt = message.text.strip().replace("$", "").replace(",", ".")
    try:
        amount = float(txt)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (например: 25):")
        return

    worker = await db.get_worker_by_tg(message.from_user.id)
    balance = worker.get("balance", 0.0)

    if amount < config.MIN_WITHDRAWAL_USD:
        await message.answer(f"Минимальная сумма вывода: {config.MIN_WITHDRAWAL_USD}$. Введите другую сумму:")
        return

    if amount > balance:
        await message.answer(f"Недостаточно средств. Ваш баланс: {balance}$. Введите сумму:")
        return

    await state.clear()
    wallet = worker.get("trc20_wallet", "")

    wid = await db.create_withdrawal(
        worker_id=worker["id"],
        telegram_id=worker["telegram_id"],
        username=worker.get("username", ""),
        amount_usd=amount,
        trc20_address=wallet
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выплатить (Crypto Bot)", callback_data=f"with_approve_{wid}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"with_reject_{wid}")
            ]
        ]
    )

    user_str = f"@{worker.get('username')}" if worker.get('username') else f"ID: {worker['telegram_id']}"
    log_text = (
        f"💸 <b>НОВАЯ ЗАЯВКА НА ВЫПЛАТУ #{wid}</b>\n\n"
        f"👤 <b>Воркер:</b> {user_str} (ID: <code>{worker['telegram_id']}</code>)\n"
        f"💵 <b>Сумма:</b> <b>{amount:,.1f}$</b>\n"
        f"💳 <b>Адрес TRC(20):</b> <code>{wallet}</code>\n"
        f"Метод: <b>Crypto Bot / USDT TRC-20</b>\n"
        f"Статус: 🟡 Ожидает выплаты"
    )

    await notify_admins(log_text, reply_markup=admin_kb)
    await log_to_channel(log_text, reply_markup=admin_kb)

    await message.answer(
        f"✅ <b>Заявка на выплату #{wid} успешно создана!</b>\n\n"
        f"Сумма: <b>{amount}$</b>\n"
        f"Адрес TRC(20): <code>{wallet}</code>\n\n"
        f"Средства заморожены до подтверждения перевода администратором через Crypto Bot.",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("with_approve_"))
async def cb_approve_withdrawal(callback: CallbackQuery):
    wid = int(callback.data.replace("with_approve_", ""))
    w = await db.process_withdrawal(wid, approve=True)
    if not w:
        await callback.answer("Заявка не найдена!", show_alert=True)
        return

    admin_str = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.message.edit_text(
        callback.message.text.replace("Статус: 🟡 Ожидает выплаты", f"Статус: ✅ ВЫПЛАЧЕНО через Crypto Bot ({admin_str})"),
        reply_markup=None,
        parse_mode=ParseMode.HTML
    )

    await notify_worker(
        w["telegram_id"],
        f"🎉 <b>Ваша выплата #{wid} на сумму {w['amount']}$ успешно отправлена!</b>\n"
        f"Кошелёк TRC(20): <code>{w['trc20_address']}</code>\n"
        f"Выплата произведена через Crypto Bot."
    )
    await callback.answer("Выплата подтверждена!")


@dp.callback_query(F.data.startswith("with_reject_"))
async def cb_reject_withdrawal(callback: CallbackQuery):
    wid = int(callback.data.replace("with_reject_", ""))
    w = await db.process_withdrawal(wid, approve=False)
    if not w:
        await callback.answer("Заявка не найдена!", show_alert=True)
        return

    admin_str = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.message.edit_text(
        callback.message.text.replace("Статус: 🟡 Ожидает выплаты", f"Статус: ❌ ОТКЛОНЕНО ({admin_str})"),
        reply_markup=None,
        parse_mode=ParseMode.HTML
    )

    await notify_worker(
        w["telegram_id"],
        f"❌ <b>Ваша заявка на выплату #{wid} была отклонена.</b>\n"
        f"Сумма {w['amount']}$ возвращена на ваш активный баланс."
    )
    await callback.answer("Выплата отклонена!")


# --- НАСТРОЙКИ КОШЕЛЬКА TRC-20 ---

@dp.callback_query(F.data == "wallet_settings")
async def cb_wallet_settings(callback: CallbackQuery, state: FSMContext):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    current_wallet = worker.get("trc20_wallet") or "не указан"

    await state.set_state(WalletState.waiting_for_address)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="nav_profile_back")]])

    await callback.message.answer(
        f"⚙️ <b>Настройка кошелька TRC(20)</b>\n\n"
        f"Текущий адрес: <code>{current_wallet}</code>\n\n"
        f"Введите новый адрес кошелька USDT (TRC-20) для получения выплат через Crypto Bot:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    await callback.answer()


@dp.message(WalletState.waiting_for_address)
async def process_wallet_address(message: Message, state: FSMContext):
    wallet = message.text.strip()
    if len(wallet) < 10:
        await message.answer("Пожалуйста, введите корректный адрес кошелька TRC-20:")
        return

    await state.clear()
    await db.set_worker_wallet(message.from_user.id, wallet)
    await message.answer(f"✅ <b>Кошелёк TRC(20) успешно сохранен:</b>\n<code>{wallet}</code>", parse_mode=ParseMode.HTML)


# --- ПЕРЕВОД СРЕДСТВ ---

@dp.callback_query(F.data == "wallet_transfer")
async def cb_wallet_transfer(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TransferState.waiting_for_recipient)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="nav_profile_back")]])
    await callback.message.answer("💸 <b>Перевод средств коллеге</b>\n\nВведите @username или Telegram ID получателя:", parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.message(TransferState.waiting_for_recipient)
async def process_transfer_recipient(message: Message, state: FSMContext):
    query = message.text.strip()
    target = await db.get_worker_by_username_or_id(query)
    if not target or target["telegram_id"] == message.from_user.id:
        await message.answer("❌ Пользователь не найден или вы указали себя. Попробуйте еще раз:")
        return

    await state.update_data(to_worker_id=target["id"], to_tg_id=target["telegram_id"], to_name=target.get("first_name") or target.get("username"))
    await state.set_state(TransferState.waiting_for_amount)
    await message.answer(f"Введите сумму перевода в $ для <b>{target.get('first_name')}</b>:", parse_mode=ParseMode.HTML)


@dp.message(TransferState.waiting_for_amount)
async def process_transfer_amount(message: Message, state: FSMContext):
    txt = message.text.strip().replace("$", "")
    try:
        amt = float(txt)
    except ValueError:
        await message.answer("Введите число:")
        return

    sender = await db.get_worker_by_tg(message.from_user.id)
    if amt <= 0 or amt > sender.get("balance", 0.0):
        await message.answer(f"Недостаточно средств. Ваш баланс: {sender.get('balance', 0.0)}$:")
        return

    data = await state.get_data()
    await state.clear()

    ok = await db.transfer_balance(sender["id"], data["to_worker_id"], amt)
    if ok:
        await message.answer(f"✅ Успешно переведено <b>{amt}$</b> пользователю <b>{data['to_name']}</b>!", parse_mode=ParseMode.HTML)
        await notify_worker(data["to_tg_id"], f"💸 <b>Вам поступил перевод {amt}$</b> от @{sender.get('username') or sender['telegram_id']}!")
    else:
        await message.answer("Ошибка перевода средств.")


@dp.callback_query(F.data == "nav_profile_back")
async def cb_profile_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_profile(callback)


# --- 🛒 MARKETPLACE & НАСТРОЙКИ САЙТА (Inside Marketplace) ---

@dp.message(F.text == "🛒 Marketplace")
async def msg_marketplace(message: Message, state: FSMContext):
    await state.clear()
    await show_marketplace(message)


async def show_marketplace(message_or_cb):
    user_id = message_or_cb.from_user.id
    worker = await db.get_worker_by_tg(user_id)
    if not worker:
        return

    domains_text = "\n".join([f"└ {d}" for d in config.DOMAINS])
    manual_url = await db.get_bot_setting("manual_url", config.MANUAL_URL)
    promo = worker.get("promo_code", "не установлен")
    discount = worker.get("discount_percent", 10)

    caption = (
        f"<b>Актуальные домены:</b>\n{domains_text}\n\n"
        f"<b>ТП:</b>\n└ {config.SUPPORT_USERNAME}\n\n"
        f"<b>Мануалы:</b>\nМануал по маркетплейсу\n└ <a href='{manual_url}'>Открыть мануал</a>\n\n"
        f"<b>Ваш промокод:</b>\n└ <code>{promo}</code> (скидка <b>{discount}%</b>)"
    )

    kb = get_marketplace_keyboard(promo)
    await send_media_screen(message_or_cb, "marketplace", caption, kb, BOT_BANNER)
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.answer()


@dp.callback_query(F.data == "nav_marketplace")
async def cb_nav_marketplace(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_marketplace(callback)


# --- НАСТРОЙКИ САЙТА (Screenshot 3) ---

@dp.callback_query(F.data == "nav_settings")
async def cb_nav_settings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return

    await send_media_screen(callback, "marketplace", "<b>Настройки сайта</b>", get_settings_keyboard(worker), BOT_BANNER)
    await callback.answer()


@dp.callback_query(F.data.in_({"toggle_action_logs", "toggle_collateral", "toggle_deposit_via_support"}))
async def cb_toggle_settings(callback: CallbackQuery):
    setting_map = {
        "toggle_action_logs": "action_logs",
        "toggle_collateral": "collateral_required",
        "toggle_deposit_via_support": "deposit_via_support"
    }
    field = setting_map[callback.data]
    worker = await db.toggle_worker_setting(callback.from_user.id, field)
    if worker:
        try:
            await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(worker))
        except Exception:
            pass
    await callback.answer("Настройка обновлена")


# --- ИЗМЕНЕНИЕ ПРОМОКОДА (Screenshot 4) ---

@dp.callback_query(F.data == "worker_change_promo")
async def cb_change_promo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting_for_promo)
    await callback.message.answer("Введите новый промокод:")
    await callback.answer()


@dp.message(PromoState.waiting_for_promo)
async def process_new_promo(message: Message, state: FSMContext):
    promo = "".join(c for c in message.text.strip() if c.isalnum() or c in "_-")
    if not promo or len(promo) < 2:
        await message.answer("Промокод должен быть от 2 символов. Попробуйте снова:")
        return

    existing = await db.get_worker_by_promo(promo)
    if existing and existing["telegram_id"] != message.from_user.id:
        await message.answer("❌ Промокод уже занят другим работником. Введите другой:")
        return

    await state.update_data(new_promo=promo)
    await state.set_state(PromoState.waiting_for_discount)
    await message.answer("Введите сумму скидки 1-75%:")


@dp.message(PromoState.waiting_for_discount)
async def process_new_discount(message: Message, state: FSMContext):
    txt = message.text.strip().replace("%", "")
    if not txt.isdigit() or int(txt) < 1 or int(txt) > 75:
        await message.answer("Введите число от 1 до 75:")
        return

    discount = int(txt)
    data = await state.get_data()
    promo = data["new_promo"]
    await state.clear()

    await db.update_worker_promo(message.from_user.id, promo, discount)

    user_str = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    await log_to_channel(f"🏷 <b>ОБНОВЛЕНИЕ ПРОМОКОДА</b>\nВоркер: {user_str}\nПромо: <code>{promo}</code> ({discount}%)")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⚙️ Настройки сайта", callback_data="nav_settings")]]
    )
    # Exactly matching Screenshot 4: "✅ Ваш промокод: ggg — 50%"
    await send_media_screen(message, "marketplace", f"✅ Ваш промокод: {promo} — {discount}%", kb, BOT_BANNER)


# --- 👥 УПРАВЛЕНИЕ КЛИЕНТАМИ (Screenshot 5) ---

@dp.callback_query(F.data == "nav_clients")
async def cb_nav_clients(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_media_screen(callback, "marketplace", "<b>Управление клиентами</b>", get_clients_keyboard(), BOT_BANNER)
    await callback.answer()


@dp.callback_query(F.data == "clients_list")
async def cb_clients_list(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return
    clients = await db.get_worker_clients(worker["id"])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_clients")]])

    if not clients:
        text = (
            "👥 <b>Клиенты на сайте:</b>\n\n"
            f"У вас пока нет зарегистрированных клиентов.\n"
            f"Используйте промокод <code>{worker['promo_code']}</code>."
        )
    else:
        text = f"👥 <b>Ваши клиенты на сайте ({len(clients)}):</b>\n\n"
        for idx, c in enumerate(clients[:15], 1):
            spent = f"{c.get('total_spent', 0):,.0f} ₽".replace(",", " ")
            text += f"{idx}. <b>{c.get('name')}</b> | 📱 <code>{c.get('phone') or 'нет'}</code>\n   Покупок: {c.get('order_count', 0)} на <b>{spent}</b>\n\n"

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "clients_add")
async def cb_clients_add(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return
    ref_link = f"{config.DOMAINS[0]}?ref={worker['promo_code']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_clients")]])
    text = (
        f"➕ <b>Добавить клиента:</b>\n\n"
        f"Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        f"Промокод: <code>{worker['promo_code']}</code> (-{worker['discount_percent']}%)\n\n"
        f"Клиент привяжется к вам при входе или оформлении заказа."
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "clients_search")
async def cb_clients_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchClientState.waiting_for_query)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="nav_clients")]])
    await callback.message.answer("🔍 Введите имя, телефон, email или ID клиента для поиска:", reply_markup=kb)
    await callback.answer()


@dp.message(SearchClientState.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    await state.clear()
    worker = await db.get_worker_by_tg(message.from_user.id)
    if not worker: return

    results = await db.search_worker_clients(worker["id"], message.text.strip())
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_clients")]])

    if not results:
        await message.answer("🔍 По запросу ничего не найдено.", reply_markup=kb)
        return

    text = f"🔎 <b>Найдено клиентов: {len(results)}</b>\n\n"
    for c in results:
        spent = f"{c.get('total_spent', 0):,.0f} ₽".replace(",", " ")
        text += f"👤 <b>{c.get('name')}</b> (ID: {c.get('id')})\n📱 Телефон: <code>{c.get('phone')}</code>\n💰 Заказов: {c.get('order_count')} на <b>{spent}</b>\n\n"
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@dp.callback_query(F.data == "clients_alias")
async def cb_clients_alias(callback: CallbackQuery, state: FSMContext):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return
    await state.set_state(AliasState.waiting_for_alias)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="nav_clients")]])
    await callback.message.answer(
        f"👤 <b>Имена для переписки</b>\nТекущее: <b>{worker.get('chat_alias')}</b>\n\nВведите новый псевдоним:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    await callback.answer()


@dp.message(AliasState.waiting_for_alias)
async def process_alias_change(message: Message, state: FSMContext):
    alias = message.text.strip()
    await state.clear()
    await db.set_worker_alias(message.from_user.id, alias)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_clients")]])
    await message.answer(f"✅ Имя для переписки изменено на: <b>{alias}</b>", parse_mode=ParseMode.HTML, reply_markup=kb)


# --- МОИ ОБЪЯВЛЕНИЯ & МАССОВАЯ РАССЫЛКА ---

@dp.callback_query(F.data == "worker_my_products")
async def cb_worker_my_products(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return
    products = await db.get_worker_products(worker["id"])
    kb = [
        [InlineKeyboardButton(text="➕ Добавить объявление", callback_data="add_product_start")],
        [InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="nav_settings")]
    ]
    text = f"📦 <b>Мои объявления на сайте ({len(products)}):</b>\n\n"
    if not products:
        text += "У вас пока нет персональных товаров."
    else:
        for idx, p in enumerate(products, 1):
            text += f"{idx}. <b>{p['title']}</b> | {p['price']:,.0f} ₽\n"

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "add_product_start")
async def cb_add_product_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProductState.waiting_for_title)
    await callback.message.answer("📦 Введите название товара:")
    await callback.answer()


@dp.message(AddProductState.waiting_for_title)
async def p_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddProductState.waiting_for_category)
    await message.answer("Укажите категорию (Сумки, Одежда, Обувь, Аксессуары):")


@dp.message(AddProductState.waiting_for_category)
async def p_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddProductState.waiting_for_price)
    await message.answer("Укажите цену товара числом (в рублях):")


@dp.message(AddProductState.waiting_for_price)
async def p_price(message: Message, state: FSMContext):
    txt = "".join(c for c in message.text if c.isdigit())
    if not txt or int(txt) <= 0:
        await message.answer("Введите число:")
        return
    await state.update_data(price=float(txt))
    await state.set_state(AddProductState.waiting_for_description)
    await message.answer("Введите описание товара:")


@dp.message(AddProductState.waiting_for_description)
async def p_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    await state.clear()
    worker = await db.get_worker_by_tg(message.from_user.id)
    if not worker: return

    prod = await db.add_worker_product(
        worker_id=worker["id"],
        title=data["title"],
        category=data["category"],
        price=data["price"],
        image_url="/static/images/p3_beigebag.png",
        description=desc
    )
    await message.answer(f"✅ Товар <b>«{prod['title']}»</b> опубликован на сайте!", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "worker_broadcast")
async def cb_worker_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.answer("📢 Введите текст уведомления для ваших клиентов на сайте:")
    await callback.answer()


@dp.message(BroadcastState.waiting_for_message)
async def p_bc(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    worker = await db.get_worker_by_tg(message.from_user.id)
    if not worker: return
    await db.add_broadcast(worker["id"], text)
    await message.answer("✅ Уведомление транслируется вашим клиентам!", parse_mode=ParseMode.HTML)


# --- 🎓 НАСТАВНИКИ & КУРАТОРЫ (Mentorship) ---

@dp.callback_query(F.data == "menu_mentors")
async def cb_mentors_list(callback: CallbackQuery):
    mentors = await db.get_all_mentors()
    worker = await db.get_worker_by_tg(callback.from_user.id)

    text = "🎓 <b>Наставники и Кураторы проекта:</b>\n\n"
    if not mentors:
        text += "В данный момент наставники набираются администрацией проекта."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="nav_menu_back")]])
    else:
        kb_buttons = []
        for m in mentors:
            user_str = f"@{m.get('username')}" if m.get('username') else m.get('first_name', 'Куратор')
            profits_cnt = m.get('mentor_profits_count', 0)
            profits_sum = m.get('mentor_profits_sum', 0)
            students = m.get('students_count', 0)

            text += (
                f"👤 <b>{m.get('first_name')} ({user_str})</b>\n"
                f"📊 Профитов учеников: <b>{profits_cnt}</b> на <b>{profits_sum:,.0f} ₽</b>\n"
                f"👥 Учеников на обучении: <b>{students}</b>\n\n"
            )
            if worker and worker.get("mentor_id") != m["id"]:
                kb_buttons.append([InlineKeyboardButton(text=f"Подать заявку к {user_str}", callback_data=f"apply_mentor_{m['id']}")])

        kb_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="nav_menu_back")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    # Check if worker already has mentor
    if worker and worker.get("mentor_id"):
        curr_mentor = await db.get_worker_by_id(worker["mentor_id"])
        if curr_mentor:
            p_count = worker.get("mentor_profits_count", 0)
            text = (
                f"🎓 <b>Ваш текущий наставник:</b> @{curr_mentor.get('username')} ({curr_mentor.get('first_name')})\n"
                f"📈 Профитов сделано вместе: <b>{p_count} / 5</b>\n"
                f"💰 Доля наставника: <b>20%</b> с ваших профитов.\n\n"
                f"<i>(Отвязаться от наставника можно после 5 успешных профитов)</i>\n\n"
            ) + text

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("apply_mentor_"))
async def cb_apply_to_mentor(callback: CallbackQuery):
    mentor_id = int(callback.data.replace("apply_mentor_", ""))
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker: return

    if worker.get("mentor_id"):
        await callback.answer("У вас уже есть активный наставник!", show_alert=True)
        return

    aid = await db.apply_to_mentor(worker["id"], mentor_id)
    mentor = await db.get_worker_by_id(mentor_id)

    # Notify mentor
    mentor_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять в ученики", callback_data=f"accept_stud_{aid}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_stud_{aid}")
            ]
        ]
    )
    user_str = f"@{worker.get('username')}" if worker.get('username') else worker.get('first_name')
    await notify_worker(
        mentor["telegram_id"],
        f"🎓 <b>НОВАЯ ЗАЯВКА НА ОБУЧЕНИЕ!</b>\n\n"
        f"Пользователь: {user_str} (ID: <code>{worker['telegram_id']}</code>)\n"
        f"Хочет стать вашим учеником. Вы будете получать 20% от его профитов!",
        reply_markup=mentor_kb
    )

    await callback.answer("Заявка на обучение отправлена наставнику!", show_alert=True)


@dp.callback_query(F.data.startswith("accept_stud_"))
async def cb_accept_student(callback: CallbackQuery):
    aid = int(callback.data.replace("accept_stud_", ""))
    app = await db.accept_mentor_application(aid)
    if not app:
        await callback.answer("Заявка не найдена!", show_alert=True)
        return

    student = await db.get_worker_by_id(app["student_id"])
    mentor = await db.get_worker_by_id(app["mentor_id"])

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>ЗАЯВКА ПРИНЯТА! Ученик добавлен.</b>",
        parse_mode=ParseMode.HTML
    )

    if student:
        await notify_worker(
            student["telegram_id"],
            f"🎉 <b>Наставник @{mentor.get('username')} принял вашу заявку на обучение!</b>\n"
            f"Теперь куратор помогает вам в доведении клиентов до профита."
        )
    await callback.answer("Ученик принят!")


@dp.callback_query(F.data.startswith("reject_stud_"))
async def cb_reject_student(callback: CallbackQuery):
    aid = int(callback.data.replace("reject_stud_", ""))
    await db.reject_mentor_application(aid)
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>ЗАЯВКА ОТКЛОНЕНА.</b>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer("Заявка отклонена!")


@dp.callback_query(F.data == "my_mentor_info")
async def cb_my_mentor_info(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker or not worker.get("mentor_id"):
        await callback.answer("У вас нет наставника", show_alert=True)
        return

    mentor = await db.get_worker_by_id(worker["mentor_id"])
    p_cnt = worker.get("mentor_profits_count", 0)

    kb = []
    if p_cnt >= 5:
        kb.append([InlineKeyboardButton(text="🔓 Отвязаться от наставника", callback_data="detach_my_mentor")])
    kb.append([InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="nav_profile_back")])

    text = (
        f"🎓 <b>Информация о вашем наставнике:</b>\n\n"
        f"Куратор: <b>{mentor.get('first_name')} (@{mentor.get('username')})</b>\n"
        f"Профитов с наставником: <b>{p_cnt} / 5</b>\n"
        f"Комиссия наставника: <b>20%</b>\n\n"
    )
    if p_cnt >= 5:
        text += "🎉 <b>Вы достигли 5 профитов!</b> Теперь вы можете отвязаться от наставника и получать полный процент (80%)."
    else:
        text += f"До возможности отвязаться осталось профитов: <b>{5 - p_cnt}</b>."

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "detach_my_mentor")
async def cb_detach_my_mentor(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    if not worker or worker.get("mentor_profits_count", 0) < 5:
        await callback.answer("Нужно сделать минимум 5 профитов!", show_alert=True)
        return

    old_mentor_id = worker.get("mentor_id")
    await db.detach_mentor(worker["id"])

    if old_mentor_id:
        mentor = await db.get_worker_by_id(old_mentor_id)
        if mentor:
            await notify_worker(
                mentor["telegram_id"],
                f"ℹ️ Ученик @{worker.get('username')} выполнил 5 профитов и успешно завершил обучение (отвязался)."
            )

    await callback.message.answer("🎉 <b>Вы успешно завершили обучение и отвязались от наставника!</b>\nТеперь вы получаете полные 80% со всех профитов.", parse_mode=ParseMode.HTML)
    await callback.answer()


# --- КАБИНЕТ НАСТАВНИКА ---

@dp.message(F.text == "🎓 Кабинет наставника")
async def msg_mentor_cabinet(message: Message):
    worker = await db.get_worker_by_tg(message.from_user.id)
    if not worker or (worker.get("role") not in ("curator", "admin") and worker.get("is_mentor") != 1):
        await message.answer("Этот раздел доступен только наставникам и кураторам.")
        return

    students = await db.get_mentor_students(worker["id"])
    pending_apps = await db.get_mentor_pending_applications(worker["id"])

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📥 Заявки на обучение ({len(pending_apps)})", callback_data="mentor_apps_list")],
            [InlineKeyboardButton(text=f"👥 Мои ученики ({len(students)})", callback_data="mentor_students_list")]
        ]
    )
    await message.answer(
        f"🎓 <b>Кабинет наставника / куратора</b>\n\n"
        f"Активных учеников: <b>{len(students)}</b>\n"
        f"Заявок на проверке: <b>{len(pending_apps)}</b>\n\n"
        f"Вы получаете <b>20%</b> от всех покупок ваших учеников до тех пор, пока ученик не наберет 5 профитов.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


@dp.callback_query(F.data == "mentor_apps_list")
async def cb_mentor_apps_list(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    apps = await db.get_mentor_pending_applications(worker["id"])
    if not apps:
        await callback.answer("Новых заявок на обучение пока нет.", show_alert=True)
        return

    for a in apps:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_stud_{a['id']}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_stud_{a['id']}")
                ]
            ]
        )
        await callback.message.answer(
            f"📥 <b>Заявка от @{a.get('username') or a['first_name']}</b> (ID: <code>{a['telegram_id']}</code>)\n"
            f"Текущих профитов: {a.get('total_profits')}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data == "mentor_students_list")
async def cb_mentor_students_list(callback: CallbackQuery):
    worker = await db.get_worker_by_tg(callback.from_user.id)
    students = await db.get_mentor_students(worker["id"])
    if not students:
        await callback.answer("У вас пока нет активных учеников.", show_alert=True)
        return

    text = f"👥 <b>Ваши ученики ({len(students)}):</b>\n\n"
    for idx, s in enumerate(students, 1):
        vol = f"{s.get('total_volume', 0):,.0f} ₽".replace(",", " ")
        text += f"{idx}. <b>{s.get('first_name')}</b> (@{s.get('username')})\n   Профитов: {s.get('profits_count', 0)} / 5 (Объем: {vol})\n\n"

    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()


# --- 👑 АДМИН-ПАНЕЛЬ ---

def is_admin(user_id: int, worker: dict = None) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    return worker and worker.get("role") == "admin"


@dp.message(F.text == "👑 Админ-панель")
async def msg_admin_panel(message: Message):
    worker = await db.get_worker_by_tg(message.from_user.id)
    if not is_admin(message.from_user.id, worker):
        await message.answer("Доступ запрещен.")
        return

    stats = await db.get_admin_dashboard_stats()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Управление баннерами (Фото/Видео/GIF)", callback_data="admin_banners_menu")],
            [InlineKeyboardButton(text="👥 Управление персоналом (Роли)", callback_data="admin_roles_menu")],
            [InlineKeyboardButton(text="🔗 Настройки ссылок (Чат, Профиты, Магазины)", callback_data="admin_links_menu")],
            [InlineKeyboardButton(text="📢 Канал выкладки профитов", callback_data="admin_profit_channel_menu")],
            [InlineKeyboardButton(text=f"💸 Заявки на вывод ({stats['pending_withdrawals']})", callback_data="admin_withdrawals_menu")],
            [InlineKeyboardButton(text="📢 Рассылка воркерам", callback_data="admin_broadcast_menu")]
        ]
    )
    text = (
        f"👑 <b>Панель Администратора</b>\n\n"
        f"👥 Всего воркеров: <b>{stats['total_workers']}</b>\n"
        f"🛍 Клиентов на сайте: <b>{stats['total_clients']}</b>\n"
        f"📦 Оформлено заказов: <b>{stats['total_orders']}</b>\n"
        f"💰 Оборот магазина: <b>{stats['total_volume']:,.0f} ₽</b>\n"
        f"💸 Заявок на вывод: <b>{stats['pending_withdrawals']}</b>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# --- 🖼 УПРАВЛЕНИЕ БАННЕРАМИ (ФОТО / ВИДЕО / GIF) ---

@dp.callback_query(F.data == "admin_banners_menu")
async def cb_admin_banners_menu(callback: CallbackQuery):
    use_unified = await db.get_bot_setting("use_unified_banner", "0")
    banners = await db.get_all_banners()

    def get_status(sec_name):
        b = banners.get(sec_name)
        if not b:
            return "Стандартный 🖼"
        icons = {"photo": "📷 Фото", "video": "🎬 Видео", "animation": "🎞 GIF"}
        return icons.get(b["media_type"], b["media_type"])

    unified_status = "🟢 ВКЛЮЧЕН" if use_unified == "1" else "🔴 ВЫКЛЮЧЕН"
    toggle_text = "🔴 Выключить единый баннер" if use_unified == "1" else "🟢 Включить единый баннер"

    text = (
        "🖼 <b>Управление баннерами бота</b>\n\n"
        "Поддерживаемые форматы баннеров:\n"
        "• 📷 <b>Фото</b> (JPG, PNG)\n"
        "• 🎬 <b>Видео</b> (MP4, обычные / кружки)\n"
        "• 🎞 <b>GIF-анимация</b>\n\n"
        f"🌟 <b>Режим «Единый баннер»:</b> <b>{unified_status}</b>\n"
        "<i>(Если включен, единый баннер заменяет баннеры на всех кнопках и разделах)</i>\n\n"
        "<b>Текущие баннеры:</b>\n"
        f"• 🌟 Единый баннер: <b>{get_status('unified')}</b>\n"
        f"• 📦 Основное меню: <b>{get_status('menu')}</b>\n"
        f"• 👤 Профиль: <b>{get_status('profile')}</b>\n"
        f"• 🛒 Marketplace: <b>{get_status('marketplace')}</b>\n"
        f"• 🤝 Помощь в работе: <b>{get_status('help')}</b>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌟 Установить Единый баннер", callback_data="admin_set_banner_unified")],
            [InlineKeyboardButton(text=f"🔘 {toggle_text}", callback_data="admin_toggle_unified_banner")],
            [
                InlineKeyboardButton(text="📦 Меню", callback_data="admin_set_banner_menu"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="admin_set_banner_profile")
            ],
            [
                InlineKeyboardButton(text="🛒 Marketplace", callback_data="admin_set_banner_marketplace"),
                InlineKeyboardButton(text="🤝 Помощь", callback_data="admin_set_banner_help")
            ],
            [InlineKeyboardButton(text="🔄 Сбросить баннеры к стандартным", callback_data="admin_reset_banners")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_main")]
        ]
    )

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_toggle_unified_banner")
async def cb_admin_toggle_unified(callback: CallbackQuery):
    is_now_on = await db.toggle_unified_banner()
    state_str = "ВКЛЮЧЕН 🟢 (отображается на всех кнопках)" if is_now_on else "ВЫКЛЮЧЕН 🔴 (для каждого раздела свой баннер)"
    await callback.answer(f"Единый баннер: {state_str}", show_alert=True)
    await cb_admin_banners_menu(callback)


@dp.callback_query(F.data == "admin_reset_banners")
async def cb_admin_reset_banners(callback: CallbackQuery):
    await db.reset_all_banners()
    await callback.answer("Все баннеры сброшены к стандартным!", show_alert=True)
    await cb_admin_banners_menu(callback)


@dp.callback_query(F.data.startswith("admin_set_banner_"))
async def cb_admin_set_banner(callback: CallbackQuery, state: FSMContext):
    section = callback.data.replace("admin_set_banner_", "")
    names = {
        "unified": "🌟 Единый баннер (для всех кнопок и разделов)",
        "menu": "📦 Основное меню",
        "profile": "👤 Профиль",
        "marketplace": "🛒 Marketplace",
        "help": "🤝 Помощь в работе"
    }
    sec_name = names.get(section, section)
    await state.set_state(AdminBannerState.waiting_for_media)
    await state.update_data(target_section=section, target_name=sec_name)

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_banners_menu")]])
    await callback.message.answer(
        f"📤 <b>Загрузка баннера для «{sec_name}»</b>\n\n"
        f"Отправьте боту прямо в этот диалог:\n"
        f"• 📷 <b>Фотографию</b>\n"
        f"• 🎬 <b>Видео (MP4)</b>\n"
        f"• 🎞 <b>GIF / Анимацию</b>\n\n"
        f"Бот автоматически определит формат и установит баннер!",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    await callback.answer()


@dp.message(AdminBannerState.waiting_for_media, F.photo | F.video | F.animation | F.document)
async def process_banner_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    section = data.get("target_section", "unified")
    sec_name = data.get("target_name", section)
    await state.clear()

    media_type = "photo"
    file_id = ""

    if message.animation:
        media_type = "animation"
        file_id = message.animation.file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        if "video" in mime or (doc.file_name and doc.file_name.endswith((".mp4", ".mov"))):
            media_type = "video"
        elif "gif" in mime or (doc.file_name and doc.file_name.endswith(".gif")):
            media_type = "animation"
        else:
            media_type = "photo"
        file_id = doc.file_id

    # Save to database
    await db.set_banner(section, media_type, file_id)

    # If setting unified, also enable unified by default
    if section == "unified":
        await db.set_bot_setting("use_unified_banner", "1")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Вернуться в меню баннеров", callback_data="admin_banners_menu")],
            [InlineKeyboardButton(text="👑 В главное меню админки", callback_data="admin_back_main")]
        ]
    )

    confirm_text = f"✅ <b>Баннер успешно сохранён!</b>\nРаздел: <b>{sec_name}</b>\nФормат: <b>{media_type.upper()}</b>\n\n<i>Предпросмотр:</i>"

    # Send preview using the uploaded file_id
    if media_type == "video":
        await message.answer_video(video=file_id, caption=confirm_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif media_type == "animation":
        await message.answer_animation(animation=file_id, caption=confirm_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await message.answer_photo(photo=file_id, caption=confirm_text, parse_mode=ParseMode.HTML, reply_markup=kb)


# --- УПРАВЛЕНИЕ РОЛЯМИ, ССЫЛКАМИ И РАССЫЛКАМИ ---

@dp.callback_query(F.data == "admin_roles_menu")
async def cb_admin_roles(callback: CallbackQuery):
    team = await db.get_team_members()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Назначить / Изменить роль", callback_data="admin_set_role_start")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_main")]
        ]
    )
    text = "👥 <b>Команда проекта и роли:</b>\n\n"
    role_icons = {"admin": "👑 Админ", "moderator": "🛡 Модератор", "curator": "🎓 Куратор/Наставник"}
    for m in team:
        r = role_icons.get(m.get("role"), m.get("role"))
        text += f"• {r}: <b>{m.get('first_name')}</b> (@{m.get('username')}) — ID: <code>{m['telegram_id']}</code>\n"

    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_set_role_start")
async def cb_admin_set_role(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminRoleState.waiting_for_user_query)
    await callback.message.answer("Введите @username или Telegram ID пользователя, которому хотите изменить роль:")
    await callback.answer()


@dp.message(AdminRoleState.waiting_for_user_query)
async def p_role_user(message: Message, state: FSMContext):
    query = message.text.strip()
    target = await db.get_worker_by_username_or_id(query)
    if not target:
        await message.answer("❌ Воркер не найден. Введите username или ID:")
        return

    await state.update_data(target_tg_id=target["telegram_id"], target_name=target.get("first_name"))
    await state.set_state(AdminRoleState.waiting_for_role_selection)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Администратор", callback_data="set_role_admin")],
            [InlineKeyboardButton(text="🛡 Модератор", callback_data="set_role_moderator")],
            [InlineKeyboardButton(text="🎓 Куратор / Наставник", callback_data="set_role_curator")],
            [InlineKeyboardButton(text="👤 Обычный воркер (Снять роль)", callback_data="set_role_worker")]
        ]
    )
    await message.answer(f"Выберите новую роль для <b>{target.get('first_name')}</b> (ID: <code>{target['telegram_id']}</code>):", parse_mode=ParseMode.HTML, reply_markup=kb)


@dp.callback_query(F.data.startswith("set_role_"))
async def cb_apply_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.replace("set_role_", "")
    data = await state.get_data()
    target_tg = data.get("target_tg_id")
    await state.clear()

    await db.update_worker_role(target_tg, role)
    await callback.message.answer(f"✅ Роль пользователя <code>{target_tg}</code> успешно обновлена на: <b>{role}</b>!", parse_mode=ParseMode.HTML)
    await notify_worker(target_tg, f"🎉 Ваша роль в проекте обновлена на: <b>{role}</b>!")
    await callback.answer("Роль обновлена!")


@dp.callback_query(F.data == "admin_links_menu")
async def cb_admin_links(callback: CallbackQuery):
    chat_url = await db.get_bot_setting("chat_url", config.DEFAULT_CHAT_URL)
    profits_url = await db.get_bot_setting("profits_url", config.DEFAULT_PROFITS_URL)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💭 Сменить ссылку на общий чат", callback_data="admin_edit_chat_link")],
            [InlineKeyboardButton(text="💰 Сменить ссылку на профиты", callback_data="admin_edit_profits_link")],
            [InlineKeyboardButton(text="🌐 Редактировать раздел «Полезное» (Магазины)", callback_data="admin_edit_shops_text")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_main")]
        ]
    )
    text = (
        f"🔗 <b>Текущие настройки ссылок:</b>\n\n"
        f"💭 Общий чат: {chat_url}\n"
        f"💰 Канал профитов: {profits_url}\n"
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_edit_chat_link")
async def cb_edit_chat_link(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminLinkState.waiting_for_chat_url)
    await callback.message.answer("Введите новую ссылку на общий чат:")
    await callback.answer()


@dp.message(AdminLinkState.waiting_for_chat_url)
async def p_chat_url(message: Message, state: FSMContext):
    url = message.text.strip()
    await state.clear()
    await db.set_bot_setting("chat_url", url)
    await message.answer(f"✅ Ссылка на общий чат обновлена:\n{url}")


@dp.callback_query(F.data == "admin_edit_profits_link")
async def cb_edit_profits_link(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminLinkState.waiting_for_profits_url)
    await callback.message.answer("Введите новую ссылку на канал профитов/выплат:")
    await callback.answer()


@dp.message(AdminLinkState.waiting_for_profits_url)
async def p_profits_url(message: Message, state: FSMContext):
    url = message.text.strip()
    await state.clear()
    await db.set_bot_setting("profits_url", url)
    await message.answer(f"✅ Ссылка на канал профитов обновлена:\n{url}")


@dp.callback_query(F.data == "admin_edit_shops_text")
async def cb_edit_shops_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminLinkState.waiting_for_shops_text)
    await callback.message.answer("Введите текст и ссылки на магазины для раздела «🌐 Полезное»:")
    await callback.answer()


@dp.message(AdminLinkState.waiting_for_shops_text)
async def p_shops_text(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    await db.set_bot_setting("shops_text", text)
    await message.answer("✅ Раздел «Полезное» успешно обновлен!")


@dp.callback_query(F.data == "admin_withdrawals_menu")
async def cb_admin_withdrawals(callback: CallbackQuery):
    pending = await db.get_pending_withdrawals()
    if not pending:
        await callback.answer("Нет ожидающих заявок на вывод.", show_alert=True)
        return

    for w in pending:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Выплатить (Crypto Bot)", callback_data=f"with_approve_{w['id']}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"with_reject_{w['id']}")
                ]
            ]
        )
        await callback.message.answer(
            f"💸 <b>Заявка #{w['id']}</b>\n"
            f"Воркер: @{w.get('username')} (ID: <code>{w['telegram_id']}</code>)\n"
            f"Сумма: <b>{w['amount']}$</b>\n"
            f"TRC(20): <code>{w['trc20_address']}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast_menu")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcastState.waiting_for_broadcast_text)
    await callback.message.answer("📢 Введите текст рассылки для ВСЕХ воркеров бота:")
    await callback.answer()


@dp.message(AdminBroadcastState.waiting_for_broadcast_text)
async def p_admin_bc(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()
    # Fetch all approved workers
    workers = await db.get_team_members()
    count = 0
    for w in workers:
        try:
            await bot.send_message(w["telegram_id"], f"📢 <b>Объявление от Администрации:</b>\n\n{text}", parse_mode=ParseMode.HTML)
            count += 1
        except Exception:
            pass
    await message.answer(f"✅ Рассылка доставлена {count} сотрудникам!")


@dp.callback_query(F.data == "admin_back_main")
async def cb_admin_back_main(callback: CallbackQuery):
    await callback.message.delete()
    await msg_admin_panel(callback.message)
    await callback.answer()


# --- 📢 ВЫКЛАДКА ПРОФИТОВ В КАНАЛ ---

@dp.callback_query(F.data == "admin_profit_channel_menu")
async def cb_admin_profit_channel_menu(callback: CallbackQuery):
    channel_id = await db.get_bot_setting("profits_channel_id", "")
    
    if channel_id:
        status_text = f"<code>{channel_id}</code>"
    else:
        status_text = f"<i>Не установлен (по умолчанию логи: {config.LOG_CHAT_ID})</i>"

    text = (
        "📢 <b>Канал для автоматической публикации профитов</b>\n\n"
        f"Текущий канал: {status_text}\n\n"
        "Формат публикации профита:\n"
        "• Ник воркера (<b>строго без @</b>)\n"
        "• Сумма профита воркера (в ₽ и $)\n"
        "• Название сервиса: MODEVA\n\n"
        "ℹ️ <i>Бот обязательно должен быть добавлен администратором в данный канал с правом публикации сообщений!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Указать / изменить ID канала", callback_data="admin_set_profit_channel")],
            [InlineKeyboardButton(text="🚀 Отправить тестовый профит", callback_data="admin_test_profit_post")],
            [InlineKeyboardButton(text="🗑 Сбросить канал к логам", callback_data="admin_reset_profit_channel")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_main")]
        ]
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "admin_set_profit_channel")
async def cb_admin_set_profit_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminProfitChannelState.waiting_for_channel_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_profit_channel_menu")]])
    await callback.message.answer(
        "📢 <b>Укажите ID или юзернейм канала для выкладки профитов:</b>\n\n"
        "Примеры:\n"
        "• Числовой ID: <code>-1004495225020</code>\n"
        "• Публичный юзернейм: <code>@modeva_profits</code>\n\n"
        "⚠️ <i>Не забудьте добавить бота @nexuss_team_bot в канал как администратора!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    await callback.answer()


@dp.message(AdminProfitChannelState.waiting_for_channel_id)
async def process_set_profit_channel(message: Message, state: FSMContext):
    raw_val = message.text.strip()
    await state.clear()

    # Clean channel link/id
    clean_val = raw_val
    if "t.me/" in clean_val:
        clean_val = "@" + clean_val.split("t.me/")[-1].replace("/", "").strip()

    await db.set_bot_setting("profits_channel_id", clean_val)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Протестировать отправку", callback_data="admin_test_profit_post")],
            [InlineKeyboardButton(text="📢 Меню канала профитов", callback_data="admin_profit_channel_menu")],
            [InlineKeyboardButton(text="👑 В главное меню админки", callback_data="admin_back_main")]
        ]
    )

    await message.answer(
        f"✅ <b>Канал выкладки профитов сохранен!</b>\n\n"
        f"Установлен: <code>{clean_val}</code>\n\n"
        f"Теперь каждый оформленный заказ по промокоду будет автоматически публиковать профит воркера без знака @ в этот канал.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


@dp.callback_query(F.data == "admin_test_profit_post")
async def cb_admin_test_profit_post(callback: CallbackQuery):
    worker_nick = callback.from_user.username or callback.from_user.first_name or "Worker"
    success, msg = await post_profit_to_channel(
        worker_name=worker_nick,
        profit_rub=35000.0,
        total_order_rub=43750.0,
        order_number="BM-TEST-001"
    )
    if success:
        await callback.answer("✅ Тестовый профит успешно отправлен в канал!", show_alert=True)
    else:
        await callback.message.answer(
            f"❌ <b>Ошибка при отправке в канал:</b>\n<code>{msg}</code>\n\n"
            f"Убедитесь, что:\n"
            f"1. ID или юзернейм канала указан правильно\n"
            f"2. Бот добавлен в канал с правами Администратора (публикация сообщений)",
            parse_mode=ParseMode.HTML
        )
        await callback.answer()


@dp.callback_query(F.data == "admin_reset_profit_channel")
async def cb_admin_reset_profit_channel(callback: CallbackQuery):
    await db.set_bot_setting("profits_channel_id", "")
    await callback.answer("Канал выкладки профитов сброшен (используется канал логов)!", show_alert=True)
    await cb_admin_profit_channel_menu(callback)


from aiohttp import web

# --- 🌐 Lightweight Web Server for Render Free Tier & Internal API Bridge ---

async def handle_root(request: web.Request):
    return web.Response(text="Bot is running and healthy! 🚀\nTelegram: @nexuss_team_bot", content_type="text/plain")

async def handle_health(request: web.Request):
    return web.json_response({
        "status": "ok",
        "bot": "@nexuss_team_bot",
        "service": "MODEVA CRM"
    })

async def handle_internal_promo(request: web.Request):
    code = request.query.get("code", "").strip()
    if not code:
        return web.json_response({"valid": False, "discount_percent": 0})
    worker = await db.get_worker_by_promo(code)
    if worker:
        return web.json_response({
            "valid": True,
            "promo": worker.get("promo_code"),
            "discount_percent": worker.get("discount_percent", 10),
            "worker_name": worker.get("first_name", "")
        })
    return web.json_response({"valid": False, "discount_percent": 0})

async def handle_internal_order(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    product_id = int(data.get("product_id", 0))
    promo_code = data.get("promo_code", "")
    client_name = data.get("client_name", "Клиент")
    client_phone = data.get("client_phone", "")
    client_address = data.get("client_address", "")

    product = await db.get_product_by_id(product_id)
    if not product:
        return web.json_response({"status": "error", "message": "Product not found"}, status=404)

    worker = await db.get_worker_by_promo(promo_code) if promo_code else None
    discount_pct = worker.get("discount_percent", 0) if worker else 0

    orig_price = float(product["price"])
    final_price = orig_price * (1.0 - (discount_pct / 100.0))

    client, _, _ = await db.register_client(
        name=client_name,
        phone=client_phone,
        email=f"client_{client_phone}@modeva.store",
        password="auto",
        promo_code=promo_code
    )

    order = await db.create_order(
        client_id=client["id"] if client else None,
        worker_id=worker["id"] if worker else None,
        product_id=product["id"],
        product_title=product["title"],
        original_price=orig_price,
        discount_percent=discount_pct,
        final_price=final_price,
        client_name=client_name,
        client_phone=client_phone,
        client_address=client_address,
        promo_code=promo_code or ""
    )

    worker_payout = order.get("worker_payout", 0.0)
    mentor_payout = order.get("mentor_payout", 0.0)
    mentor_worker = order.get("mentor_worker")

    if worker:
        payout_usd = round(worker_payout / config.USD_RUB_RATE, 2)
        worker_notif = (
            f"💰 <b>НОВАЯ ОПЛАТА ЗАКАЗА!</b>\n\n"
            f"🧾 <b>Номер заказа:</b> <code>#{order['order_number']}</code>\n"
            f"📦 <b>Товар:</b> {product['title']}\n"
            f"💵 <b>Исходная цена:</b> {orig_price:,.0f} ₽\n"
            f"🏷 <b>Скидка:</b> {discount_pct}%\n"
            f"💳 <b>Итого к оплате:</b> <b>{final_price:,.0f} ₽</b>\n\n"
            f"💸 <b>ВАША ВЫПЛАТА:</b> <b>+{worker_payout:,.0f} ₽ (~{payout_usd}$)</b>\n"
            f"(зачислено на баланс в профиле)\n\n"
            f"👤 <b>Покупатель:</b> {client_name}\n"
            f"📱 <b>Телефон:</b> <code>{client_phone}</code>\n"
            f"📍 <b>Адрес доставки:</b> {client_address}"
        )
        if mentor_worker:
            worker_notif += f"\n\n🎓 <i>(Учтена доля наставника @{mentor_worker.get('username')}: 20%)</i>"
        await notify_worker(worker["telegram_id"], worker_notif)

        if mentor_worker and mentor_payout > 0:
            mentor_usd = round(mentor_payout / config.USD_RUB_RATE, 2)
            mentor_notif = (
                f"🎓 <b>ПРОФИТ ВАШЕГО УЧЕНИКА!</b>\n\n"
                f"👤 Ученик: @{worker.get('username') or worker['telegram_id']}\n"
                f"📦 Заказ: #{order['order_number']} на сумму <b>{final_price:,.0f} ₽</b>\n"
                f"💰 <b>Ваша доля куратора (20%):</b> <b>+{mentor_payout:,.0f} ₽ (~{mentor_usd}$)</b>\n"
                f"(баланс наставника пополнен)"
            )
            await notify_worker(mentor_worker["telegram_id"], mentor_notif)

        worker_mention = f"@{worker.get('username')}" if worker.get('username') else f"ID: {worker['telegram_id']}"
        channel_log = (
            f"🛍 <b>НОВАЯ ПОКУПКА В МАГАЗИНЕ!</b>\n\n"
            f"🧾 <b>Заказ:</b> <code>#{order['order_number']}</code>\n"
            f"👨‍💻 <b>Воркер:</b> {worker_mention}\n"
            f"🏷 <b>Промокод:</b> <code>{promo_code}</code> (-{discount_pct}%)\n"
            f"📦 <b>Товар:</b> {product['title']}\n"
            f"💳 <b>Оплачено:</b> <b>{final_price:,.0f} ₽</b>\n"
            f"💰 <b>Выплата воркеру:</b> <b>{worker_payout:,.0f} ₽</b>\n"
        )
        if mentor_worker:
            channel_log += f"🎓 <b>Доля куратора @{mentor_worker.get('username')}:</b> <b>{mentor_payout:,.0f} ₽</b>\n"
        channel_log += (
            f"👤 <b>Покупатель:</b> {client_name} (📱 <code>{client_phone}</code>)\n"
            f"📍 <b>Адрес:</b> {client_address}"
        )
        await log_to_channel(channel_log)

        # Post profit to dedicated channel (worker nick without @)
        worker_clean_nick = (worker.get("username") or worker.get("first_name") or f"Воркер #{worker['id']}").replace("@", "").strip()
        await post_profit_to_channel(
            worker_name=worker_clean_nick,
            profit_rub=worker_payout,
            total_order_rub=final_price,
            order_number=order.get("order_number", "")
        )

    return web.json_response({"status": "ok", "order": order})

async def handle_internal_action_log(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error"}, status=400)

    promo_code = data.get("promo_code", "")
    if not promo_code:
        return web.json_response({"status": "skipped"})

    worker = await db.get_worker_by_promo(promo_code)
    if not worker or not worker.get("action_logs", 1):
        return web.json_response({"status": "disabled"})

    action_text = f"⚡️ <b>[Логи сайта]</b> Клиент <b>{data.get('client_name')}</b> {data.get('action')}"
    if data.get("product_title"):
        action_text += f": «{data.get('product_title')}»"

    await notify_worker(worker["telegram_id"], action_text)
    return web.json_response({"status": "ok"})


# --- Runner ---
async def start_bot():
    logger.info("Initializing database...")
    await db.init_db()

    # Web server on PORT for Render free tier
    port = int(os.environ.get("PORT", "8080"))
    web_app = web.Application()
    web_app.router.add_get("/", handle_root)
    web_app.router.add_get("/health", handle_health)
    web_app.router.add_get("/api/internal/promo", handle_internal_promo)
    web_app.router.add_post("/api/internal/order", handle_internal_order)
    web_app.router.add_post("/api/internal/action-log", handle_internal_action_log)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Render Web Server started on port {port} (Listening on 0.0.0.0:{port})")

    logger.info("Starting Telegram Bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    try:
        asyncio.run(start_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
