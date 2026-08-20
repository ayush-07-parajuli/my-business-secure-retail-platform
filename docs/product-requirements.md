# POS SaaS Requirements Addendum

This document upgrades the project from a single-shop POS concept into a multi-tenant SaaS-ready platform. It should be treated as mandatory scope for future implementation, even while the prototype continues to use SQLite.

## Scope Update

- The system must support multiple independent businesses on one shared platform.
- Each business is a tenant and may only access its own records.
- The platform must support three roles: `super_admin`, `business_owner`, and `staff`.
- The Super Admin operates at platform level, while business users operate only within their assigned tenant.
- SQLite is acceptable for the prototype, but the code structure must resemble a scalable SaaS design.

## 11. Multi-Tenant System + Super Admin Panel

### Requirement

The platform must no longer be modeled as a single standalone POS. It must support multiple businesses using the same application independently and securely.

### Tenant Rules

- Each business is a separate tenant.
- One business must never be able to read, edit, export, or infer another business's data.
- The Super Admin can monitor platform-wide activity and business-level summaries.
- Business Owners and Staff may only access data for their own business.

### Acceptance Criteria

- Every business-scoped module is tied to `business_id`.
- Tenant isolation is enforced in routes, service methods, queries, exports, dashboards, and logs.
- Platform-wide pages live in a dedicated Super Admin area with separate navigation and role checks.

## 12. User Roles

### Supported Roles

1. `super_admin`
2. `business_owner`
3. `staff`

### A. Super Admin Capabilities

- View all registered businesses using the system
- Create, approve, suspend, reactivate, or delete business accounts
- View all owners and staff linked to each business
- View overall platform statistics
- View total businesses, active businesses, and suspended businesses
- View total users, products, sales, revenue, and credit across the platform
- View total unpaid and overdue balances across businesses
- View system-wide audit logs
- Monitor suspicious activities and failed logins
- View recent logins
- Reset owner account passwords if needed
- Manage subscription or package status if enabled
- Configure global settings
- Manage supported languages
- Broadcast platform announcements
- View support or contact requests if enabled
- Access platform health dashboards and admin reporting

### B. Business Owner Capabilities

- Access only their own business dashboard
- Manage products, stock, sales, customers, credit, and repayments for their business
- View analytics and reports for their business
- Add or remove staff in their business
- View business-level audit logs where appropriate
- Update business profile and settings

### C. Staff Capabilities

- Record sales
- View products
- View stock operations
- Add customer during sale if permitted by policy
- Access only limited operational screens
- No access to owner-only analytics, business settings, or Super Admin pages

### Role Acceptance Criteria

- All pages, APIs, and mutations must be protected by role checks.
- Staff users must never receive business-owner or super-admin data in the UI or API payloads.
- Super Admins must use dedicated platform-level routes and layouts.

## 13. Multi-Tenant Database Design

### Core Requirement

Add a `businesses` table with at least the following fields:

- `business_id`
- `business_name`
- `owner_name`
- `phone`
- `email`
- `address`
- `business_type`
- `registration_date`
- `status`
- `subscription_plan` optional
- `logo` optional
- `preferred_language`
- `created_at`
- `updated_at`

### Tenant-Scoped Tables

All business-specific tables must include `business_id` and be queryable only within that tenant context:

- `users`
- `products`
- `categories`
- `stock_batches`
- `customers`
- `sales`
- `sale_items`
- `repayments`
- `audit_logs`
- `settings`

### Data Isolation Rules

- Every business-scoped query must filter by `business_id`.
- All create, update, delete, read, export, report, and analytics operations must respect tenant boundaries.
- Resource lookups must verify both the record ID and the active `business_id`.
- Owners must not be able to manipulate URLs or request parameters to access another tenant's data.

## 14. Super Admin Panel Pages

The project must include a dedicated Super Admin panel with a separate layout and navigation.

### Required Pages

- Super Admin login
- Super Admin dashboard
- Businesses list
- Add new business
- Business details page
- Edit business
- Suspend or reactivate business
- Platform users list
- Business owners list
- Staff overview
- Global sales analytics page
- Global revenue analytics page
- Global credit analytics page
- Global activity logs page
- Security monitoring page
- Global settings page
- Announcement or notification page
- Reports or export page

