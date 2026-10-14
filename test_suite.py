import asyncio
import os
import database as db

async def run_tests():
    print("=== STARTING FULL SYSTEM VERIFICATION ===")
    
    # 1. DB Init
    await db.init_db()
    print("[OK] 1. Database initialized and seeded")

    # 2. Application submission
    app_id = await db.submit_application(
        telegram_id=999888777,
        username="tester_worker",
        first_name="Алексей",
        source="Форум Lolzteam",
        time_commit="4-6 часов в день",
        experience="2 года в арбитраже и продажах брендовой одежды"
    )
    app = await db.get_application_by_id(app_id)
    assert app is not None
    assert app["status"] == "pending"
    print(f"[OK] 2. Application submitted successfully (ID: {app_id}, Status: {app['status']})")

    # 3. Admin Approval
    worker = await db.approve_application(app_id)
    assert worker is not None
    assert worker["telegram_id"] == 999888777
    initial_promo = worker["promo_code"]
    print(f"[OK] 3. Application approved! Worker created with initial promo: {initial_promo}")

    # 4. Promo code update (as in Screenshot 4: "ggg" -> 50%)
    await db.update_worker_promo(999888777, "ggg", 50)
    worker = await db.get_worker_by_tg(999888777)
    assert worker["promo_code"] == "ggg"
    assert worker["discount_percent"] == 50
    print(f"[OK] 4. Worker updated promo code to: {worker['promo_code']} (Discount: {worker['discount_percent']}%)")

    # 5. Worker settings toggle (Screenshot 3)
    worker = await db.toggle_worker_setting(999888777, "action_logs")
    worker = await db.toggle_worker_setting(999888777, "collateral_required")
    worker = await db.toggle_worker_setting(999888777, "deposit_via_support")
    assert worker["collateral_required"] == 1
    assert worker["deposit_via_support"] == 1
    print("[OK] 5. Worker custom settings toggled successfully (Settings per-worker)")

    # 6. Mass Broadcast
    await db.add_broadcast(worker["id"], "Внимание! Сегодня действует дополнительная скидка 15% на сумки Hermès!")
    latest_bc = await db.get_latest_broadcast_for_promo("ggg")
    assert latest_bc is not None
    assert "Hermès" in latest_bc["message"]
    print("[OK] 6. Mass broadcast created and retrieved for clients")

    # 7. Add Custom Listing by Worker ("Мои объявления")
    custom_prod = await db.add_worker_product(
        worker_id=worker["id"],
        title="Сумка Dior Saddle Bag Black",
        category="Сумки",
        price=180000.0,
        image_url="/static/images/p3_beigebag.png",
        description="Оригинал, кожа ягненка, идеальное состояние"
    )
    assert custom_prod is not None
    my_prods = await db.get_worker_products(worker["id"])
    assert len(my_prods) >= 1
    print(f"[OK] 7. Custom product added by worker: {custom_prod['title']}")

    # 8. Client registration under worker promo
    client, linked_worker, is_new = await db.register_client(
        name="Елена Воронина",
        phone="+79991234567",
        email="elena_luxury@mail.ru",
        password="securepass123",
        promo_code="ggg"
    )
    assert linked_worker is not None
    assert linked_worker["id"] == worker["id"]
    print(f"[OK] 8. Client {client['name']} registered and linked to worker (Promo: ggg)")

    # 9. Catalog query with promo discount
    catalog = await db.get_catalog_products(promo_code="ggg")
    assert len(catalog) >= 8
    print(f"[OK] 9. Catalog returned {len(catalog)} products (including worker custom items)")

    # 10. Order placement with discount and worker payout
    target_product = catalog[0]
    orig_price = float(target_product["price"])
    discount_pct = worker["discount_percent"] # 50%
    final_price = orig_price * (1 - discount_pct / 100) # 50% of price
    payout_pct = worker["payout_percent"] # 70%
    worker_payout = final_price * (payout_pct / 100)

    order = await db.create_order(
        client_id=client["id"],
        worker_id=worker["id"],
        product_id=target_product["id"],
        product_title=target_product["title"],
        original_price=orig_price,
        discount_percent=discount_pct,
        final_price=final_price,
        worker_payout=worker_payout,
        client_name=client["name"],
        client_phone=client["phone"],
        client_address="г. Москва, Рублевское шоссе 45",
        promo_code="ggg"
    )
    assert order is not None
    assert order["order_number"].startswith("BM-")

    # Verify worker balance updated
    updated_worker = await db.get_worker_by_tg(999888777)
    assert updated_worker["balance"] == worker_payout
    print(f"[OK] 10. Order #{order['order_number']} created! Final: {final_price:,.0f} ₽ | Worker Payout: +{worker_payout:,.0f} ₽ | Worker Balance: {updated_worker['balance']:,.0f} ₽")

    # 11. Worker clients list & search
    worker_clients = await db.get_worker_clients(worker["id"])
    assert len(worker_clients) >= 1
    assert worker_clients[0]["total_spent"] == final_price
    print(f"[OK] 11. Client verified in worker's client management list (Total spent: {worker_clients[0]['total_spent']:,.0f} ₽)")

    search_res = await db.search_worker_clients(worker["id"], "Воронина")
    assert len(search_res) == 1
    print(f"[OK] 12. Search client by name returned: {search_res[0]['name']}")

    print("\n>>> ALL 12 TESTS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())
