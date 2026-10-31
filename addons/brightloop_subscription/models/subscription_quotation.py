from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SubscriptionQuotationTemplate(models.Model):
    _name = "subscription.quotation.template"
    _description = "Subscription Quotation Template"
    _order = "name"

    name = fields.Char(required=True)
    plan_id = fields.Many2one("subscription.plan", required=True, ondelete="restrict")
    validity_days = fields.Integer(default=30, required=True, help="Default validity duration in days")
    payment_term_id = fields.Many2one("account.payment.term")
    line_ids = fields.One2many("subscription.quotation.template.line", "template_id")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )


class SubscriptionQuotationTemplateLine(models.Model):
    _name = "subscription.quotation.template.line"
    _description = "Subscription Quotation Template Line"

    template_id = fields.Many2one(
        "subscription.quotation.template", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1)
    price_unit = fields.Monetary(required=True, currency_field="currency_id")
    discount = fields.Float(default=0)
    currency_id = fields.Many2one(
        "res.currency", related="template_id.plan_id.currency_id", store=True, readonly=True
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            extra = getattr(self.product_id, "variant_extra_price", 0.0)
            self.price_unit = self.product_id.list_price + extra
            if self.product_id.taxes_id:
                self.tax_ids = [(6, 0, self.product_id.taxes_id.ids)]


class SubscriptionQuotation(models.Model):
    _name = "subscription.quotation"
    _description = "Subscription Quotation"
    _order = "create_date desc"

    name = fields.Char(required=True, copy=False, default="New", index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", index=True)
    template_id = fields.Many2one("subscription.quotation.template", string="Quotation Template")
    plan_id = fields.Many2one("subscription.plan", required=True, ondelete="restrict")
    quotation_date = fields.Date(required=True, default=fields.Date.context_today)
    validity_date = fields.Date(required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    payment_term_id = fields.Many2one("account.payment.term")
    line_ids = fields.One2many("subscription.quotation.line", "quotation_id")
    currency_id = fields.Many2one(
        "res.currency", related="plan_id.currency_id", store=True, readonly=True
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )
    amount_untaxed = fields.Monetary(compute="_compute_amounts", store=True)
    amount_total = fields.Monetary(compute="_compute_amounts", store=True)
    subscription_id = fields.Many2one("subscription.subscription", readonly=True, copy=False, string="Created Subscription")

    _sql_constraints = [
        ("quotation_name_company_unique", "unique(name, company_id)", "Quotation number must be unique."),
    ]

    @api.depends("line_ids.subtotal")
    def _compute_amounts(self):
        for quotation in self:
            amount = sum(quotation.line_ids.mapped("subtotal"))
            quotation.amount_untaxed = amount
            quotation.amount_total = amount

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id:
            self.plan_id = self.template_id.plan_id
            self.payment_term_id = self.template_id.payment_term_id
            if self.quotation_date and self.template_id.validity_days:
                self.validity_date = self.quotation_date + timedelta(days=self.template_id.validity_days)
            if self.template_id.line_ids:
                lines = []
                for tline in self.template_id.line_ids:
                    lines.append((0, 0, {
                        "product_id": tline.product_id.id,
                        "quantity": tline.quantity,
                        "price_unit": tline.price_unit,
                        "discount": tline.discount,
                    }))
                self.line_ids = [(5, 0, 0)] + lines
            elif self.template_id.plan_id:
                self._populate_plan_line()

    @api.onchange("plan_id")
    def _onchange_plan_id(self):
        if self.plan_id and not self.line_ids:
            self._populate_plan_line()

    def _populate_plan_line(self):
        if self.plan_id:
            extra = getattr(self.plan_id.product_id, "variant_extra_price", 0.0)
            price = self.plan_id.price or (self.plan_id.product_id.list_price + extra)
            self.line_ids = [(5, 0, 0), (0, 0, {
                "product_id": self.plan_id.product_id.id,
                "quantity": self.plan_id.minimum_quantity,
                "price_unit": price,
            })]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("subscription.quotation") or "New"
            if not vals.get("validity_date"):
                qdate = fields.Date.from_string(vals.get("quotation_date")) or fields.Date.context_today(self)
                vals["validity_date"] = qdate + timedelta(days=30)
        return super().create(vals_list)

    @api.constrains("quotation_date", "validity_date", "line_ids")
    def _check_validity(self):
        for quotation in self:
            if quotation.validity_date and quotation.quotation_date and quotation.validity_date < quotation.quotation_date:
                raise ValidationError(_("Quotation validity date cannot be before quotation date."))
            if quotation.line_ids and quotation.plan_id:
                for line in quotation.line_ids:
                    if line.quantity < quotation.plan_id.minimum_quantity:
                        raise ValidationError(
                            _("All quotation lines must meet the plan minimum quantity (%s).")
                            % quotation.plan_id.minimum_quantity
                        )

    def action_send(self):
        self.write({"state": "sent"})
        return True

    def action_accept(self):
        self.write({"state": "accepted"})
        return True

    def action_reject(self):
        self.write({"state": "rejected"})
        return True

    def action_convert_to_subscription(self):
        self.ensure_one()
        if self.subscription_id:
            raise UserError(_("A subscription (%s) has already been created from this quotation.") % self.subscription_id.name)
        if self.state != "accepted":
            raise UserError(_("Only accepted quotations can be converted into subscriptions."))
        if not self.line_ids:
            raise UserError(_("Add at least one product line before converting to subscription."))

        Subscription = self.env["subscription.subscription"]
        lines_data = []
        for line in self.line_ids:
            lines_data.append((0, 0, {
                "product_id": line.product_id.id,
                "quantity": line.quantity,
                "price_unit": line.price_unit,
                "discount": line.discount,
                "tax_ids": [(6, 0, line.tax_ids.ids)],
            }))

        sub_vals = {
            "partner_id": self.partner_id.id,
            "plan_id": self.plan_id.id,
            "payment_term_id": self.payment_term_id.id or False,
            "start_date": fields.Date.context_today(self),
            "state": "confirmed",
            "quotation_id": self.id,
            "line_ids": lines_data,
        }
        subscription = Subscription.create(sub_vals)
        self.subscription_id = subscription.id

        return {
            "name": _("Subscription"),
            "type": "ir.actions.act_window",
            "res_model": "subscription.subscription",
            "res_id": subscription.id,
            "view_mode": "form",
        }


class SubscriptionQuotationLine(models.Model):
    _name = "subscription.quotation.line"
    _description = "Subscription Quotation Line"

    quotation_id = fields.Many2one(
        "subscription.quotation", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1)
    price_unit = fields.Monetary(required=True, currency_field="currency_id")
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    discount = fields.Float(default=0)
    currency_id = fields.Many2one(related="quotation_id.currency_id", store=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            extra = getattr(self.product_id, "variant_extra_price", 0.0)
            self.price_unit = self.product_id.list_price + extra
            if self.product_id.taxes_id:
                self.tax_ids = [(6, 0, self.product_id.taxes_id.ids)]

    @api.depends("quantity", "price_unit", "discount")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit * (1 - line.discount / 100)

    @api.constrains("quantity", "discount")
    def _check_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Line quantity must be greater than zero."))
            if not 0 <= line.discount <= 100:
                raise ValidationError(_("Line discount must be between 0 and 100."))
