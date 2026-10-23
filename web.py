import os
import json
import logging
import socketio
from fastapi import FastAPI, Request, HTTPException, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List

import config
import database as db

logger = logging.getLogger("web")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "modeva2026")

app = FastAPI(title="MODEVA Marketplace")

@app.on_event("startup")
async def on_startup():
    logger.info("Initializing database on web app startup...")
    try:
        await db.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

# Socket.IO Real-time Server
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
sio_asgi = socketio.ASGIApp(sio)
app.mount("/socket.io", sio_asgi)

# Native WebSockets Connection Manager
class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for ws in list(self.active_connections):
            try:
                await ws.send_json(data)
            except Exception:
                pass

ws_manager = WebSocketConnectionManager()

async def broadcast_delivery_update(stage_data: dict):
    try:
        await sio.emit("delivery_stage_update", stage_data)
    except Exception as e:
        logger.warning(f"Error emitting via socketio: {e}")
    await ws_manager.broadcast(stage_data)

async def broadcast_support_message(msg_data: dict):
    try:
        await sio.emit("support_message", msg_data)
    except Exception as e:
        logger.warning(f"Error emitting support message via socketio: {e}")
    await ws_manager.broadcast({
        "type": "support_message",
        "data": msg_data
    })

@sio.event
async def connect(sid, environ):
    stage = await db.get_delivery_stage("GLOBAL")
    await sio.emit("delivery_stage_update", stage, to=sid)

@sio.event
async def subscribe_order(sid, data):
    order_num = data.get("order_number", "GLOBAL") if isinstance(data, dict) else str(data or "GLOBAL")
    stage = await db.get_delivery_stage(order_num)
    await sio.emit("delivery_stage_update", stage, to=sid)

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


class LoginRequest(BaseModel):
    login: str
    password: Optional[str] = ""


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


class DeliveryStageUpdateRequest(BaseModel):
    stage: int
    order_number: Optional[str] = "GLOBAL"


class SupportMessageRequest(BaseModel):
    session_id: str
    message: str
    client_name: Optional[str] = "Покупатель"
    client_phone: Optional[str] = ""


class SupportReplyRequest(BaseModel):
    session_id: str
    message: str
    manager_name: Optional[str] = "Консьерж MODEVA"


class AdminLoginRequest(BaseModel):
    password: str


class AdminProductCreateRequest(BaseModel):
    title: str
    category: str
    price: float
    image_url: str
    description: Optional[str] = ""


class AdminProductPriceUpdateRequest(BaseModel):
    price: float


class AdminOrderStatusUpdateRequest(BaseModel):
    status: str
    delivery_stage: Optional[int] = None


class AdminPromoCreateRequest(BaseModel):
    promo_code: str
    discount_percent: int


class AdminSettingsUpdateRequest(BaseModel):
    site_name: Optional[str] = "MODEVA"
    site_hero_title: Optional[str] = None
    site_hero_subtitle: Optional[str] = None
    broadcast_message: Optional[str] = None


