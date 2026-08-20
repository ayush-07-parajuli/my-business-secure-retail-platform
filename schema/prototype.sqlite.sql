PRAGMA foreign_keys = ON;

-- Multi-tenant prototype schema for a SaaS-style POS platform.
-- SQLite is used for the prototype, but table boundaries and keys are
-- organized to resemble a scalable production design.

CREATE TABLE businesses (
  business_id TEXT PRIMARY KEY,
  business_name TEXT NOT NULL,
  owner_name TEXT NOT NULL,
  phone TEXT,
  email TEXT,
  address TEXT,
  business_type TEXT,
  registration_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'suspended', 'inactive', 'pending')),
  subscription_plan TEXT,
  logo TEXT,
  preferred_language TEXT DEFAULT 'en',
  trial_start_date TEXT,
  trial_end_date TEXT,
  subscription_status TEXT CHECK (subscription_status IN ('trial', 'active', 'past_due', 'cancelled', 'inactive')),
  last_login_at TEXT,
  storage_usage_bytes INTEGER DEFAULT 0,
  support_note TEXT,
  account_notes TEXT,
  suspended_at TEXT,
  suspended_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  business_id TEXT,
  full_name TEXT NOT NULL,
  phone TEXT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin', 'business_owner', 'staff')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'inactive')),
  is_primary_owner INTEGER NOT NULL DEFAULT 0 CHECK (is_primary_owner IN (0, 1)),
  preferred_language TEXT DEFAULT 'en',
  failed_login_count INTEGER NOT NULL DEFAULT 0,
  last_login_at TEXT,
  last_password_reset_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, user_id),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  CHECK (
    (role = 'super_admin' AND business_id IS NULL) OR
    (role IN ('business_owner', 'staff') AND business_id IS NOT NULL)
  )
);

CREATE TABLE categories (
  category_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, category_id),
  UNIQUE (business_id, name),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE
);

CREATE TABLE products (
  product_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  category_id TEXT,
  sku TEXT NOT NULL,
  barcode TEXT,
  name TEXT NOT NULL,
  description TEXT,
  unit TEXT NOT NULL DEFAULT 'unit',
  cost_price NUMERIC NOT NULL DEFAULT 0 CHECK (cost_price >= 0),
  selling_price NUMERIC NOT NULL DEFAULT 0 CHECK (selling_price >= 0),
  low_stock_threshold NUMERIC NOT NULL DEFAULT 0 CHECK (low_stock_threshold >= 0),
  reorder_level NUMERIC NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_by_user_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, product_id),
  UNIQUE (business_id, sku),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, category_id) REFERENCES categories (business_id, category_id) ON DELETE SET NULL,
  FOREIGN KEY (business_id, created_by_user_id) REFERENCES users (business_id, user_id) ON DELETE SET NULL
);

CREATE TABLE stock_batches (
  batch_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  batch_code TEXT NOT NULL,
  quantity_received NUMERIC NOT NULL CHECK (quantity_received >= 0),
  quantity_remaining NUMERIC NOT NULL CHECK (quantity_remaining >= 0),
  unit_cost NUMERIC NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
  expiry_date TEXT,
  supplier_name TEXT,
  received_by_user_id TEXT,
  received_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'depleted', 'expired')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, batch_id),
  UNIQUE (business_id, batch_code),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, product_id) REFERENCES products (business_id, product_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, received_by_user_id) REFERENCES users (business_id, user_id) ON DELETE SET NULL
);

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  full_name TEXT NOT NULL,
  phone TEXT,
  email TEXT,
  address TEXT,
  credit_limit NUMERIC NOT NULL DEFAULT 0 CHECK (credit_limit >= 0),
  outstanding_balance NUMERIC NOT NULL DEFAULT 0 CHECK (outstanding_balance >= 0),
  risk_level TEXT NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low', 'medium', 'high')),
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, customer_id),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE
);

CREATE TABLE sales (
  sale_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  customer_id TEXT,
  sold_by_user_id TEXT NOT NULL,
  sale_number TEXT NOT NULL,
  sale_date TEXT NOT NULL,
  subtotal_amount NUMERIC NOT NULL DEFAULT 0 CHECK (subtotal_amount >= 0),
  discount_amount NUMERIC NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
  tax_amount NUMERIC NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
  total_amount NUMERIC NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
  amount_paid NUMERIC NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
  balance_due NUMERIC NOT NULL DEFAULT 0 CHECK (balance_due >= 0),
  payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'partial', 'unpaid', 'overdue')),
  gross_profit_amount NUMERIC NOT NULL DEFAULT 0,
  realized_profit_amount NUMERIC NOT NULL DEFAULT 0,
  unrealized_profit_amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, sale_id),
  UNIQUE (business_id, sale_number),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, customer_id) REFERENCES customers (business_id, customer_id) ON DELETE SET NULL,
  FOREIGN KEY (business_id, sold_by_user_id) REFERENCES users (business_id, user_id) ON DELETE RESTRICT
);

