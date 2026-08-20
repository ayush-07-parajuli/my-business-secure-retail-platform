# My Business Demo Guide

This guide is for viva presentation, screenshots, and thesis demonstration.

## Before The Demo

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Prepare the database

Fresh setup:

```powershell
python -m flask --app run init-db --with-seed
```

If you already used the older project schema before this SaaS-role update:

```powershell
python -m flask --app run reset-db --with-seed
```

### 3. Verify the full demo flow

```powershell
python -m flask --app run demo-smoke
```

### 4. Start the app

```powershell
python run.py
```

Open `http://127.0.0.1:5000/`.

## Demo Credentials

- Super Admin: `admin@example.com / Admin123!`
- Ops Admin: `ops@example.com / Ops12345!`
- Biz Admin: `biz@example.com / Biz12345!`
- Owner: `owner@example.com / Owner123!`
- Staff: `staff@example.com / Staff123!`

## Suggested Presentation Flow

### 1. Start at the landing/login page

Explain that `My Business` is not just a single-shop POS. It is a multi-tenant SaaS platform where multiple businesses use the same backend securely.

Point out the separate login routes:

- `/login`
- `/admin/login`
- `/ops/login`
- `/biz/login`

### 2. Show owner registration

Open `/register` and explain that business registration creates:

- a tenant business record
- an owner account
- default subscription settings
- isolated tenant context

### 3. Login as Owner

Use:

- `owner@example.com`
- `Owner123!`

Show:

- owner dashboard
- sales and profit metrics
- low stock and expiry indicators
- subscription banner and subscription menu entry

### 4. Show core business modules

Demonstrate:

- categories
- products
- inventory batches
- customers
- sales
- credits
- repayments

Explain that these are all tenant-scoped by `business_id`.

### 5. Show subscription flow from owner side

Open `/owner/subscription`.

Explain:

- plan name: `Full Plan`
- monthly fee: `Rs. 500`
- current status
- renewal instructions
- manual payment submission flow

Open the submit-payment screen and explain:

- eSewa
- Khalti
- bank transfer
- cash

### 6. Show staff access

Login with:

- `staff@example.com`
- `Staff123!`

Show that staff can:

- create sales
- view products
- view customers

Show that staff cannot access owner-only or company-side areas.

### 7. Show Business Admin area

Login with:

- `biz@example.com`
- `Biz12345!`

Open:

- `/biz/dashboard`
- `/biz/subscriptions`
- `/biz/payments`
- `/biz/revenue`

Explain that the Business Admin handles:

- payment approval
- subscription status
- outstanding dues
- SaaS revenue

Important viva point:
This company revenue is separate from shopkeepers' product profit.

### 8. Show Operational Admin area

Login with:

- `ops@example.com`
- `Ops12345!`

Open:

- `/ops/dashboard`
- `/ops/businesses`
- `/ops/users`
- `/ops/activity-logs`
- `/ops/login-attempts`

Explain that the Operational Admin focuses on:

- business monitoring
- user oversight
- audit logs
- security events
- suspension/reactivation

### 9. Show Super Admin area

Login with:

- `admin@example.com`
- `Admin123!`

Show that Super Admin can access both operational and business-admin views, plus the top-level platform dashboard.

Highlight:

- total businesses
- total users
- total sales and product metrics
- subscription revenue and outstanding dues
- ops admin and biz admin visibility
- business/user management

### 10. Explain restriction logic

Discuss the subscription rules:

- active or trial: full access
- pending approval: warning shown, business can still log in
- expired: login allowed, but new sales, restocking, and reports are blocked
- suspended: stronger restrictions with renewal/reactivation guidance

### 11. Explain security

Highlight:

- role-based access control
- separate company-side admin roles
- tenant isolation
- failed login tracking
- audit logs
- password change support

## Suggested Screenshot List

1. Tenant login page
2. Super Admin login page
3. Ops Admin login page
4. Biz Admin login page
5. Owner dashboard
6. Owner subscription page
7. POS sales page
8. Customer ledger
9. Biz Admin dashboard
10. Subscription payments list
11. Ops Admin dashboard
12. Super Admin dashboard

## Quick Reset Before Presentation

```powershell
python -m flask --app run reset-db --with-seed
python run.py
```

## Quick Health Check

```powershell
python -m flask --app run demo-smoke
```
