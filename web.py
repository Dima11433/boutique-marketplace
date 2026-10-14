import os
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List

import config
import database as db

logger = logging.getLogger("web")
BOT_API_URL = os.getenv("BOT_API_URL", "").rstrip("/")

try:
    from bot import notify_worker, log_to_channel, post_profit_to_channel
except Exception:
    async def notify_worker(*args, **kwargs): pass
    async def log_to_channel(*args, **kwargs): pass
    async def post_profit_to_channel(*args, **kwargs): return True, ""

app = FastAPI(title="MODEVA Marketplace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# --- Pydantic Schemas ---

class RegisterRequest(BaseModel):
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    password: Optional[str] = "123456"
    promo_code: Optional[str] = ""


class OrderRequest(BaseModel):
    product_id: int
    client_name: str
    client_phone: str
    client_address: str
    promo_code: Optional[str] = ""


class ActionLogRequest(BaseModel):
    action: str
    product_title: Optional[str] = ""
    client_name: Optional[str] = "Гость"
    promo_code: Optional[str] = ""


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request, ref: Optional[str] = None, promo: Optional[str] = None):
    active_promo = (promo or ref or "").strip()
    worker = None
    discount = 0
    broadcast_msg = None

    # Load dynamic site settings (support, site name, hero texts)
    settings = {}
    if BOT_API_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{BOT_API_URL}/api/internal/settings")
                if res.status_code == 200:
                    settings = res.json()
        except Exception:
            pass
    if not settings:
        settings = await db.get_site_settings()

    support_username = settings.get("support_username", config.SUPPORT_USERNAME)
    site_name = settings.get("site_name", "MODEVA")
    site_hero_title = settings.get("site_hero_title", "Не просто маркетплейс, a MODEVA — стиль вне времени")
    site_hero_subtitle = settings.get("site_hero_subtitle", "Ваш надёжный посредник с продавцом.")

    if active_promo:
        if BOT_API_URL:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(f"{BOT_API_URL}/api/internal/promo", params={"code": active_promo})
                    if res.status_code == 200 and res.json().get("valid"):
                        discount = res.json().get("discount_percent", 0)
            except Exception:
                pass
        else:
            worker = await db.get_worker_by_promo(active_promo)
            if worker:
                discount = worker.get("discount_percent", 0)
                latest_bc = await db.get_latest_broadcast_for_promo(active_promo)
                if latest_bc:
                    broadcast_msg = latest_bc["message"]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "promo_code": active_promo,
            "worker": worker,
            "discount": discount,
            "broadcast_message": broadcast_msg,
            "support_username": support_username,
            "site_name": site_name,
            "site_hero_title": site_hero_title,
            "site_hero_subtitle": site_hero_subtitle
        }
    )


@app.get("/api/products")
async def get_products(category: Optional[str] = None, search: Optional[str] = None, promo: Optional[str] = None):
    products = []
    if BOT_API_URL:
        try:
            params = {}
            if category: params["category"] = category
            if search: params["search"] = search
            if promo: params["promo_code"] = promo
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(f"{BOT_API_URL}/api/internal/catalog", params=params)
                if res.status_code == 200:
                    products = res.json().get("products", [])
        except Exception as e:
            logger.warning(f"Error fetching catalog via BOT_API_URL: {e}")

    if not products:
        products = await db.get_catalog_products(category=category, search=search, promo_code=promo)

    discount_pct = 0
    if promo:
        if BOT_API_URL:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    res = await client.get(f"{BOT_API_URL}/api/internal/promo", params={"code": promo})
                    if res.status_code == 200 and res.json().get("valid"):
                        discount_pct = res.json().get("discount_percent", 0)
            except Exception:
                pass
        else:
            worker = await db.get_worker_by_promo(promo)
            discount_pct = worker.get("discount_percent", 0) if worker else 0

    results = []
    for p in products:
        item = dict(p)
        orig_price = float(item["price"])
        if discount_pct > 0:
            final_price = round(orig_price * (1 - discount_pct / 100), 2)
            item["original_price"] = orig_price
            item["final_price"] = final_price
            item["discount_percent"] = discount_pct
        else:
            item["original_price"] = orig_price
            item["final_price"] = orig_price
            item["discount_percent"] = 0
        results.append(item)

    return {"status": "ok", "products": results, "discount_percent": discount_pct}


