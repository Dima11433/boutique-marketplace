// Global State
let currentCategory = "Все";
let currentSort = "popular";
let searchQuery = "";
let allProducts = [];
let activeProduct = null;
let activePromo = localStorage.getItem("modeva_promo") || localStorage.getItem("mirelle_promo") || window.INITIAL_PROMO || "";
let activeDiscount = parseInt(localStorage.getItem("modeva_discount") || localStorage.getItem("mirelle_discount") || window.INITIAL_DISCOUNT || "0");
let favorites = JSON.parse(localStorage.getItem("modeva_favs") || localStorage.getItem("mirelle_favs") || "[]");
let currentUser = JSON.parse(localStorage.getItem("modeva_user") || localStorage.getItem("mirelle_user") || "null");

// Static Fallback Data for GitHub Pages & Offline (Empty by default per owner request; populated if added via Admin)
const STATIC_DEFAULT_PRODUCTS = JSON.parse(localStorage.getItem("modeva_custom_products") || "[]");

const STATIC_PROMOS = {
    "MODEVA": 15,
    "VIP20": 20,
    "LUXURY": 10,
    "WELCOME": 10,
    "SALE10": 10
};

function getSafeImageUrl(url) {
    if (!url) return 'static/images/p1_briefcase.png';
    if (url.startsWith('/static/')) return url.substring(1);
    return url;
}

document.addEventListener("DOMContentLoaded", () => {
    // Check URL params for ref / promo
    const urlParams = new URLSearchParams(window.location.search);
    const refParam = urlParams.get("ref") || urlParams.get("promo");
    if (refParam) {
        verifyAndSetPromo(refParam);
    } else if (activePromo) {
        updatePromoUI();
    }

    updateFavoritesUI();
    updateUserUI();
    loadProducts();
    initHero3DGem();

    // Close dropdowns when clicking outside
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".categories-dropdown-wrapper")) {
            document.getElementById("categoriesMenu")?.classList.remove("show");
        }
        if (!e.target.closest(".sort-dropdown-wrapper")) {
            document.getElementById("sortMenu")?.classList.remove("show");
        }
    });
});

// --- Promo Code Management ---

async function verifyAndSetPromo(code) {
    if (!code) return;
    const cleanCode = code.trim().toUpperCase();
    try {
        const res = await fetch(`/api/promo/check?code=${encodeURIComponent(cleanCode)}`);
        if (res.ok) {
            const data = await res.json();
            if (data.valid) {
                activePromo = data.promo;
                activeDiscount = data.discount_percent;
                localStorage.setItem("modeva_promo", activePromo);
                localStorage.setItem("modeva_discount", activeDiscount.toString());
                updatePromoUI();
                loadProducts();
                return;
            }
        }
    } catch (e) {
        // Fallback for static GitHub Pages
    }

    if (STATIC_PROMOS[cleanCode]) {
        activePromo = cleanCode;
        activeDiscount = STATIC_PROMOS[cleanCode];
        localStorage.setItem("modeva_promo", activePromo);
        localStorage.setItem("modeva_discount", activeDiscount.toString());
        updatePromoUI();
        loadProducts();
    }
}

function updatePromoUI() {
    const bar = document.getElementById("promoNoticeBar");
    const codeEl = document.getElementById("activePromoCode");
    const discountEl = document.getElementById("activeDiscountVal");

    if (activePromo && activeDiscount > 0) {
        if (bar) bar.style.display = "block";
        if (codeEl) codeEl.textContent = activePromo;
        if (discountEl) discountEl.textContent = `${activeDiscount}%`;
    } else {
        if (bar) bar.style.display = "none";
    }
}

function clearPromo() {
    activePromo = "";
    activeDiscount = 0;
    localStorage.removeItem("modeva_promo");
    localStorage.removeItem("modeva_discount");
    localStorage.removeItem("mirelle_promo");
    localStorage.removeItem("mirelle_discount");
    updatePromoUI();
    loadProducts();
}

// --- Action Logging (Live worker logs) ---
async function logClientAction(action, productTitle = "") {
    if (!activePromo) return;
    const clientName = currentUser ? currentUser.name : (localStorage.getItem("last_buyer_name") || "Посетитель");
    try {
        await fetch("/api/action-log", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action: action,
                product_title: productTitle,
                client_name: clientName,
                promo_code: activePromo
            })
        });
    } catch (e) {
        // Silent
    }
}

// --- Products Loading & Rendering ---

