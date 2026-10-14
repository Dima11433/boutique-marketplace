import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8848109793:AAFXloV-AG_ZH-dq2EDs6UCL3Rnabt0gyms")
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "-1004495225020"))

ADMIN_IDS = [8391813279, 6667583896]

DEFAULT_CHAT_URL = "https://t.me/+NJRGOHnueMhjMDFh"
DEFAULT_PROFITS_URL = "https://t.me/+NJRGOHnueMhjMDFh"
DEFAULT_SHOPS_TEXT = (
    "🌐 <b>Наши официальные магазины и ресурсы:</b>\n\n"
    "1. <b>Boutique Mirelle</b> (Премиум одежда и аксессуары)\n"
    "└ Домен 1: https://boutiquemirelle.com/\n"
    "└ Домен 2: https://boutique-mirelle.com/\n\n"
    "2. <b>Mirelle Jewelry</b> (Ювелирные изделия и часы)\n"
    "└ Ссылка: https://boutique-mirelle.com/jewelry\n\n"
    "3. <b>Поддержка покупателей:</b> @kristiq_q"
)

USD_RUB_RATE = 95.0  # 1$ = 95 RUB
MIN_WITHDRAWAL_USD = 20.0  # Вывод от 20$

DOMAINS = [
    "https://boutiquemirelle.com/",
    "https://boutique-mirelle.com/"
]

SUPPORT_USERNAME = "@kristiq_q"
MANUAL_URL = "https://telegra.ph/Manual-Marketplace-Boutique-Mirelle-01-01"

DB_PATH = os.path.join(os.path.dirname(__file__), "marketplace.db")
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{SERVER_PORT}")
