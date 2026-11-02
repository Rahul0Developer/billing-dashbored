/**
 * Apex Enterprise Retail - Operations & POS Controller
 * Handles real-time cashier checkout, Trie search, customer footfall tracking,
 * returns & refunds, cash shift balancing (Z-Report), multi-period expenses, and inventory.
 */

// Global Application State
const state = {
  cart: [], // [{ barcode, name, price, mrp, quantity, unit, tax_rate }]
  allProducts: [],
  activeCustomer: null, // { phone, name, visit_count, tier, points, tier_disc }
  paymentMethod: "CASH",
  activeUser: { id: "CASHIER-01", name: "Rajesh Sharma", role: "CASHIER" },
  activeBranch: { id: "BR-DEL-01", code: "DEL-01", name: "Indirapuram Flagship" },
  branches: [],
  currentShift: null,
  activePeriod: "today",
  activeCategory: "ALL",
  salesTrendChart: null,
  categoryChart: null,
  dayOfWeekChart: null,
  hourlyPeakChart: null,
  theme: localStorage.getItem("apex_theme") || "light"
};


// ============================================================================
// SECURITY HELPERS (XSS escaping + authenticated API transport)
// ============================================================================
const authSession = {
  token: sessionStorage.getItem("apex_pos_token") || null,
  user: JSON.parse(sessionStorage.getItem("apex_pos_user") || "null"),
  set(token, user) {
    this.token = token; this.user = user;
    sessionStorage.setItem("apex_pos_token", token);
    sessionStorage.setItem("apex_pos_user", JSON.stringify(user));
  },
  clear() {
    this.token = null; this.user = null;
    sessionStorage.removeItem("apex_pos_token");
    sessionStorage.removeItem("apex_pos_user");
  }
};

/** Escape untrusted values before any innerHTML interpolation (prevents XSS). */
function escHtml(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** Authenticated fetch wrapper: attaches bearer token, handles 401 -> login. */
async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (authSession.token) headers["Authorization"] = "Bearer " + authSession.token;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(url, Object.assign({}, options, { headers, credentials: "same-origin" }));
  if (res.status === 401) { authSession.clear(); showLoginOverlay(); }
  return res;
}

function showLoginOverlay() {
  if (document.getElementById("login-overlay")) return;
  const overlay = document.createElement("div");
  overlay.id = "login-overlay";
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(15,23,42,.92);z-index:9999;display:flex;align-items:center;justify-content:center;";
  overlay.innerHTML = `
    <form id="login-form" style="background:#fff;border-radius:14px;padding:32px;width:340px;box-shadow:0 20px 60px rgba(0,0,0,.4);">
      <h2 style="margin:0 0 4px;color:#1e3a8a;">Apex POS Login</h2>
      <p style="margin:0 0 18px;font-size:13px;color:#64748b;">Authenticate to access the register.</p>
      <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:#334155;">Username</label>
      <input id="login-username" autocomplete="username" style="width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:12px;" />
      <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:#334155;">PIN</label>
      <input id="login-pin" type="password" inputmode="numeric" autocomplete="current-password" style="width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:16px;" />
      <button type="submit" style="width:100%;padding:12px;background:#2563eb;color:#fff;border:0;border-radius:8px;font-weight:700;cursor:pointer;">Sign In</button>
      <div id="login-error" style="margin-top:10px;font-size:12px;color:#dc2626;"></div>
    </form>`;
  document.body.appendChild(overlay);
  document.getElementById("login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const u = document.getElementById("login-username").value.trim();
    const p = document.getElementById("login-pin").value;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, pin: p })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        document.getElementById("login-error").textContent = data.detail || "Invalid credentials.";
        return;
      }
      authSession.set(data.token, data.user);
      state.activeUser = { id: data.user.id, name: data.user.name, role: data.user.role };
      overlay.remove();
      showToast(`Welcome back, ${escHtml(data.user.name)} (${escHtml(data.user.role)})`, "success");
      bootstrapApp();
    } catch (err) {
      document.getElementById("login-error").textContent = "Network error. Try again.";
    }
  });
  setTimeout(() => document.getElementById("login-username").focus(), 50);
}

// ============================================================================
// INITIALIZATION ON DOM READY
// ============================================================================
function bootstrapApp() {
  initTheme();
  initClock();
  initUserSelector();
  initBranchEvents();
  initNavigation();
  initPosEvents();
  initSalesEvents();
  initShiftEvents();
  initDashboardEvents();
  initInventoryEvents();
  initCustomerEvents();
  initExpenseEvents();
  loadInitialStoreData();
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  if (authSession.token && authSession.user) {
    state.activeUser = { id: authSession.user.id, name: authSession.user.name, role: authSession.user.role };
    bootstrapApp();
  } else {
    showLoginOverlay();
  }
});

// --- THEME TOGGLE (LIGHT / DARK) ---
function initTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  const themeBtn = document.getElementById("theme-toggle-btn");
  updateThemeIcon(themeBtn);

  themeBtn.addEventListener("click", () => {
    state.theme = state.theme === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", state.theme);
    localStorage.setItem("apex_theme", state.theme);
    updateThemeIcon(themeBtn);
    showToast(`Switched to ${state.theme === 'dark' ? 'Dark' : 'Light'} Mode`, "info");
    
    // Re-render charts for theme compatibility
    if (state.salesTrendChart) state.salesTrendChart.update();
    if (state.categoryChart) state.categoryChart.update();
    if (state.dayOfWeekChart) state.dayOfWeekChart.update();
    if (state.hourlyPeakChart) state.hourlyPeakChart.update();
  });
}

function updateThemeIcon(btn) {
  if (state.theme === "dark") {
    btn.innerHTML = `<i class="fa-solid fa-sun" style="color: #f59e0b;"></i>`;
  } else {
    btn.innerHTML = `<i class="fa-solid fa-moon"></i>`;
  }
}

// --- CLOCK & STATUS ---
function initClock() {
  const clockEl = document.getElementById("live-clock");
  function tick() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  tick();
  setInterval(tick, 1000);
}

// --- ACTIVE USER SELECTOR ---
function initUserSelector() {
  // SECURITY: operator identity is fixed by the authenticated session token.
  // The old free-switching dropdown allowed cashier spoofing and is removed.
  const userSelect = document.getElementById("active-user-select");
  if (!userSelect) return;
  const wrapper = userSelect.parentElement;
  if (authSession.user) {
    const u = authSession.user;
    state.activeUser = { id: u.id, name: u.name, role: u.role };
    userSelect.innerHTML = `<option>${escHtml(u.name)} (${escHtml(u.role)})</option>`;
    userSelect.disabled = true;
    userSelect.style.pointerEvents = "none";
    // Logout button
    if (!document.getElementById("logout-btn")) {
      const btn = document.createElement("button");
      btn.id = "logout-btn";
      btn.type = "button";
      btn.textContent = "Logout";
      btn.title = "End this POS session";
      btn.style.cssText = "margin-left:8px;padding:6px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#334155;font-weight:600;cursor:pointer;font-size:12px;";
      btn.onclick = async () => {
        try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
        authSession.clear();
        location.reload();
      };
      wrapper.appendChild(btn);
    }
  } else {
    showLoginOverlay();
  }
}

// --- SIDEBAR NAVIGATION ---
function initNavigation() {
  const navItems = document.querySelectorAll(".sidebar-nav .nav-item");
  const titleEl = document.getElementById("current-view-title");
  const descEl = document.getElementById("current-view-desc");

  const viewMetadata = {
    "tab-pos": { title: "POS Billing Counter", desc: "High-speed barcode scanning & retail checkout" },
    "tab-sales": { title: "Sales & Invoices Register", desc: "Audit trail of all retail bills, payment tenders, returns, and invoice reprinting" },
    "tab-shifts": { title: "Register Shifts & Z-Report", desc: "POS cash drawer reconciliation, shift balancing, and safe drop audit" },
    "tab-dashboard": { title: "Store Executive BI & P&L", desc: "Real-time revenue, cost of goods sold (COGS), operating expenses, and net profit margins" },
    "tab-branches": { title: "Store Branches & Multi-Location Logistics", desc: "Enterprise multi-store management, inter-branch inventory transfers, and location comparisons" },
    "tab-inventory": { title: "Catalog & Stock Valuation", desc: "Real-time SKU stock levels, barcode assignments, procurement costs, and adjustments" },
    "tab-customers": { title: "Customer Footfall & CRM", desc: "Track customer visits frequency, lifetime spend, and loyalty tiers" },
    "tab-expenses": { title: "Operating Expenses Tracker", desc: "Track store expenditures across Weekly, Monthly, and Yearly fiscal cycles" },
    "tab-reports": { title: "Store Audit & Data Exports", desc: "Download complete CSV reports for transactions, store expenses, and catalog inventory" }
  };

  navItems.forEach(item => {
    item.addEventListener("click", () => {
      navItems.forEach(n => n.classList.remove("active"));
      item.classList.add("active");

      const targetTabId = item.getAttribute("data-tab");
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      const activePane = document.getElementById(targetTabId);
      if (activePane) activePane.classList.add("active");

      if (viewMetadata[targetTabId]) {
        titleEl.textContent = viewMetadata[targetTabId].title;
        descEl.textContent = viewMetadata[targetTabId].desc;
      }

      // Lazy load tab data on activation
      if (targetTabId === "tab-pos") {
        document.getElementById("barcode-input")?.focus();
      } else if (targetTabId === "tab-sales") {
        loadSalesOrders();
      } else if (targetTabId === "tab-shifts") {
        loadShiftStatus();
        loadShiftsHistory();
      } else if (targetTabId === "tab-dashboard") {
        loadDashboardData(state.activePeriod);
        loadBusinessIntelligenceData();
      } else if (targetTabId === "tab-branches") {
        loadBranchesData();
      } else if (targetTabId === "tab-inventory") {
        loadInventoryData();
        loadValuationData();
      } else if (targetTabId === "tab-customers") {
        loadCustomersData();
      } else if (targetTabId === "tab-expenses") {
        loadExpensesData();
        loadExpenseSummary();
      }
    });
  });
}

