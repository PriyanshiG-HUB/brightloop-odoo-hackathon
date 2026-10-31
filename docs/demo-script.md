# Brightloop Hackathon Demonstration Script (16-Step Walkthrough)

This script provides an end-to-end demonstration path for the hackathon judges, verifying all requirements across Modules A through M.

---

## Part 1: Product, Plan, and Customer Setup (Modules A, B, C)

### Step 1: User Registration & Password Security
1. Navigate to **Settings > Users & Companies > Users**.
2. Click **New** and enter:
   - **Name:** Sales Representative
   - **Login:** `sales@brightloop.com`
   - **Password:** `simple` (Test weak password)
3. **Verify:** Odoo raises a `ValidationError` requiring 8+ characters, uppercase, lowercase, and special character.
4. Set password to `BrightLoop@2026!` and save successfully.

### Step 2: Customer Creation & Email Uniqueness
1. Navigate to **Brightloop > Customers**.
2. Click **New** and create:
   - **Name:** Acme Cloud Solutions
   - **Email:** `contact@acmecloud.com`
   - **Customer Rank:** Customer
3. Try creating a second customer with the exact same email `contact@acmecloud.com`.
4. **Verify:** Odoo raises a `ValidationError` preventing duplicate customer emails.

### Step 3: Service Products & Variant Extra Pricing
1. Navigate to **Brightloop > Products**.
2. Create product **Cloud Storage Service**:
   - **Product Type:** Service
   - **Sales Price:** \$50.00
   - **Brand:** Brightloop Cloud
   - **Variants:** Add attribute `Storage Tier` with values `100 GB`, `500 GB` (set extra price +\$560.00).
3. **Verify:** Selecting the `500 GB` variant dynamically computes unit price as \$610.00 (\$50 + \$560).

### Step 4: Recurring Subscription Plan Setup
1. Navigate to **Brightloop > Plans**.
2. Create **Enterprise SaaS Plan**:
   - **Plan Name:** Enterprise Monthly
   - **Recurring Price:** \$100.00
   - **Billing Frequency:** Monthly
   - **Minimum Quantity:** 1
   - **Policies:** Check `Allow Pause`, `Allow Early Close`, `Allow Renewal`, `Allow Cancel`.
3. **Verify:** Plan status computes as `Available`.

---

## Part 2: Quotations & Lifecycle Management (Modules D, E, F)

### Step 5: Reusable Quotation Template
1. Navigate to **Brightloop > Quotation Templates**.
2. Create **Standard SaaS Starter**:
   - **Plan:** Enterprise Monthly
   - **Validity Days:** 30
   - **Lines:** Add Cloud Storage Service (Quantity: 2, Unit Price: \$100.00).

### Step 6: Create Quotation from Template
1. Navigate to **Brightloop > Quotations**.
2. Click **New**, select Customer `Acme Cloud Solutions` and Template `Standard SaaS Starter`.
3. **Verify:** Lines and plan details auto-populate, sequence generates `BL/QUO/YYYY/NNNNN`.
4. Click **Send** (`state -> sent`).

### Step 7: Accept Quotation & Convert to Subscription
1. Click **Accept** (`state -> accepted`).
2. Click **Convert to Subscription**.
3. **Verify:**
   - Active modal redirects to newly created Subscription `BL/SUB/YYYY/NNNNN`.
   - Lines, quantities, pricing, and taxes match exactly.
   - Status starts in `Confirmed`.

### Step 8: Promotional Discount Application
1. Navigate to **Brightloop > Discounts** (Administrator view).
2. Create discount **WELCOME20**:
   - **Discount Type:** Percentage (20%)
   - **Eligibility:** Minimum subtotal \$100.
3. Open the subscription, add discount `WELCOME20`, and save.
4. **Verify:** `amount_untaxed` reduces by 20%, and `amount_tax` reflects the discounted base.

---

## Part 3: Automated Recurring Billing & Idempotency (Modules G, H, I, M)

### Step 9: Activate Subscription
1. On the subscription form, click **Activate**.
2. **Verify:**
   - Status changes to `Active`.
   - `next_invoice_date` is initialized to today.

### Step 10: Generate First Recurring Invoice
1. Trigger the scheduled action manually or click **Generate Invoices** from cron:
   - **Settings > Technical > Automation > Scheduled Actions > Brightloop: Generate recurring invoices**.
   - Click **Run Manually**.
2. Return to the subscription form.
3. **Verify:**
   - Invoices smart button now shows `1 Invoice`.
   - A new row is added under **Billing History** with state `invoiced` and linked invoice number.
   - `next_invoice_date` automatically advances by 1 month.

### Step 11: Idempotency & Failure Resilience
1. Run the scheduled action a second time immediately.
2. **Verify:** No duplicate invoice is generated, and the invoice count remains `1`.
3. Show that existing invoiced billing periods are strictly protected by `unique(subscription_id, period_start, period_end)`.

### Step 12: Native Payment Registration & Reconciliation
1. Click the **Invoices** smart button and open the generated invoice.
2. Click **Register Payment**, select Bank/Cash, and validate.
3. **Verify:** Invoice displays the green **In Payment / Paid** ribbon. The subscription's billing ledger reflects the paid state directly through Odoo Accounting.

---

## Part 4: Customer Portal Self-Service (Module K)

### Step 13: Portal Home & Subscriptions Overview
1. Log in as the customer portal user `contact@acmecloud.com` and visit `/my`.
2. **Verify:**
   - The portal home displays the **Subscriptions** card with the active count badge.
   - Breadcrumb navigation displays `Home / Subscriptions`.
3. Click into **Subscriptions** (`/my/brightloop/subscriptions`).
4. **Verify:** Clean table displaying subscription number, plan name, status badge, dates, and total amount.

### Step 14: Customer Subscription Detail & Self-Service
1. Click on the subscription row to open `/my/brightloop/subscriptions/<id>`.
2. **Verify:**
   - Line items table displays products, quantities, unit prices, and tax breakdown.
   - Billing Periods history and linked invoice status are visible.
3. Click **Pause Subscription**.
   - **Verify:** Subscription state updates to `Paused` with a confirmation banner.
4. Click **Resume Subscription**.
   - **Verify:** Subscription state updates back to `Active`.

---

## Part 5: High-Performance Executive Dashboard (Module L)

### Step 15: Executive Dashboard & Financial Metrics
1. Log back in as Administrator and open **Brightloop > Dashboard**.
2. **Verify:**
   - **Monthly Recurring Revenue (MRR)** and **Annual Recurring Revenue (ARR)** calculated accurately.
   - **Active Subscriptions**, **Total Customers**, and status counts displayed.
   - **Revenue Received** and **Outstanding Amounts** aggregated directly from PostgreSQL.
3. Highlight that all metrics execute via direct SQL aggregation in <50 milliseconds.

---

## Part 6: Automated Test Suite Verification

### Step 16: Automated Test Execution
Run the full 24-test suite inside the Odoo Docker container:
```bash
docker compose exec odoo odoo -d brightloop_test -i brightloop_subscription --test-enable --stop-after-init
```
**Verify:** All 24 tests pass cleanly with zero failures or errors:
- 16 tests in `test_billing.py`
- 8 tests in `test_core_modules.py`
