# My Business

`My Business` is a thesis-ready multi-tenant POS and inventory SaaS platform built with Flask, SQLite, SQLAlchemy, Flask-Login, Flask-WTF, Bootstrap, and Chart.js.

The system now models a more realistic commercial SaaS structure with separate company-side admin roles, manual subscription approval, tenant isolation, and role-specific login areas.

## Role Structure

- `super_admin`
  Full access to platform operations and company subscription controls
- `ops_admin`
  Operational monitoring, business control, users, audit logs, login attempts
- `biz_admin`
  Subscription approvals, payments, revenue, unpaid businesses, company-side reports
- `owner`
  Manages only their own business
- `staff`
  Limited operational access inside their own business

## Login Routes

- Tenant owner/staff: `http://127.0.0.1:5000/login`
- Super Admin: `http://127.0.0.1:5000/admin/login`
- Ops Admin: `http://127.0.0.1:5000/ops/login`
- Biz Admin: `http://127.0.0.1:5000/biz/login`

## SaaS Subscription Model

- Plan name: `Full Plan`
- Monthly fee: `Rs. 500`
- All features included
- Manual renewal flow:
  owner submits payment proof, `biz_admin` approves or rejects, subscription becomes active

Subscription states:

- `active`
- `trial`
- `pending_approval`
- `expired`
- `suspended`

Restriction behavior:

- `active` or `trial`: full business access
- `pending_approval`: login allowed, warning shown, business remains usable
- `expired`: login allowed, but new sales, restocking, and report routes are restricted
- `suspended`: login allowed, but restricted business actions remain blocked until reactivated

## Feature Highlights

- Multi-tenant tenant-isolated business data with `business_id`
- Super Admin dashboard with platform-wide operational and revenue visibility
- Dedicated Operational Admin area
- Dedicated Business Admin area
- Owner dashboard, POS, inventory, credit sales, repayments, reports, and subscription page
- Staff operational workspace
- Batch-based stock tracking with FIFO deduction
- Realized vs unrealized profit logic
- Manual subscription payment submission and approval flow
- CSV exports and print-friendly reports
- English and Nepali UI support
- Audit logs, login attempt tracking, and brute-force mitigation
- Change-password flow for every authenticated role

## Quick Setup

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Fresh database setup

For a brand-new database:

```powershell
python -m flask --app run init-db --with-seed
```

### 3. If you already have the older SQLite demo database

This update adds new roles and subscription tables. Older SQLite files need a one-time reset:

```powershell
python -m flask --app run reset-db --with-seed
```

### 4. Run the app

```powershell
python run.py
```

Open `http://127.0.0.1:5000/`.

## Seeded Demo Accounts

After `init-db --with-seed`, `reset-db --with-seed`, or `seed-demo`:

- `super_admin`: `admin@example.com / Admin123!`
- `ops_admin`: `ops@example.com / Ops12345!`
- `biz_admin`: `biz@example.com / Biz12345!`
- `owner`: `owner@example.com / Owner123!`
- `staff`: `staff@example.com / Staff123!`

The demo dataset also creates:

- 1 business with subscription info
- categories, products, stock batches, customers
- cash, credit, and partial sales
- repayments
- approved subscription payment history

## Useful Commands

Initialize schema only:

```powershell
python -m flask --app run init-db
```

Initialize and seed:

```powershell
python -m flask --app run init-db --with-seed
```

Reset and reseed:

```powershell
python -m flask --app run reset-db --with-seed
```

Baseline accounts only:

```powershell
python -m flask --app run seed-dev
```

Refresh full demo data:

```powershell
python -m flask --app run seed-demo
```

Run the end-to-end smoke flow:

```powershell
python -m flask --app run demo-smoke
```

## Verified Smoke Flow

The built-in smoke test now covers:

1. New business registration
2. Owner login
3. Product creation
4. Inventory restock
5. Customer creation
6. Cash sale
7. Credit sale
8. Repayment
9. Owner dashboard and reports
10. Owner subscription page and payment submission
11. Super Admin login
12. Biz Admin login and payment approval
13. Ops Admin login and dashboard visibility

## Project Structure

```text
app/
  models/
  routes/
  services/
  utils/
  templates/
  static/
docs/
schema/
config.py
run.py
requirements.txt
```

## Demo Guide

Use [docs/demo-guide.md](C:\Users\Administrator\Documents\New project\docs\demo-guide.md) for the full viva/demo walkthrough.
