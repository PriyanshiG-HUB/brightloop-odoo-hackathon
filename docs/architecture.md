# Brightloop architecture

Brightloop is a native Odoo 17 Community addon. `subscription.subscription` owns
the business lifecycle and references native `res.partner`, `product.product`,
`sale.order`, `account.payment.term`, and `account.move` records.

`subscription.subscription.line` stores recurring products and taxes. The daily
cron creates a `subscription.billing.period` first, then creates and posts one
native customer invoice. The period's SQL uniqueness constraint is the idempotency
boundary. Invoice payment status is read from Odoo Accounting rather than copied
into a custom payment table.

Portal routes are read-only and filter by the authenticated user's partner. Staff
access is restricted to their allowed companies, while discount maintenance is
limited to administrators.

