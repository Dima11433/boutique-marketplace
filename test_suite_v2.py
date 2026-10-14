import asyncio
import os
import database as db
import config

async def run_v2_tests():
    print("=== STARTING FULL V2 VERIFICATION ===")
    await db.init_db()
    print("[OK] 1. Database initialized and seeded")

    # Verify default admins
    admin1 = await db.get_worker_by_tg(8391813279)
    admin2 = await db.get_worker_by_tg(6667583896)
    assert admin1 and admin1["role"] == "admin"
    assert admin2 and admin2["role"] == "admin"
    print(f"[OK] 2. Default Admins verified: {admin1['telegram_id']}, {admin2['telegram_id']}")

    # Create curator/mentor
    curator = await db.create_worker(555111222, "master_curator", "Олег Наставник", role="curator")
    await db.update_worker_role(555111222, "curator")
    curator = await db.get_worker_by_tg(555111222)
    assert curator["role"] == "curator"
    print(f"[OK] 3. Curator created: @{curator['username']} (role: {curator['role']})")

    # Create student worker
    student = await db.create_worker(777333444, "newbie_worker", "Денис Ученик", promo_code="denis_shop")
    print(f"[OK] 4. Student worker created: @{student['username']}")

    # Apply to mentor
    app_id = await db.apply_to_mentor(student["id"], curator["id"])
    apps = await db.get_mentor_pending_applications(curator["id"])
    assert len(apps) >= 1
    print(f"[OK] 5. Student submitted application to mentor (App ID: {app_id})")

    # Mentor accepts
    accepted_app = await db.accept_mentor_application(app_id)
    assert accepted_app is not None
    student = await db.get_worker_by_tg(777333444)
    assert student["mentor_id"] == curator["id"]
    print(f"[OK] 6. Mentor accepted student! Student linked to mentor: {student['mentor_id']}")

    # Client purchases item with student's promo
    # Total price 100 000 RUB:
    # Student gets 60% (60 000 RUB = ~631.58$), Curator gets 20% (20 000 RUB = ~210.53$), Team gets 20%
    order = await db.create_order(
        client_id=1,
        worker_id=student["id"],
        product_id=1,
        product_title="Тестовый лот",
        original_price=100000.0,
        discount_percent=0,
        final_price=100000.0,
        client_name="Виктория Покупатель",
        client_phone="+79998881122",
        client_address="Москва",
        promo_code="denis_shop"
    )
    assert order["worker_payout"] == 60000.0
    assert order["mentor_payout"] == 20000.0
    print(f"[OK] 7. Order with mentor split verified: Student +{order['worker_payout']} RUB | Mentor +{order['mentor_payout']} RUB")

    # Check updated balances in USD
    student = await db.get_worker_by_tg(777333444)
    curator = await db.get_worker_by_tg(555111222)
    assert student["balance"] > 0
    assert curator["balance"] > 0
    print(f"[OK] 8. Balances credited: Student={student['balance']}$ | Curator={curator['balance']}$")

    # Set TRC20 wallet
    await db.set_worker_wallet(student["telegram_id"], "TYDzsYUE22q5w89pP9sY")
    student = await db.get_worker_by_tg(777333444)
    assert student["trc20_wallet"] == "TYDzsYUE22q5w89pP9sY"
    print(f"[OK] 9. TRC20 wallet saved: {student['trc20_wallet']}")

    # Create withdrawal request (>= 20$)
    wid = await db.create_withdrawal(student["id"], student["telegram_id"], student["username"], 50.0, student["trc20_wallet"])
    student = await db.get_worker_by_tg(777333444)
    assert student["frozen_balance"] == 50.0
    print(f"[OK] 10. Withdrawal request created (#{wid}): 50$ frozen")

    # Admin approves payout via Crypto Bot
    w = await db.process_withdrawal(wid, approve=True)
    assert w["status"] == "pending" # returned row before update
    student = await db.get_worker_by_tg(777333444)
    assert student["frozen_balance"] == 0.0
    print(f"[OK] 11. Withdrawal approved! Frozen balance released.")

    # Mentorship detach after 5 profits simulation
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("UPDATE workers SET mentor_profits_count = 5 WHERE id = ?", (student["id"],))
        await conn.commit()

    student = await db.get_worker_by_tg(777333444)
    assert student["mentor_profits_count"] == 5
    await db.detach_mentor(student["id"])
    student = await db.get_worker_by_tg(777333444)
    assert student["mentor_id"] is None
    print("[OK] 12. Student successfully detached from mentor after 5 profits!")

    # Now purchase again: student should receive full 80%
    order2 = await db.create_order(
        client_id=1,
        worker_id=student["id"],
        product_id=1,
        product_title="Тестовый лот 2",
        original_price=100000.0,
        discount_percent=0,
        final_price=100000.0,
        client_name="Виктория Покупатель",
        client_phone="+79998881122",
        client_address="Москва",
        promo_code="denis_shop"
    )
    assert order2["worker_payout"] == 80000.0
    assert order2["mentor_payout"] == 0.0
    print(f"[OK] 13. Detached student now receives full 80% ({order2['worker_payout']} RUB)")

    print("\n>>> ALL V2 SYSTEM TESTS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    asyncio.run(run_v2_tests())
