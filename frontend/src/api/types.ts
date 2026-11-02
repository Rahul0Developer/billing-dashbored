// ---- API domain types (mirrors FastAPI Pydantic responses) ----

export type UserRole = "ADMIN" | "STORE_MANAGER" | "CASHIER" | "INVENTORY_MANAGER";
export type CustomerTier = "BRONZE" | "SILVER" | "GOLD" | "PLATINUM";
export type OrderStatus = "COMPLETED" | "VOIDED" | "RETURNED" | "PARTIALLY_RETURNED";
export type PaymentMethod = "CASH" | "UPI" | "CARD" | "WALLET" | "SPLIT";

export interface SessionUser {
  id: string;
  username: string;
  name: string;
  role: UserRole;
  branch_id: string;
}

export interface LoginResponse {
  success: boolean;
  token: string;
  user: SessionUser;
}

export interface StoreProfile {
  name: string;
  tagline: string;
  store_code: string;
  gstin: string;
  fssai: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  currency_symbol: string;
  currency_code: string;
}

export interface Product {
  barcode: string;
  sku: string;
  name: string;
  category: string;
  brand: string;
  unit: string;
  cost_price: number;
  selling_price: number;
  mrp: number;
  discount_on_mrp: number;
  stock_quantity: number;
  reorder_level: number;
  tax_rate_percent: number;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
}

export interface CartLine {
  barcode: string;
  name: string;
  quantity: number;
  unit: string;
  unit_price: number;
  unit_mrp: number;
  total: number;
  is_low_stock: boolean;
  available_stock: number;
}

export interface CartTotals {
  items: CartLine[];
  items_count: number;
  subtotal: number;
  total_mrp: number;
  total_savings: number;
  total_tax: number;
  cgst: number;
  sgst: number;
  tier_discount_percent: number;
  tier_discount_amount: number;
  volume_discount_amount: number;
  order_discount: number;
  points_redeemed: number;
  points_discount: number;
  grand_total: number;
  customer_tier: CustomerTier;
}

export interface CheckoutResult extends CartTotals {
  bill_number: string;
  payment_method: PaymentMethod;
  tendered_amount: number;
  change_amount: number;
  points_earned: number;
  status: OrderStatus;
  date?: string;
}

export interface Customer {
  phone: string;
  name: string;
  email?: string;
  tier: CustomerTier;
  loyalty_points: number;
  lifetime_value: number;
  visit_count: number;
  joined_date?: string;
}

export interface CustomerInsights {
  customer: Customer;
  favorite_categories?: { category: string; count: number }[];
  avg_basket_value?: number;
  purchase_frequency_days?: number;
  last_visit?: string;
  [key: string]: unknown;
}

export interface OrderSummary {
  bill_number: string;
  branch_id: string;
  branch_name: string;
  cashier: string;
  customer: string;
  items_count: number;
  grand_total: number;
  savings: number;
  payment_method: PaymentMethod;
  status: OrderStatus;
  date: string;
}

export interface ShiftInfo {
  shift_id: string;
  cashier_id: string;
  cashier_name: string;
  branch_id?: string;
  opening_float: number;
  current_cash_in_drawer: number;
  expected_cash: number;
  sales_count: number;
  refunds_count?: number;
  started_at: string;
  is_active: boolean;
  [key: string]: unknown;
}

export interface ZReport {
  shift_id: string;
  cashier_name: string;
  gross_sales: number;
  total_refunds: number;
  net_sales: number;
  cash_sales: number;
  upi_sales: number;
  card_sales: number;
  other_sales?: number;
  safe_drops: number;
  expected_cash: number;
  counted_cash: number;
  variance: number;
  closed_at?: string;
  [key: string]: unknown;
}

export interface Branch {
  branch_id: string;
  name: string;
  code?: string;
  city?: string;
  address?: string;
  gstin?: string;
  today_sales?: number;
  inventory_value?: number;
  low_stock_items?: number;
  staff_count?: number;
  status?: string;
  [key: string]: unknown;
}

export interface Expense {
  id: string;
  date: string;
  category: string;
  amount: number;
  description: string;
  branch_id?: string;
}

export interface AuditLogEntry {
  id: string;
  actor_id: string;
  actor_name?: string;
  action: string;
  entity: string;
  details: string;
  timestamp: string;
  [key: string]: unknown;
}

export interface DashboardData {
  today_revenue?: number;
  today_bills?: number;
  low_stock_count?: number;
  active_customers?: number;
  [key: string]: unknown;
}

export interface BIReport {
  revenue?: number;
  cogs?: number;
  gross_margin?: number;
  expenses?: number;
  net_profit?: number;
  restock_queue?: { barcode: string; name: string; stock: number; urgency: number }[];
  dead_stock?: { barcode: string; name: string; days_since_sale: number; value: number }[];
  [key: string]: unknown;
}

export interface Movement {
  id: string;
  barcode: string;
  product_name?: string;
  change: number;
  reason: string;
  branch_id: string;
  actor_id: string;
  timestamp: string;
  [key: string]: unknown;
}
