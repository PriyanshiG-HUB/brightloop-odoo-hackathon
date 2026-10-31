from calendar import monthrange
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Subscription(models.Model):
    _name = "subscription.subscription"
    _description = "Subscription"
    _order = "create_date desc"

    name = fields.Char(required=True, copy=False, default="New", index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", index=True)
    plan_id = fields.Many2one("subscription.plan", required=True, ondelete="restrict")
    sale_order_id = fields.Many2one("sale.order", readonly=True, copy=False)
    quotation_id = fields.Many2one("subscription.quotation", readonly=True, copy=False, string="Source Quotation")
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date()
    next_invoice_date = fields.Date(index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("quotation", "Quotation"),
            ("confirmed", "Confirmed"),
            ("active", "Active"),
            ("paused", "Paused"),
            ("cancelled", "Cancelled"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    payment_term_id = fields.Many2one("account.payment.term")
    line_ids = fields.One2many("subscription.subscription.line", "subscription_id")
    discount_ids = fields.Many2many("subscription.discount")
    currency_id = fields.Many2one(
        "res.currency", related="plan_id.currency_id", store=True, readonly=True
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )
    amount_untaxed = fields.Monetary(compute="_compute_amounts", store=True)
    amount_total = fields.Monetary(compute="_compute_amounts", store=True)
    billing_period_ids = fields.One2many(
        "subscription.billing.period", "subscription_id", string="Billing History"
    )

    _sql_constraints = [
        ("subscription_name_company_unique", "unique(name, company_id)", "Subscription number must be unique."),
    ]

    @api.depends("line_ids.subtotal", "discount_ids", "line_ids.quantity")
    def _compute_amounts(self):
        today = fields.Date.context_today(self)
        for subscription in self:
            amount = sum(subscription.line_ids.mapped("subtotal"))
            discount_amount = 0
            for discount in subscription.discount_ids:
                if discount.is_eligible(subscription.line_ids, amount, today):
                    discount_amount += (
                        amount * discount.discount_value / 100
                        if discount.discount_type == "percentage"
                        else discount.discount_value
                    )
            subscription.amount_untaxed = max(amount - discount_amount, 0)
            subscription.amount_total = subscription.amount_untaxed

    @api.onchange("plan_id")
    def _onchange_plan_id(self):
        if self.plan_id:
            self.currency_id = self.plan_id.currency_id
            extra_price = getattr(self.plan_id.product_id, "variant_extra_price", 0.0)
            unit_price = self.plan_id.price or (self.plan_id.product_id.list_price + extra_price)
            self.line_ids = [(5, 0, 0), (0, 0, {
                "product_id": self.plan_id.product_id.id,
                "quantity": self.plan_id.minimum_quantity,
                "price_unit": unit_price,
            })]

    @api.constrains("start_date", "end_date", "plan_id", "line_ids")
    def _check_dates_and_quantity(self):
        for subscription in self:
            if subscription.end_date and subscription.end_date < subscription.start_date:
                raise ValidationError("Subscription end date cannot be before its start date.")
            if subscription.plan_id and any(
                line.quantity < subscription.plan_id.minimum_quantity for line in subscription.line_ids
            ):
                raise ValidationError("All subscription lines must meet the plan minimum quantity.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("subscription.subscription") or "New"
            if not vals.get("next_invoice_date") and vals.get("start_date"):
                vals["next_invoice_date"] = vals["start_date"]
        return super().create(vals_list)

    def action_submit_quotation(self):
        self.write({"state": "quotation"})
        return True

    def action_confirm(self):
        for subscription in self:
            if not subscription.line_ids:
                raise UserError(_("Add at least one product before confirming a subscription."))
        self.write({"state": "confirmed"})
        return True

    def action_activate(self):
        for subscription in self:
            if subscription.state not in ("confirmed", "paused"):
                raise UserError(_("Only confirmed or paused subscriptions can be activated."))
            subscription.write({"state": "active", "next_invoice_date": subscription.next_invoice_date or subscription.start_date})
        return True

    def action_pause(self):
        for subscription in self:
            if not subscription.plan_id.allow_pause:
                raise UserError(_("Pausing is not allowed for this plan."))
            if subscription.state != "active":
                raise UserError(_("Only active subscriptions can be paused."))
        self.write({"state": "paused"})
        return True

    def action_resume(self):
        return self.action_activate()

    def action_cancel(self):
        for subscription in self:
            if subscription.plan_id and not subscription.plan_id.allow_cancel:
                raise UserError(_("Cancellation is not allowed for this plan."))
            if subscription.state in ("closed", "cancelled"):
                raise UserError(_("Subscription is already %s.") % subscription.state)
        self.write({"state": "cancelled"})
        return True

    def action_close(self):
        for subscription in self:
            if not subscription.plan_id.allow_early_close and not subscription.end_date:
                raise UserError(_("Early closure is not allowed for this plan."))
        self.write({"state": "closed", "end_date": fields.Date.context_today(self)})
        return True

    def action_renew(self):
        self.ensure_one()
        if not self.plan_id.allow_renewal:
            raise UserError(_("Renewal is not allowed for this plan."))
        self.write({"state": "active", "end_date": False, "next_invoice_date": fields.Date.context_today(self)})
        return True

    @staticmethod
    def _next_date(current, period):
        if period == "daily":
            return current + timedelta(days=1)
        if period == "weekly":
            return current + timedelta(days=7)
        if period == "yearly":
            return current + relativedelta(years=1)
        next_month = current + relativedelta(months=1)
        return next_month.replace(day=min(current.day, monthrange(next_month.year, next_month.month)[1]))

    def _billing_period(self):
        self.ensure_one()
        start = self.next_invoice_date or self.start_date
        end = self._next_date(start, self.plan_id.billing_period) - timedelta(days=1)
        return start, end

    def _prepare_invoice(self, period_start, period_end):
        self.ensure_one()
        invoice_lines = []
        eligible_discounts = self.discount_ids.filtered(
            lambda discount: discount.is_eligible(
                self.line_ids, sum(self.line_ids.mapped("subtotal")), period_start
            )
        )
        fixed_discount = sum(
            discount.discount_value
            for discount in eligible_discounts
            if discount.discount_type == "fixed"
        )
        percentage_discount = sum(
            discount.discount_value
            for discount in eligible_discounts
            if discount.discount_type == "percentage"
        )
        lines_total = sum(self.line_ids.mapped("subtotal"))
        for line in self.line_ids:
            fixed_share = fixed_discount * line.subtotal / lines_total if lines_total else 0
            discount = min(100, line.discount + percentage_discount)
            price_unit = line.price_unit - (fixed_share / line.quantity if line.quantity else 0)
            invoice_lines.append((0, 0, {
                "product_id": line.product_id.id,
                "name": line.product_id.display_name,
                "quantity": line.quantity,
                "price_unit": max(price_unit, 0),
                "discount": discount,
                "tax_ids": [(6, 0, line.tax_ids.ids)],
            }))
        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "invoice_date": period_start,
            "invoice_date_due": period_end,
            "invoice_origin": self.name,
            "invoice_payment_term_id": self.payment_term_id.id or False,
            "invoice_line_ids": invoice_lines,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
        }

    def _generate_invoice(self):
        AccountMove = self.env["account.move"]
        BillingPeriod = self.env["subscription.billing.period"]
        for subscription in self:
            if subscription.state != "active" or not subscription.next_invoice_date:
                continue
            period_start, period_end = subscription._billing_period()
            existing = BillingPeriod.search([
                ("subscription_id", "=", subscription.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
            ], limit=1)
            if existing:
                continue
            period = BillingPeriod.create({
                "subscription_id": subscription.id,
                "period_start": period_start,
                "period_end": period_end,
                "state": "pending",
            })
            try:
                invoice = AccountMove.create(subscription._prepare_invoice(period_start, period_end))
                invoice.action_post()
                period.write({"invoice_id": invoice.id, "state": "invoiced"})
                subscription.next_invoice_date = subscription._next_date(period_start, subscription.plan_id.billing_period)
                for discount in subscription.discount_ids:
                    if discount.is_eligible(subscription.line_ids, subscription.amount_untaxed, period_start):
                        discount.used_count += 1
            except Exception:
                period.state = "failed"
                raise
        return True

    @api.model
    def _cron_generate_invoices(self):
        today = fields.Date.context_today(self)
        subscriptions = self.search([
            ("state", "=", "active"),
            ("next_invoice_date", "<=", today),
        ])
        for subscription in subscriptions:
            with self.env.cr.savepoint():
                subscription._generate_invoice()
        return True