// --- INITIAL DATA LOAD ---
async function loadInitialStoreData() {
  try {
    // 1. Fetch branches list
    const bRes = await apiFetch("/api/branches");
    if (bRes.ok) {
      state.branches = await bRes.json();
      if (!state.activeBranch && state.branches.length > 0) {
        state.activeBranch = state.branches[0];
      }
      const bSelect = document.getElementById("active-branch-select");
      if (bSelect) {
        bSelect.innerHTML = state.branches.map(b => `
          <option value="${escHtml(b.id)}" ${escHtml(b.id === state.activeBranch.id ? 'selected' : '')}>
            ${escHtml(b.name)} (${escHtml(b.code)})
          </option>
        `).join("");
      }
    }

    // 2. Fetch branch-specific inventory shelf stock
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/branches/${branchId}/inventory`);
    if (res.ok) {
      state.allProducts = await res.json();
    } else {
      const pRes = await apiFetch("/api/products");
      state.allProducts = await pRes.json();
    }

    renderShelfProducts(state.allProducts);
    loadShiftStatus();
  } catch (err) {
    console.error("Failed to load catalog products:", err);
    showToast("Failed to connect to store server", "error");
  }
}

// ============================================================================
// TAB 1: POINT OF SALE (POS) BILLING COUNTER LOGIC
// ============================================================================
function initPosEvents() {
  const barcodeInput = document.getElementById("barcode-input");
  const suggestionsBox = document.getElementById("trie-suggestions");
  const clearSearchBtn = document.getElementById("clear-search-btn");

  // Trie Autocomplete search on keystrokes
  let debounceTimer;
  barcodeInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    const query = e.target.value.trim();
    if (!query) {
      suggestionsBox.classList.add("hidden");
      filterAndRenderShelf();
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const res = await apiFetch(`/api/products/search?q=${encodeURIComponent(query)}`);
        const matches = await res.json();
        renderSuggestions(matches);
      } catch (err) {
        console.error("Search failed:", err);
      }
    }, 150);
  });

  // Enter key barcode scan handler
  barcodeInput.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const code = barcodeInput.value.trim();
      if (!code) return;

      const direct = state.allProducts.find(p => p.barcode === code || p.sku.toLowerCase() === code.toLowerCase());
      if (direct) {
        addItemToCart(direct);
        barcodeInput.value = "";
        suggestionsBox.classList.add("hidden");
        showToast(`Added: ${direct.name}`, "success");
      } else {
        // Try searching Trie prefix
        try {
          const res = await apiFetch(`/api/products/search?q=${encodeURIComponent(code)}`);
          const matches = await res.json();
          if (matches.length > 0) {
            addItemToCart(matches[0]);
            barcodeInput.value = "";
            suggestionsBox.classList.add("hidden");
            showToast(`Added: ${matches[0].name}`, "success");
          } else {
            showToast(`Barcode ${code} not found in catalog!`, "error");
          }
        } catch (err) {
          showToast(`Item not found`, "error");
        }
      }
    }
  });

  clearSearchBtn.addEventListener("click", () => {
    barcodeInput.value = "";
    suggestionsBox.classList.add("hidden");
    filterAndRenderShelf();
    barcodeInput.focus();
  });

  // Category Filter Pills
  document.querySelectorAll(".category-filter-bar .cat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".category-filter-bar .cat-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.activeCategory = chip.getAttribute("data-cat");
      filterAndRenderShelf();
    });
  });

  // Smart Customer Recognition (Mobile Phone or Membership QR Code)
  const phoneInput = document.getElementById("customer-phone-input");
  const lookupBtn = document.getElementById("lookup-customer-btn");
  
  lookupBtn.addEventListener("click", () => performCustomerLookup(phoneInput.value.trim()));
  phoneInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      performCustomerLookup(phoneInput.value.trim());
    }
  });

  // QR Scanner Modal Triggers
  document.getElementById("btn-open-qr-scanner")?.addEventListener("click", () => {
    document.getElementById("manual-qr-payload-input").value = "";
    document.getElementById("modal-scan-member-qr").classList.remove("hidden");
    document.getElementById("manual-qr-payload-input").focus();
  });
  document.getElementById("close-scan-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-scan-member-qr").classList.add("hidden");
  });
  document.getElementById("dismiss-scan-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-scan-member-qr").classList.add("hidden");
  });
  document.getElementById("btn-submit-scanned-qr")?.addEventListener("click", () => {
    const val = document.getElementById("manual-qr-payload-input").value.trim();
    if (val) {
      document.getElementById("modal-scan-member-qr").classList.add("hidden");
      phoneInput.value = val;
      performCustomerLookup(val);
    }
  });

  // Customer Card & Insights Modal Triggers
  document.getElementById("btn-view-cust-history")?.addEventListener("click", () => {
    if (state.activeCustomer) {
      window.viewCustomerBills(state.activeCustomer.phone, state.activeCustomer.name);
    }
  });
  document.getElementById("btn-view-cust-habits")?.addEventListener("click", () => {
    if (state.activeCustomer) {
      window.showCustomerInsightsModal(state.activeCustomer.phone);
    }
  });
  document.getElementById("btn-view-cust-card")?.addEventListener("click", () => {
    if (state.activeCustomer) {
      window.showCustomerMemberCard(state.activeCustomer);
    }
  });

  document.getElementById("close-card-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-member-card").classList.add("hidden");
  });
  document.getElementById("dismiss-card-btn")?.addEventListener("click", () => {
    document.getElementById("modal-member-card").classList.add("hidden");
  });
  document.getElementById("close-insights-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-customer-insights").classList.add("hidden");
  });

  // Points redemption checkbox
  document.getElementById("redeem-points-chk")?.addEventListener("change", () => {
    recalculateCart();
  });

  // Payment Method Chips
  document.querySelectorAll(".payment-modes-bar .pay-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".payment-modes-bar .pay-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      state.paymentMethod = chip.getAttribute("data-method");
      updatePaymentUI();
    });
  });

  // Cash Tender Input calculation
  const tenderedInput = document.getElementById("tendered-cash-input");
  tenderedInput.addEventListener("input", () => {
    updateCashChange();
  });

  // Split Cash Input calculation
  const splitCashInput = document.getElementById("split-cash-input");
  splitCashInput?.addEventListener("input", () => {
    const total = state.cartPreview ? state.cartPreview.grand_total : 0;
    const cashVal = parseFloat(splitCashInput.value) || 0;
    const digitalVal = Math.max(0, total - cashVal);
    document.getElementById("split-digital-input").value = digitalVal.toFixed(2);
  });

  // Complete Sale Button
  document.getElementById("complete-sale-btn").addEventListener("click", executeCheckout);

  // Global Keyboard Shortcuts (F9 for Checkout, Esc to close modals)
  document.addEventListener("keydown", (e) => {
    if (e.key === "F9") {
      e.preventDefault();
      const checkoutBtn = document.getElementById("complete-sale-btn");
      if (!checkoutBtn.disabled) executeCheckout();
    } else if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
    }
  });

  // Thermal Receipt Modal Controls
  document.getElementById("close-receipt-btn").addEventListener("click", () => {
    document.getElementById("receipt-modal").classList.add("hidden");
  });
  document.getElementById("dismiss-receipt-btn").addEventListener("click", () => {
    document.getElementById("receipt-modal").classList.add("hidden");
    resetCart();
  });
  document.getElementById("print-receipt-btn").addEventListener("click", () => {
    window.print();
  });
}

function filterAndRenderShelf() {
  let filtered = state.allProducts;
  if (state.activeCategory !== "ALL") {
    filtered = filtered.filter(p => p.category.toLowerCase().includes(state.activeCategory.toLowerCase()));
  }
  renderShelfProducts(filtered);
}

function renderShelfProducts(products) {
  const grid = document.getElementById("products-grid");
  if (!products || products.length === 0) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">No products match filter.</div>`;
    return;
  }

  grid.innerHTML = products.map(p => `
    <div class="product-item-card" onclick="addBarcodeToCart('${escHtml(p.barcode)}')">
      <div>
        <span class="cat-badge">${escHtml(p.category)}</span>
        <h4>${escHtml(p.name)}</h4>
        <div class="barcode-tag">${escHtml(p.barcode)}</div>
      </div>
      <div>
        <div class="product-pricing-box">
          <span class="selling-price">₹${p.selling_price.toFixed(2)}</span>
          <span class="mrp-price">₹${p.mrp.toFixed(2)}</span>
        </div>
        <div class="product-stock-tag ${escHtml(p.is_low_stock ? 'low' : '')}">
          Stock: ${escHtml(p.stock_quantity)} ${escHtml(p.unit)} ${escHtml(p.is_low_stock ? '⚠️ [Low]' : '')}
        </div>
      </div>
    </div>
  `).join("");
}

function renderSuggestions(matches) {
  const box = document.getElementById("trie-suggestions");
  if (!matches || matches.length === 0) {
    box.classList.add("hidden");
    return;
  }

  box.innerHTML = matches.map(m => `
    <div class="autocomplete-item" onclick="selectSuggestion('${escHtml(m.barcode)}')">
      <div>
        <strong>${escHtml(m.name)}</strong>
        <small style="display:block; color: var(--text-muted); font-family: var(--font-mono);">${escHtml(m.barcode)} | ${escHtml(m.category)}</small>
      </div>
      <div style="text-align: right;">
        <span style="color: var(--success-dark); font-weight: 800;">₹${m.selling_price.toFixed(2)}</span>
        <small style="display:block; color: var(--text-muted); text-decoration: line-through;">₹${m.mrp.toFixed(2)}</small>
      </div>
    </div>
  `).join("");
  box.classList.remove("hidden");
}

window.selectSuggestion = function(barcode) {
  const prod = state.allProducts.find(p => p.barcode === barcode);
  if (prod) addItemToCart(prod);
  document.getElementById("barcode-input").value = "";
  document.getElementById("trie-suggestions").classList.add("hidden");
  document.getElementById("barcode-input").focus();
};

window.addBarcodeToCart = function(barcode) {
  const prod = state.allProducts.find(p => p.barcode === barcode);
  if (prod) {
    addItemToCart(prod);
    showToast(`Added: ${prod.name}`, "success");
  }
};

function addItemToCart(prod) {
  const existing = state.cart.find(i => i.barcode === prod.barcode);
  if (existing) {
    existing.quantity += 1;
  } else {
    state.cart.push({
      barcode: prod.barcode,
      name: prod.name,
      price: prod.selling_price,
      mrp: prod.mrp,
      quantity: 1,
      unit: prod.unit,
      tax_rate: prod.tax_rate_percent
    });
  }
  recalculateCart();
}

function updateCartQty(barcode, delta) {
  const item = state.cart.find(i => i.barcode === barcode);
  if (!item) return;

  item.quantity += delta;
  if (item.quantity <= 0) {
    state.cart = state.cart.filter(i => i.barcode !== barcode);
  }
  recalculateCart();
}

function removeCartItem(barcode) {
  state.cart = state.cart.filter(i => i.barcode !== barcode);
  recalculateCart();
}

async function recalculateCart() {
  renderCartTable();
  const checkoutBtn = document.getElementById("complete-sale-btn");

  if (state.cart.length === 0) {
    checkoutBtn.disabled = true;
    updateCartTotalsDisplay({
      subtotal: 0,
      total_tax: 0,
      order_discount: 0,
      points_discount: 0,
      grand_total: 0,
      total_savings: 0
    });
    return;
  }

  // Calculate live preview from backend pricing engine
  const redeemChk = document.getElementById("redeem-points-chk");
  const pointsToRedeem = (redeemChk && redeemChk.checked && state.activeCustomer) ? state.activeCustomer.points : 0;

  try {
    const res = await apiFetch("/api/pos/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: state.cart.map(i => ({ barcode: i.barcode, quantity: i.quantity })),
        customer_phone: state.activeCustomer ? state.activeCustomer.phone : null,
        points_to_redeem: pointsToRedeem,
        branch_id: state.activeBranch ? state.activeBranch.id : "BR-DEL-01"
      })
    });

    const preview = await res.json();
    state.cartPreview = preview;
    updateCartTotalsDisplay(preview);
    checkoutBtn.disabled = false;
    updateCashChange();
  } catch (err) {
    console.error("Cart preview calculation error:", err);
  }
}