# --- Customer Marketplace Routes ---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request, ref: Optional[str] = None, promo: Optional[str] = None):
    active_promo = (promo or ref or "").strip()
    discount = 0
    broadcast_msg = None

    settings = await db.get_site_settings()
    support_username = settings.get("support_username", config.SUPPORT_USERNAME)
    site_name = settings.get("site_name", "MODEVA")
    site_hero_title = settings.get("site_hero_title", "Не просто маркетплейс, a MODEVA — стиль вне времени")
    site_hero_subtitle = settings.get("site_hero_subtitle", "Ваш надёжный посредник с продавцом.")

    announcement = await db.get_bot_setting("broadcast_announcement", "")
    if announcement:
        broadcast_msg = announcement

    if active_promo:
        worker = await db.get_worker_by_promo(active_promo)
        if worker:
            discount = worker.get("discount_percent", 0)
            if not broadcast_msg:
                latest_bc = await db.get_latest_broadcast_for_promo(active_promo)
                if latest_bc:
                    broadcast_msg = latest_bc["message"]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "promo_code": active_promo,
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
    try:
        products = await db.get_catalog_products(category=category, search=search, promo_code=promo)
    except Exception as e:
        logger.warning(f"Error fetching catalog, initializing DB: {e}")
        await db.init_db()
        products = await db.get_catalog_products(category=category, search=search, promo_code=promo)

    discount_pct = 0
    if promo:
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
    try:
        client, worker, is_new = await db.register_client(
            name=data.name,
            phone=data.phone,
            email=data.email,
            password=data.password,
            promo_code=data.promo_code
        )
    except Exception as e:
        logger.warning(f"Error in register_client, initializing database fallback: {e}")
        try:
            await db.init_db()
            client, worker, is_new = await db.register_client(
                name=data.name,
                phone=data.phone,
                email=data.email,
                password=data.password,
                promo_code=data.promo_code
            )
        except Exception as err2:
            logger.error(f"Fatal registration error: {err2}")
            raise HTTPException(status_code=400, detail="Ошибка при создании аккаунта. Пожалуйста, проверьте данные.")

    return {"status": "ok", "client": client, "worker_linked": bool(worker)}


@app.post("/api/login")
async def api_login(data: LoginRequest):
    client = await db.verify_client_login(data.login, data.password)
    if not client:
        # Graceful auto-creation if not exists
        client, _, _ = await db.register_client(
            name=data.login.split("@")[0] or "Покупатель",
            phone=data.login if "@" not in data.login else "",
            email=data.login if "@" in data.login else f"{data.login}@modeva.store",
            password=data.password or "123456"
        )
    return {"status": "ok", "client": client}


