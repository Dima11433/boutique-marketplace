import aiosqlite
import os
import random
import string
from datetime import datetime
import config
from config import DB_PATH, USD_RUB_RATE

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        
        # Workers table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            status TEXT DEFAULT 'approved',
            role TEXT DEFAULT 'worker',
            promo_code TEXT UNIQUE NOT NULL,
            discount_percent INTEGER DEFAULT 10,
            payout_percent INTEGER DEFAULT 80,
            action_logs INTEGER DEFAULT 1,
            collateral_required INTEGER DEFAULT 0,
            deposit_via_support INTEGER DEFAULT 0,
            chat_alias TEXT DEFAULT 'Менеджер Mirelle',
            balance REAL DEFAULT 0.0,
            frozen_balance REAL DEFAULT 0.0,
            trc20_wallet TEXT DEFAULT '',
            mentor_id INTEGER NULL,
            mentor_profits_count INTEGER DEFAULT 0,
            is_mentor INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mentor_id) REFERENCES workers(id) ON DELETE SET NULL
        );
        """)

        # Migration columns for workers if table already existed
        existing_cols = []
        async with db.execute("PRAGMA table_info(workers)") as cursor:
            async for row in cursor:
                existing_cols.append(row[1])

        new_cols = [
            ("role", "TEXT DEFAULT 'worker'"),
            ("frozen_balance", "REAL DEFAULT 0.0"),
            ("trc20_wallet", "TEXT DEFAULT ''"),
            ("mentor_id", "INTEGER NULL"),
            ("mentor_profits_count", "INTEGER DEFAULT 0"),
            ("is_mentor", "INTEGER DEFAULT 0")
        ]
        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                try:
                    await db.execute(f"ALTER TABLE workers ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # Migration columns for orders if table already existed
        existing_order_cols = []
        async with db.execute("PRAGMA table_info(orders)") as cursor:
            async for row in cursor:
                existing_order_cols.append(row[1])

        if "mentor_payout" not in existing_order_cols:
            try:
                await db.execute("ALTER TABLE orders ADD COLUMN mentor_payout REAL DEFAULT 0.0")
            except Exception:
                pass

        # Seed super admins
        for admin_id in config.ADMIN_IDS:
            await db.execute("""
                INSERT INTO workers (telegram_id, username, first_name, promo_code, role, status)
                VALUES (?, 'admin', 'Администратор', ?, 'admin', 'approved')
                ON CONFLICT(telegram_id) DO UPDATE SET role = 'admin', status = 'approved'
            """, (admin_id, f"admin_{admin_id % 1000}"))

        # Applications table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            source TEXT,
            time_commitment TEXT,
            experience TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Clients table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT UNIQUE,
            password TEXT,
            promo_used TEXT,
            balance REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL
        );
        """)

        # Products table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            image_url TEXT NOT NULL,
            description TEXT,
            condition TEXT DEFAULT 'Новое с биркой',
            is_featured INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL
        );
        """)

        # Orders table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            client_id INTEGER,
            worker_id INTEGER,
            product_id INTEGER,
            product_title TEXT,
            original_price REAL,
            discount_percent INTEGER DEFAULT 0,
            final_price REAL,
            worker_payout REAL,
            mentor_payout REAL DEFAULT 0.0,
            client_name TEXT,
            client_phone TEXT,
            client_address TEXT,
            promo_code TEXT,
            status TEXT DEFAULT 'Оплачен',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );
        """)

        # Withdrawals table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            amount REAL NOT NULL,
            trc20_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        """)

        # Internal transfers table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_worker_id INTEGER NOT NULL,
            to_worker_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_worker_id) REFERENCES workers(id) ON DELETE CASCADE,
            FOREIGN KEY (to_worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        """)

        # Mentor applications table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS mentor_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            mentor_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES workers(id) ON DELETE CASCADE,
            FOREIGN KEY (mentor_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        """)

        # Broadcasts table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
        );
        """)

        # Bot dynamic settings table (chat url, profits url, shops text, manual url, unified banner)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL
        );
        """)

        # Bot banners table (for photo, video, gif/animation per section or unified)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_banners (
            section TEXT PRIMARY KEY,
            media_type TEXT NOT NULL,
            file_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        default_settings = {
            "chat_url": config.DEFAULT_CHAT_URL,
            "profits_url": config.DEFAULT_PROFITS_URL,
            "shops_text": config.DEFAULT_SHOPS_TEXT,
            "manual_url": config.MANUAL_URL,
            "use_unified_banner": "0",
            "profits_channel_id": ""
        }
        for k, v in default_settings.items():
            await db.execute("""
                INSERT INTO bot_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
            """, (k, v))

        await db.commit()

    # Seed products if empty
    await seed_default_products()


async def seed_default_products():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM products WHERE worker_id IS NULL") as cursor:
            count = (await cursor.fetchone())[0]
            if count > 0:
                return

        default_products = [
            (
                "Антрацитовый кожаный портфель Hermès Sac à Dépêches",
                "Сумки",
                250000.0,
                "/static/images/p1_briefcase.png",
                "Изысканный мужской портфель из зернистой кожи Togo антрацитового цвета. Фурнитура из палладия, идеальное состояние.",
                "Идеальное"
            ),
            (
                "Антрацитовый чемодан Louis Vuitton Horizon 55",
                "Сумки",
                150000.0,
                "/static/images/p2_suitcase.png",
                "Культовый чемодан на 4 колесах с монограммой Eclipse. Компактный ручной багаж премиум-класса с кодовым замком TSA.",
                "Новое с биркой"
            ),
            (
                "Бежевая кожаная сумка Chloé Marcie Small",
                "Сумки",
                31200.0,
                "/static/images/p3_beigebag.png",
                "Элегантная сумка через плечо из мягкой телячьей кожи песочно-бежевого оттенка. Золотистая фурнитура, классический силуэт.",
                "Новое"
            ),
            (
                "Бежевая куртка SAINT LAURENT Teddy Jacket",
                "Одежда",
                31400.0,
                "/static/images/p4_jacket.png",
                "Легендарная куртка бомбер в песочном цвете с контрастными кожаными вставками. 100% шерсть с шелковой подкладкой.",
                "Новое с биркой"
            ),
            (
                "Сумка Longchamp Le Pliage Heritage Cuir",
                "Сумки",
                45000.0,
                "/static/images/p5_longchamp.png",
                "Трапециевидная сумка из натуральной кожи тонкой выделки. В комплекте съемный плечевой ремень и пыльник.",
                "Отличное"
            ),
            (
                "Кожаная сумка Chanel Classic Double Flap Mini",
                "Сумки",
                380000.0,
                "/static/images/p6_handbag.png",
                "Черная стеганая кожа ягненка, фурнитура с 24-каратным золотым напылением. Аутентифицирована экспертами Mirelle.",
                "Идеальное"
            ),
            (
                "Сумка на плечо Prada Re-Edition 2005 Re-Nylon",
                "Сумки",
                125000.0,
                "/static/images/p7_shoulderbag.png",
                "Культовая нейлоновая сумка со съемным чехлом на ремне и металлической цепочкой. Серебристая фурнитура.",
                "Новое"
            ),
            (
                "Солнцезащитные очки Jacques Marie Mage Dealan",
                "Аксессуары",
                68000.0,
                "/static/images/p8_sunglasses.png",
                "Лимитированная серия ручной работы из ацетата премиум качества со вставками из драгоценных металлов.",
                "Новое в коробке"
            )
        ]

        await db.executemany("""
            INSERT INTO products (title, category, price, image_url, description, condition, worker_id)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
        """, default_products)
        await db.commit()


# --- Dynamic Settings ---

async def get_bot_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default


async def set_bot_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value.strip()))
        await db.commit()


# --- Banner Management (Photo, Video, GIF / Animation) ---

async def set_banner(section: str, media_type: str, file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_banners (section, media_type, file_id)
            VALUES (?, ?, ?)
            ON CONFLICT(section) DO UPDATE SET
                media_type = excluded.media_type,
                file_id = excluded.file_id,
                updated_at = CURRENT_TIMESTAMP
        """, (section.strip(), media_type.strip(), file_id.strip()))
        await db.commit()