async function loadProducts() {
    const grid = document.getElementById("productsGrid");
    if (!grid) return;
    grid.innerHTML = '<div class="loading-spinner">Загрузка каталога...</div>';

    let url = `/api/products?category=${encodeURIComponent(currentCategory)}&search=${encodeURIComponent(searchQuery)}`;
    if (activePromo) {
        url += `&promo=${encodeURIComponent(activePromo)}`;
    }

    let loaded = false;
    try {
        const res = await fetch(url);
        if (res.ok) {
            const data = await res.json();
            allProducts = data.products || [];
            loaded = true;
        }
    } catch (e) {
        // Fallback to static catalog
    }

    if (!loaded) {
        // Fallback for GitHub Pages or offline
        let filtered = STATIC_DEFAULT_PRODUCTS.slice();
        if (currentCategory && currentCategory !== "Все") {
            filtered = filtered.filter(p => p.category === currentCategory);
        }
        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            filtered = filtered.filter(p => p.title.toLowerCase().includes(q) || (p.description && p.description.toLowerCase().includes(q)));
        }
        allProducts = filtered.map(p => {
            const orig = p.original_price;
            const disc = activeDiscount || 0;
            const finalP = disc > 0 ? Math.round(orig * (1 - disc / 100)) : orig;
            return {
                ...p,
                discount_percent: disc,
                final_price: finalP
            };
        });
    }

    // Apply client sorting
    if (currentSort === "price_asc") {
        allProducts.sort((a, b) => a.final_price - b.final_price);
    } else if (currentSort === "price_desc") {
        allProducts.sort((a, b) => b.final_price - a.final_price);
    }

    renderProducts(allProducts);
}

