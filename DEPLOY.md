# 🚀 Руководство по бесплатному деплою: Бот на Render + Сайт на отдельном хосте

В этом руководстве описано, как запустить **Telegram-бота на Render (Free Web Service)** и **Сайт маркетплейса на отдельном бесплатном хостинге** (Koyeb, Render или Vercel), чтобы клиенты на сайте ничего не знали о существовании бота.

---

## ЧАСТЬ 1. Запуск Telegram-бота на Render (100% бесплатно)

### Почему в боте нужен веб-сервер?
На Render бесплатный тариф предоставляется **только для Web Services**. Если запустить обычный Telegram-бот без HTTP-порта, Render выдаст ошибку `Timed out waiting for open ports` и остановит контейнер.
В файл `bot.py` уже встроены необходимые строки: при запуске бот поднимает микро-веб-сервер на `0.0.0.0:$PORT` с эндпоинтами `/` и `/health`, благодаря чему Render мгновенно одобряет деплой и держит бота активным.

### Инструкция по шагам:
1. Зарегистрируйтесь на [render.com](https://render.com) (удобно через GitHub).
2. Загрузите файлы проекта в ваш репозиторий GitHub.
3. В панели Render нажмите **«New +»** ➔ **«Web Service»**.
4. Подключите ваш репозиторий.
5. Заполните параметры:
   - **Name:** `boutique-worker-bot` (любое имя)
   - **Region:** Frankfurt (EU) или любой другой
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Instance Type:** `Free`
6. В разделе **Environment Variables** добавьте переменные:
   - `PYTHONIOENCODING` = `utf-8`
   - `BOT_TOKEN` = `ВАШ_ТОКЕН_БОТА`
   - `LOG_CHAT_ID` = `-1004495225020`
7. Нажмите **«Deploy Web Service»**.
8. Через 1–2 минуты Render выведет:
   ```
   ==> Render Web Server started on port 10000
   ==> Starting Telegram Bot polling...
   ==> Your service is live 🎉
   ```
9. Скопируйте полученный URL вашего бота на Render (например, `https://boutique-worker-bot.onrender.com`).

> [!TIP]
> **Лайфхак от засыпания Render:**
> Бесплатные веб-сервисы Render переходят в спящий режим через 15 минут неактивности.
> Чтобы бот никогда не засыпал и отвечал круглосуточно:
> 1. Зайдите на бесплатный сервис [cron-job.org](https://cron-job.org) или [uptimerobot.com](https://uptimerobot.com).
> 2. Создайте задачу пинговать URL: `https://boutique-worker-bot.onrender.com/health` каждые 10 минут.
> 3. Бот будет работать 24/7 без перерывов абсолютно бесплатно!

---

## ЧАСТЬ 2. Запуск Сайта на отдельном бесплатном хостинге

Сайт маркетплейса можно разместить на отдельном сервисе, чтобы у него был независимый адрес.

### Вариант A. Отдельный Web Service на Render (самый простой)
1. В Render снова нажмите **«New +»** ➔ **«Web Service»**.
2. Выберите тот же репозиторий.
3. Укажите параметры:
   - **Name:** `modeva` (или `modeva-store`)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn web:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`
4. В **Environment Variables** укажите:
   - `PYTHONIOENCODING` = `utf-8`
   - `BOT_API_URL` = `https://boutique-worker-bot.onrender.com` *(ссылка на вашего бота из Части 1)*
5. Нажмите **«Deploy Web Service»**.
6. Сайт заработает по отдельному красивому адресу: `https://modeva.onrender.com`.

---

### Вариант B. Хостинг Koyeb (koyeb.com — 24/7 без засыпания)
1. Зарегистрируйтесь на [koyeb.com](https://www.koyeb.com).
2. Нажмите **«Create Service»** ➔ **«GitHub»** ➔ выберите репозиторий.
3. Параметры:
   - **App name:** `modeva`
   - **Builder:** `Buildpack`
   - **Build Command:** `pip install -r requirements.txt`
   - **Run Command:** `uvicorn web:app --host 0.0.0.0 --port 8000`
4. В Environment variables добавьте:
   - `BOT_API_URL` = `https://boutique-worker-bot.onrender.com`
5. Нажмите **«Deploy»**.
6. Сайт получит красивый брендовый адрес: `https://modeva.koyeb.app`!

---

## 🔗 Как они взаимодействуют между собой?
1. Покупатель заходит на сайт (`modeva.koyeb.app` или `modeva.onrender.com`).
2. При вводе промокода сайт отправляет скрытый запрос боту на `BOT_API_URL/api/internal/promo`.
3. При оформлении заказа сайт отправляет данные на `BOT_API_URL/api/internal/order`.
4. Бот на Render:
   - Автоматически начисляет воркеру выплату (80% или 60% при наставнике).
   - Присылает воркеру уведомление в Telegram о покупке.
   - Отправляет лог в админ-чат `-1004495225020`.
   - Автоматически публикует профит в ваш канал (с ником воркера **строго без @**).
5. Покупатель видит только статус успешного заказа и красивый магазин!
