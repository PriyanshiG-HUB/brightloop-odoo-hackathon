# Brightloop Architecture Documentation

## 1. System Overview

**Brightloop** is an enterprise-grade Subscription Management System built natively on **Odoo 17 Community Edition** and **PostgreSQL 16**. It is architected to handle recurring billing, product and plan management, subscription lifecycle transitions, quotation conversion, automated invoice creation, customer portal self-service, and executive financial reporting without external billing engines.

```mermaid
graph TD
    User([Customer / Portal]) <-->|HTTP / Portal| PortalCtrl[Portal Controller]
    Staff([Sales & Billing Staff]) <-->|Web Client| OdooWeb[Odoo 17 Web UI]
    API([External Systems]) <-->|REST JSON API| APICtrl[Brightloop REST Controller]

    subgraph Brightloop Core Addon
        PortalCtrl --> SubModel[subscription.subscription]
        OdooWeb --> SubModel
        OdooWeb --> PlanModel[subscription.plan]
        OdooWeb --> QuoModel[subscription.quotation]
        OdooWeb --> DashModel[subscription.dashboard]
        APICtrl --> SubModel

        SubModel --> PeriodModel[subscription.billing.period]
        SubModel --> LineModel[subscription.subscription.line]
        SubModel --> DiscModel[subscription.discount]
        QuoModel --> SubModel
    end

    subgraph Native Odoo 17 Core
        SubModel --> Partner[res.partner]
        SubModel --> Product[product.product]
        PeriodModel --> AccountMove[account.move / Invoices]
        AccountMove --> AccountPayment[account.payment]
        Cron[ir.cron Recurring Job] --> SubModel
    end

    subgraph Database
        PeriodModel --> PG[(PostgreSQL 16)]
        DashModel -->|Aggregated SQL| PG
    end
```

---

## 2. Key Architecture Pillars

### 2.1 Native Odoo 17 Integration
- Extends standard Odoo models (`res.partner`, `res.users`, `product.template`, `product.product`, `account.move`).
- Adheres strictly to Odoo 17 Community patterns: `tree` root elements, Python expression-based `invisible` modifiers, `env.company` multi-company scoping, and transactional ORM methods.

### 2.2 Idempotency & The Billing Period Engine
- Every billing iteration is tracked by `subscription.billing.period`.
- The compound SQL constraint `unique(subscription_id, period_start, period_end)` forms the **idempotency boundary**.
- Even if a cron job runs repeatedly or concurrently, duplicate invoices can never be generated for the same subscription period.
- Transient errors mark the period as `failed` without advancing `next_invoice_date`, allowing seamless retries without data corruption.

### 2.3 Quotation-to-Subscription Conversion
- Quotations can be built manually or instantly populated from reusable `subscription.quotation.template` presets.
- When an administrator or customer accepts the quotation, `action_convert_to_subscription()` instantiates the confirmed `subscription.subscription` with exact lines, prices, and plan parameters.

### 2.4 Customer Self-Service Portal
- Portal users (`base.group_portal`) access their own subscriptions at `/my/brightloop/subscriptions`.
- Clean detail view displays line items, pricing totals, billing period audit trails, and linked invoices.
- Customers can pause, resume, cancel, or renew subscriptions directly from the UI, subject to the plan's policy permissions (`allow_pause`, `allow_cancel`, `allow_renewal`).

### 2.5 High-Performance Executive Dashboard
- The dashboard calculates MRR, ARR, active counts, receivables, and cash flow via direct, indexed PostgreSQL queries (`SUM`, `COUNT`, `GROUP BY`).
- Achieves sub-50ms execution times even with large databases (>100,000 subscriptions and invoices).

---

## 3. Data Flow & Billing Engine Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Cron as ir.cron Scheduler
    participant Sub as subscription.subscription
    participant Period as subscription.billing.period
    participant Move as account.move (Invoice)
    participant Account as Odoo Accounting

    Cron->>Sub: _cron_generate_invoices()
    Sub->>Sub: Search active subscriptions where next_invoice_date <= today
    loop Each Due Subscription
        Sub->>Period: Find or create pending period (period_start, period_end)
        alt Invoiced period exists
            Sub-->>Sub: Skip (Idempotent)
        else Period pending or failed
            Sub->>Sub: Resolve product income account & sales journal
            Sub->>Move: Create out_invoice with taxes & discounted lines
            alt Creation succeeds
                Sub->>Move: action_post()
                Sub->>Period: Link invoice_id & set state = 'invoiced'
                Sub->>Sub: Advance next_invoice_date by plan billing_period
            else Error occurs
                Sub->>Period: Rollback to savepoint & set state = 'failed'
                Sub-->>Cron: Log error, continue next subscription
            end
        end
    end
```

---

## 4. Multi-Company & Security Architecture

1. **Company Isolation:** Record rules enforce `('company_id', 'in', company_ids)` on subscriptions, quotations, plans, and discounts.
2. **Customer Portal Isolation:** Portal users are restricted strictly by `[('partner_id', '=', user.partner_id.id)]` across subscriptions, quotations, lines, and billing history.
3. **Password Security:** Model constraints on `res.users` enforce enterprise complexity: minimum 8 characters, at least 1 uppercase letter, 1 lowercase letter, and 1 special symbol.
4. **Unique Partner Identifiers:** Unique email constraint ensures customer records cannot be duplicated.