### Required Dashboard Cards

- Total Businesses
- Active Businesses
- Suspended Businesses
- Total Users
- Total Owners
- Total Staff
- Total Sales Across Platform
- Total Revenue Across Platform
- Total Gross Profit Across Platform
- Total Realized Profit Across Platform
- Total Unrealized Profit Across Platform
- Total Credit Outstanding Across Platform
- Total Low Stock Alerts Across Businesses
- Total Near Expiry Alerts Across Businesses
- Total Expired Stock Batches Across Businesses

### Required Dashboard Charts

- Business growth over time
- Platform sales trend
- Platform revenue trend
- Platform profit trend
- Outstanding credit trend
- Most active businesses
- Businesses with highest sales
- Businesses with highest outstanding dues

## 15. Real-World Admin Functions

The Super Admin must be able to:

- Onboard new business accounts
- Assign an owner account to a business
- View whether a business is active or suspended
- Disable access for unpaid or problematic accounts
- Inspect usage metrics for each business
- Identify businesses with high overdue credit risk
- Identify actively using businesses
- Review recent activity and admin logs
- Monitor failed logins or suspicious behavior
- Review important platform events
- Manage global configuration values
- Set default system preferences
- Manage platform notices and alerts

### Valuable Optional Business Fields

- `plan_type`
- `trial_start_date`
- `trial_end_date`
- `subscription_status`
- `last_login_time`
- `storage_usage`
- `support_note`
- `account_notes`

## 16. Security Requirements for Admin Panel

The admin panel must be strongly protected.

### Required Controls

- Separate admin authentication flow if useful for the implementation
- Strong role checking for super-admin routes
- Strict access control middleware or decorators
- Auditing for all admin actions
- Prevention of normal-user access to admin URLs
- Failed-login logging
- Secure session handling for admin sessions
- Tenant leakage protection
- Cross-tenant URL tampering protection

### Security Acceptance Criteria

- Normal tenant users are denied access to `/admin` routes and APIs.
- Super Admin actions are written to platform audit logs.
- Failed login attempts are stored with enough metadata for later investigation.
- Business users can only query records owned by their active `business_id`.

## 17. Admin-Side Business Analytics

The Super Admin must be able to open a business profile and view:

- Business name
- Owner
- Contact details
- Account status
- Total users
- Total products
- Total stock batches
- Total customers
- Total sales
- Total revenue
- Total gross profit
- Total realized profit
- Total unrealized profit
- Total outstanding credit
- Low stock count
- Near expiry count
- Expired stock count
- Recent activity
- Last login information
- Recent transactions summary

## 18. System Architecture Update

The architecture must clearly describe the system as a multi-tenant web platform with:

- Super Admin layer
- Tenant or business layer
- Staff or operational user layer
- Shared application backend
- Tenant-isolated SQLite data design for the prototype
- Secure role-based routing and authorization

### Architectural Expectation

Even with SQLite, the project should be organized like a SaaS platform so it can be upgraded later with minimal redesign.

## 19. UI and UX for Admin Panel

The Super Admin panel must feel modern and professional.

### Design Requirements

- Clean sidebar navigation
- Elegant dashboard cards
- Filterable and searchable tables
- Clear business status badges
- Warning colors for suspended or high-risk businesses
- Polished charts and analytics
- Quick actions for approve, suspend, reactivate, and view
- Responsive layout
- Professional color palette aligned with the rest of the platform

## 20. Updated Deliverables

The final generated solution must include:

- Super Admin authentication
- Multi-tenant database structure
- Super Admin dashboard
- Business account management
- Business-level monitoring
- Tenant isolation logic
- Business Owner panel
- Staff panel
- Secure role-based authorization across all modules

## Implementation Gate

No future implementation should be considered complete unless it satisfies the following:

- All business tables contain `business_id`
- Admin routes are separate from tenant routes
- Role checks exist at both route and service level
- Business-level analytics are available to owners only for their own tenant
- Platform-level analytics are available only to Super Admin
- Audit logs exist for admin and tenant actions
- Failed login attempts and security events are recorded
