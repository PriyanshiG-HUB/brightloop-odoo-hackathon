from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class SubscriptionDashboard(models.Model):
    _name = "subscription.dashboard"
    _description = "Brightloop Dashboard"

    name = fields.Char(default="Brightloop Overview", required=True)
    active_subscriptions = fields.Integer(compute="_compute_metrics")
    monthly_recurring_revenue = fields.Monetary(compute="_compute_metrics")
    annual_recurring_revenue = fields.Monetary(compute="_compute_metrics")
    revenue_received = fields.Monetary(compute="_compute_metrics")
    outstanding_amount = fields.Monetary(compute="_compute_metrics")
    overdue_invoice_count = fields.Integer(compute="_compute_metrics")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True
    )

    @api.depends_context("company")
    def _compute_metrics(self):
        Subscription = self.env["subscription.subscription"]
        Move = self.env["account.move"]
        for dashboard in self:
            active = Subscription.search([("state", "=", "active")])
            monthly = sum(
                subscription.amount_total
                * {"daily": 30, "weekly": 52 / 12, "monthly": 1, "yearly": 1 / 12}.get(
                    subscription.plan_id.billing_period, 1
                )
                for subscription in active
            )
            invoices = Move.search([
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("company_id", "=", self.env.company.id),
            ])
            dashboard.active_subscriptions = len(active)
            dashboard.monthly_recurring_revenue = monthly
            dashboard.annual_recurring_revenue = monthly * 12
            dashboard.revenue_received = sum(invoices.mapped("amount_total")) - sum(
                invoices.mapped("amount_residual")
            )
            dashboard.outstanding_amount = sum(invoices.mapped("amount_residual"))
            dashboard.overdue_invoice_count = len(
                invoices.filtered(lambda invoice: invoice.invoice_date_due and invoice.invoice_date_due < fields.Date.today() and invoice.payment_state not in ("paid", "reversed"))
            )