function renderCartTable() {
  const tbody = document.getElementById("cart-tbody");
  const emptyState = document.getElementById("empty-cart-state");

  if (state.cart.length === 0) {
    tbody.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  tbody.innerHTML = state.cart.map(item => `
    <tr>
      <td class="cart-item-desc">
        <strong>${escHtml(item.name)}</strong>
        <small>${escHtml(item.barcode)} | MRP: ₹${item.mrp.toFixed(2)}</small>
      </td>
      <td class="text-center">
        <div class="cart-qty-ctrl">
          <button class="qty-btn" onclick="updateCartQty('${escHtml(item.barcode)}', -1)">-</button>
          <span style="font-weight: 700; min-width: 20px;">${escHtml(item.quantity)}</span>
          <button class="qty-btn" onclick="updateCartQty('${escHtml(item.barcode)}', 1)">+</button>
        </div>
      </td>
      <td class="text-right">₹${item.price.toFixed(2)}</td>
      <td class="text-right"><strong>₹${(item.price * item.quantity).toFixed(2)}</strong></td>
      <td class="text-center">
        <button class="cart-del-btn" onclick="removeCartItem('${escHtml(item.barcode)}')" title="Delete">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </td>
    </tr>
  `).join("");
}

function updateCartTotalsDisplay(p) {
  document.getElementById("cart-subtotal").textContent = `₹${p.subtotal.toFixed(2)}`;
  document.getElementById("cart-savings").textContent = `- ₹${p.total_savings.toFixed(2)}`;
  document.getElementById("cart-tax").textContent = `₹${p.total_tax.toFixed(2)}`;
  document.getElementById("cart-grand-total").textContent = `₹${p.grand_total.toFixed(2)}`;
  document.getElementById("upi-amount-display").textContent = `Pay ₹${p.grand_total.toFixed(2)}`;

  // Discount rows
  const tierRow = document.getElementById("tier-discount-row");
  const volRow = document.getElementById("vol-discount-row");
  const ptsRow = document.getElementById("points-discount-row");

  if (p.tier_discount_percent > 0) {
    tierRow.classList.remove("hidden");
    document.getElementById("cart-tier-discount").textContent = `(${p.tier_discount_percent}% OFF)`;
  } else {
    tierRow.classList.add("hidden");
  }

  if (p.volume_discount_amount > 0) {
    volRow.classList.remove("hidden");
    document.getElementById("cart-vol-discount").textContent = `- ₹${p.volume_discount_amount.toFixed(2)}`;
  } else {
    volRow.classList.add("hidden");
  }

  if (p.points_discount > 0) {
    ptsRow.classList.remove("hidden");
    document.getElementById("cart-points-discount").textContent = `- ₹${p.points_discount.toFixed(2)}`;
  } else {
    ptsRow.classList.add("hidden");
  }
}

function updatePaymentUI() {
  const cashArea = document.getElementById("cash-tender-area");
  const splitArea = document.getElementById("split-tender-area");
  const upiArea = document.getElementById("upi-qr-area");

  cashArea.classList.add("hidden");
  if (splitArea) splitArea.classList.add("hidden");
  upiArea.classList.add("hidden");

  if (state.paymentMethod === "CASH") {
    cashArea.classList.remove("hidden");
    document.getElementById("tendered-cash-input").focus();
  } else if (state.paymentMethod === "SPLIT") {
    if (splitArea) splitArea.classList.remove("hidden");
  } else if (state.paymentMethod === "UPI_QR") {
    upiArea.classList.remove("hidden");
  }
}

function updateCashChange() {
  const tenderedVal = parseFloat(document.getElementById("tendered-cash-input").value) || 0;
  const grandTotal = state.cartPreview ? state.cartPreview.grand_total : 0;
  const change = Math.max(0, tenderedVal - grandTotal);
  document.getElementById("change-returned-val").textContent = `₹${change.toFixed(2)}`;
}

// Smart Customer Recognition (Mobile Phone or Membership QR Code)
async function performCustomerLookup(identifier) {
  const clean = (identifier || "").trim();
  if (!clean) {
    showToast("Please enter a mobile number or scan a membership QR code", "error");
    return;
  }

  try {
    const res = await apiFetch(`/api/customers/recognize?identifier=${encodeURIComponent(clean)}`);
    const data = await res.json();

    const banner = document.getElementById("customer-profile-banner");
    const tierPill = document.getElementById("cust-tier-pill");
    const returningPill = document.getElementById("cust-returning-pill");

    if (data.found) {
      state.activeCustomer = {
        phone: data.phone,
        name: data.name,
        email: data.email,
        address: data.address,
        membership_code: data.membership_code,
        membership_qr_data: data.membership_qr_data,
        visit_count: data.visit_count,
        tier: data.tier,
        points: data.loyalty_points,
        points_cash_value: data.points_cash_value,
        tier_discount_percent: data.tier_discount_percent,
        is_returning: data.is_returning,
        purchase_history: data.purchase_history,
        category_preferences: data.category_preferences,
        top_purchased_products: data.top_purchased_products,
        digital_card: data.digital_card
      };

      document.getElementById("cust-disp-name").textContent = data.name;
      const codeEl = document.getElementById("cust-disp-code");
      if (codeEl) codeEl.textContent = data.membership_code;
      document.getElementById("cust-visit-count").textContent = `${data.visit_count} Times`;
      document.getElementById("cust-loyalty-pts").textContent = `${data.loyalty_points} Pts (₹${data.points_cash_value.toFixed(0)})`;
      document.getElementById("cust-days-ago").textContent = data.days_since_last_visit === 0 ? "Visited today" : `Last seen: ${data.days_since_last_visit} days ago`;
      
      const discEl = document.getElementById("cust-tier-disc");
      if (discEl) discEl.textContent = `${data.tier_discount_percent}% OFF`;

      tierPill.textContent = data.tier;
      tierPill.className = `tier-chip-badge ${data.tier.toLowerCase()}`;
      tierPill.classList.remove("hidden");

      if (returningPill) {
        if (data.is_returning) {
          returningPill.textContent = `RETURNING (${data.visit_count} visits) ⭐`;
          returningPill.className = "returning-badge";
          returningPill.classList.remove("hidden");
        } else {
          returningPill.textContent = "NEW SHOPPER";
          returningPill.className = "returning-badge";
          returningPill.classList.remove("hidden");
        }
      }

      banner.classList.remove("hidden");
      showToast(data.is_returning ? `Welcome back, ${data.name}! (${data.visit_count} visits ⭐)` : `Customer Recognized: ${data.name}`, "success");
    } else {
      // New Walk-in shopper registration if clean contains phone digits
      const phoneDigits = clean.replace(/\D/g, "").slice(-10);
      const isNum = phoneDigits.length === 10;

      state.activeCustomer = {
        phone: isNum ? phoneDigits : clean,
        name: `Customer (${clean.slice(-4)})`,
        membership_code: `MEM-${isNum ? phoneDigits : clean}`,
        membership_qr_data: `RETAIL:MEM:MEM-${isNum ? phoneDigits : clean}:${isNum ? phoneDigits : clean}`,
        visit_count: 1,
        tier: "BRONZE",
        points: 0,
        points_cash_value: 0,
        tier_discount_percent: 0.0,
        is_returning: false,
        purchase_history: [],
        category_preferences: [],
        top_purchased_products: []
      };

      document.getElementById("cust-disp-name").textContent = state.activeCustomer.name;
      const codeEl = document.getElementById("cust-disp-code");
      if (codeEl) codeEl.textContent = state.activeCustomer.membership_code;
      document.getElementById("cust-visit-count").textContent = `1st Visit (New)`;
      document.getElementById("cust-loyalty-pts").textContent = `0 Pts`;
      document.getElementById("cust-days-ago").textContent = `First time shopper`;

      const discEl = document.getElementById("cust-tier-disc");
      if (discEl) discEl.textContent = `0% OFF`;

      tierPill.textContent = "NEW";
      tierPill.className = "tier-chip-badge bronze";
      tierPill.classList.remove("hidden");

      if (returningPill) {
        returningPill.textContent = "NEW SHOPPER";
        returningPill.className = "returning-badge";
        returningPill.classList.remove("hidden");
      }
      banner.classList.remove("hidden");

      showToast(`New Customer Mobile Linked (+91 ${state.activeCustomer.phone})`, "info");
    }

    recalculateCart();
  } catch (err) {
    console.error("Customer recognition failed:", err);
  }
}

// Draw Deterministic High-Contrast QR Code on HTML5 Canvas
function drawMemberQRCode(canvasId, textPayload) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, size, size);

  const modules = 21;
  const cellSize = size / modules;
  ctx.fillStyle = "#000000";

  function drawFinder(x, y) {
    ctx.fillRect(x * cellSize, y * cellSize, 7 * cellSize, 7 * cellSize);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect((x + 1) * cellSize, (y + 1) * cellSize, 5 * cellSize, 5 * cellSize);
    ctx.fillStyle = "#000000";
    ctx.fillRect((x + 2) * cellSize, (y + 2) * cellSize, 3 * cellSize, 3 * cellSize);
  }
  drawFinder(0, 0);
  drawFinder(14, 0);
  drawFinder(0, 14);

  // Timing patterns
  for (let i = 8; i < 13; i += 2) {
    ctx.fillRect(i * cellSize, 6 * cellSize, cellSize, cellSize);
    ctx.fillRect(6 * cellSize, i * cellSize, cellSize, cellSize);
  }

  // Hash-based data module mapping
  let hash = 0;
  for (let i = 0; i < textPayload.length; i++) {
    hash = ((hash << 5) - hash) + textPayload.charCodeAt(i);
    hash |= 0;
  }

  for (let r = 0; r < modules; r++) {
    for (let c = 0; c < modules; c++) {
      if ((r < 8 && c < 8) || (r < 8 && c >= 13) || (r >= 13 && c < 8)) continue;
      if (r === 6 || c === 6) continue;
      const bit = (Math.abs(hash * (r * 31 + c * 17 + 13)) % 100) > 45;
      if (bit) {
        ctx.fillRect(c * cellSize, r * cellSize, cellSize, cellSize);
      }
    }
  }
}

// Display Digital Membership Card Modal
window.showCustomerMemberCard = function(customer) {
  if (!customer) return;
  document.getElementById("card-cust-name").textContent = customer.name;
  document.getElementById("card-cust-code").textContent = customer.membership_code || `MEM-${customer.phone}`;
  document.getElementById("card-cust-phone").textContent = `+91 ${customer.phone}`;
  document.getElementById("card-tier-tag").textContent = `${customer.tier} MEMBER`;
  document.getElementById("card-stat-visits").textContent = `${customer.visit_count} Visits`;
  document.getElementById("card-stat-points").textContent = `${customer.loyalty_points || customer.points || 0} Pts`;

  const qrPayload = customer.membership_qr_data || `RETAIL:MEM:${customer.membership_code || customer.phone}:${customer.phone}`;
  drawMemberQRCode("member-qr-canvas", qrPayload);

  document.getElementById("modal-member-card").classList.remove("hidden");
};

// Display Customer Shopping Habits & Insights Modal
window.showCustomerInsightsModal = async function(phone) {
  try {
    const res = await apiFetch(`/api/customers/${encodeURIComponent(phone)}/insights`);
    const data = await res.json();

    document.getElementById("insights-modal-title").innerHTML = `<i class="fa-solid fa-chart-pie"></i> ${escHtml(data.name)} (${escHtml(data.phone)}) - Shopping Habits`;

    // 1. Preferred Categories
    const catContainer = document.getElementById("cust-insights-categories");
    if (catContainer) {
      if (!data.category_preferences || data.category_preferences.length === 0) {
        catContainer.innerHTML = "<p class='text-muted'>No category purchase records yet.</p>";
      } else {
        catContainer.innerHTML = data.category_preferences.map(c => `
          <div class="mb-10" style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
              <strong>${escHtml(c.category)}</strong>
              <span>₹${c.spent.toFixed(2)} (${escHtml(c.percentage)}%)</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill active" style="width: ${escHtml(c.percentage)}%;"></div>
            </div>
          </div>
        `).join("");
      }
    }

    // 2. Top Purchased Products
    const prodTbody = document.getElementById("cust-insights-products-tbody");
    if (prodTbody) {
      if (!data.top_purchased_products || data.top_purchased_products.length === 0) {
        prodTbody.innerHTML = "<tr><td colspan='3' class='text-center text-muted'>No items recorded yet</td></tr>";
      } else {
        prodTbody.innerHTML = data.top_purchased_products.map(p => `
          <tr>
            <td><strong>${escHtml(p.name)}</strong><br><small class="text-muted">${escHtml(p.category)}</small></td>
            <td class="text-center font-weight-bold">${escHtml(p.units)}</td>
            <td class="text-right">₹${p.spent.toFixed(2)}</td>
          </tr>
        `).join("");
      }
    }

    // 3. Recent Invoices
    const ordContainer = document.getElementById("cust-insights-orders-list");
    if (ordContainer) {
      if (!data.recent_orders || data.recent_orders.length === 0) {
        ordContainer.innerHTML = "<p class='text-muted'>No historical invoices found.</p>";
      } else {
        ordContainer.innerHTML = data.recent_orders.map(o => `
          <div class="card mb-10" style="padding: 10px 14px; margin-bottom: 10px; background: var(--bg-surface-elevated);">
            <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 13px;">
              <span>Bill: ${escHtml(o.bill_number)} (${escHtml(o.date)})</span>
              <span style="color: var(--success-dark);">₹${o.grand_total.toFixed(2)} [${escHtml(o.payment_method)}]</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
              Items: ${escHtml(o.items_count)} | Savings: ₹${o.savings.toFixed(2)}
            </div>
          </div>
        `).join("");
      }
    }

    document.getElementById("modal-customer-insights").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to load customer insights", "error");
  }
};

