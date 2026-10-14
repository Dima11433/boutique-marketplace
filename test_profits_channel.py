import asyncio
import os
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

import config
import database as db
import bot

async def run_test():
    print("--- 1. Testing Bot Setting profits_channel_id ---")
    await db.init_db()
    
    # Check default
    val = await db.get_bot_setting("profits_channel_id", "")
    print(f"Initial profits_channel_id: '{val}'")
    
    # Set custom channel id
    test_channel = "-1004495225020"
    await db.set_bot_setting("profits_channel_id", test_channel)
    val2 = await db.get_bot_setting("profits_channel_id")
    assert val2 == test_channel, f"Expected {test_channel}, got {val2}"
    print(f"Updated profits_channel_id: '{val2}' - OK")

    print("\n--- 2. Testing post_profit_to_channel with different nicknames ---")
    # Case A: Nickname has '@'
    nick_with_at = "@super_worker_99"
    success, res = await bot.post_profit_to_channel(
        worker_name=nick_with_at,
        profit_rub=64000.0,
        total_order_rub=80000.0,
        order_number="BM-TEST-777"
    )
    print(f"Sent post for '{nick_with_at}': success={success}, msg={res}")

    # Case B: Plain nickname without '@'
    plain_nick = "AlexElite"
    success2, res2 = await bot.post_profit_to_channel(
        worker_name=plain_nick,
        profit_rub=120000.0,
        total_order_rub=150000.0,
        order_number="BM-TEST-888"
    )
    print(f"Sent post for '{plain_nick}': success={success2}, msg={res2}")

    print("\n--- 3. Testing Reset Setting ---")
    await db.set_bot_setting("profits_channel_id", "")
    val3 = await db.get_bot_setting("profits_channel_id", "")
    assert val3 == "", f"Expected empty, got {val3}"
    print(f"Reset profits_channel_id: '{val3}' - OK")

    print("\nAll profit channel unit tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_test())
