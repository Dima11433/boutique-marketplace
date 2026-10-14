import asyncio
import os
import sys
import httpx
from aiohttp import web

# Set encoding
sys.stdout.reconfigure(encoding="utf-8")

import config
import database as db
import bot

async def test_bot_web_server():
    print("=== Testing Bot Web Server for Render ===")
    await db.init_db()

    # Create worker with promo code for testing
    worker = await db.create_worker(
        telegram_id=999888777,
        username="render_test_worker",
        first_name="RenderTester",
        promo_code="TEST-RENDER-15",
        discount_percent=15
    )

    # Setup web application on port 8089
    test_port = 8089
    app = web.Application()
    app.router.add_get("/", bot.handle_root)
    app.router.add_get("/health", bot.handle_health)
    app.router.add_get("/api/internal/promo", bot.handle_internal_promo)
    app.router.add_post("/api/internal/order", bot.handle_internal_order)
    app.router.add_post("/api/internal/action-log", bot.handle_internal_action_log)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", test_port)
    await site.start()
    print(f"Test web server started on 127.0.0.1:{test_port}")

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{test_port}") as client:
        # 1. Test Root
        res_root = await client.get("/")
        assert res_root.status_code == 200, f"Expected 200, got {res_root.status_code}"
        print(f"[OK] 1. Root route: {res_root.text}")

        # 2. Test Health
        res_health = await client.get("/health")
        assert res_health.status_code == 200, f"Expected 200, got {res_health.status_code}"
        assert res_health.json()["status"] == "ok"
        print(f"[OK] 2. Health check route: {res_health.json()}")

        # 3. Test Promo Check
        res_promo = await client.get("/api/internal/promo?code=TEST-RENDER-15")
        assert res_promo.status_code == 200
        d_promo = res_promo.json()
        assert d_promo["valid"] is True
        assert d_promo["discount_percent"] == 15
        print(f"[OK] 3. Internal promo check: {d_promo}")

        # 4. Test Action Log
        res_action = await client.post("/api/internal/action-log", json={
            "promo_code": "TEST-RENDER-15",
            "client_name": "Виктория",
            "action": "смотрит каталог",
            "product_title": "Сумка"
        })
        assert res_action.status_code == 200
        print(f"[OK] 4. Internal action log: {res_action.json()}")

        # 5. Test Order placement
        res_order = await client.post("/api/internal/order", json={
            "product_id": 1,
            "promo_code": "TEST-RENDER-15",
            "client_name": "Виктория",
            "client_phone": "+79990001122",
            "client_address": "Москва, Ленина 1"
        })
        assert res_order.status_code == 200
        d_order = res_order.json()
        assert d_order["status"] == "ok"
        print(f"[OK] 5. Internal order creation: Order #{d_order['order']['order_number']}")

    await runner.cleanup()
    print("\n>>> ALL RENDER WEB SERVER TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(test_bot_web_server())