@app.post("/api/orders")
async def api_create_order(data: OrderRequest):
    product = await db.get_product_by_id(data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    worker = await db.get_worker_by_promo(data.promo_code) if data.promo_code else None
    discount_pct = worker.get("discount_percent", 0) if worker else 0

    orig_price = float(product["price"])
    final_price = round(orig_price * (1 - discount_pct / 100), 2)

    client, _, _ = await db.register_client(
        name=data.client_name,
        phone=data.client_phone,
        email=f"client_{data.client_phone.replace('+', '').replace(' ', '')}@modeva.store",
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

    return {"status": "ok", "order": order}


@app.post("/api/action-log")
async def api_action_log(data: ActionLogRequest):
    return {"status": "ok"}


# --- 🚚 3D Interactive Delivery Tracking Endpoints ---

@app.get("/tracking")
async def tracking_page():
    return RedirectResponse(url="/", status_code=302)


@app.get("/api/delivery-stage")
async def api_get_delivery_stage(order: Optional[str] = "GLOBAL"):
    order_num = (order or "GLOBAL").strip().upper()
    data = await db.get_delivery_stage(order_num)
    return {"status": "ok", "delivery": data}


@app.post("/api/internal/delivery-stage")
async def api_update_delivery_stage(data: DeliveryStageUpdateRequest):
    updated = await db.set_delivery_stage(data.stage, data.order_number)
    await broadcast_delivery_update(updated)
    return {"status": "ok", "delivery": updated}


@app.websocket("/ws/tracking")
@app.websocket("/ws/tracking/{order_number}")
async def websocket_tracking(websocket: WebSocket, order_number: Optional[str] = "GLOBAL"):
    await ws_manager.connect(websocket)
    ord_num = (order_number or "GLOBAL").strip().upper()
    try:
        curr = await db.get_delivery_stage(ord_num)
        await websocket.send_json(curr)
        while True:
            msg = await websocket.receive_text()
            if "ping" in msg:
                await websocket.send_text("pong")
            elif "subscribe" in msg:
                try:
                    obj = json.loads(msg)
                    target_ord = obj.get("order_number", ord_num)
                    stg = await db.get_delivery_stage(target_ord)
                    await websocket.send_json(stg)
                except Exception:
                    pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# --- 💬 On-Site Live Support Chat Endpoints ---

@app.post("/api/support/message")
async def api_send_support_message(data: SupportMessageRequest):
    session_id = data.session_id.strip()
    msg_text = data.message.strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    saved_msg = await db.save_support_message(
        session_id=session_id,
        sender="client",
        message=msg_text,
        client_name=data.client_name,
        client_phone=data.client_phone
    )

    await broadcast_support_message(saved_msg)

    # Smart Concierge Auto-reply for instant customer satisfaction
    lowered = msg_text.lower()
    auto_reply = None
    if any(k in lowered for k in ["заказ", "доставк", "где", "трек", "статус"]):
        stg = await db.get_delivery_stage("GLOBAL")
        auto_reply = (
            f"Здравствуйте, {data.client_name}! Вы можете отслеживать перемещение вашего заказа в интерактивном 3D-трекинге на сайте. "
            f"Текущий этап: «{stg.get('stage_name', 'В обработке')}» ({stg.get('stage_subtitle', '')}). "
            f"Курьерская служба: {stg.get('carrier', 'MODEVA White Glove')}."
        )
    elif any(k in lowered for k in ["промокод", "скидк", "бонус", "реферал", "код"]):
        auto_reply = (
            f"Здравствуйте! Для получения эксклюзивной скидки используйте промокод MODEVA-VIP при оформлении заказа или регистрации. "
            f"Скидка рассчитывается моментально!"
        )
    elif any(k in lowered for k in ["оплат", "карт", "деньг", "гарант", "чек"]):
        auto_reply = (
            f"Каждая покупка в бутике MODEVA защищена гарантией подлинности и экспертной опломбировкой. "
            f"Оплата происходит безопасно. Дежурный консьерж службы заботы подключен к диалогу!"
        )

    if auto_reply:
        concierge_msg = await db.save_support_message(
            session_id=session_id,
            sender="support",
            message=auto_reply,
            client_name="Консьерж MODEVA"
        )
        await broadcast_support_message(concierge_msg)

    return {"status": "ok", "message": saved_msg, "auto_reply": bool(auto_reply)}


@app.get("/api/support/messages")
async def api_get_support_messages(session_id: str):
    if not session_id:
        return {"status": "ok", "messages": []}
    messages = await db.get_support_messages(session_id)
    return {"status": "ok", "messages": messages}


@app.post("/api/internal/support/reply")
async def api_internal_support_reply(data: SupportReplyRequest):
    session_id = data.session_id.strip()
    msg_text = data.message.strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    saved_msg = await db.save_support_message(
        session_id=session_id,
        sender="support",
        message=msg_text,
        client_name=data.manager_name or "Консьерж MODEVA"
    )
    await broadcast_support_message(saved_msg)
    return {"status": "ok", "message": saved_msg}


@app.get("/api/internal/support/sessions")
async def api_internal_support_sessions(limit: int = 20):
    sessions = await db.get_recent_support_sessions(limit)
    return {"status": "ok", "sessions": sessions}


# --- 👑 Pure Marketplace Web Admin Dashboard API ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    settings = await db.get_site_settings()
    stage = await db.get_delivery_stage("GLOBAL")
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "site_name": settings.get("site_name", "MODEVA"),
            "current_stage": stage.get("current_stage", 1)
        }
    )


@app.post("/api/admin/login")
async def api_admin_login(data: AdminLoginRequest):
    if data.password.strip() == ADMIN_SECRET:
        return {"status": "ok", "token": "modeva_admin_authorized"}
    raise HTTPException(status_code=401, detail="Неверный пароль администратора")


@app.get("/api/admin/stats")
async def api_admin_stats():
    stats = await db.get_marketplace_stats()
    return {"status": "ok", "stats": stats}


@app.get("/api/admin/orders")
async def api_admin_orders(limit: int = 50):
    orders = await db.get_all_orders(limit)
    return {"status": "ok", "orders": orders}