// Checkout Execution
async function executeCheckout() {
  if (state.cart.length === 0) return;

  const total = state.cartPreview ? state.cartPreview.grand_total : 0;
  let tendered = total;

  if (state.paymentMethod === "CASH") {
    const cashInputVal = parseFloat(document.getElementById("tendered-cash-input").value);
    tendered = isNaN(cashInputVal) || cashInputVal < total ? total : cashInputVal;
  }

  const redeemChk = document.getElementById("redeem-points-chk");
  const pointsToRedeem = (redeemChk && redeemChk.checked && state.activeCustomer) ? state.activeCustomer.points : 0;

  const payload = {
    items: state.cart.map(i => ({ barcode: i.barcode, quantity: i.quantity })),
    payment_method: state.paymentMethod,
    tendered_amount: tendered,
    cashier_id: state.activeUser.id,
    cashier_name: state.activeUser.name,
    customer_phone: state.activeCustomer ? state.activeCustomer.phone : null,
    customer_name: state.activeCustomer ? state.activeCustomer.name : null,
    points_to_redeem: pointsToRedeem,
    branch_id: state.activeBranch ? state.activeBranch.id : "BR-DEL-01"
  };

  try {
    const res = await apiFetch("/api/pos/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Checkout failed");
    }

    const orderRes = await res.json();
    showToast(`Bill #${orderRes.bill_number} completed successfully!`, "success");

    // Display Thermal Receipt
    document.getElementById("receipt-content").textContent = orderRes.thermal_receipt_text;
    document.getElementById("receipt-modal").classList.remove("hidden");

    // Reset POS cart
    resetCart();
    loadInitialStoreData(); // Refresh product stock levels
  } catch (err) {
    showToast(err.message, "error");
  }
}

function resetCart() {
  state.cart = [];
  state.activeCustomer = null;
  state.cartPreview = null;
  document.getElementById("customer-phone-input").value = "";
  document.getElementById("customer-profile-banner").classList.add("hidden");
  document.getElementById("cust-tier-pill").classList.add("hidden");
  document.getElementById("tendered-cash-input").value = "";
  document.getElementById("change-returned-val").textContent = "₹0.00";
  recalculateCart();
  document.getElementById("barcode-input").focus();
}

// ============================================================================
// TAB 2: SALES & INVOICES REGISTER LOGIC
// ============================================================================
function initSalesEvents() {
  document.getElementById("refresh-orders-btn")?.addEventListener("click", loadSalesOrders);
  
  // Search & Filter
  const searchFilter = document.getElementById("sales-search-filter");
  const payFilter = document.getElementById("sales-payment-filter");
  const statusFilter = document.getElementById("sales-status-filter");

  [searchFilter, payFilter, statusFilter].forEach(el => {
    el?.addEventListener("input", applySalesFilters);
    el?.addEventListener("change", applySalesFilters);
  });

  // Returns Modal Trigger
  document.getElementById("open-returns-modal-btn")?.addEventListener("click", () => {
    document.getElementById("return-bill-input").value = "";
    document.getElementById("return-bill-details").classList.add("hidden");
    document.getElementById("confirm-return-btn").disabled = true;
    document.getElementById("return-modal").classList.remove("hidden");
  });
  document.getElementById("close-return-modal-btn")?.addEventListener("click", () => {
    document.getElementById("return-modal").classList.add("hidden");
  });
  document.getElementById("cancel-return-btn")?.addEventListener("click", () => {
    document.getElementById("return-modal").classList.add("hidden");
  });

  // Return Fetch Bill
  document.getElementById("fetch-return-bill-btn")?.addEventListener("click", fetchBillForReturn);
  document.getElementById("confirm-return-btn")?.addEventListener("click", submitCustomerReturn);

  // Void Modal Controls
  document.getElementById("close-void-modal-btn")?.addEventListener("click", () => {
    document.getElementById("void-modal").classList.add("hidden");
  });
  document.getElementById("cancel-void-btn")?.addEventListener("click", () => {
    document.getElementById("void-modal").classList.add("hidden");
  });
  document.getElementById("confirm-void-btn")?.addEventListener("click", submitVoidBill);

  // A4 Modal Controls
  document.getElementById("close-a4-modal-btn")?.addEventListener("click", () => {
    document.getElementById("a4-invoice-modal").classList.add("hidden");
  });
  document.getElementById("dismiss-a4-btn")?.addEventListener("click", () => {
    document.getElementById("a4-invoice-modal").classList.add("hidden");
  });
  document.getElementById("print-a4-btn")?.addEventListener("click", () => {
    window.print();
  });
}

async function loadSalesOrders() {
  try {
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/orders?branch_id=${branchId}`);
    state.recentOrders = await res.json();
    renderSalesTable(state.recentOrders);
  } catch (err) {
    console.error("Failed to load orders:", err);
  }
}

function applySalesFilters() {
  if (!state.recentOrders) return;
  const term = document.getElementById("sales-search-filter").value.toLowerCase();
  const payType = document.getElementById("sales-payment-filter").value;
  const statusType = document.getElementById("sales-status-filter").value;

  const filtered = state.recentOrders.filter(o => {
    const matchTerm = o.bill_number.toLowerCase().includes(term) || o.customer.toLowerCase().includes(term);
    const matchPay = payType === "ALL" || o.payment_method === payType;
    const matchStatus = statusType === "ALL" || o.status === statusType;
    return matchTerm && matchPay && matchStatus;
  });

  renderSalesTable(filtered);
}

function renderSalesTable(orders) {
  const tbody = document.getElementById("sales-orders-tbody");
  if (!orders || orders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 30px; color: var(--text-muted);">No sales records found.</td></tr>`;
    return;
  }

  tbody.innerHTML = orders.map(o => `
    <tr>
      <td><strong><code>${escHtml(o.bill_number)}</code></strong></td>
      <td>${escHtml(o.date)}</td>
      <td>${escHtml(o.customer)}</td>
      <td>${escHtml(o.cashier)}</td>
      <td class="text-center">${escHtml(o.items_count)}</td>
      <td class="text-center"><span class="status-pill">${escHtml(o.payment_method)}</span></td>
      <td class="text-right"><strong>₹${o.grand_total.toFixed(2)}</strong></td>
      <td class="text-center">
        <span class="status-pill ${escHtml(o.status.toLowerCase())}">${escHtml(o.status)}</span>
      </td>
      <td class="text-center" style="white-space: nowrap;">
        <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="reprintThermal('${escHtml(o.bill_number)}')" title="Reprint 80mm Thermal">
          <i class="fa-solid fa-receipt"></i>
        </button>
        <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="viewA4Invoice('${escHtml(o.bill_number)}')" title="View A4 Tax Invoice">
          <i class="fa-solid fa-file-invoice"></i>
        </button>
        ${o.status === 'COMPLETED' ? `
          <button class="btn-danger" style="padding: 4px 8px; font-size: 11px;" onclick="openVoidDialog('${o.bill_number}')" title="Void Transaction">
            <i class="fa-solid fa-ban"></i>
          </button>
        ` : ''}
      </td>
    </tr>
  `).join("");
}

window.reprintThermal = async function(billNumber) {
  try {
    const res = await apiFetch(`/api/orders/${billNumber}/thermal`);
    const txt = await res.text();
    document.getElementById("receipt-content").textContent = txt;
    document.getElementById("receipt-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to fetch receipt", "error");
  }
};

window.viewA4Invoice = async function(billNumber) {
  try {
    const res = await apiFetch(`/api/orders/${billNumber}/a4`);
    const html = await res.text();
    document.getElementById("a4-invoice-content").innerHTML = html;
    document.getElementById("a4-invoice-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to fetch A4 invoice", "error");
  }
};

window.openVoidDialog = function(billNumber) {
  state.voidTargetBill = billNumber;
  document.getElementById("void-bill-display").textContent = billNumber;
  document.getElementById("void-manager-pin").value = "";
  document.getElementById("void-modal").classList.remove("hidden");
};

async function submitVoidBill() {
  const pin = document.getElementById("void-manager-pin").value.trim();
  const reason = document.getElementById("void-reason-input").value.trim() || "Cashier Void";

  if (!pin) {
    showToast("Manager Authorization PIN required!", "error");
    return;
  }

  try {
    const res = await apiFetch(`/api/orders/${state.voidTargetBill}/void`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manager_pin: pin, reason: reason })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Void operation failed");
    }

    showToast(`Bill ${state.voidTargetBill} voided and inventory restored!`, "success");
    document.getElementById("void-modal").classList.add("hidden");
    loadSalesOrders();
    loadInitialStoreData();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Returns & Refunds
async function fetchBillForReturn() {
  const billNum = document.getElementById("return-bill-input").value.trim();
  if (!billNum) return;

  try {
    const res = await apiFetch(`/api/orders/${billNum}`);
    if (!res.ok) throw new Error("Bill not found");
    const order = await res.json();

    state.returnOrder = order;
    const tbody = document.getElementById("return-items-tbody");
    tbody.innerHTML = order.items.map(i => `
      <tr>
        <td class="text-center">
          <input type="checkbox" class="return-item-chk" data-barcode="${escHtml(i.barcode)}" data-price="${escHtml(i.unit_price)}" ${escHtml(i.is_returned ? 'disabled' : '')}>
        </td>
        <td>
          <strong>${escHtml(i.product_name)}</strong>
          ${escHtml(i.is_returned ? '<span class="status-pill refunded" style="font-size: 9px;">ALREADY RETURNED</span>' : '')}
        </td>
        <td class="text-center">${escHtml(i.quantity)}</td>
        <td class="text-center">
          <input type="number" class="return-qty-input" data-barcode="${escHtml(i.barcode)}" min="1" max="${escHtml(i.quantity)}" value="1" style="width: 50px; text-align: center;" ${escHtml(i.is_returned ? 'disabled' : '')}>
        </td>
        <td class="text-right">₹${i.unit_price.toFixed(2)}</td>
        <td class="text-right return-line-refund" data-barcode="${escHtml(i.barcode)}">₹0.00</td>
      </tr>
    `).join("");

    document.getElementById("return-bill-details").classList.remove("hidden");
    document.getElementById("confirm-return-btn").disabled = false;

    // Attach checkbox & quantity change listeners
    document.querySelectorAll(".return-item-chk, .return-qty-input").forEach(el => {
      el.addEventListener("change", updateReturnRefundTotals);
      el.addEventListener("input", updateReturnRefundTotals);
    });

    updateReturnRefundTotals();
  } catch (err) {
    showToast("Bill number not found in store database", "error");
  }
}

function updateReturnRefundTotals() {
  let totalRefund = 0;
  document.querySelectorAll(".return-item-chk").forEach(chk => {
    const barcode = chk.getAttribute("data-barcode");
    const price = parseFloat(chk.getAttribute("data-price"));
    const qtyInput = document.querySelector(`.return-qty-input[data-barcode="${barcode}"]`);
    const lineTotalCell = document.querySelector(`.return-line-refund[data-barcode="${barcode}"]`);

    if (chk.checked) {
      const qty = parseInt(qtyInput.value) || 1;
      const lineRefund = price * qty;
      lineTotalCell.textContent = `₹${lineRefund.toFixed(2)}`;
      totalRefund += lineRefund;
    } else {
      lineTotalCell.textContent = `₹0.00`;
    }
  });

  document.getElementById("return-total-refund-disp").textContent = `₹${totalRefund.toFixed(2)}`;
}

