import asyncio
import database as db

async def test_banners():
    print("=== TESTING BANNER SYSTEM ===")
    await db.init_db()

    # 1. Test set custom banner
    await db.set_banner("menu", "video", "BAACAgIAAxkBAAIB...")
    banner = await db.get_banner("menu")
    assert banner is not None
    assert banner["media_type"] == "video"
    assert banner["file_id"] == "BAACAgIAAxkBAAIB..."
    print(f"[OK] 1. Custom video banner set for menu: {banner['media_type']}")

    # 2. Test set animation for help
    await db.set_banner("help", "animation", "CgACAgQAAxkBAAIC...")
    banner_help = await db.get_banner("help")
    assert banner_help["media_type"] == "animation"
    print(f"[OK] 2. Animation banner set for help: {banner_help['media_type']}")

    # 3. Test set unified banner and toggle
    await db.set_banner("unified", "photo", "AgACAgIAAxkBAAID...")
    is_on = await db.toggle_unified_banner()
    assert is_on is True
    print(f"[OK] 3. Unified banner enabled: {is_on}")

    # Now get_banner("menu") should return the unified photo banner!
    active_for_menu = await db.get_banner("menu")
    assert active_for_menu["file_id"] == "AgACAgIAAxkBAAID..."
    print(f"[OK] 4. When unified banner is ON, get_banner('menu') returns unified banner ({active_for_menu['media_type']})")

    # Toggle off
    is_on = await db.toggle_unified_banner()
    assert is_on is False
    active_for_menu_off = await db.get_banner("menu")
    assert active_for_menu_off["media_type"] == "video"
    print(f"[OK] 5. When unified banner is OFF, get_banner('menu') returns section video banner ({active_for_menu_off['media_type']})")

    # Reset all banners
    await db.reset_all_banners()
    reset_banner = await db.get_banner("menu")
    assert reset_banner is None
    print("[OK] 6. All banners reset cleanly back to default artwork!")

    print("\n>>> ALL BANNER TESTS PASSED! <<<")

if __name__ == "__main__":
    asyncio.run(test_banners())
