# Database schema

| Model | Purpose |
|---|---|
| `subscription.plan` | Product, recurring price, frequency and lifecycle policy |
| `subscription.subscription` | Customer subscription and lifecycle state |
| `subscription.subscription.line` | Products, quantities, taxes and line discounts |
| `subscription.discount` | Fixed or percentage discount eligibility and usage |
| `subscription.billing.period` | Idempotent billing-period-to-invoice link |
| `account.move` | Native Odoo customer invoice |
| `account.payment` | Native Odoo payment and reconciliation workflow |

The unique key `(subscription_id, period_start, period_end)` prevents duplicate
billing records for a subscription period.