async function submitCustomerReturn() {
  const pin = document.getElementById("return-manager-pin").value.trim();
  const reason = document.getElementById("return-reason-select").value;
  if (!pin) {
    showToast("Manager PIN is required to authorize refund", "error");
    return;
  }

  const itemsToReturn = [];
  document.querySelectorAll(".return-item-chk:checked").forEach(chk => {
    const barcode = chk.getAttribute("data-barcode");
    const qtyInput = document.querySelector(`.return-qty-input[data-barcode="${barcode}"]`);
    itemsToReturn.push({
      barcode: barcode,
      quantity: parseInt(qtyInput.value) || 1
    });
  });

  if (itemsToReturn.length === 0) {
    showToast("Please select at least 1 item to return", "error");
    return;
  }

  try {
    const res = await apiFetch("/api/returns/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bill_number: state.returnOrder.bill_number,
        items: itemsToReturn,
        manager_pin: pin,
        cashier_id: state.activeUser.id,
        reason: reason
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Refund failed");
    }

    const retRes = await res.json();
    showToast(`Refund memo #${retRes.return_number} issued for ₹${retRes.refund_amount.toFixed(2)}`, "success");
    document.getElementById("return-modal").classList.add("hidden");
    loadSalesOrders();
    loadInitialStoreData();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ============================================================================
// TAB 3: REGISTER SHIFTS & DAY-END Z-REPORT
// ============================================================================
function initShiftEvents() {
  document.getElementById("safe-drop-btn")?.addEventListener("click", () => {
    document.getElementById("cash-drop-modal").classList.remove("hidden");
  });
  document.getElementById("close-drop-modal-btn")?.addEventListener("click", () => {
    document.getElementById("cash-drop-modal").classList.add("hidden");
  });
  document.getElementById("cancel-drop-btn")?.addEventListener("click", () => {
    document.getElementById("cash-drop-modal").classList.add("hidden");
  });
  document.getElementById("confirm-drop-btn")?.addEventListener("click", executeSafeDrop);

  document.getElementById("close-shift-btn")?.addEventListener("click", () => {
    document.getElementById("z-report-result").classList.add("hidden");
    document.getElementById("closing-counted-cash-input").value = "";
    document.getElementById("close-shift-modal").classList.remove("hidden");
  });
  document.getElementById("close-shift-modal-btn")?.addEventListener("click", () => {
    document.getElementById("close-shift-modal").classList.add("hidden");
  });
  document.getElementById("cancel-close-shift-btn")?.addEventListener("click", () => {
    document.getElementById("close-shift-modal").classList.add("hidden");
  });
  document.getElementById("confirm-close-shift-btn")?.addEventListener("click", executeCloseShift);
}

async function loadShiftStatus() {
  try {
    const res = await apiFetch(`/api/shifts/current?cashier_id=${state.activeUser.id}`);
    const shift = await res.json();
    state.currentShift = shift;

    document.getElementById("shift-disp-id").textContent = `Shift ID: ${shift.shift_id}`;
    document.getElementById("shift-start-time").textContent = `Opened: ${shift.start_time} | Cashier: ${shift.cashier}`;
    document.getElementById("shift-opening-float").textContent = `₹${shift.opening_float.toFixed(2)}`;
    document.getElementById("shift-cash-sales").textContent = `₹${shift.cash_sales.toFixed(2)}`;
    document.getElementById("shift-digital-sales").textContent = `₹${(shift.upi_sales + shift.card_sales).toFixed(2)}`;
    document.getElementById("shift-cash-drops").textContent = `₹${shift.cash_drops.toFixed(2)}`;
    document.getElementById("shift-expected-cash").textContent = `₹${shift.expected_drawer_cash.toFixed(2)}`;
  } catch (err) {
    console.error("Failed to load shift status:", err);
  }
}

async function loadShiftsHistory() {
  try {
    const res = await apiFetch("/api/shifts/history");
    const shifts = await res.json();

    const tbody = document.getElementById("shifts-history-tbody");
    tbody.innerHTML = shifts.map(s => `
      <tr>
        <td><code>${escHtml(s.id)}</code></td>
        <td>${escHtml(s.cashier_name)}</td>
        <td>${escHtml(s.start_time)}</td>
        <td>${escHtml(s.end_time)}</td>
        <td class="text-right">₹${s.opening_float.toFixed(2)}</td>
        <td class="text-right">₹${s.total_sales.toFixed(2)}</td>
        <td class="text-right">₹${s.expected_drawer_cash.toFixed(2)}</td>
        <td class="text-right">₹${s.actual_counted_cash.toFixed(2)}</td>
        <td class="text-right" style="color: ${escHtml(s.cash_variance === 0 ? 'var(--success-dark)' : s.cash_variance < 0 ? 'var(--danger-dark)' : 'var(--warning-dark)')}; font-weight: 800;">
          ${escHtml(s.cash_variance >= 0 ? '+' : '')}₹${s.cash_variance.toFixed(2)}
        </td>
        <td class="text-center">
          <span class="status-pill ${escHtml(s.is_closed ? 'completed' : 'in-progress')}">
            ${escHtml(s.is_closed ? 'CLOSED' : 'OPEN')}
          </span>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load shift history:", err);
  }
}

async function executeSafeDrop() {
  const amt = parseFloat(document.getElementById("drop-amount-input").value);
  const reason = document.getElementById("drop-reason-input").value.trim() || "Safe Drop";

  if (isNaN(amt) || amt <= 0) {
    showToast("Please enter a valid drop amount", "error");
    return;
  }

  try {
    const res = await apiFetch("/api/shifts/drop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cashier_id: state.activeUser.id,
        amount: amt,
        reason: reason
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Safe drop failed");
    }

    showToast(`₹${amt.toFixed(2)} transferred to store safe`, "success");
    document.getElementById("cash-drop-modal").classList.add("hidden");
    loadShiftStatus();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function executeCloseShift() {
  const counted = parseFloat(document.getElementById("closing-counted-cash-input").value);
  const notes = document.getElementById("closing-shift-notes").value.trim();

  if (isNaN(counted) || counted < 0) {
    showToast("Please enter actual counted physical drawer cash", "error");
    return;
  }

  try {
    const res = await apiFetch("/api/shifts/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cashier_id: state.activeUser.id,
        closing_counted_cash: counted,
        notes: notes
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Shift close failed");
    }

    const zReport = await res.json();
    document.getElementById("z-report-text").textContent = zReport.z_report_text;
    document.getElementById("z-report-result").classList.remove("hidden");
    showToast("Shift closed and Z-Report generated!", "success");

    loadShiftStatus();
    loadShiftsHistory();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ============================================================================
// TAB 4: STORE BI & P&L DASHBOARD
// ============================================================================
function initDashboardEvents() {
  document.querySelectorAll(".period-toggle-pills .period-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".period-toggle-pills .period-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.activePeriod = pill.getAttribute("data-period");
      loadDashboardData(state.activePeriod);
    });
  });

  document.querySelectorAll(".bi-subnav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".bi-subnav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-bi-target");
      document.querySelectorAll(".bi-subpane").forEach(pane => pane.classList.add("hidden"));
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.remove("hidden");

      if (targetId !== "bi-view-pl") {
        loadBusinessIntelligenceData();
      }
    });
  });
}

async function loadDashboardData(period = "today") {
  try {
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/dashboard?branch_id=${branchId}`);
    const data = await res.json();
    state.dashboardData = data;

    // Financial KPI Cards for selected period
    const p = data[period] || data.weekly || {};
    const rev = p.revenue !== undefined ? p.revenue : data.total_revenue;
    const cogs = p.cogs !== undefined ? p.cogs : data.cost_of_goods_sold;
    const exp = p.expenses !== undefined ? p.expenses : data.operating_expenses;
    const net = p.net_profit !== undefined ? p.net_profit : data.net_operating_profit;
    const orders = p.orders_count !== undefined ? p.orders_count : data.total_orders;
    const margin = p.profit_margin_pct !== undefined ? p.profit_margin_pct : data.net_profit_margin_percent;

    document.getElementById("dash-revenue").textContent = `₹${rev.toFixed(2)}`;
    document.getElementById("dash-cogs").textContent = `₹${cogs.toFixed(2)}`;
    document.getElementById("dash-expenses").textContent = `₹${exp.toFixed(2)}`;
    document.getElementById("dash-net-profit").textContent = `₹${net.toFixed(2)}`;
    document.getElementById("dash-orders-count").textContent = `${orders} Completed Bills`;
    document.getElementById("dash-profit-margin").textContent = `${margin}% Net Margin`;

    // Render Charts
    renderSalesTrendChart(data.seven_day_trend);
    renderCategoryChart(data.category_distribution);

    // Fast Moving Products Table
    const topTbody = document.getElementById("top-products-tbody");
    topTbody.innerHTML = data.top_moving_products.map(p => `
      <tr>
        <td><strong>${escHtml(p.name)}</strong></td>
        <td><span class="status-pill">${escHtml(p.category)}</span></td>
        <td class="text-center"><strong>${escHtml(p.units_sold)}</strong></td>
        <td class="text-right">₹${p.revenue.toFixed(2)}</td>
      </tr>
    `).join("");

    // Depleted Stock Alerts (Min-Heap Priority Queue)
    const lowTbody = document.getElementById("low-stock-tbody");
    lowTbody.innerHTML = data.low_stock_alerts.map(p => `
      <tr>
        <td><strong>${escHtml(p.name)}</strong></td>
        <td>${escHtml(p.category)}</td>
        <td class="text-center" style="color: var(--danger-dark); font-weight: 800;">${escHtml(p.current_stock)}</td>
        <td class="text-center">${escHtml(p.reorder_level)}</td>
        <td class="text-center"><span class="status-pill cancelled">CRITICAL REORDER</span></td>
      </tr>
    `).join("");

  } catch (err) {
    console.error("Failed to load dashboard data:", err);
  }
}

function renderSalesTrendChart(trend) {
  const ctx = document.getElementById("salesTrendChart").getContext("2d");
  if (state.salesTrendChart) state.salesTrendChart.destroy();

  const labels = trend.map(t => t.date);
  const revenueData = trend.map(t => t.revenue);
  const ordersData = trend.map(t => t.orders_count);

  state.salesTrendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Daily Revenue (₹)",
          data: revenueData,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          fill: true,
          tension: 0.35,
          yAxisID: "y"
        },
        {
          label: "Bills Generated",
          data: ordersData,
          borderColor: "#10b981",
          backgroundColor: "transparent",
          borderDash: [5, 5],
          tension: 0.2,
          yAxisID: "y1"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          type: "linear",
          position: "left",
          ticks: { callback: v => `₹${v}` }
        },
        y1: {
          type: "linear",
          position: "right",
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}

function renderCategoryChart(catData) {
  const ctx = document.getElementById("categoryChart").getContext("2d");
  if (state.categoryChart) state.categoryChart.destroy();

  const labels = catData.map(c => c.category);
  const values = catData.map(c => c.revenue);

  state.categoryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: [
          "#3b82f6", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4", "#64748b"
        ]
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right" }
      }
    }
  });
}