async def get_banner(section: str):
    # If not querying 'unified' directly, check if unified banner is active
    if section != "unified":
        use_unified = await get_bot_setting("use_unified_banner", "0")
        if use_unified == "1":
            unified = await get_banner("unified")
            if unified:
                return unified

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bot_banners WHERE section = ?", (section.strip(),)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_banners():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bot_banners") as cursor:
            rows = await cursor.fetchall()
            return {r["section"]: dict(r) for r in rows}


async def reset_all_banners():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bot_banners")
        await db.execute("UPDATE bot_settings SET value = '0' WHERE key = 'use_unified_banner'")
        await db.commit()


async def toggle_unified_banner():
    current = await get_bot_setting("use_unified_banner", "0")
    new_val = "0" if current == "1" else "1"
    await set_bot_setting("use_unified_banner", new_val)
    return new_val == "1"


# --- Worker Operations ---

async def get_worker_by_tg(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_worker_by_id(worker_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_worker_by_promo(promo_code: str):
    if not promo_code:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers WHERE LOWER(promo_code) = LOWER(?)", (promo_code.strip(),)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_worker_by_username_or_id(query: str):
    clean = query.strip().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if clean.isdigit():
            async with db.execute("SELECT * FROM workers WHERE telegram_id = ? OR id = ?", (int(clean), int(clean))) as cursor:
                row = await cursor.fetchone()
                if row: return dict(row)
        async with db.execute("SELECT * FROM workers WHERE LOWER(username) = LOWER(?)", (clean,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_worker(telegram_id: int, username: str, first_name: str, promo_code: str = None, discount_percent: int = 10, role: str = "worker"):
    if not promo_code:
        clean_user = "".join(c for c in (username or "user") if c.isalnum()).lower()
        promo_code = f"{clean_user}_{random.randint(10, 99)}"

    # If telegram_id in config.ADMIN_IDS, force role admin
    if telegram_id in config.ADMIN_IDS:
        role = "admin"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO workers (telegram_id, username, first_name, promo_code, discount_percent, status, role)
            VALUES (?, ?, ?, ?, ?, 'approved', ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                promo_code = excluded.promo_code,
                discount_percent = excluded.discount_percent,
                status = 'approved'
        """, (telegram_id, username or "", first_name or "", promo_code, discount_percent, role))
        await db.commit()
    return await get_worker_by_tg(telegram_id)


async def update_worker_role(telegram_id: int, new_role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        is_m = 1 if new_role == "curator" else 0
        await db.execute("UPDATE workers SET role = ?, is_mentor = ? WHERE telegram_id = ?", (new_role, is_m, telegram_id))
        await db.commit()
    return await get_worker_by_tg(telegram_id)


async def set_worker_wallet(telegram_id: int, wallet: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE workers SET trc20_wallet = ? WHERE telegram_id = ?", (wallet.strip(), telegram_id))
        await db.commit()


async def update_worker_promo(telegram_id: int, new_promo: str, discount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE workers
            SET promo_code = ?, discount_percent = ?
            WHERE telegram_id = ?
        """, (new_promo.strip(), discount, telegram_id))
        await db.commit()


async def toggle_worker_setting(telegram_id: int, setting_name: str):
    valid_settings = {"action_logs", "collateral_required", "deposit_via_support"}
    if setting_name not in valid_settings:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            UPDATE workers
            SET {setting_name} = CASE WHEN {setting_name} = 1 THEN 0 ELSE 1 END
            WHERE telegram_id = ?
        """, (telegram_id,))
        await db.commit()
    return await get_worker_by_tg(telegram_id)


async def set_worker_alias(telegram_id: int, alias: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE workers SET chat_alias = ? WHERE telegram_id = ?", (alias.strip(), telegram_id))
        await db.commit()


# --- Profit Statistics (Day, Month, All-time) ---

async def get_worker_profit_stats(worker_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Today
        async with db.execute("""
            SELECT COUNT(*), COALESCE(SUM(worker_payout), 0)
            FROM orders
            WHERE worker_id = ? AND date(created_at) = date('now')
        """, (worker_id,)) as cur:
            day_count, day_sum = await cur.fetchone()

        # Month
        async with db.execute("""
            SELECT COUNT(*), COALESCE(SUM(worker_payout), 0)
            FROM orders
            WHERE worker_id = ? AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """, (worker_id,)) as cur:
            month_count, month_sum = await cur.fetchone()

        # All time
        async with db.execute("""
            SELECT COUNT(*), COALESCE(SUM(worker_payout), 0)
            FROM orders
            WHERE worker_id = ?
        """, (worker_id,)) as cur:
            all_count, all_sum = await cur.fetchone()

        return {
            "day_count": day_count, "day_sum": day_sum,
            "month_count": month_count, "month_sum": month_sum,
            "all_count": all_count, "all_sum": all_sum
        }


# --- Withdrawals & Transfers ---

async def create_withdrawal(worker_id: int, telegram_id: int, username: str, amount_usd: float, trc20_address: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # Deduct balance, add to frozen
        await db.execute("""
            UPDATE workers
            SET balance = balance - ?, frozen_balance = frozen_balance + ?
            WHERE id = ? AND balance >= ?
        """, (amount_usd, amount_usd, worker_id, amount_usd))

        cursor = await db.execute("""
            INSERT INTO withdrawals (worker_id, telegram_id, username, amount, trc20_address, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (worker_id, telegram_id, username or "", amount_usd, trc20_address.strip()))
        wid = cursor.lastrowid
        await db.commit()
        return wid


async def get_withdrawal_by_id(wid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def process_withdrawal(wid: int, approve: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)) as cursor:
            w = await cursor.fetchone()
            if not w: return None
            w = dict(w)

        if approve:
            await db.execute("UPDATE withdrawals SET status = 'completed' WHERE id = ?", (wid,))
            await db.execute("UPDATE workers SET frozen_balance = MAX(0, frozen_balance - ?) WHERE id = ?", (w["amount"], w["worker_id"]))
        else:
            await db.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = ?", (wid,))
            # Refund frozen balance back to active
            await db.execute("""
                UPDATE workers
                SET balance = balance + ?, frozen_balance = MAX(0, frozen_balance - ?)
                WHERE id = ?
            """, (w["amount"], w["amount"], w["worker_id"]))

        await db.commit()
        return w


async def transfer_balance(from_worker_id: int, to_worker_id: int, amount_usd: float):
    async with aiosqlite.connect(DB_PATH) as db:
        # Check sender balance
        async with db.execute("SELECT balance FROM workers WHERE id = ?", (from_worker_id,)) as cur:
            row = await cur.fetchone()
            if not row or row[0] < amount_usd:
                return False

        await db.execute("UPDATE workers SET balance = balance - ? WHERE id = ?", (amount_usd, from_worker_id))
        await db.execute("UPDATE workers SET balance = balance + ? WHERE id = ?", (amount_usd, to_worker_id))
        await db.execute("INSERT INTO transfers (from_worker_id, to_worker_id, amount) VALUES (?, ?, ?)", (from_worker_id, to_worker_id, amount_usd))
        await db.commit()
        return True


# --- Mentorship System (Curators) ---

async def get_all_mentors():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT w.*,
                   (SELECT COUNT(*) FROM workers s WHERE s.mentor_id = w.id) as students_count,
                   (SELECT COUNT(*) FROM orders o 
                    JOIN workers w2 ON o.worker_id = w2.id 
                    WHERE w2.mentor_id = w.id) as mentor_profits_count,
                   (SELECT COALESCE(SUM(o.final_price), 0) FROM orders o 
                    JOIN workers w2 ON o.worker_id = w2.id 
                    WHERE w2.mentor_id = w.id) as mentor_profits_sum
            FROM workers w
            WHERE w.role = 'curator' OR w.is_mentor = 1
            ORDER BY students_count DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def apply_to_mentor(student_id: int, mentor_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO mentor_applications (student_id, mentor_id, status)
            VALUES (?, ?, 'pending')
        """, (student_id, mentor_id))
        aid = cursor.lastrowid
        await db.commit()
        return aid


async def get_mentor_pending_applications(mentor_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ma.*, w.username, w.first_name, w.telegram_id,
                   (SELECT COUNT(*) FROM orders WHERE worker_id = w.id) as total_profits
            FROM mentor_applications ma
            JOIN workers w ON ma.student_id = w.id
            WHERE ma.mentor_id = ? AND ma.status = 'pending'
            ORDER BY ma.id DESC
        """, (mentor_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def accept_mentor_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM mentor_applications WHERE id = ?", (app_id,)) as cur:
            row = await cur.fetchone()
            if not row: return None
            app = dict(row)

        await db.execute("UPDATE mentor_applications SET status = 'accepted' WHERE id = ?", (app_id,))
        # Attach student to mentor
        await db.execute("""
            UPDATE workers
            SET mentor_id = ?, mentor_profits_count = 0
            WHERE id = ?
        """, (app["mentor_id"], app["student_id"]))
        await db.commit()
        return app


async def reject_mentor_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE mentor_applications SET status = 'rejected' WHERE id = ?", (app_id,))
        await db.commit()


async def detach_mentor(student_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE workers SET mentor_id = NULL, mentor_profits_count = 0 WHERE id = ?", (student_id,))
        await db.commit()


async def get_mentor_students(mentor_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT w.*,
                   (SELECT COUNT(*) FROM orders WHERE worker_id = w.id) as profits_count,
                   (SELECT COALESCE(SUM(final_price), 0) FROM orders WHERE worker_id = w.id) as total_volume
            FROM workers w
            WHERE w.mentor_id = ?
        """, (mentor_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# --- Admin Personnel & Stats ---

async def get_team_members():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM workers
            WHERE role IN ('admin', 'moderator', 'curator')
            ORDER BY CASE role 
                WHEN 'admin' THEN 1 
                WHEN 'moderator' THEN 2 
                WHEN 'curator' THEN 3 
                ELSE 4 END
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_admin_dashboard_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM workers") as cur:
            total_workers = (await cur.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM clients") as cur:
            total_clients = (await cur.fetchone())[0]

        async with db.execute("SELECT COUNT(*), COALESCE(SUM(final_price), 0), COALESCE(SUM(worker_payout), 0) FROM orders") as cur:
            total_orders, total_volume, total_payouts = await cur.fetchone()

        async with db.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'") as cur:
            pending_withdrawals = (await cur.fetchone())[0]

        return {
            "total_workers": total_workers,
            "total_clients": total_clients,
            "total_orders": total_orders,
            "total_volume": total_volume,
            "total_payouts": total_payouts,
            "pending_withdrawals": pending_withdrawals
        }


# --- Applications (Recruitment) ---

async def submit_application(telegram_id: int, username: str, first_name: str, source: str, time_commit: str, experience: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO applications (telegram_id, username, first_name, source, time_commitment, experience, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (telegram_id, username or "", first_name or "", source, time_commit, experience))
        app_id = cursor.lastrowid
        await db.commit()
        return app_id


async def get_application_by_tg(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE telegram_id = ? ORDER BY id DESC LIMIT 1", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_application_by_id(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE id = ?", (app_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def approve_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE id = ?", (app_id,)) as cursor:
            app = await cursor.fetchone()
            if not app:
                return None
            app_dict = dict(app)

        await db.execute("UPDATE applications SET status = 'approved' WHERE id = ?", (app_id,))
        await db.commit()

    clean_user = "".join(c for c in (app_dict.get("username") or "worker") if c.isalnum()).lower()
    promo = f"{clean_user}_{random.randint(100, 999)}" if clean_user else f"mirelle_{random.randint(100, 999)}"
    worker = await create_worker(
        telegram_id=app_dict["telegram_id"],
        username=app_dict.get("username") or "",
        first_name=app_dict.get("first_name") or "",
        promo_code=promo,
        discount_percent=10
    )
    return worker


async def reject_application(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status = 'rejected' WHERE id = ?", (app_id,))
        await db.commit()


# --- Client operations ---

async def register_client(name: str, phone: str, email: str, password: str, promo_code: str = None):
    worker = await get_worker_by_promo(promo_code) if promo_code else None
    worker_id = worker["id"] if worker else None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if email:
            async with db.execute("SELECT * FROM clients WHERE email = ?", (email.strip(),)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return dict(existing), worker, False

        cursor = await db.execute("""
            INSERT INTO clients (worker_id, name, phone, email, password, promo_used)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (worker_id, name.strip(), phone.strip() if phone else "", email.strip() if email else "", password or "123456", promo_code.strip() if promo_code else ""))
        client_id = cursor.lastrowid
        await db.commit()

        async with db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)) as cursor:
            client = dict(await cursor.fetchone())
            return client, worker, True


async def get_worker_clients(worker_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.*, 
                   COUNT(o.id) as order_count, 
                   COALESCE(SUM(o.final_price), 0) as total_spent
            FROM clients c
            LEFT JOIN orders o ON o.client_id = c.id
            WHERE c.worker_id = ?
            GROUP BY c.id
            ORDER BY c.id DESC
        """, (worker_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def search_worker_clients(worker_id: int, query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = f"%{query.strip()}%"
        async with db.execute("""
            SELECT c.*, 
                   COUNT(o.id) as order_count, 
                   COALESCE(SUM(o.final_price), 0) as total_spent
            FROM clients c
            LEFT JOIN orders o ON o.client_id = c.id
            WHERE c.worker_id = ? AND (c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? OR c.id = ?)
            GROUP BY c.id
            ORDER BY c.id DESC
        """, (worker_id, q, q, q, query.strip() if query.strip().isdigit() else -1)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# --- Order Operations & Profit Split ---

async def create_order(
    client_id: int,
    worker_id: int,
    product_id: int,
    product_title: str,
    original_price: float,
    discount_percent: int,
    final_price: float,
    client_name: str,
    client_phone: str,
    client_address: str,
    promo_code: str
):
    order_num = f"BM-{random.randint(100000, 999999)}"
    
    # Calculate profit split:
    # Worker: 80% if no mentor, 60% if with mentor
    # Mentor: 20% if exists
    # Team: 20%
    worker_payout_rub = 0.0
    mentor_payout_rub = 0.0
    mentor_worker = None

    if worker_id:
        worker = await get_worker_by_id(worker_id)
        if worker:
            if worker.get("mentor_id"):
                # With mentor: worker gets 60%, mentor gets 20%
                worker_payout_rub = round(final_price * 0.60, 2)
                mentor_payout_rub = round(final_price * 0.20, 2)
                mentor_worker = await get_worker_by_id(worker["mentor_id"])
            else:
                # Without mentor: worker gets full 80%
                worker_payout_rub = round(final_price * 0.80, 2)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            INSERT INTO orders (
                order_number, client_id, worker_id, product_id, product_title,
                original_price, discount_percent, final_price, worker_payout, mentor_payout,
                client_name, client_phone, client_address, promo_code, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Оплачен')
        """, (
            order_num, client_id, worker_id, product_id, product_title,
            original_price, discount_percent, final_price, worker_payout_rub, mentor_payout_rub,
            client_name, client_phone, client_address, promo_code
        ))
        order_id = cursor.lastrowid

        # Convert RUB payout to USD and credit to balance
        if worker_id and worker_payout_rub > 0:
            worker_payout_usd = round(worker_payout_rub / USD_RUB_RATE, 2)
            await db.execute("""
                UPDATE workers
                SET balance = balance + ?,
                    mentor_profits_count = CASE WHEN mentor_id IS NOT NULL THEN mentor_profits_count + 1 ELSE mentor_profits_count END
                WHERE id = ?
            """, (worker_payout_usd, worker_id))

        if mentor_worker and mentor_payout_rub > 0:
            mentor_payout_usd = round(mentor_payout_rub / USD_RUB_RATE, 2)
            await db.execute("""
                UPDATE workers
                SET balance = balance + ?
                WHERE id = ?
            """, (mentor_payout_usd, mentor_worker["id"]))

        await db.commit()

        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            order_dict = dict(row)
            order_dict["mentor_worker"] = mentor_worker
            return order_dict


# --- Custom Products, Broadcasts & Catalog ---

async def add_worker_product(worker_id: int, title: str, category: str, price: float, image_url: str, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            INSERT INTO products (worker_id, title, category, price, image_url, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (worker_id, title.strip(), category.strip(), price, image_url.strip(), description.strip()))
        pid = cursor.lastrowid
        await db.commit()
        async with db.execute("SELECT * FROM products WHERE id = ?", (pid,)) as cursor:
            return dict(await cursor.fetchone())


async def get_worker_products(worker_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE worker_id = ? ORDER BY id DESC", (worker_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_broadcast(worker_id: int, message: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO broadcasts (worker_id, message) VALUES (?, ?)", (worker_id, message.strip()))
        await db.commit()


async def get_latest_broadcast_for_promo(promo_code: str):
    worker = await get_worker_by_promo(promo_code)
    if not worker:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM broadcasts WHERE worker_id = ? ORDER BY id DESC LIMIT 1", (worker["id"],)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_catalog_products(category: str = None, search: str = None, promo_code: str = None):
    worker = await get_worker_by_promo(promo_code) if promo_code else None
    worker_id = worker["id"] if worker else None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM products WHERE (worker_id IS NULL OR worker_id = ?)"
        params = [worker_id or -1]

        if category and category != "Все":
            query += " AND category = ?"
            params.append(category)

        if search:
            query += " AND (title LIKE ? OR description LIKE ?)"
            s = f"%{search.strip()}%"
            params.extend([s, s])

        query += " ORDER BY id ASC"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_product_by_id(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
