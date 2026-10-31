from odoo import fields, models


class SubscriptionBillingPeriod(models.Model):
    _name = "subscription.billing.period"
    _description = "Subscription Billing Period"
    _order = "period_start desc"

    subscription_id = fields.Many2one(
        "subscription.subscription", required=True, ondelete="cascade", index=True
    )
    period_start = fields.Date(required=True, index=True)
    period_end = fields.Date(required=True, index=True)
    invoice_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [("pending", "Pending"), ("invoiced", "Invoiced"), ("failed", "Failed")],
        default="pending",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company", related="subscription_id.company_id", store=True, index=True
    )

    _sql_constraints = [
        (
            "subscription_period_unique",
            "unique(subscription_id, period_start, period_end)",
            "A billing period can only be invoiced once.",
        ),
    ]