// --- BUSINESS INTELLIGENCE SUITE ---
async function loadBusinessIntelligenceData() {
  try {
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/analytics/business-intelligence?branch_id=${branchId}`);
    if (!res.ok) throw new Error("Failed to load business intelligence");
    const bi = await res.json();
    state.businessIntelligence = bi;

    // 1. Best-Selling Products Table
    const bsTbody = document.getElementById("bi-bestsellers-tbody");
    if (bsTbody) {
      if (!bi.best_selling_products || bi.best_selling_products.length === 0) {
        bsTbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding: 24px;">No completed sales records found for this branch.</td></tr>`;
      } else {
        bsTbody.innerHTML = bi.best_selling_products.map(p => `
          <tr>
            <td class="text-center"><span class="rank-badge ${escHtml(p.rank <= 3 ? 'top3' : '')}">#${escHtml(p.rank)}</span></td>
            <td><strong>${escHtml(p.name)}</strong><br><small class="text-muted">${escHtml(p.brand)}</small></td>
            <td><code>${escHtml(p.barcode)}</code></td>
            <td><span class="status-pill">${escHtml(p.category)}</span></td>
            <td class="text-center">${escHtml(p.units_sold_30d)}</td>
            <td class="text-center font-weight-bold">${escHtml(p.units_sold)}</td>
            <td class="text-right font-weight-bold">₹${p.gross_revenue.toFixed(2)}</td>
            <td class="text-right" style="color: var(--success-dark); font-weight: 700;">₹${p.gross_profit.toFixed(2)}</td>
            <td class="text-center font-weight-bold">${escHtml(p.profit_margin_percent)}%</td>
            <td class="text-center">${escHtml(p.current_stock)}</td>
          </tr>
        `).join("");
      }
    }

    // 2. Slow-Moving Stock & Tied-up Working Capital
    const sm = bi.slow_moving_stock;
    if (sm) {
      const lockedCapEl = document.getElementById("bi-total-locked-capital");
      if (lockedCapEl) lockedCapEl.textContent = `₹${sm.total_locked_capital.toFixed(2)}`;

      const smTbody = document.getElementById("bi-slowmoving-tbody");
      if (smTbody) {
        if (!sm.items || sm.items.length === 0) {
          smTbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding: 24px;">All stock items have healthy velocity turnover (no stagnant inventory).</td></tr>`;
        } else {
          smTbody.innerHTML = sm.items.map(s => `
            <tr>
              <td><strong>${escHtml(s.name)}</strong><br><small class="text-muted">${escHtml(s.barcode)} | ${escHtml(s.brand)}</small></td>
              <td><span class="status-pill">${escHtml(s.category)}</span></td>
              <td class="text-center font-weight-bold">${escHtml(s.current_stock)}</td>
              <td class="text-center">${escHtml(s.units_sold_30d)}</td>
              <td class="text-right">₹${s.cost_price.toFixed(2)}</td>
              <td class="text-right">₹${s.selling_price.toFixed(2)}</td>
              <td class="text-right" style="color: var(--danger-dark); font-weight: 800;">₹${s.capital_locked.toFixed(2)}</td>
              <td class="text-center">
                <span class="risk-chip ${escHtml(s.risk_level.toLowerCase())}">${escHtml(s.risk_level.replace(/_/g, " "))}</span>
              </td>
              <td><span style="font-size: 11px; font-weight: 600;">${escHtml(s.recommended_action)}</span></td>
            </tr>
          `).join("");
        }
      }
    }

    // 3. Customer Retention & Churn Monitoring
    const cr = bi.customer_retention;
    if (cr) {
      document.getElementById("bi-retention-rate").textContent = `${cr.repeat_customer_rate_percent}%`;
      document.getElementById("bi-returning-count").textContent = cr.returning_customers;
      document.getElementById("bi-singlevisit-count").textContent = cr.single_visit_customers;
      document.getElementById("bi-avg-ltv").textContent = `₹${cr.average_lifetime_value.toFixed(2)}`;

      const totCust = Math.max(1, cr.total_customers);
      const act = cr.churn_status.active_recent;
      const risk = cr.churn_status.at_risk_cooling;
      const dorm = cr.churn_status.dormant_churned;

      document.getElementById("bi-churn-active-count").textContent = `${act} Customers`;
      document.getElementById("bi-churn-active-bar").style.width = `${Math.min(100, Math.round(act / totCust * 100))}%`;

      document.getElementById("bi-churn-risk-count").textContent = `${risk} Customers`;
      document.getElementById("bi-churn-risk-bar").style.width = `${Math.min(100, Math.round(risk / totCust * 100))}%`;

      document.getElementById("bi-churn-dormant-count").textContent = `${dorm} Customers`;
      document.getElementById("bi-churn-dormant-bar").style.width = `${Math.min(100, Math.round(dorm / totCust * 100))}%`;

      const tiersTbody = document.getElementById("bi-tiers-tbody");
      if (tiersTbody) {
        tiersTbody.innerHTML = cr.tier_distribution.map(t => `
          <tr>
            <td><span class="tier-chip-badge ${escHtml(t.tier.toLowerCase())}">${escHtml(t.tier)}</span></td>
            <td class="text-center font-weight-bold">${escHtml(t.customers_count)}</td>
            <td class="text-right"><strong>₹${t.total_spend.toFixed(2)}</strong></td>
          </tr>
        `).join("");
      }
    }

    // 4. Seasonal & Peak Demand Patterns
    const sd = bi.seasonal_demand;
    if (sd) {
      const busyTag = document.getElementById("bi-busiest-day-tag");
      if (busyTag) busyTag.textContent = `Busiest Day: ${sd.busiest_day}`;
      const peakTag = document.getElementById("bi-peak-hour-tag");
      if (peakTag) peakTag.textContent = `Peak Rush: ${sd.peak_hour}`;

      renderDayOfWeekChart(sd.day_of_week);
      renderHourlyPeakChart(sd.hourly_peaks);

      const catTbody = document.getElementById("bi-seasonal-categories-tbody");
      if (catTbody) {
        if (!sd.category_distribution || sd.category_distribution.length === 0) {
          catTbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted" style="padding: 16px;">No category demand data available.</td></tr>`;
        } else {
          catTbody.innerHTML = sd.category_distribution.map(c => `
            <tr>
              <td><strong>${escHtml(c.category)}</strong></td>
              <td class="text-center font-weight-bold">${escHtml(c.units_sold)}</td>
              <td class="text-right"><strong>₹${c.revenue.toFixed(2)}</strong></td>
              <td class="text-right"><span class="status-pill">${escHtml(c.share_percent)}%</span></td>
            </tr>
          `).join("");
        }
      }
    }

    // 5. Restock Priority Queue
    const rp = bi.restock_priority;
    if (rp) {
      const budgetEl = document.getElementById("bi-total-restock-budget");
      if (budgetEl) budgetEl.textContent = `₹${rp.estimated_total_restock_cost.toFixed(2)}`;

      const restockTbody = document.getElementById("bi-restock-tbody");
      if (restockTbody) {
        if (!rp.items || rp.items.length === 0) {
          restockTbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding: 24px;">All shelf stock levels are healthy above reorder thresholds.</td></tr>`;
        } else {
          restockTbody.innerHTML = rp.items.map(r => `
            <tr>
              <td><strong>${escHtml(r.name)}</strong><br><small class="text-muted">${escHtml(r.brand)}</small></td>
              <td><code>${escHtml(r.barcode)}</code></td>
              <td><span class="status-pill">${escHtml(r.category)}</span></td>
              <td class="text-center" style="${escHtml(r.current_stock === 0 ? 'color: var(--danger-dark); font-weight: 800;' : 'font-weight: 700;')}">${escHtml(r.current_stock)}</td>
              <td class="text-center">${escHtml(r.reorder_level)}</td>
              <td class="text-center">${escHtml(r.depletion_ratio)}x</td>
              <td class="text-center">
                <span class="status-pill ${escHtml(r.current_stock === 0 ? 'cancelled' : r.depletion_ratio <= 0.5 ? 'refunded' : 'completed')}">
                  ${escHtml(r.urgency.replace(/_/g, " "))}
                </span>
              </td>
              <td class="text-center font-weight-bold">${escHtml(r.suggested_order_quantity)} Units</td>
              <td class="text-right font-weight-bold">₹${r.estimated_restock_cost.toFixed(2)}</td>
              <td><span style="font-size: 11px;">${escHtml(r.supplier)}</span></td>
            </tr>
          `).join("");
        }
      }
    }
  } catch (err) {
    console.error("Failed to load business intelligence data:", err);
  }
}

function renderDayOfWeekChart(dowData) {
  const canvas = document.getElementById("dayOfWeekChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (state.dayOfWeekChart) state.dayOfWeekChart.destroy();

  const labels = (dowData || []).map(d => d.day.slice(0, 3));
  const revs = (dowData || []).map(d => d.revenue);
  const orders = (dowData || []).map(d => d.orders_count);

  state.dayOfWeekChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Gross Sales (₹)",
          data: revs,
          backgroundColor: "rgba(37, 99, 235, 0.75)",
          borderColor: "#2563eb",
          borderWidth: 1,
          borderRadius: 4,
          yAxisID: "y"
        },
        {
          label: "Footfall / Bills",
          data: orders,
          type: "line",
          borderColor: "#10b981",
          backgroundColor: "#10b981",
          tension: 0.3,
          yAxisID: "y1"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          type: "linear",
          position: "left",
          ticks: { callback: v => `₹${v}` }
        },
        y1: {
          type: "linear",
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { precision: 0 }
        }
      }
    }
  });
}

function renderHourlyPeakChart(hourlyData) {
  const canvas = document.getElementById("hourlyPeakChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (state.hourlyPeakChart) state.hourlyPeakChart.destroy();

  const labels = (hourlyData || []).map(h => h.hour);
  const orders = (hourlyData || []).map(h => h.orders_count);

  state.hourlyPeakChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Cashier Transactions / Hr",
          data: orders,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointBackgroundColor: "#f59e0b"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 }
        }
      }
    }
  });
}