@app.get("/api/products/{product_id}")
async def get_product(product_id: int, promo: Optional[str] = None):
    p = await db.get_product_by_id(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Товар не найден")

    item = dict(p)
    worker = await db.get_worker_by_promo(promo) if promo else None
    discount_pct = worker.get("discount_percent", 0) if worker else 0
    orig_price = float(item["price"])

    if discount_pct > 0:
        item["original_price"] = orig_price
        item["final_price"] = round(orig_price * (1 - discount_pct / 100), 2)
        item["discount_percent"] = discount_pct
    else:
        item["original_price"] = orig_price
        item["final_price"] = orig_price
        item["discount_percent"] = 0

    return item


@app.get("/api/promo/check")
async def check_promo(code: str):
    if BOT_API_URL:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(f"{BOT_API_URL}/api/internal/promo", params={"code": code})
                if res.status_code == 200:
                    d = res.json()
                    if d.get("valid"):
                        return {
                            "valid": True,
                            "promo": d["promo"],
                            "discount_percent": d["discount_percent"],
                            "message": f"Скидка {d['discount_percent']}% успешно применена!"
                        }
                    return {"valid": False, "message": "Промокод не найден"}
        except Exception as e:
            logger.warning(f"Failed to check promo via BOT_API_URL: {e}")

    worker = await db.get_worker_by_promo(code)
    if not worker:
        return {"valid": False, "message": "Промокод не найден"}

    return {
        "valid": True,
        "promo": worker["promo_code"],
        "discount_percent": worker["discount_percent"],
        "message": f"Скидка {worker['discount_percent']}% успешно применена!"
    }


@app.post("/api/register")
async def api_register(data: RegisterRequest):
    client, worker, is_new = await db.register_client(
        name=data.name,
        phone=data.phone,
        email=data.email,
        password=data.password,
        promo_code=data.promo_code
    )

    # If linked to a worker, send notification to worker bot!
    if worker and is_new:
        user_mention = f"@{worker.get('username')}" if worker.get('username') else f"ID: {worker['telegram_id']}"
        worker_notif = (
            f"👤 <b>НОВЫЙ КЛИЕНТ ЗАКРЕПЛЕН ЗА ВАМИ!</b>\n\n"
            f"🏷 <b>Промокод:</b> <code>{worker['promo_code']}</code>\n"
            f"👤 <b>Имя:</b> {data.name}\n"
            f"📱 <b>Телефон:</b> <code>{data.phone or 'не указан'}</code>\n"
            f"✉️ <b>Email:</b> <code>{data.email or 'не указан'}</code>\n\n"
            f"🎉 Теперь любые покупки этого клиента будут приносить вам выплату!"
        )
        await notify_worker(worker["telegram_id"], worker_notif)

        channel_log = (
            f"👤 <b>РЕГИСТРАЦИЯ НОВОГО КЛИЕНТА</b>\n\n"
            f"👨‍💻 <b>Воркер:</b> {user_mention}\n"
            f"🏷 <b>Промокод:</b> <code>{worker['promo_code']}</code>\n"
            f"👤 <b>Клиент:</b> {data.name} (📱 {data.phone or 'нет'})\n"
            f"✉️ <b>Email:</b> {data.email or 'нет'}"
        )
        await log_to_channel(channel_log)

    return {"status": "ok", "client": client, "worker_linked": bool(worker)}


@app.post("/api/orders")
async def api_create_order(data: OrderRequest):
    if BOT_API_URL:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{BOT_API_URL}/api/internal/order", json=data.model_dump())
                if res.status_code == 200:
                    return res.json()
                elif res.status_code == 404:
                    raise HTTPException(status_code=404, detail="Товар не найден")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to submit order via BOT_API_URL, falling back to local: {e}")

    product = await db.get_product_by_id(data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    worker = await db.get_worker_by_promo(data.promo_code) if data.promo_code else None
    discount_pct = worker.get("discount_percent", 0) if worker else 0

    orig_price = float(product["price"])
    final_price = round(orig_price * (1 - discount_pct / 100), 2)

    # Worker payout (e.g. 70% of the sale or worker's payout_percent)
    payout_pct = worker.get("payout_percent", 70) if worker else 0
    worker_payout = round(final_price * (payout_pct / 100), 2) if worker else 0.0

    # Auto-register client if not registered
    client, _, _ = await db.register_client(
        name=data.client_name,
        phone=data.client_phone,
        email=f"client_{data.client_phone}@modeva.store",
        password="auto",
        promo_code=data.promo_code
    )

    order = await db.create_order(
        client_id=client["id"] if client else None,
        worker_id=worker["id"] if worker else None,
        product_id=product["id"],
        product_title=product["title"],
        original_price=orig_price,
        discount_percent=discount_pct,
        final_price=final_price,
        client_name=data.client_name,
        client_phone=data.client_phone,
        client_address=data.client_address,
        promo_code=data.promo_code or ""
    )

    worker_payout = order.get("worker_payout", 0.0)
    mentor_payout = order.get("mentor_payout", 0.0)
    mentor_worker = order.get("mentor_worker")

    # Send Notification to Worker
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
            f"👤 <b>Покупатель:</b> {data.client_name}\n"
            f"📱 <b>Телефон:</b> <code>{data.client_phone}</code>\n"
            f"📍 <b>Адрес доставки:</b> {data.client_address}"
        )
        if mentor_worker:
            worker_notif += f"\n\n🎓 <i>(Учтена доля наставника @{mentor_worker.get('username')}: 20%)</i>"
        await notify_worker(worker["telegram_id"], worker_notif)

        # If mentor exists, notify mentor
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

        # Send Log to Channel
        worker_mention = f"@{worker.get('username')}" if worker.get('username') else f"ID: {worker['telegram_id']}"
        channel_log = (
            f"🛍 <b>НОВАЯ ПОКУПКА В МАГАЗИНЕ!</b>\n\n"
            f"🧾 <b>Заказ:</b> <code>#{order['order_number']}</code>\n"
            f"👨‍💻 <b>Воркер:</b> {worker_mention}\n"
            f"🏷 <b>Промокод:</b> <code>{data.promo_code}</code> (-{discount_pct}%)\n"
            f"📦 <b>Товар:</b> {product['title']}\n"
            f"💳 <b>Оплачено:</b> <b>{final_price:,.0f} ₽</b>\n"
            f"💰 <b>Выплата воркеру:</b> <b>{worker_payout:,.0f} ₽</b>\n"
        )
        if mentor_worker:
            channel_log += f"🎓 <b>Доля куратора @{mentor_worker.get('username')}:</b> <b>{mentor_payout:,.0f} ₽</b>\n"
        channel_log += (
            f"👤 <b>Покупатель:</b> {data.client_name} (📱 <code>{data.client_phone}</code>)\n"
            f"📍 <b>Адрес:</b> {data.client_address}"
        )
        await log_to_channel(channel_log)

        # Post profit to dedicated channel (worker nickname strictly WITHOUT '@')
        worker_clean_nick = (worker.get("username") or worker.get("first_name") or f"Воркер #{worker['id']}").replace("@", "").strip()
        await post_profit_to_channel(
            worker_name=worker_clean_nick,
            profit_rub=worker_payout,
            total_order_rub=final_price,
            order_number=order.get("order_number", "")
        )

    return {"status": "ok", "order": order}


@app.post("/api/action-log")
async def api_action_log(data: ActionLogRequest):
    if not data.promo_code:
        return {"status": "skipped"}

    if BOT_API_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(f"{BOT_API_URL}/api/internal/action-log", json=data.model_dump())
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning(f"Failed to forward action log via BOT_API_URL: {e}")

    worker = await db.get_worker_by_promo(data.promo_code)
    if not worker or not worker.get("action_logs", 1):
        return {"status": "disabled"}

    # Worker has live logs enabled
    action_text = f"⚡️ <b>[Логи сайта]</b> Клиент <b>{data.client_name}</b> {data.action}"
    if data.product_title:
        action_text += f": «{data.product_title}»"

    await notify_worker(worker["telegram_id"], action_text)
    return {"status": "ok"}
