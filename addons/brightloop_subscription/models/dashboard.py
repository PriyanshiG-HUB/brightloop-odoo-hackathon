from odoo import api, fields, models


class SubscriptionDashboard(models.Model):
    _name = "subscription.dashboard"
    _description = "Brightloop Dashboard"

    name = fields.Char(default="Brightloop Overview", required=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True
    )

    # Subscription Operational KPIs
    total_subscriptions = fields.Integer(compute="_compute_metrics", string="Total Subscriptions")
    active_subscriptions = fields.Integer(compute="_compute_metrics", string="Active Subscriptions")
    paused_subscriptions = fields.Integer(compute="_compute_metrics", string="Paused Subscriptions")
    closed_subscriptions = fields.Integer(compute="_compute_metrics", string="Closed Subscriptions")
    cancelled_subscriptions = fields.Integer(compute="_compute_metrics", string="Cancelled Subscriptions")
    total_customers = fields.Integer(compute="_compute_metrics", string="Total Customers")
    failed_billing_period_count = fields.Integer(compute="_compute_metrics", string="Failed Billing Periods")

    # Financial KPIs
    monthly_recurring_revenue = fields.Monetary(compute="_compute_metrics", string="MRR")
    annual_recurring_revenue = fields.Monetary(compute="_compute_metrics", string="ARR")
    revenue_received = fields.Monetary(compute="_compute_metrics", string="Revenue Received")
    outstanding_amount = fields.Monetary(compute="_compute_metrics", string="Outstanding Amount")
    overdue_invoice_count = fields.Integer(compute="_compute_metrics", string="Overdue Invoices")

    @api.depends_context("company")
    def _compute_metrics(self):
        for dashboard in self:
            company_id = self.env.company.id

            # 1. Subscriptions counts by state for current company
            self.env.cr.execute(
                """
                SELECT state, COUNT(*)
                FROM subscription_subscription
                WHERE company_id = %s
                GROUP BY state
                """,
                [company_id],
            )
            state_counts = dict(self.env.cr.fetchall())
            dashboard.active_subscriptions = state_counts.get("active", 0)
            dashboard.paused_subscriptions = state_counts.get("paused", 0)
            dashboard.closed_subscriptions = state_counts.get("closed", 0)
            dashboard.cancelled_subscriptions = state_counts.get("cancelled", 0)
            dashboard.total_subscriptions = sum(state_counts.values())

            # Distinct customers with subscriptions in this company
            self.env.cr.execute(
                """
                SELECT COUNT(DISTINCT partner_id)
                FROM subscription_subscription
                WHERE company_id = %s
                """,
                [company_id],
            )
            res = self.env.cr.fetchone()
            dashboard.total_customers = res[0] if res else 0

            # Failed billing periods count
            self.env.cr.execute(
                """
                SELECT COUNT(*)
                FROM subscription_billing_period bp
                JOIN subscription_subscription s ON bp.subscription_id = s.id
                WHERE s.company_id = %s AND bp.state = 'failed'
                """,
                [company_id],
            )
            res = self.env.cr.fetchone()
            dashboard.failed_billing_period_count = res[0] if res else 0

            # 2. MRR calculation via SQL aggregation
            self.env.cr.execute(
                """
                SELECT p.billing_period, COALESCE(SUM(s.amount_total), 0)
                FROM subscription_subscription s
                JOIN subscription_plan p ON s.plan_id = p.id
                WHERE s.company_id = %s AND s.state = 'active'
                GROUP BY p.billing_period
                """,
                [company_id],
            )
            period_multiplier = {
                "daily": 30.0,
                "weekly": 52.0 / 12.0,
                "monthly": 1.0,
                "yearly": 1.0 / 12.0,
            }
            mrr = 0.0
            for period, total in self.env.cr.fetchall():
                mult = period_multiplier.get(period, 1.0)
                mrr += float(total or 0.0) * mult
            dashboard.monthly_recurring_revenue = mrr
            dashboard.annual_recurring_revenue = mrr * 12.0

            # 3. Invoices metrics (posted out_invoices for current company)
            self.env.cr.execute(
                """
                SELECT
                    COALESCE(SUM(amount_total), 0) - COALESCE(SUM(amount_residual), 0) AS received,
                    COALESCE(SUM(amount_residual), 0) AS outstanding,
                    COUNT(CASE WHEN invoice_date_due < CURRENT_DATE AND payment_state NOT IN ('paid', 'reversed') THEN 1 END) AS overdue
                FROM account_move
                WHERE move_type = 'out_invoice'
                  AND state = 'posted'
                  AND company_id = %s
                """,
                [company_id],
            )
            inv_stats = self.env.cr.fetchone()
            if inv_stats:
                dashboard.revenue_received = inv_stats[0] or 0.0
                dashboard.outstanding_amount = inv_stats[1] or 0.0
                dashboard.overdue_invoice_count = inv_stats[2] or 0
            else:
                dashboard.revenue_received = 0.0
                dashboard.outstanding_amount = 0.0
                dashboard.overdue_invoice_count = 0