@app.post("/api/admin/orders/{order_number}/status")
async def api_admin_order_status(order_number: str, data: AdminOrderStatusUpdateRequest):
    await db.update_order_status(order_number, data.status, data.delivery_stage)
    if data.delivery_stage:
        updated = await db.set_delivery_stage(data.delivery_stage, order_number)
        await broadcast_delivery_update(updated)
    return {"status": "ok"}


@app.get("/api/admin/products")
async def api_admin_products():
    products = await db.get_all_store_products()
    return {"status": "ok", "products": products}


@app.post("/api/admin/products")
async def api_admin_create_product(data: AdminProductCreateRequest):
    product = await db.add_store_product(
        title=data.title.strip(),
        category=data.category.strip(),
        price=data.price,
        image_url=data.image_url.strip(),
        description=data.description.strip() or "Премиальное изделие MODEVA"
    )
    return {"status": "ok", "product": product}


@app.delete("/api/admin/products/{product_id}")
async def api_admin_delete_product(product_id: int):
    await db.delete_product(product_id)
    return {"status": "ok"}


@app.put("/api/admin/products/{product_id}/price")
async def api_admin_update_product_price(product_id: int, data: AdminProductPriceUpdateRequest):
    await db.update_product_price(product_id, data.price)
    return {"status": "ok"}


@app.post("/api/admin/delivery-stage")
async def api_admin_delivery_stage(data: DeliveryStageUpdateRequest):
    updated = await db.set_delivery_stage(data.stage, data.order_number)
    await broadcast_delivery_update(updated)
    return {"status": "ok", "delivery": updated}


@app.get("/api/admin/support/chats")
async def api_admin_support_chats(limit: int = 30):
    sessions = await db.get_recent_support_sessions(limit)
    return {"status": "ok", "sessions": sessions}


@app.get("/api/admin/support/messages")
async def api_admin_support_messages(session_id: str):
    msgs = await db.get_support_messages(session_id)
    await db.mark_support_messages_read(session_id)
    return {"status": "ok", "messages": msgs}


@app.post("/api/admin/support/reply")
async def api_admin_support_reply(data: SupportReplyRequest):
    session_id = data.session_id.strip()
    msg_text = data.message.strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    saved_msg = await db.save_support_message(
        session_id=session_id,
        sender="support",
        message=msg_text,
        client_name=data.manager_name or "Консьерж MODEVA"
    )
    await broadcast_support_message(saved_msg)
    return {"status": "ok", "message": saved_msg}


@app.get("/api/admin/promos")
async def api_admin_promos():
    promos = await db.get_all_promos()
    return {"status": "ok", "promos": promos}


@app.post("/api/admin/promos")
async def api_admin_create_promo(data: AdminPromoCreateRequest):
    res = await db.create_or_update_promo(data.promo_code, data.discount_percent)
    return {"status": "ok", "promo": res}


@app.delete("/api/admin/promos/{code}")
async def api_admin_delete_promo(code: str):
    await db.delete_promo(code)
    return {"status": "ok"}


@app.get("/api/admin/settings")
async def api_admin_get_settings():
    settings = await db.get_site_settings()
    bc = await db.get_bot_setting("broadcast_announcement", "")
    settings["broadcast_announcement"] = bc
    return {"status": "ok", "settings": settings}


@app.post("/api/admin/settings")
async def api_admin_save_settings(data: AdminSettingsUpdateRequest):
    if data.site_name:
        await db.set_bot_setting("site_name", data.site_name.strip())
    if data.site_hero_title:
        await db.set_bot_setting("site_hero_title", data.site_hero_title.strip())
    if data.site_hero_subtitle:
        await db.set_bot_setting("site_hero_subtitle", data.site_hero_subtitle.strip())
    if data.broadcast_message is not None:
        await db.set_bot_setting("broadcast_announcement", data.broadcast_message.strip())
    return {"status": "ok"}
