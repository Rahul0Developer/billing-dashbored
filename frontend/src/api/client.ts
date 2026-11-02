// ---- Typed API client with bearer-token auth + offline queue ----
import type {
  LoginResponse, StoreProfile, Product, CartTotals, CheckoutResult, Customer,
  CustomerInsights, OrderSummary, ShiftInfo, ZReport, Branch, Expense,
  AuditLogEntry, DashboardData, BIReport, Movement, PaymentMethod, UserRole,
} from "./types";

const TOKEN_KEY = "apex_token";

export const auth = {
  get token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  set token(v: string | null) {
    if (v) localStorage.setItem(TOKEN_KEY, v);
    else localStorage.removeItem(TOKEN_KEY);
  },
};

// Fired when a 401 arrives -> App listens and shows login screen.
type UnauthorizedListener = () => void;
const unauthorizedListeners: UnauthorizedListener[] = [];
export function onUnauthorized(fn: UnauthorizedListener): () => void {
  unauthorizedListeners.push(fn);
  return () => {
    const i = unauthorizedListeners.indexOf(fn);
    if (i >= 0) unauthorizedListeners.splice(i, 1);
  };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (auth.token) headers["Authorization"] = `Bearer ${auth.token}`;

  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch (e) {
    throw new ApiError(0, "NETWORK_ERROR");
  }

  if (res.status === 401) {
    auth.token = null;
    unauthorizedListeners.forEach((fn) => fn());
    throw new ApiError(401, "Session expired. Please sign in again.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- Auth ----------
export const login = (username: string, pin: string) =>
  request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, pin }),
  });

export const logout = () =>
  request<{ success: boolean }>("/api/auth/logout", { method: "POST" }).catch(() => undefined);

export const verifyManagerPin = (pin: string, allowedRoles?: UserRole[]) =>
  request<{ valid: boolean; name?: string; role?: UserRole; user_id?: string }>(
    "/api/auth/verify-pin",
    { method: "POST", body: JSON.stringify({ pin, allowed_roles: allowedRoles }) },
  );

// ---------- Store / catalog ----------
export const getStoreProfile = () => request<StoreProfile>("/api/store-profile");
export const searchProducts = (q: string) =>
  request<Product[]>(`/api/products/search?q=${encodeURIComponent(q)}`);
export const listProducts = () => request<Product[]>("/api/products");

// ---------- POS ----------
export interface CartItemInput { barcode: string; quantity: number }

export interface PosPayload {
  items: CartItemInput[];
  customer_phone?: string | null;
  points_to_redeem?: number;
  branch_id: string;
}

export const calculateCart = (payload: PosPayload) =>
  request<CartTotals>("/api/pos/calculate", { method: "POST", body: JSON.stringify(payload) });

export interface CheckoutPayload extends PosPayload {
  payment_method: PaymentMethod;
  tendered_amount: number;
  cashier_id: string;
  cashier_name: string;
  customer_name?: string | null;
  split_payments?: { method: string; amount: number }[] | null;
}

/**
 * Offline-first checkout: if the network is down (ApiError status 0),
 * queue the sale in localStorage and resolve with a synthetic QUEUED result.
 * The queue drains automatically once connectivity returns.
 */
const QUEUE_KEY = "apex_offline_queue";
export type QueuedSale = { payload: CheckoutPayload; queued_at: string };