// ============================================================================
// TAB 5: INVENTORY & STOCK MANAGEMENT
// ============================================================================
function initInventoryEvents() {
  document.getElementById("add-product-modal-btn")?.addEventListener("click", () => {
    document.getElementById("product-form").reset();
    document.getElementById("product-modal").classList.remove("hidden");
  });
  document.getElementById("close-product-modal-btn")?.addEventListener("click", () => {
    document.getElementById("product-modal").classList.add("hidden");
  });
  document.getElementById("cancel-product-btn")?.addEventListener("click", () => {
    document.getElementById("product-modal").classList.add("hidden");
  });

  // Product Form Submit
  document.getElementById("product-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      barcode: document.getElementById("prod-barcode-input").value.trim(),
      sku: document.getElementById("prod-sku-input").value.trim(),
      name: document.getElementById("prod-name-input").value.trim(),
      category: document.getElementById("prod-category-input").value.trim(),
      brand: document.getElementById("prod-brand-input").value.trim(),
      unit: document.getElementById("prod-unit-input").value.trim(),
      cost_price: parseFloat(document.getElementById("prod-cost-input").value),
      selling_price: parseFloat(document.getElementById("prod-price-input").value),
      mrp: parseFloat(document.getElementById("prod-mrp-input").value),
      stock_quantity: parseInt(document.getElementById("prod-stock-input").value),
      reorder_level: parseInt(document.getElementById("prod-reorder-input").value),
      tax_rate_percent: parseFloat(document.getElementById("prod-tax-input").value)
    };

    try {
      const res = await apiFetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("Failed to save product");

      showToast("Product SKU added to catalog!", "success");
      document.getElementById("product-modal").classList.add("hidden");
      loadInitialStoreData();
      loadInventoryData();
      loadValuationData();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Stock Adjustment Modal
  document.getElementById("close-adjust-modal-btn")?.addEventListener("click", () => {
    document.getElementById("stock-adjust-modal").classList.add("hidden");
  });
  document.getElementById("cancel-adjust-btn")?.addEventListener("click", () => {
    document.getElementById("stock-adjust-modal").classList.add("hidden");
  });
  document.getElementById("confirm-adjust-btn")?.addEventListener("click", submitStockAdjustment);

  // Bulk CSV Import Modal
  document.getElementById("import-catalog-modal-btn")?.addEventListener("click", () => {
    document.getElementById("import-csv-textarea").value = "";
    document.getElementById("import-catalog-modal").classList.remove("hidden");
  });
  document.getElementById("close-import-modal-btn")?.addEventListener("click", () => {
    document.getElementById("import-catalog-modal").classList.add("hidden");
  });
  document.getElementById("cancel-import-csv-btn")?.addEventListener("click", () => {
    document.getElementById("import-catalog-modal").classList.add("hidden");
  });
  document.getElementById("confirm-import-csv-btn")?.addEventListener("click", submitBulkCSVImport);

  // Barcode Tag Modal
  document.getElementById("close-tag-modal-btn")?.addEventListener("click", () => {
    document.getElementById("shelf-tag-modal").classList.add("hidden");
  });
  document.getElementById("dismiss-tag-btn")?.addEventListener("click", () => {
    document.getElementById("shelf-tag-modal").classList.add("hidden");
  });

  // Filter Inventory
  const searchEl = document.getElementById("inventory-search-filter");
  const stockEl = document.getElementById("inventory-stock-filter");
  [searchEl, stockEl].forEach(el => {
    el?.addEventListener("input", filterInventoryTable);
    el?.addEventListener("change", filterInventoryTable);
  });
}

async function loadInventoryData() {
  try {
    const res = await apiFetch("/api/products");
    state.inventoryProducts = await res.json();
    renderInventoryTable(state.inventoryProducts);
  } catch (err) {
    console.error("Failed to load inventory:", err);
  }
}

async function loadValuationData() {
  try {
    const res = await apiFetch("/api/inventory/valuation");
    const val = await res.json();
    document.getElementById("val-skus-count").textContent = val.total_distinct_skus;
    document.getElementById("val-units-count").textContent = val.total_physical_units;
    document.getElementById("val-cost-total").textContent = `₹${val.total_cost_valuation.toFixed(2)}`;
    document.getElementById("val-retail-total").textContent = `₹${val.total_retail_valuation.toFixed(2)}`;
    document.getElementById("val-gross-margin").textContent = `₹${val.potential_gross_margin.toFixed(2)}`;
  } catch (err) {
    console.error("Failed to load valuation:", err);
  }
}

function filterInventoryTable() {
  if (!state.inventoryProducts) return;
  const term = document.getElementById("inventory-search-filter").value.toLowerCase();
  const filterType = document.getElementById("inventory-stock-filter").value;

  const filtered = state.inventoryProducts.filter(p => {
    const matchTerm = p.name.toLowerCase().includes(term) || p.barcode.includes(term) || p.brand.toLowerCase().includes(term);
    let matchStock = true;
    if (filterType === "LOW") matchStock = p.is_low_stock && !p.is_out_of_stock;
    if (filterType === "OUT") matchStock = p.is_out_of_stock;
    return matchTerm && matchStock;
  });

  renderInventoryTable(filtered);
}

function renderInventoryTable(products) {
  const tbody = document.getElementById("inventory-tbody");
  tbody.innerHTML = products.map(p => `
    <tr>
      <td><code>${escHtml(p.barcode)}</code></td>
      <td><strong>${escHtml(p.name)}</strong><br><small style="color: var(--text-muted);">${escHtml(p.brand)}</small></td>
      <td><span class="status-pill">${escHtml(p.category)}</span></td>
      <td class="text-right">₹${p.cost_price.toFixed(2)}</td>
      <td class="text-right"><strong>₹${p.selling_price.toFixed(2)}</strong></td>
      <td class="text-right" style="color: var(--text-muted);">₹${p.mrp.toFixed(2)}</td>
      <td class="text-right" style="color: var(--success-dark); font-weight: 700;">₹${(p.selling_price - p.cost_price).toFixed(2)}</td>
      <td class="text-center" style="${escHtml(p.is_low_stock ? 'color: var(--danger-dark); font-weight: 800;' : '')}">
        ${escHtml(p.stock_quantity)} ${escHtml(p.unit)}
      </td>
      <td class="text-center">
        ${escHtml(p.is_out_of_stock 
          ? '<span class="status-pill cancelled">OUT OF STOCK</span>' 
          : p.is_low_stock 
            ? '<span class="status-pill refunded">LOW STOCK</span>' 
            : '<span class="status-pill completed">HEALTHY</span>')}
      </td>
      <td class="text-center" style="white-space: nowrap;">
        <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="openStockAdjustModal('${escHtml(p.barcode)}', '${escHtml(p.name.replace(/'/g, "\\'"))}', ${escHtml(p.stock_quantity)})" title="Adjust Stock">
          <i class="fa-solid fa-sliders"></i>
        </button>
        <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="openShelfBarcodeTag('${escHtml(p.barcode)}')" title="Print Shelf Tag">
          <i class="fa-solid fa-barcode"></i>
        </button>
      </td>
    </tr>
  `).join("");
}

window.openStockAdjustModal = function(barcode, name, currQty) {
  document.getElementById("adjust-barcode-input").value = barcode;
  document.getElementById("adjust-name-input").value = name;
  document.getElementById("adjust-qty-input").value = currQty;
  document.getElementById("adjust-notes-input").value = "";
  document.getElementById("stock-adjust-modal").classList.remove("hidden");
};

async function submitStockAdjustment() {
  const barcode = document.getElementById("adjust-barcode-input").value;
  const newQty = parseInt(document.getElementById("adjust-qty-input").value);
  const reasonType = document.getElementById("adjust-reason-type").value;
  const notes = document.getElementById("adjust-notes-input").value.trim();

  if (isNaN(newQty) || newQty < 0) {
    showToast("Please enter a valid stock quantity", "error");
    return;
  }

  try {
    const res = await apiFetch("/api/inventory/adjust", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        barcode: barcode,
        new_quantity: newQty,
        reason_type: reasonType,
        notes: notes
      })
    });

    if (!res.ok) throw new Error("Stock adjustment failed");
    showToast("Stock level updated and audited!", "success");
    document.getElementById("stock-adjust-modal").classList.add("hidden");
    loadInitialStoreData();
    loadInventoryData();
    loadValuationData();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function submitBulkCSVImport() {
  const csvContent = document.getElementById("import-csv-textarea").value.trim();
  if (!csvContent) {
    showToast("Please paste CSV contents to import", "error");
    return;
  }

  try {
    const res = await apiFetch("/api/inventory/import-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_content: csvContent })
    });

    if (!res.ok) throw new Error("Bulk import failed");
    const data = await res.json();
    showToast(`Successfully upserted ${data.imported_products} products into catalog!`, "success");
    document.getElementById("import-catalog-modal").classList.add("hidden");
    loadInitialStoreData();
    loadInventoryData();
    loadValuationData();
  } catch (err) {
    showToast(err.message, "error");
  }
}

window.openShelfBarcodeTag = async function(barcode) {
  try {
    const res = await apiFetch(`/api/inventory/barcode/${barcode}`);
    const tag = await res.json();

    const container = document.getElementById("shelf-tag-container");
    container.innerHTML = `
      <div style="text-align: left; font-size: 11px; font-weight: 700; color: #1e3a8a;">APEX ENTERPRISE RETAIL</div>
      <h2 style="margin: 8px 0; font-size: 16px;">${escHtml(tag.name)}</h2>
      <div style="color: #64748b; font-size: 11px;">Category: ${escHtml(tag.category)} | SKU: ${escHtml(tag.sku)}</div>
      <div class="tag-price">₹${tag.selling_price.toFixed(2)}</div>
      <div style="font-size: 12px; color: #059669; font-weight: 700; margin-bottom: 8px;">
        MRP ₹${tag.mrp.toFixed(2)} (SAVE ₹${tag.save_amount.toFixed(2)})
      </div>
      <div class="tag-barcode">||| | ||||| || |||||| | |||</div>
      <div style="font-family: var(--font-mono); font-size: 12px; letter-spacing: 2px;">${escHtml(tag.barcode)}</div>
    `;

    document.getElementById("shelf-tag-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to generate shelf tag", "error");
  }
};

// ============================================================================
// TAB 6: CUSTOMER FOOTFALL & CRM LOGIC
// ============================================================================
function initCustomerEvents() {
  const filterInput = document.getElementById("cust-table-filter");
  filterInput?.addEventListener("input", (e) => {
    const term = e.target.value.toLowerCase();
    const rows = document.querySelectorAll("#customers-tbody tr");
    rows.forEach(r => {
      const txt = r.textContent.toLowerCase();
      r.style.display = txt.includes(term) ? "" : "none";
    });
  });

  document.getElementById("close-history-modal-btn")?.addEventListener("click", () => {
    document.getElementById("cust-history-modal").classList.add("hidden");
  });
}

async function loadCustomersData() {
  try {
    const res = await apiFetch("/api/customers");
    const customers = await res.json();

    const tbody = document.getElementById("customers-tbody");
    tbody.innerHTML = customers.map(c => `
      <tr>
        <td><code class="membership-id-pill">${escHtml(c.membership_code || ('MEM-' + c.phone))}</code></td>
        <td><strong>${escHtml(c.name)}</strong></td>
        <td><code>${escHtml(c.phone)}</code></td>
        <td class="text-center">
          <strong style="color: var(--primary); font-size: 13px;">${escHtml(c.visit_count)} Visits</strong>
        </td>
        <td class="text-center">
          <span class="tier-chip-badge ${escHtml(c.tier.toLowerCase())}">${escHtml(c.tier)}</span>
        </td>
        <td class="text-center">⭐ ${escHtml(c.loyalty_points)}</td>
        <td class="text-right">₹${c.total_spent.toFixed(2)}</td>
        <td class="text-right">₹${c.avg_basket.toFixed(2)}</td>
        <td>${escHtml(c.last_visited)}</td>
        <td class="text-center" style="white-space: nowrap;">
          <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="viewCustomerBills('${escHtml(c.phone)}', '${escHtml(c.name.replace(/'/g, "\\'"))}')" title="Order History">
            <i class="fa-solid fa-receipt"></i>
          </button>
          <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px; margin-left: 3px;" onclick="showCustomerInsightsModal('${escHtml(c.phone)}')" title="Shopping Habits">
            <i class="fa-solid fa-chart-pie"></i>
          </button>
          <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px; margin-left: 3px;" onclick="viewCustomerCardByPhone('${escHtml(c.phone)}')" title="Membership Digital Card">
            <i class="fa-solid fa-id-card"></i>
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load customers:", err);
  }
}

window.viewCustomerCardByPhone = async function(phone) {
  try {
    const res = await apiFetch(`/api/customers/recognize?identifier=${encodeURIComponent(phone)}`);
    const data = await res.json();
    if (data.found) {
      window.showCustomerMemberCard(data);
    } else {
      showToast("Customer profile not found", "error");
    }
  } catch (err) {
    showToast("Failed to fetch customer card", "error");
  }
};

window.viewCustomerBills = async function(phone, name) {
  try {
    const res = await apiFetch(`/api/customers/${encodeURIComponent(phone)}/history`);
    const history = await res.json();

    document.getElementById("history-modal-title").innerHTML = `<i class="fa-solid fa-clock-rotate-left"></i> ${escHtml(name)} (${escHtml(phone)}) - Order History`;
    const listContainer = document.getElementById("customer-history-list");

    if (!history || history.length === 0) {
      listContainer.innerHTML = "<p>No previous orders found for this customer.</p>";
    } else {
      listContainer.innerHTML = history.map(h => `
        <div class="card mb-10" style="padding: 12px; margin-bottom: 10px; background-color: var(--bg-surface-elevated);">
          <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 13px; margin-bottom: 6px;">
            <span>Bill: ${escHtml(h.bill_number)} (${escHtml(h.date)})</span>
            <span style="color: var(--success-dark);">Grand Total: ₹${h.grand_total.toFixed(2)} [${escHtml(h.payment_method)}]</span>
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">
            Items Count: ${escHtml(h.items_count)} | Total MRP Savings: ₹${h.savings.toFixed(2)} | Status: ${escHtml(h.status)}
          </div>
          <ul style="padding-left: 20px; font-size: 12px;">
            ${h.items.map(i => `<li>${i.name} (Qty: ${i.quantity}) - ₹${i.total.toFixed(2)} ${i.is_returned ? '<span class="status-pill refunded" style="font-size: 8px;">RETURNED</span>' : ''}</li>`).join("")}
          </ul>
        </div>
      `).join("");
    }

    document.getElementById("cust-history-modal").classList.remove("hidden");
  } catch (err) {
    showToast("Failed to load customer history", "error");
  }
};

// ============================================================================
// TAB 7: EXPENSE TRACKER (WEEKLY, MONTHLY, YEARLY)
// ============================================================================
function initExpenseEvents() {
  document.getElementById("add-expense-modal-btn")?.addEventListener("click", () => {
    document.getElementById("expense-form").reset();
    document.getElementById("exp-date-input").value = new Date().toISOString().split("T")[0];
    document.getElementById("expense-modal").classList.remove("hidden");
  });
  document.getElementById("close-expense-modal-btn")?.addEventListener("click", () => {
    document.getElementById("expense-modal").classList.add("hidden");
  });
  document.getElementById("cancel-expense-btn")?.addEventListener("click", () => {
    document.getElementById("expense-modal").classList.add("hidden");
  });

  document.getElementById("expense-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      category: document.getElementById("exp-category-input").value,
      amount: parseFloat(document.getElementById("exp-amount-input").value),
      expense_date: document.getElementById("exp-date-input").value,
      description: document.getElementById("exp-desc-input").value.trim(),
      payment_mode: document.getElementById("exp-mode-input").value,
      vendor_name: document.getElementById("exp-vendor-input").value.trim(),
      branch_id: state.activeBranch ? state.activeBranch.id : "BR-DEL-01"
    };

    try {
      const res = await apiFetch("/api/expenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("Failed to record expense");

      showToast("Store operating expense saved!", "success");
      document.getElementById("expense-modal").classList.add("hidden");
      loadExpensesData();
      loadExpenseSummary();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

async function loadExpenseSummary() {
  try {
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/expenses/summary?branch_id=${branchId}`);
    const summary = await res.json();
    document.getElementById("exp-total-weekly").textContent = `₹${summary.weekly_total.toFixed(2)}`;
    document.getElementById("exp-total-monthly").textContent = `₹${summary.monthly_total.toFixed(2)}`;
    document.getElementById("exp-total-yearly").textContent = `₹${summary.yearly_total.toFixed(2)}`;
  } catch (err) {
    console.error("Failed to load expense summary:", err);
  }
}

