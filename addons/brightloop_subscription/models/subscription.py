import logging
from calendar import monthrange
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


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
    amount_tax = fields.Monetary(compute="_compute_amounts", store=True, string="Taxes")
    amount_total = fields.Monetary(compute="_compute_amounts", store=True)
    invoice_ids = fields.Many2many(
        "account.move",
        compute="_compute_invoice_ids",
        string="Invoices",
    )
    invoice_count = fields.Integer(compute="_compute_invoice_ids", string="Invoices Count")
    billing_period_ids = fields.One2many(
        "subscription.billing.period", "subscription_id", string="Billing History"
    )

    _sql_constraints = [
        ("subscription_name_company_unique", "unique(name, company_id)", "Subscription number must be unique."),
    ]

    @api.depends("line_ids.subtotal", "line_ids.tax_ids", "discount_ids", "line_ids.quantity")
    def _compute_amounts(self):
        today = fields.Date.context_today(self)
        for subscription in self:
            lines_total = sum(subscription.line_ids.mapped("subtotal"))
            discount_amount = 0
            for discount in subscription.discount_ids:
                if discount.is_eligible(subscription.line_ids, lines_total, today):
                    applicable_lines = subscription.line_ids.filtered(
                        lambda l: not discount.product_ids or l.product_id in discount.product_ids
                    )
                    applicable_total = sum(applicable_lines.mapped("subtotal"))
                    if discount.discount_type == "percentage":
                        discount_amount += applicable_total * (discount.discount_value / 100.0)
                    elif discount.discount_type == "fixed":
                        discount_amount += min(discount.discount_value, applicable_total)
            subscription.amount_untaxed = max(lines_total - discount_amount, 0)

            total_tax = 0.0
            currency = subscription.currency_id or subscription.company_id.currency_id
            for line in subscription.line_ids:
                if line.tax_ids:
                    line_taxes = line.tax_ids.compute_all(
                        line.price_unit * (1 - line.discount / 100.0),
                        currency=currency,
                        quantity=line.quantity,
                        product=line.product_id,
                        partner=subscription.partner_id,
                    )
                    total_tax += line_taxes["total_included"] - line_taxes["total_excluded"]

            if lines_total > 0 and discount_amount > 0:
                tax_ratio = subscription.amount_untaxed / lines_total
                total_tax = total_tax * tax_ratio

            subscription.amount_tax = total_tax
            subscription.amount_total = subscription.amount_untaxed + total_tax

    @api.depends("billing_period_ids.invoice_id")
    def _compute_invoice_ids(self):
        for sub in self:
            invoices = sub.billing_period_ids.filtered(lambda p: p.invoice_id).mapped("invoice_id")
            sub.invoice_ids = [(6, 0, invoices.ids)]
            sub.invoice_count = len(invoices)

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids
        action = {
            "name": _("Invoices"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [("id", "in", invoices.ids)],
            "context": {"default_move_type": "out_invoice"},
        }
        if len(invoices) == 1:
            action["res_id"] = invoices.id
            action["view_mode"] = "form"
        return action

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
        for subscription in self:
            subscription._get_or_create_sale_order()
        self.write({"state": "quotation"})
        return True

    def action_confirm(self):
        for subscription in self:
            if not subscription.line_ids:
                raise UserError(_("Add at least one product before confirming a subscription."))
            sale_order = subscription._get_or_create_sale_order()
            if sale_order.state in ("draft", "sent"):
                sale_order.action_confirm()
        self.write({"state": "confirmed"})
        return True

    def action_create_quotation(self):
        """Recover or create the quotation linked to a confirmed subscription."""
        for subscription in self:
            subscription._get_or_create_sale_order()
        return True

    def _get_or_create_sale_order(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM subscription_subscription WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        self.invalidate_recordset(["sale_order_id"])
        if self.sale_order_id:
            return self.sale_order_id
        if not self.line_ids:
            raise UserError(_("Add at least one product before creating a quotation."))
        existing_order = self.env["sale.order"].search([
            ("origin", "=", self.name),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if existing_order:
            self.sale_order_id = existing_order
            return existing_order

        order_lines = []
        for line_values in self._prepare_sale_order_line_values():
            order_lines.append((0, 0, line_values))
        sale_order = self.env["sale.order"].create({
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "payment_term_id": self.payment_term_id.id or False,
            "origin": self.name,
            "order_line": order_lines,
        })
        self.sale_order_id = sale_order
        return sale_order

    def _get_eligible_discounts(self, amount, today):
        self.ensure_one()
        return self.discount_ids.filtered(
            lambda discount: discount.is_eligible(self.line_ids, amount, today)
        )

    def _prepare_discounted_line_values(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        lines_total = sum(self.line_ids.mapped("subtotal"))
        eligible_discounts = self._get_eligible_discounts(lines_total, today)

        line_fixed_discounts = {line.id: 0.0 for line in self.line_ids}
        line_pct_discounts = {line.id: 0.0 for line in self.line_ids}

        for discount in eligible_discounts:
            applicable_lines = self.line_ids.filtered(
                lambda l: not discount.product_ids or l.product_id in discount.product_ids
            )
            if not applicable_lines:
                continue

            if discount.discount_type == "percentage":
                for line in applicable_lines:
                    line_pct_discounts[line.id] += discount.discount_value
            elif discount.discount_type == "fixed":
                applicable_total = sum(applicable_lines.mapped("subtotal"))
                if applicable_total > 0:
                    capped_fixed = min(discount.discount_value, applicable_total)
                    for line in applicable_lines:
                        line_fixed_discounts[line.id] += capped_fixed * (line.subtotal / applicable_total)

        values = []
        for line in self.line_ids:
            fixed_share = line_fixed_discounts.get(line.id, 0.0)
            pct_share = line_pct_discounts.get(line.id, 0.0)
            price_unit = max(
                line.price_unit - (fixed_share / line.quantity if line.quantity else 0),
                0,
            )
            discount = min(100.0, line.discount + pct_share)
            values.append({
                "product_id": line.product_id.id,
                "name": line.product_id.get_product_multiline_description_sale(),
                "quantity": line.quantity,
                "price_unit": price_unit,
                "discount": discount,
                "tax_ids": line.tax_ids,
            })
        return values

    def _prepare_sale_order_line_values(self, today=None):
        return [
            {
                "product_id": values["product_id"],
                "name": values["name"],
                "product_uom_qty": values["quantity"],
                "price_unit": values["price_unit"],
                "discount": values["discount"],
                "tax_id": [(6, 0, values["tax_ids"].ids)],
            }
            for values in self._prepare_discounted_line_values(today=today)
        ]

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
        journal = self.env["account.journal"].search([
            ("type", "=", "sale"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "No sales journal found for company '%s'. "
                "Please configure a sales journal before generating invoices."
            ) % self.company_id.name)

        invoice_lines = []
        for values in self._prepare_discounted_line_values(today=period_start):
            product = self.env["product.product"].browse(
                values["product_id"]
            ).with_company(self.company_id)

            # Native Odoo 17 income account resolution:
            income_account = False
            if hasattr(product, "_get_product_accounts"):
                income_account = product._get_product_accounts().get("income")
            elif hasattr(product.product_tmpl_id, "get_product_accounts"):
                income_account = product.product_tmpl_id.get_product_accounts().get("income")

            if not income_account:
                income_account = (
                    product.property_account_income_id
                    or product.categ_id.property_account_income_categ_id
                )

            # Company fallback to active income account
            if not income_account:
                income_account = self.env["account.account"].search([
                    ("account_type", "=", "income"),
                    ("company_id", "=", self.company_id.id),
                    ("deprecated", "=", False),
                ], limit=1)

            if not income_account:
                raise UserError(_(
                    "No income account found for product '%s' in company '%s'. "
                    "Please configure an income account on the product, its category, "
                    "or create an active income account for the company."
                ) % (product.display_name, self.company_id.name))

            invoice_lines.append((0, 0, {
                "product_id": product.id,
                "account_id": income_account.id,
                "name": values["name"],
                "quantity": values["quantity"],
                "price_unit": values["price_unit"],
                "discount": values["discount"],
                "tax_ids": [(6, 0, values["tax_ids"].ids)],
            }))

        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "journal_id": journal.id,
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
            lines_total = sum(subscription.line_ids.mapped("subtotal"))
            existing = BillingPeriod.search([
                ("subscription_id", "=", subscription.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
            ], limit=1)

            if existing:
                if existing.state == "invoiced":
                    continue
                period = existing
                period.write({"state": "pending"})
            else:
                period = BillingPeriod.create({
                    "subscription_id": subscription.id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "state": "pending",
                })

            try:
                with self.env.cr.savepoint():
                    invoice = AccountMove.create(subscription._prepare_invoice(period_start, period_end))
                    invoice.action_post()
                    period.write({"invoice_id": invoice.id, "state": "invoiced"})
                    subscription.next_invoice_date = subscription._next_date(period_start, subscription.plan_id.billing_period)
                    for discount in subscription.discount_ids:
                        if discount.is_eligible(subscription.line_ids, lines_total, period_start):
                            discount.used_count += 1
            except Exception:
                period.write({"state": "failed"})
                raise
        return True

    @api.model
    def _check_auto_close_plans(self):
        today = fields.Date.context_today(self)
        expired_subscriptions = self.search([
            ("state", "=", "active"),
            ("plan_id.auto_close", "=", True),
            ("plan_id.end_date", "<", today),
        ])
        for sub in expired_subscriptions:
            try:
                sub.action_close()
                _logger.info("Auto-closed subscription %s because plan %s has reached its end date.", sub.name, sub.plan_id.name)
            except Exception as e:
                _logger.error("Failed to auto-close subscription %s: %s", sub.name, e)

    @api.model
    def _cron_generate_invoices(self):
        self._check_auto_close_plans()
        today = fields.Date.context_today(self)
        subscriptions = self.search([
            ("state", "=", "active"),
            ("next_invoice_date", "<=", today),
        ])
        for subscription in subscriptions:
            try:
                subscription._generate_invoice()
            except Exception as e:
                _logger.error(
                    "Brightloop billing cron failed for subscription %s (ID %s): %s",
                    subscription.name,
                    subscription.id,
                    e,
                    exc_info=True,
                )
        return True
