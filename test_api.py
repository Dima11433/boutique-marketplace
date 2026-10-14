import asyncio
from httpx import AsyncClient, ASGITransport
from web import app

async def test_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/")
        assert r.status_code == 200, f"Status {r.status_code}"
        print("[OK] GET / returned 200 OK")

        r = await ac.get("/api/products?promo=ggg")
        assert r.status_code == 200
        data = r.json()
        assert data["discount_percent"] == 50
        print(f"[OK] GET /api/products?promo=ggg returned {len(data['products'])} items with 50% discount")

        r = await ac.get("/api/promo/check?code=ggg")
        assert r.status_code == 200
        assert r.json()["valid"] is True
        print("[OK] GET /api/promo/check?code=ggg is valid")

        r = await ac.post("/api/action-log", json={
            "action": "смотрит каталог",
            "promo_code": "ggg",
            "client_name": "Тест"
        })
        assert r.status_code == 200
        print("[OK] POST /api/action-log processed")

if __name__ == "__main__":
    asyncio.run(test_api())
    print("\n>>> All API tests passed! <<<")