export function getQueuedSales(): QueuedSale[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]") as QueuedSale[];
  } catch {
    return [];
  }
}
function saveQueue(q: QueuedSale[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
}

async function postCheckout(payload: CheckoutPayload): Promise<CheckoutResult> {
  return request<CheckoutResult>("/api/pos/checkout", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function checkout(payload: CheckoutPayload): Promise<CheckoutResult & { queued?: boolean }> {
  try {
    const result = await postCheckout(payload);
    void drainOfflineQueue(); // opportunistic sync after successful sale
    return result;
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) {
      const q = getQueuedSales();
      q.push({ payload, queued_at: new Date().toISOString() });
      saveQueue(q);
      return {
        ...(({} as CheckoutResult)),
        bill_number: `QUEUED-${q.length}`,
        grand_total: 0,
        change_amount: 0,
        queued: true,
      } as CheckoutResult & { queued: boolean };
    }
    throw e;
  }
}

export async function drainOfflineQueue(): Promise<number> {
  const q = getQueuedSales();
  if (q.length === 0) return 0;
  const remaining: QueuedSale[] = [];
  let synced = 0;
  for (const item of q) {
    try {
      await postCheckout(item.payload);
      synced += 1;
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) remaining.push(item); // still offline — keep
      // Non-network errors (validation etc.) are dropped to avoid poison-pill loops.
    }
  }
  saveQueue(remaining);
  return synced;
}

// ---------- Orders / returns ----------
export const listOrders = (branchId?: string) =>
  request<OrderSummary[]>(`/api/orders${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ""}`);
export const getOrder = (billNumber: string) => request<Record<string, unknown>>(`/api/orders/${encodeURIComponent(billNumber)}`);
export const getThermalReceipt = (billNumber: string) =>
  request<{ html?: string; receipt?: string; text?: string }>(`/api/orders/${encodeURIComponent(billNumber)}/thermal`);
export const getA4Invoice = (billNumber: string) =>
  request<{ html: string }>(`/api/orders/${encodeURIComponent(billNumber)}/a4`);
export const voidOrder = (billNumber: string, reason: string, managerPin: string) =>
  request<{ success: boolean }>(`/api/orders/${encodeURIComponent(billNumber)}/void`, {
    method: "POST",
    body: JSON.stringify({ reason, manager_pin: managerPin }),
  });
export const processReturn = (body: Record<string, unknown>) =>
  request<{ success: boolean; refund_amount: number; credit_note?: string }>("/api/returns/process", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const listReturns = () => request<Record<string, unknown>[]>("/api/returns");

// ---------- Customers ----------
export const recognizeCustomer = (code: string) =>
  request<Customer | null>(`/api/customers/recognize?code=${encodeURIComponent(code)}`);
export const lookupCustomer = (phone: string) =>
  request<Customer | null>(`/api/customers/lookup?phone=${encodeURIComponent(phone)}`);
export const listCustomers = () => request<Customer[]>("/api/customers");
export const topCustomers = () => request<Customer[]>("/api/customers/top");
export const customerInsights = (identifier: string) =>
  request<CustomerInsights>(`/api/customers/${encodeURIComponent(identifier)}/insights`);
export const customerHistory = (phone: string) =>
  request<OrderSummary[]>(`/api/customers/${encodeURIComponent(phone)}/history`);

// ---------- Shifts ----------
export const currentShift = (cashierId: string) =>
  request<ShiftInfo | { active: false }>(`/api/shifts/current?cashier_id=${encodeURIComponent(cashierId)}`);
export const startShift = (openingFloat: number, branchId: string) =>
  request<ShiftInfo>("/api/shifts/start", {
    method: "POST",
    body: JSON.stringify({ opening_float: openingFloat, branch_id: branchId }),
  });
export const cashDrop = (amount: number) =>
  request<{ success: boolean }>("/api/shifts/drop", { method: "POST", body: JSON.stringify({ amount }) });
export const closeShift = (countedCash: number, varianceReason: string) =>
  request<ZReport>("/api/shifts/close", {
    method: "POST",
    body: JSON.stringify({ counted_cash: countedCash, variance_reason: varianceReason }),
  });
export const shiftHistory = () => request<Record<string, unknown>[]>("/api/shifts/history");

// ---------- Inventory ----------
export const adjustStock = (barcode: string, quantityChange: number, reason: string, branchId: string) =>
  request<{ success: boolean }>("/api/inventory/adjust", {
    method: "POST",
    body: JSON.stringify({ barcode, quantity_change: quantityChange, reason, branch_id: branchId }),
  });
export const inventoryValuation = (branchId?: string) =>
  request<Record<string, unknown>>(`/api/inventory/valuation${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ""}`);
export const listMovements = (limit = 50) => request<Movement[]>(`/api/inventory/movements?limit=${limit}`);
export const transferStock = (fromBranch: string, toBranch: string, barcode: string, quantity: number) =>
  request<{ success: boolean }>("/api/inventory/transfer", {
    method: "POST",
    body: JSON.stringify({ from_branch_id: fromBranch, to_branch_id: toBranch, barcode, quantity }),
  });

// ---------- Expenses ----------
export const listExpenses = () => request<Expense[]>("/api/expenses");
export const expenseSummary = () => request<Record<string, number>>("/api/expenses/summary");
export const addExpense = (category: string, amount: number, description: string) =>
  request<{ success: boolean; id: string }>("/api/expenses", {
    method: "POST",
    body: JSON.stringify({ category, amount, description }),
  });
export const deleteExpense = (id: string) =>
  request<{ success: boolean }>(`/api/expenses/${encodeURIComponent(id)}`, { method: "DELETE" });

// ---------- Analytics / dashboard ----------
export const getDashboard = (branchId?: string) =>
  request<DashboardData>(`/api/dashboard${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ""}`);
export const getBI = (branchId?: string) =>
  request<BIReport>(`/api/analytics/business-intelligence${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ""}`);

// ---------- Branches ----------
export const listBranches = () => request<Branch[]>("/api/branches");
export const createBranch = (body: Record<string, unknown>) =>
  request<Branch>("/api/branches", { method: "POST", body: JSON.stringify(body) });
export const branchInventory = (branchId: string) =>
  request<Record<string, unknown>[]>(`/api/branches/${encodeURIComponent(branchId)}/inventory`);

// ---------- Users / audit ----------
export const listUsers = () =>
  request<{ id: string; name: string; username: string; role: UserRole; branch_id: string; is_active: boolean }[]>("/api/auth/users");
export const createUser = (body: Record<string, unknown>) =>
  request<{ success: boolean }>("/api/auth/users", { method: "POST", body: JSON.stringify(body) });
export const setUserStatus = (userId: string, isActive: boolean) =>
  request<{ success: boolean }>(`/api/auth/users/${encodeURIComponent(userId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
export const listAuditLogs = (limit = 100) => request<AuditLogEntry[]>(`/api/audit/logs?limit=${limit}`);

// ---------- Report exports (download helpers) ----------
export function downloadUrl(path: string, filename: string) {
  // Uses cookie session (login also sets an httponly cookie) so browsers can download directly.
  const a = document.createElement("a");
  a.href = path;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