function renderProducts(products) {
    const grid = document.getElementById("productsGrid");
    if (!grid) return;

    if (!products.length) {
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 70px 20px; background: #fafafa; border: 1px dashed #e4e4e7; border-radius: 20px; margin: 20px 0;">
                <div style="font-size: 40px; margin-bottom: 12px;">✨</div>
                <h3 style="font-family: 'Cormorant Garamond', Georgia, serif; font-size: 26px; font-weight: 600; color: #18181b; margin: 0 0 10px 0;">Каталог обновляется</h3>
                <p style="font-size: 14px; max-width: 440px; margin: 0 auto; color: #71717a; line-height: 1.6;">В данный момент на витрине нет доступных товаров. Новые поступления появятся в ближайшее время.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = products.map(p => {
        const isFav = favorites.includes(p.id);
        const priceStr = formatMoney(p.final_price);
        const origPriceStr = formatMoney(p.original_price);
        const hasDiscount = p.discount_percent > 0;

        return `
            <div class="product-card" onclick="openProductModal(${p.id})">
                <div class="product-card-glare"></div>
                <div class="product-img-box">
                    <img src="${getSafeImageUrl(p.image_url)}" alt="${escapeHtml(p.title)}" loading="lazy">
                </div>
                <div class="product-info">
                    <h3 class="product-title" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</h3>
                    <div class="product-category">${escapeHtml(p.category)}</div>
                    
                    <div class="product-price-pill" onclick="event.stopPropagation()">
                        <div class="price-values">
                            ${hasDiscount ? `<span class="price-strike">${origPriceStr}</span>` : ''}
                            <span class="price-current">${priceStr}</span>
                        </div>
                        <button class="pill-heart-btn ${isFav ? 'active' : ''}" onclick="toggleFavorite(event, ${p.id})">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="${isFav ? '#ef4444' : 'none'}" stroke="currentColor" stroke-width="2">
                                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join("");

    init3DCardTilt();
}

// --- Product Modal & Quick Buy ---

async function openProductModal(productId) {
    const product = allProducts.find(x => x.id === productId);
    if (!product) return;
    activeProduct = product;

    // Log action to worker bot
    logClientAction("просматривает товар", product.title);

    const content = document.getElementById("productModalContent");
    const priceStr = formatMoney(product.final_price);
    const origPriceStr = formatMoney(product.original_price);
    const hasDiscount = product.discount_percent > 0;

    content.innerHTML = `
        <div style="flex: 1; min-width: 260px; max-height: 380px; border-radius: 18px; overflow: hidden; background: #f4f4f6;">
            <img src="${getSafeImageUrl(product.image_url)}" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
        <div style="flex: 1.2; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <span style="font-size: 12px; color: #a1a1aa; text-transform: uppercase; font-weight: 600;">${escapeHtml(product.category)}</span>
                <h2 style="font-size: 20px; font-weight: 600; margin: 6px 0 12px; color: #18181b;">${escapeHtml(product.title)}</h2>
                
                <div style="background: #f4f4f6; border-radius: 12px; padding: 12px 16px; margin-bottom: 16px;">
                    <div style="font-size: 11px; color: #71717a; margin-bottom: 2px;">Состояние лота:</div>
                    <div style="font-size: 13px; font-weight: 600; color: #18181b;">${escapeHtml(product.condition || 'Новое с биркой')} • 100% Оригинал</div>
                </div>

                <p style="font-size: 13px; color: #52525b; line-height: 1.5; margin-bottom: 20px;">
                    ${escapeHtml(product.description || 'Эксклюзивный лот премиального качества. Товар прошёл полную аутентификацию экспертами MODEVA.')}
                </p>
            </div>

            <div>
                <div style="display: flex; align-items: baseline; gap: 10px; margin-bottom: 16px;">
                    ${hasDiscount ? `<span style="font-size: 15px; color: #a1a1aa; text-decoration: line-through;">${origPriceStr}</span>` : ''}
                    <span style="font-size: 24px; font-weight: 700; color: #18181b;">${priceStr}</span>
                    ${hasDiscount ? `<span style="background: #ecfdf5; color: #059669; font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 6px;">-${product.discount_percent}%</span>` : ''}
                </div>

                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-dark" style="flex: 1; height: 48px;" onclick="startCheckout(${product.id})">Оформить покупку</button>
                </div>
            </div>
        </div>
    `;

    openModal("productModal");
}

// --- Checkout Flow ---

function startCheckout(productId) {
    const product = allProducts.find(x => x.id === productId);
    if (!product) return;
    activeProduct = product;
    closeModal("productModal");

    // Log action to worker
    logClientAction("открыл форму оформления заказа", product.title);

    const summaryBox = document.getElementById("orderSummaryBox");
    summaryBox.innerHTML = `
        <img src="${getSafeImageUrl(product.image_url)}" class="order-summary-img">
        <div class="order-summary-info">
            <h4>${escapeHtml(product.title)}</h4>
            <span>Категория: ${escapeHtml(product.category)}</span>
        </div>
    `;

    // Fill client info if logged in or saved in profile
    const savedProf = JSON.parse(localStorage.getItem("modeva_user_profile") || "{}");
    const nameInput = document.getElementById("orderClientName");
    const phoneInput = document.getElementById("orderClientPhone");
    const addrInput = document.getElementById("orderClientAddress");

    if (nameInput) nameInput.value = (currentUser && currentUser.name) || savedProf.name || localStorage.getItem("last_buyer_name") || "";
    if (phoneInput) phoneInput.value = (currentUser && currentUser.phone) || savedProf.phone || localStorage.getItem("last_buyer_phone") || "";
    if (addrInput && !addrInput.value) addrInput.value = savedProf.address || "";

    // Set promo input
    const promoInput = document.getElementById("orderPromoInput");
    if (promoInput) {
        promoInput.value = activePromo || "";
    }

    recalcOrderPricing();
    openModal("checkoutModal");
}

function recalcOrderPricing() {
    if (!activeProduct) return;

    const origPrice = activeProduct.original_price;
    const discountPct = activeDiscount || 0;
    const discountAmt = Math.round(origPrice * (discountPct / 100));
    const finalPrice = origPrice - discountAmt;

    document.getElementById("orderOrigPriceText").textContent = formatMoney(origPrice);
    
    const discountRow = document.getElementById("orderDiscountRow");
    if (discountPct > 0) {
        discountRow.style.display = "flex";
        document.getElementById("orderDiscountPercentText").textContent = `${discountPct}%`;
        document.getElementById("orderDiscountAmountText").textContent = `-${formatMoney(discountAmt)}`;
    } else {
        discountRow.style.display = "none";
    }

    document.getElementById("orderFinalPriceText").textContent = formatMoney(finalPrice);
}

async function applyPromoFromInput() {
    const promoVal = document.getElementById("orderPromoInput").value.trim().toUpperCase();
    const feedback = document.getElementById("promoFeedbackMsg");

    if (!promoVal) {
        feedback.className = "promo-feedback error";
        feedback.textContent = "Введите промокод";
        return;
    }

    try {
        const res = await fetch(`/api/promo/check?code=${encodeURIComponent(promoVal)}`);
        if (res.ok) {
            const data = await res.json();
            if (data.valid) {
                activePromo = data.promo;
                activeDiscount = data.discount_percent;
                localStorage.setItem("modeva_promo", activePromo);
                localStorage.setItem("modeva_discount", activeDiscount.toString());
                feedback.className = "promo-feedback success";
                feedback.textContent = `✅ Промокод применен! Скидка ${activeDiscount}%`;
                updatePromoUI();
                recalcOrderPricing();
                return;
            }
        }
    } catch (e) {
        // Fallback for static GitHub Pages
    }

    if (STATIC_PROMOS[promoVal]) {
        activePromo = promoVal;
        activeDiscount = STATIC_PROMOS[promoVal];
        localStorage.setItem("modeva_promo", activePromo);
        localStorage.setItem("modeva_discount", activeDiscount.toString());
        feedback.className = "promo-feedback success";
        feedback.textContent = `✅ Промокод применен! Скидка ${activeDiscount}%`;
        updatePromoUI();
        recalcOrderPricing();
    } else {
        feedback.className = "promo-feedback error";
        feedback.textContent = "❌ Неверный промокод";
    }
}

async function submitOrder(e) {
    e.preventDefault();
    if (!activeProduct) return;

    const name = document.getElementById("orderClientName").value.trim();
    const phone = document.getElementById("orderClientPhone").value.trim();
    const address = document.getElementById("orderClientAddress").value.trim();
    const promo = document.getElementById("orderPromoInput").value.trim() || activePromo;

    localStorage.setItem("last_buyer_name", name);

    const btn = document.querySelector(".btn-pay");
    const origBtnText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Обработка заказа...";

    let orderSuccess = false;
    let orderNum = "BM-" + Math.floor(100000 + Math.random() * 900000);

    try {
        const res = await fetch("/api/orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                product_id: activeProduct.id,
                client_name: name,
                client_phone: phone,
                client_address: address,
                promo_code: promo
            })
        });

        if (res.ok) {
            const data = await res.json();
            if (data.status === "ok") {
                orderSuccess = true;
                if (data.order && data.order.order_number) {
                    orderNum = data.order.order_number;
                }
            }
        }
    } catch (err) {
        // Fallback for static GitHub Pages
        console.warn("Backend unavailable, processing order via local store:", err);
    }

    // Save order locally for demo/static tracking
    try {
        const localOrders = JSON.parse(localStorage.getItem("modeva_orders") || "[]");
        localOrders.unshift({
            order_number: orderNum,
            product_title: activeProduct.title,
            final_price: activeProduct.final_price,
            client_name: name,
            client_phone: phone,
            client_address: address,
            promo_code: promo,
            created_at: new Date().toISOString()
        });
        localStorage.setItem("modeva_orders", JSON.stringify(localOrders));
        orderSuccess = true;
    } catch (e) {}

    btn.disabled = false;
    btn.textContent = origBtnText;

    if (orderSuccess) {
        closeModal("checkoutModal");
        const trackBtn = document.getElementById("successTrackBtn");
        if (trackBtn) {
            trackBtn.href = `tracking.html?order=${encodeURIComponent(orderNum)}`;
        }
        openModal("successModal");
        document.getElementById("orderForm")?.reset();
    }
}

// --- Registration & Auth ---

async function submitRegister(e) {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    const origText = btn ? btn.textContent : "Зарегистрироваться";
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Регистрация...";
    }

    const name = document.getElementById("regName").value.trim();
    const phone = document.getElementById("regPhone").value.trim();
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value;
    const promo = document.getElementById("regPromo").value.trim() || activePromo;

    try {
        const res = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: name,
                phone: phone,
                email: email,
                password: password,
                promo_code: promo
            })
        });

        const data = await res.json().catch(() => ({}));
        if (res.ok && data.status === "ok") {
            currentUser = data.client;
            localStorage.setItem("modeva_user", JSON.stringify(currentUser));
            localStorage.setItem("mirelle_user", JSON.stringify(currentUser));
            if (promo) {
                await verifyAndSetPromo(promo);
            }
            updateUserUI();
            closeModal("authModal");
            closeModal("registerModal");
            alert(`Добро пожаловать в MODEVA, ${name}!`);
        } else {
            const msg = data.detail || data.message || "Ошибка регистрации. Проверьте правильность введенных данных.";
            alert(msg);
        }
    } catch (err) {
        alert("Ошибка связи с сервером при регистрации. Пожалуйста, попробуйте еще раз.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = origText;
        }
    }
}

async function submitLogin(e) {
    e.preventDefault();
    const login = document.getElementById("loginInput").value.trim();
    const passInput = e.target.querySelector("input[type=password]");
    const pass = passInput ? passInput.value : "";

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ login: login, password: pass })
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.status === "ok") {
            currentUser = data.client;
            localStorage.setItem("modeva_user", JSON.stringify(currentUser));
            localStorage.setItem("mirelle_user", JSON.stringify(currentUser));
            updateUserUI();
            closeModal("authModal");
            closeModal("loginModal");
            alert(`С возвращением в MODEVA, ${currentUser.name}!`);
            return;
        }
    } catch (err) {}

    currentUser = { name: login.split("@")[0] || "Клиент", phone: login };
    localStorage.setItem("modeva_user", JSON.stringify(currentUser));
    localStorage.setItem("mirelle_user", JSON.stringify(currentUser));
    updateUserUI();
    closeModal("authModal");
    closeModal("loginModal");
}

function logoutUser() {
    currentUser = null;
    localStorage.removeItem("modeva_user");
    localStorage.removeItem("mirelle_user");
    updateUserUI();
    closeModal("profileModal");
}

function updateUserUI() {
    const authButtons = document.getElementById("authButtons");
    const userProfile = document.getElementById("userProfile");
    const greeting = document.getElementById("userGreeting");

    if (currentUser) {
        if (authButtons) authButtons.style.display = "none";
        if (userProfile) userProfile.style.display = "flex";
        if (greeting) greeting.textContent = currentUser.name || "Клиент";
        const initial = (currentUser.name || 'К').charAt(0).toUpperCase();
        const avatarHeader = document.getElementById("userAvatarBadge");
        if (avatarHeader) avatarHeader.textContent = initial;
    } else {
        if (authButtons) authButtons.style.display = "flex";
        if (userProfile) userProfile.style.display = "none";
    }
}

// --- ✦ Luxury Client Suite (Личный кабинет) Functions ✦ ---

function openProfileModal() {
    if (!currentUser) {
        openAuthModal('login');
        return;
    }
    updateProfileModalData();
    openModal("profileModal");
}

function updateProfileModalData() {
    if (!currentUser) return;

    const initial = (currentUser.name || 'К').charAt(0).toUpperCase();
    const avatarHeader = document.getElementById("userAvatarBadge");
    if (avatarHeader) avatarHeader.textContent = initial;

    const avatarLarge = document.getElementById("profileAvatarLarge");
    if (avatarLarge) avatarLarge.textContent = initial;

    const nameEl = document.getElementById("profileUserName");
    if (nameEl) nameEl.textContent = currentUser.name || "Клиент";

    const contactEl = document.getElementById("profileUserContact");
    if (contactEl) contactEl.textContent = currentUser.phone || currentUser.email || "+7 (999) 000-00-00";

    const cardName = document.getElementById("profileCardName");
    if (cardName) cardName.textContent = currentUser.name || "Клиент";

    const cardDisc = document.getElementById("profileCardDiscount");
    if (cardDisc) cardDisc.textContent = `${activeDiscount || 15}%`;

    const levelEl = document.getElementById("profileUserLevel");
    if (levelEl) levelEl.textContent = `Персональная скидка ${activeDiscount || 15}%`;

    // Fill address form from saved profile
    const saved = JSON.parse(localStorage.getItem("modeva_user_profile") || "{}");
    const prefName = document.getElementById("prefClientName");
    if (prefName) prefName.value = saved.name || currentUser.name || "";

    const prefPhone = document.getElementById("prefClientPhone");
    if (prefPhone) prefPhone.value = saved.phone || currentUser.phone || "";

    const prefAddr = document.getElementById("prefClientAddress");
    if (prefAddr) prefAddr.value = saved.address || "";

    const prefNotes = document.getElementById("prefClientNotes");
    if (prefNotes) prefNotes.value = saved.notes || "";

    renderProfileOrders();
}

function switchProfileTab(tabId) {
    document.querySelectorAll(".profile-tab-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".profile-tab-panel").forEach(p => p.classList.remove("active"));

    const btn = document.querySelector(`.profile-tab-btn[onclick*="${tabId}"]`);
    if (btn) btn.classList.add("active");

    const panel = document.getElementById(tabId);
    if (panel) panel.classList.add("active");
}

async function renderProfileOrders() {
    const listEl = document.getElementById("profileOrdersList");
    const countEl = document.getElementById("profileOrdersCount");
    if (!listEl) return;

    let orders = JSON.parse(localStorage.getItem("modeva_orders") || "[]");

    // Attempt online sync if backend has client orders
    if (currentUser && currentUser.phone) {
        try {
            const res = await fetch(`/api/client/orders?phone=${encodeURIComponent(currentUser.phone)}`);
            if (res.ok) {
                const data = await res.json();
                if (data.status === "ok" && Array.isArray(data.orders) && data.orders.length > 0) {
                    orders = data.orders;
                }
            }
        } catch(e) {}
    }

    if (countEl) countEl.textContent = orders.length;

    if (!orders.length) {
        listEl.innerHTML = `
            <div class="profile-empty-orders">
                <div class="profile-empty-icon">🛍</div>
                <h4 class="profile-empty-title">Заказов пока нет</h4>
                <p class="profile-empty-desc">Вы ещё не совершали покупок в бутике. Выберите понравившиеся изделия в каталоге и воспользуйтесь персональной скидкой резидента.</p>
                <button type="button" class="btn btn-dark" style="background: linear-gradient(135deg, #18191f, #0d0e12); color: #fff; padding: 10px 22px; border-radius: 10px;" onclick="closeModal('profileModal')">Перейти к покупкам</button>
            </div>
        `;
        return;
    }

    listEl.innerHTML = orders.map(o => {
        const orderNum = o.order_number || "ORD-" + Math.floor(100000 + Math.random() * 900000);
        const title = o.product_title || "Изделие из коллекции MODEVA";
        const price = formatMoney(o.final_price || 0);
        const dateStr = o.created_at ? new Date(o.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Сегодня";
        const status = o.status || "Оплачен";
        
        let statusClass = "order-status-paid";
        if (status === "В обработке") statusClass = "order-status-process";
        else if (status === "В пути" || status === "Отправлен") statusClass = "order-status-transit";
        else if (status === "Доставлен") statusClass = "order-status-delivered";

        return `
            <div class="profile-order-card">
                <div class="order-card-header">
                    <div>
                        <span class="order-num-tag">#${escapeHtml(orderNum)}</span>
                        <span class="order-date-text">${dateStr}</span>
                    </div>
                    <span class="order-status-badge ${statusClass}">${escapeHtml(status)}</span>
                </div>
                <div class="order-card-body">
                    <div class="order-product-title">${escapeHtml(title)}</div>
                    <div class="order-price-val">${price}</div>
                </div>
                <div class="order-card-actions">
                    <button type="button" class="btn-order-action" onclick="closeModal('profileModal'); openModevaSupport('Здравствуйте! Вопрос по моему заказу #${escapeHtml(orderNum)} («${escapeHtml(title)}»).');">
                        💬 Вопрос по заказу
                    </button>
                    <a href="tracking.html?order=${encodeURIComponent(orderNum)}" class="btn-order-action btn-order-action-gold">
                        🚚 Отследить
                    </a>
                </div>
            </div>
        `;
    }).join("");
}

function saveClientAddress(e) {
    e.preventDefault();
    const name = document.getElementById("prefClientName").value.trim();
    const phone = document.getElementById("prefClientPhone").value.trim();
    const address = document.getElementById("prefClientAddress").value.trim();
    const notes = document.getElementById("prefClientNotes").value.trim();

    const profileData = { name, phone, address, notes };
    localStorage.setItem("modeva_user_profile", JSON.stringify(profileData));
    
    // Also update currentUser name/phone if present
    if (currentUser) {
        currentUser.name = name;
        currentUser.phone = phone;
        localStorage.setItem("modeva_user", JSON.stringify(currentUser));
        localStorage.setItem("mirelle_user", JSON.stringify(currentUser));
        updateUserUI();
    }

    const toast = document.getElementById("addressSavedToast");
    if (toast) {
        toast.style.display = "inline";
        setTimeout(() => { toast.style.display = "none"; }, 3000);
    }
}

async function applyPromoDirectly(code) {
    await verifyAndSetPromo(code);
    updateProfileModalData();
    alert(`Промокод ${code} активирован! Ваша персональная скидка ${activeDiscount}% применена на весь каталог.`);
}

// --- Categories & Filtering ---

function toggleCategoriesMenu() {
    document.getElementById("categoriesMenu")?.classList.toggle("show");
}

function selectCategory(category) {
    currentCategory = category;
    document.getElementById("selectedCategoryLabel").textContent = category;
    document.getElementById("categoriesMenu")?.classList.remove("show");

    const pill = document.getElementById("currentCategoryPill");
    if (category !== "Все") {
        pill.style.display = "inline-block";
        pill.textContent = `Категория: ${category}`;
    } else {
        pill.style.display = "none";
    }

    loadProducts();
}

function toggleSortMenu() {
    document.getElementById("sortMenu")?.classList.toggle("show");
}

function selectSort(sortType) {
    currentSort = sortType;
    const labels = {
        "popular": "Популярное",
        "price_asc": "Сначала дешевле",
        "price_desc": "Сначала дороже"
    };
    document.getElementById("selectedSortLabel").textContent = labels[sortType];
    document.getElementById("sortMenu")?.classList.remove("show");
    loadProducts();
}

let searchTimer;
function onSearchInput(val) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        searchQuery = val.trim();
        loadProducts();
    }, 300);
}

function triggerSearch() {
    const val = document.getElementById("searchInput").value;
    searchQuery = val.trim();
    loadProducts();
}

// --- Favorites ---

function toggleFavorite(e, productId) {
    e.stopPropagation();
    const idx = favorites.indexOf(productId);
    if (idx > -1) {
        favorites.splice(idx, 1);
    } else {
        favorites.push(productId);
    }
    localStorage.setItem("mirelle_favs", JSON.stringify(favorites));
    updateFavoritesUI();
    renderProducts(allProducts);
}

function updateFavoritesUI() {
    const countEl = document.getElementById("favCount");
    if (countEl) countEl.textContent = favorites.length;
}

function openFavorites() {
    if (!favorites.length) {
        alert("Список избранного пуст. Нажимайте на сердечко у понравившихся товаров!");
        return;
    }
    alert(`В вашем списке избранного ${favorites.length} товаров.`);
}

function openCartModal() {
    if (!allProducts.length) return;
    startCheckout(allProducts[0].id);
}

function closeBroadcast() {
    const el = document.getElementById("broadcastBanner");
    if (el) el.style.display = "none";
}

// --- Unified Auth Modal Logic (Switch between Login and Signup) ---
function openAuthModal(mode = 'login') {
    switchAuthTab(mode);
    const el = document.getElementById('authModal');
    if (el) el.classList.add("show");
}

function switchAuthTab(mode) {
    const pillLogin = document.getElementById('authPillLogin');
    const pillSignup = document.getElementById('authPillSignup');
    const secLogin = document.getElementById('authLoginSection');
    const secSignup = document.getElementById('authSignupSection');

    if (mode === 'signup') {
        if (pillSignup) pillSignup.classList.add('active');
        if (pillLogin) pillLogin.classList.remove('active');
        if (secSignup) {
            secSignup.style.display = 'block';
            secSignup.classList.remove('auth-view-active');
            void secSignup.offsetWidth;
            secSignup.classList.add('auth-view-active');
        }
        if (secLogin) secLogin.style.display = 'none';
    } else {
        if (pillLogin) pillLogin.classList.add('active');
        if (pillSignup) pillSignup.classList.remove('active');
        if (secLogin) {
            secLogin.style.display = 'block';
            secLogin.classList.remove('auth-view-active');
            void secLogin.offsetWidth;
            secLogin.classList.add('auth-view-active');
        }
        if (secSignup) secSignup.style.display = 'none';
    }
}

function togglePassVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPass = input.type === 'password';
    input.type = isPass ? 'text' : 'password';
    const offSvg = btn.querySelector('.eye-off-svg');
    const onSvg = btn.querySelector('.eye-on-svg');
    if (offSvg && onSvg) {
        offSvg.style.display = isPass ? 'none' : 'block';
        onSvg.style.display = isPass ? 'block' : 'none';
    }
}

function quickGuestLogin() {
    currentUser = { name: "Гость", phone: "+7 (999) 000-00-00", is_guest: true };
    localStorage.setItem("modeva_user", JSON.stringify(currentUser));
    localStorage.setItem("mirelle_user", JSON.stringify(currentUser));
    updateUserUI();
    closeModal("authModal");
    alert("Вы вошли как гость! Теперь вам доступны все функции покупок.");
}

// --- Modal Helpers ---

function openModal(id) {
    if (id === 'loginModal') {
        openAuthModal('login');
        return;
    }
    if (id === 'registerModal') {
        openAuthModal('signup');
        return;
    }
    const el = document.getElementById(id);
    if (el) el.classList.add("show");
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("show");
}

function formatMoney(amount) {
    return Math.round(amount).toLocaleString("ru-RU") + " ₽";
}

function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// --- 3D Hero Gemstone Animation (Three.js WebGL) ---
function initHero3DGem() {
    const canvas = document.getElementById("hero3DCanvas");
    const container = document.getElementById("hero3DContainer");
    if (!canvas || typeof THREE === "undefined") return;

    const width = 150;
    const height = 150;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 0, 4.3);

    const renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance"
    });
    renderer.setSize(width, height, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    // Master 3D Group
    const gemGroup = new THREE.Group();

    // 1. Faceted Gold Octahedron Gemstone
    const gemGeo = new THREE.OctahedronGeometry(1.25, 0);
    const gemMat = new THREE.MeshStandardMaterial({
        color: 0xf3d27a,
        metalness: 0.9,
        roughness: 0.18,
        flatShading: true
    });
    const gemMesh = new THREE.Mesh(gemGeo, gemMat);
    gemGroup.add(gemMesh);

    // 2. Glowing Golden Wireframe Edges
    const edgesGeo = new THREE.EdgesGeometry(gemGeo);
    const edgesMat = new THREE.LineBasicMaterial({
        color: 0xffffff,
        linewidth: 1.5,
        transparent: true,
        opacity: 0.75
    });
    const edgeLines = new THREE.LineSegments(edgesGeo, edgesMat);
    gemGroup.add(edgeLines);

    // 3. Orbital Luxury Torus Ring
    const ringGeo = new THREE.TorusGeometry(1.65, 0.038, 16, 64);
    const ringMat = new THREE.MeshStandardMaterial({
        color: 0xd4af37,
        metalness: 0.95,
        roughness: 0.12
    });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 3;
    gemGroup.add(ringMesh);

    scene.add(gemGroup);

    // Studio Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xfff6c5, 2.2);
    dirLight1.position.set(4, 5, 4);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xd4af37, 1.5);
    dirLight2.position.set(-4, -2, -2);
    scene.add(dirLight2);

    const pointLight = new THREE.PointLight(0xffffff, 1.2, 10);
    pointLight.position.set(0, 0, 3.5);
    scene.add(pointLight);

    // Interactive Parallax & Dragging
    let mouseX = 0, mouseY = 0;
    let targetRotX = 0, targetRotY = 0;
    let isDragging = false;
    let prevMouseX = 0, prevMouseY = 0;

    window.addEventListener("mousemove", (e) => {
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        mouseX = (e.clientX - centerX) / (window.innerWidth / 2);
        mouseY = (e.clientY - centerY) / (window.innerHeight / 2);
        targetRotY = mouseX * 0.7;
        targetRotX = mouseY * 0.7;
    });

    canvas.addEventListener("mousedown", (e) => {
        isDragging = true;
        prevMouseX = e.clientX;
        prevMouseY = e.clientY;
    });

    window.addEventListener("mouseup", () => { isDragging = false; });

    window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const deltaX = e.clientX - prevMouseX;
        const deltaY = e.clientY - prevMouseY;
        gemGroup.rotation.y += deltaX * 0.02;
        gemGroup.rotation.x += deltaY * 0.02;
        prevMouseX = e.clientX;
        prevMouseY = e.clientY;
    });

    // Touch support for mobile
    canvas.addEventListener("touchstart", (e) => {
        if (e.touches.length === 1) {
            isDragging = true;
            prevMouseX = e.touches[0].clientX;
            prevMouseY = e.touches[0].clientY;
        }
    }, { passive: true });

    window.addEventListener("touchend", () => { isDragging = false; });

    window.addEventListener("touchmove", (e) => {
        if (!isDragging || e.touches.length !== 1) return;
        const deltaX = e.touches[0].clientX - prevMouseX;
        const deltaY = e.touches[0].clientY - prevMouseY;
        gemGroup.rotation.y += deltaX * 0.02;
        gemGroup.rotation.x += deltaY * 0.02;
        prevMouseX = e.touches[0].clientX;
        prevMouseY = e.touches[0].clientY;
    }, { passive: true });

    let clock = new THREE.Clock();

    function animate() {
        requestAnimationFrame(animate);
        const elapsedTime = clock.getElapsedTime();

        if (!isDragging) {
            gemGroup.rotation.y += 0.012;
            gemGroup.rotation.x += (targetRotX - gemGroup.rotation.x) * 0.05;
            gemGroup.rotation.z = Math.sin(elapsedTime * 0.8) * 0.08;
        }

        ringMesh.rotation.z += 0.008;
        gemGroup.position.y = Math.sin(elapsedTime * 1.8) * 0.07;

        renderer.render(scene, camera);
    }
    animate();
}

// --- 3D Interactive Card Tilt & Specular Glare ---
function init3DCardTilt() {
    const cards = document.querySelectorAll(".product-card");
    cards.forEach(card => {
        const glare = card.querySelector(".product-card-glare");
        
        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            const rotateX = ((y - centerY) / centerY) * -12;
            const rotateY = ((x - centerX) / centerX) * 12;

            card.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) scale3d(1.025, 1.025, 1.025)`;

            if (glare) {
                const percentX = (x / rect.width) * 100;
                const percentY = (y / rect.height) * 100;
                glare.style.background = `radial-gradient(circle at ${percentX}% ${percentY}%, rgba(255, 255, 255, 0.28) 0%, rgba(212, 175, 55, 0.12) 35%, rgba(255, 255, 255, 0) 70%)`;
                glare.style.opacity = "1";
            }
        });

        card.addEventListener("mouseleave", () => {
            card.style.transform = "perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)";
            if (glare) {
                glare.style.opacity = "0";
            }
        });
    });
}