async function loadExpensesData() {
  try {
    const branchId = state.activeBranch ? state.activeBranch.id : "BR-DEL-01";
    const res = await apiFetch(`/api/expenses?branch_id=${branchId}`);
    const expenses = await res.json();

    const tbody = document.getElementById("expenses-tbody");
    tbody.innerHTML = expenses.map(e => `
      <tr>
        <td>${escHtml(e.expense_date)}</td>
        <td><span class="status-pill">${escHtml(e.category)}</span></td>
        <td><strong>${escHtml(e.description)}</strong></td>
        <td>${escHtml(e.payment_mode)}</td>
        <td>${escHtml(e.vendor_name || 'Store')}</td>
        <td class="text-right"><strong>₹${e.amount.toFixed(2)}</strong></td>
        <td class="text-center">
          <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px; color: var(--danger-dark);" onclick="deleteExpenseItem('${escHtml(e.id)}')">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load expenses:", err);
  }
}

window.deleteExpenseItem = async function(id) {
  if (confirm("Are you sure you want to delete this expense record?")) {
    try {
      await apiFetch(`/api/expenses/${id}`, { method: "DELETE" });
      showToast("Expense record removed", "info");
      loadExpensesData();
      loadExpenseSummary();
    } catch (err) {
      showToast("Failed to delete expense", "error");
    }
  }
};

// ============================================================================
// TAB 9: MULTI-BRANCH STORE ARCHITECTURE & INTER-BRANCH LOGISTICS
// ============================================================================
function initBranchEvents() {
  const branchSelect = document.getElementById("active-branch-select");
  if (branchSelect) {
    branchSelect.addEventListener("change", (e) => {
      const selectedId = e.target.value;
      const b = state.branches.find(br => br.id === selectedId);
      if (b) {
        state.activeBranch = b;
        document.getElementById("sidebar-branch-name").textContent = b.name;
        document.getElementById("sidebar-branch-code").textContent = `Branch ID: ${b.code}`;
        showToast(`Active Store switched to: ${b.name}`, "info");
        loadInitialStoreData();
      }
    });
  }

  // Open Register Branch Modal
  const openBranchBtn = document.getElementById("btn-open-register-branch");
  if (openBranchBtn) {
    openBranchBtn.addEventListener("click", () => {
      document.getElementById("branch-form").reset();
      document.getElementById("modal-register-branch").classList.remove("hidden");
    });
  }
  document.getElementById("close-branch-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-register-branch").classList.add("hidden");
  });
  document.getElementById("cancel-branch-btn")?.addEventListener("click", () => {
    document.getElementById("modal-register-branch").classList.add("hidden");
  });

  // Register Branch Form Submit
  const branchForm = document.getElementById("branch-form");
  if (branchForm) {
    branchForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        code: document.getElementById("branch-code-input").value.trim().toUpperCase(),
        name: document.getElementById("branch-name-input").value.trim(),
        address: document.getElementById("branch-address-input").value.trim(),
        city: document.getElementById("branch-city-input").value.trim(),
        state: document.getElementById("branch-state-input").value.trim(),
        pincode: document.getElementById("branch-pincode-input").value.trim(),
        phone: document.getElementById("branch-phone-input").value.trim(),
        gstin: document.getElementById("branch-gstin-input").value.trim(),
        manager_name: document.getElementById("branch-manager-input").value.trim(),
        is_headquarters: false,
      };

      try {
        const res = await apiFetch("/api/branches", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Failed to register branch");
        }
        const data = await res.json();
        showToast(`Store branch ${data.name} registered successfully!`, "success");
        document.getElementById("modal-register-branch").classList.add("hidden");
        await loadBranchesData();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }

  // Open Transfer Modal
  const openTransferBtn = document.getElementById("btn-open-transfer-modal");
  if (openTransferBtn) {
    openTransferBtn.addEventListener("click", () => {
      populateTransferModalDropdowns();
      document.getElementById("modal-stock-transfer").classList.remove("hidden");
    });
  }
  document.getElementById("close-transfer-modal-btn")?.addEventListener("click", () => {
    document.getElementById("modal-stock-transfer").classList.add("hidden");
  });
  document.getElementById("cancel-transfer-btn")?.addEventListener("click", () => {
    document.getElementById("modal-stock-transfer").classList.add("hidden");
  });

  // Submit Inter-Branch Transfer
  const transferForm = document.getElementById("transfer-stock-form");
  if (transferForm) {
    transferForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fromBranch = document.getElementById("transfer-from-select").value;
      const toBranch = document.getElementById("transfer-to-select").value;
      const barcode = document.getElementById("transfer-product-select").value;
      const qty = parseInt(document.getElementById("transfer-qty-input").value, 10);
      const reason = document.getElementById("transfer-reason-input").value.trim();

      if (fromBranch === toBranch) {
        showToast("Source and destination store branches must be different!", "error");
        return;
      }

      try {
        const res = await apiFetch("/api/inventory/transfer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            from_branch_id: fromBranch,
            to_branch_id: toBranch,
            barcode: barcode,
            quantity: qty,
            reason: reason,
            user_id: state.activeUser.id
          })
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Stock transfer failed");
        }

        const data = await res.json();
        showToast(`Transferred ${qty} units successfully from ${fromBranch} to ${toBranch}!`, "success");
        document.getElementById("modal-stock-transfer").classList.add("hidden");
        loadBranchesData();
        loadInitialStoreData();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }
}

function populateTransferModalDropdowns() {
  const fromSel = document.getElementById("transfer-from-select");
  const toSel = document.getElementById("transfer-to-select");
  const prodSel = document.getElementById("transfer-product-select");

  if (fromSel && state.branches.length > 0) {
    fromSel.innerHTML = state.branches.map(b => `<option value="${escHtml(b.id)}" ${escHtml(b.id === state.activeBranch.id ? 'selected' : '')}>${escHtml(b.name)} (${escHtml(b.code)})</option>`).join("");
  }
  if (toSel && state.branches.length > 0) {
    toSel.innerHTML = state.branches.map((b, idx) => `<option value="${escHtml(b.id)}" ${escHtml(b.id !== state.activeBranch.id ? 'selected' : '')}>${escHtml(b.name)} (${escHtml(b.code)})</option>`).join("");
  }
  if (prodSel && state.allProducts.length > 0) {
    prodSel.innerHTML = state.allProducts.map(p => `<option value="${escHtml(p.barcode)}">${escHtml(p.name)} (Barcode: ${escHtml(p.barcode)} | Current Stock: ${escHtml(p.stock_quantity)})</option>`).join("");
  }
}

async function loadBranchesData() {
  try {
    const res = await apiFetch("/api/branches");
    const branches = await res.json();
    state.branches = branches;

    // Update active-branch-select options
    const bSelect = document.getElementById("active-branch-select");
    if (bSelect) {
      bSelect.innerHTML = branches.map(b => `
        <option value="${escHtml(b.id)}" ${escHtml(b.id === state.activeBranch.id ? 'selected' : '')}>
          ${escHtml(b.name)} (${escHtml(b.code)})
        </option>
      `).join("");
    }

    // Update KPIs
    document.getElementById("kpi-branch-count").textContent = branches.length;
    const totalChainSales = branches.reduce((sum, b) => sum + (b.total_sales || 0), 0);
    const totalChainOrders = branches.reduce((sum, b) => sum + (b.orders_count || 0), 0);
    document.getElementById("kpi-chain-revenue").textContent = `₹${totalChainSales.toFixed(2)}`;
    document.getElementById("kpi-chain-orders").textContent = `${totalChainOrders} Bills`;

    // Render Branch Cards
    const cardsContainer = document.getElementById("branch-cards-grid");
    if (cardsContainer) {
      cardsContainer.innerHTML = branches.map(b => `
        <div class="branch-card ${escHtml(b.id === state.activeBranch.id ? 'active-store' : '')}">
          <div class="branch-card-header">
            <div class="branch-card-icon">
              <i class="fa-solid fa-store"></i>
            </div>
            <span class="branch-badge ${escHtml(b.is_headquarters ? 'hq' : 'retail')}">
              ${escHtml(b.is_headquarters ? 'Flagship / HQ' : 'Retail Branch')}
            </span>
          </div>
          <div class="branch-card-body">
            <h3>${escHtml(b.name)}</h3>
            <p><i class="fa-solid fa-location-dot"></i> ${escHtml(b.address)}, ${escHtml(b.city)}, ${escHtml(b.state)} (${escHtml(b.pincode)})</p>
            <div class="branch-metrics-row">
              <div class="branch-metric-box">
                <span class="metric-label">Completed Sales</span>
                <span class="metric-val">₹${(b.total_sales || 0).toFixed(2)}</span>
              </div>
              <div class="branch-metric-box">
                <span class="metric-label">Orders Billed</span>
                <span class="metric-val">${escHtml(b.orders_count || 0)} Bills</span>
              </div>
            </div>
          </div>
          <div class="branch-card-footer">
            <div class="branch-manager-tag">
              <i class="fa-solid fa-user-shield"></i>
              <span>Mgr: ${escHtml(b.manager_name || 'Store Manager')}</span>
            </div>
            <button class="btn-sm btn-primary" onclick="switchToBranch('${escHtml(b.id)}')">
              ${escHtml(b.id === state.activeBranch.id ? '<i class="fa-solid fa-check"></i> Active Store' : 'Switch Store')}
            </button>
          </div>
        </div>
      `).join("");
    }

    // Render Table
    const tbody = document.getElementById("branch-summary-tbody");
    if (tbody) {
      tbody.innerHTML = branches.map(b => `
        <tr>
          <td><strong>${escHtml(b.code)}</strong></td>
          <td><strong>${escHtml(b.name)}</strong></td>
          <td><span class="branch-badge ${escHtml(b.is_headquarters ? 'hq' : 'retail')}">${escHtml(b.is_headquarters ? 'Flagship / HQ' : 'Retail Store')}</span></td>
          <td>${escHtml(b.city)}, ${escHtml(b.state)}</td>
          <td>${escHtml(b.manager_name || 'N/A')}</td>
          <td class="text-right"><strong>${escHtml(b.orders_count || 0)}</strong></td>
          <td class="text-right"><strong>₹${(b.total_sales || 0).toFixed(2)}</strong></td>
          <td><span class="status-pill completed">OPERATIONAL</span></td>
          <td>
            <button class="btn-sm btn-secondary" onclick="switchToBranch('${escHtml(b.id)}')">
              ${escHtml(b.id === state.activeBranch.id ? 'Selected' : 'Operate Here')}
            </button>
          </td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Failed to load store branches:", err);
  }
}

window.switchToBranch = function(branchId) {
  const b = state.branches.find(br => br.id === branchId);
  if (b) {
    state.activeBranch = b;
    const bSelect = document.getElementById("active-branch-select");
    if (bSelect) bSelect.value = branchId;
    document.getElementById("sidebar-branch-name").textContent = b.name;
    document.getElementById("sidebar-branch-code").textContent = `Branch ID: ${b.code}`;
    showToast(`Active Store Terminal switched to: ${b.name}`, "info");
    loadInitialStoreData();
    loadBranchesData();
    loadBusinessIntelligenceData();
  }
};

// ============================================================================
// TOAST NOTIFICATION UTILITY
// ============================================================================
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  const icon = type === "success" ? "fa-circle-check" : type === "error" ? "fa-circle-exclamation" : "fa-circle-info";
  toast.innerHTML = `<i class="fa-solid ${escHtml(icon)}"></i> <span>${escHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