CREATE TABLE sale_items (
  sale_item_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  sale_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  stock_batch_id TEXT,
  quantity NUMERIC NOT NULL CHECK (quantity > 0),
  unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
  unit_cost NUMERIC NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
  discount_amount NUMERIC NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
  total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),
  profit_amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (business_id, sale_item_id),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, sale_id) REFERENCES sales (business_id, sale_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, product_id) REFERENCES products (business_id, product_id) ON DELETE RESTRICT,
  FOREIGN KEY (business_id, stock_batch_id) REFERENCES stock_batches (business_id, batch_id) ON DELETE SET NULL
);

CREATE TABLE repayments (
  repayment_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  sale_id TEXT,
  received_by_user_id TEXT NOT NULL,
  amount NUMERIC NOT NULL CHECK (amount > 0),
  payment_method TEXT,
  reference_number TEXT,
  paid_at TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (business_id, repayment_id),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (business_id, customer_id) REFERENCES customers (business_id, customer_id) ON DELETE RESTRICT,
  FOREIGN KEY (business_id, sale_id) REFERENCES sales (business_id, sale_id) ON DELETE SET NULL,
  FOREIGN KEY (business_id, received_by_user_id) REFERENCES users (business_id, user_id) ON DELETE RESTRICT
);

CREATE TABLE audit_logs (
  audit_log_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  actor_user_id TEXT,
  action_type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
  metadata_json TEXT,
  ip_address TEXT,
  user_agent TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (business_id, audit_log_id),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (actor_user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE settings (
  setting_id TEXT PRIMARY KEY,
  business_id TEXT NOT NULL,
  setting_key TEXT NOT NULL,
  setting_value TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (business_id, setting_id),
  UNIQUE (business_id, setting_key),
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE CASCADE
);

CREATE TABLE platform_audit_logs (
  platform_audit_log_id TEXT PRIMARY KEY,
  actor_user_id TEXT,
  action_type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  target_business_id TEXT,
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
  metadata_json TEXT,
  ip_address TEXT,
  user_agent TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (actor_user_id) REFERENCES users (user_id) ON DELETE SET NULL,
  FOREIGN KEY (target_business_id) REFERENCES businesses (business_id) ON DELETE SET NULL
);

CREATE TABLE login_attempts (
  attempt_id TEXT PRIMARY KEY,
  target_scope TEXT NOT NULL CHECK (target_scope IN ('admin', 'tenant')),
  target_business_id TEXT,
  attempted_identifier TEXT NOT NULL,
  user_id TEXT,
  role_attempted TEXT CHECK (role_attempted IN ('super_admin', 'business_owner', 'staff')),
  success INTEGER NOT NULL CHECK (success IN (0, 1)),
  failure_reason TEXT,
  ip_address TEXT,
  user_agent TEXT,
  attempted_at TEXT NOT NULL,
  FOREIGN KEY (target_business_id) REFERENCES businesses (business_id) ON DELETE SET NULL,
  FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE security_events (
  event_id TEXT PRIMARY KEY,
  business_id TEXT,
  user_id TEXT,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  event_type TEXT NOT NULL,
  description TEXT NOT NULL,
  ip_address TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE SET NULL,
  FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE platform_notifications (
  notification_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  audience_type TEXT NOT NULL CHECK (audience_type IN ('all_businesses', 'active_businesses', 'suspended_businesses', 'specific_business')),
  target_business_id TEXT,
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
  starts_at TEXT,
  ends_at TEXT,
  created_by_user_id TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (target_business_id) REFERENCES businesses (business_id) ON DELETE CASCADE,
  FOREIGN KEY (created_by_user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE global_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT,
  updated_by_user_id TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (updated_by_user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE TABLE support_requests (
  request_id TEXT PRIMARY KEY,
  business_id TEXT,
  requester_name TEXT NOT NULL,
  requester_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'closed')),
  handled_by_user_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (business_id) REFERENCES businesses (business_id) ON DELETE SET NULL,
  FOREIGN KEY (handled_by_user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE INDEX idx_users_business_role ON users (business_id, role);
CREATE INDEX idx_businesses_status ON businesses (status);
CREATE INDEX idx_products_business ON products (business_id);
CREATE INDEX idx_stock_batches_business ON stock_batches (business_id);
CREATE INDEX idx_customers_business ON customers (business_id);
CREATE INDEX idx_sales_business_date ON sales (business_id, sale_date);
CREATE INDEX idx_sales_business_payment_status ON sales (business_id, payment_status);
CREATE INDEX idx_sale_items_business ON sale_items (business_id);
CREATE INDEX idx_repayments_business_paid_at ON repayments (business_id, paid_at);
CREATE INDEX idx_audit_logs_business_created_at ON audit_logs (business_id, created_at);
CREATE INDEX idx_login_attempts_scope_time ON login_attempts (target_scope, attempted_at);
CREATE INDEX idx_security_events_business_time ON security_events (business_id, created_at);

CREATE VIEW inventory_snapshot_view AS
SELECT
  business_id,
  product_id,
  SUM(quantity_remaining) AS current_quantity,
  MIN(expiry_date) AS nearest_expiry_date
FROM stock_batches
GROUP BY business_id, product_id;

CREATE VIEW business_summary_view AS
SELECT
  b.business_id,
  b.business_name,
  b.owner_name,
  b.email,
  b.phone,
  b.status,
  b.subscription_plan,
  b.subscription_status,
  (
    SELECT COUNT(*)
    FROM users u
    WHERE u.business_id = b.business_id
      AND u.role <> 'super_admin'
  ) AS total_users,
  (
    SELECT COUNT(*)
    FROM users u
    WHERE u.business_id = b.business_id
      AND u.role = 'business_owner'
  ) AS total_owners,
  (
    SELECT COUNT(*)
    FROM users u
    WHERE u.business_id = b.business_id
      AND u.role = 'staff'
  ) AS total_staff,
  (
    SELECT COUNT(*)
    FROM products p
    WHERE p.business_id = b.business_id
  ) AS total_products,
  (
    SELECT COUNT(*)
    FROM stock_batches sb
    WHERE sb.business_id = b.business_id
  ) AS total_stock_batches,
  (
    SELECT COUNT(*)
    FROM customers c
    WHERE c.business_id = b.business_id
  ) AS total_customers,
  (
    SELECT COUNT(*)
    FROM sales s
    WHERE s.business_id = b.business_id
  ) AS total_sales,
  COALESCE((
    SELECT SUM(s.total_amount)
    FROM sales s
    WHERE s.business_id = b.business_id
  ), 0) AS total_revenue,
  COALESCE((
    SELECT SUM(s.gross_profit_amount)
    FROM sales s
    WHERE s.business_id = b.business_id
  ), 0) AS total_gross_profit,
  COALESCE((
    SELECT SUM(s.realized_profit_amount)
    FROM sales s
    WHERE s.business_id = b.business_id
  ), 0) AS total_realized_profit,
  COALESCE((
    SELECT SUM(s.unrealized_profit_amount)
    FROM sales s
    WHERE s.business_id = b.business_id
  ), 0) AS total_unrealized_profit,
  COALESCE((
    SELECT SUM(c.outstanding_balance)
    FROM customers c
    WHERE c.business_id = b.business_id
  ), 0) AS total_outstanding_credit,
  COALESCE((
    SELECT SUM(s.balance_due)
    FROM sales s
    WHERE s.business_id = b.business_id
      AND s.payment_status = 'overdue'
  ), 0) AS total_overdue_balance,
  (
    SELECT COUNT(*)
    FROM products p
    LEFT JOIN inventory_snapshot_view inv
      ON inv.business_id = p.business_id
     AND inv.product_id = p.product_id
    WHERE p.business_id = b.business_id
      AND COALESCE(inv.current_quantity, 0) <= p.low_stock_threshold
  ) AS low_stock_count,
  (
    SELECT COUNT(*)
    FROM stock_batches sb
    WHERE sb.business_id = b.business_id
      AND sb.expiry_date IS NOT NULL
      AND date(sb.expiry_date) BETWEEN date('now') AND date('now', '+30 day')
      AND sb.quantity_remaining > 0
  ) AS near_expiry_count,
  (
    SELECT COUNT(*)
    FROM stock_batches sb
    WHERE sb.business_id = b.business_id
      AND sb.expiry_date IS NOT NULL
      AND date(sb.expiry_date) < date('now')
      AND sb.quantity_remaining > 0
  ) AS expired_stock_count,
  (
    SELECT MAX(u.last_login_at)
    FROM users u
    WHERE u.business_id = b.business_id
  ) AS last_login_at
FROM businesses b;

CREATE VIEW platform_summary_view AS
SELECT
  COUNT(*) AS total_businesses,
  SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_businesses,
  SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END) AS suspended_businesses,
  COALESCE(SUM(total_users), 0) AS total_users,
  COALESCE(SUM(total_owners), 0) AS total_owners,
  COALESCE(SUM(total_staff), 0) AS total_staff,
  COALESCE(SUM(total_sales), 0) AS total_sales,
  COALESCE(SUM(total_revenue), 0) AS total_revenue,
  COALESCE(SUM(total_gross_profit), 0) AS total_gross_profit,
  COALESCE(SUM(total_realized_profit), 0) AS total_realized_profit,
  COALESCE(SUM(total_unrealized_profit), 0) AS total_unrealized_profit,
  COALESCE(SUM(total_outstanding_credit), 0) AS total_outstanding_credit,
  COALESCE(SUM(total_overdue_balance), 0) AS total_overdue_balance,
  COALESCE(SUM(low_stock_count), 0) AS total_low_stock_alerts,
  COALESCE(SUM(near_expiry_count), 0) AS total_near_expiry_alerts,
  COALESCE(SUM(expired_stock_count), 0) AS total_expired_stock_batches
FROM business_summary_view;

CREATE VIEW business_credit_risk_view AS
SELECT
  business_id,
  business_name,
  total_outstanding_credit,
  total_overdue_balance,
  CASE
    WHEN total_overdue_balance >= 100000 THEN 'high'
    WHEN total_overdue_balance >= 25000 THEN 'medium'
    ELSE 'low'
  END AS overdue_risk_level
FROM business_summary_view;
