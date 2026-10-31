from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SubscriptionPlan(models.Model):
    _name = "subscription.plan"
    _description = "Subscription Plan"
    _order = "name"

    name = fields.Char(required=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    price = fields.Monetary(required=True, currency_field="currency_id")
    billing_period = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        required=True,
        default="monthly",
    )
    minimum_quantity = fields.Float(default=1, required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    auto_close = fields.Boolean(default=False)
    allow_pause = fields.Boolean(default=True)
    allow_early_close = fields.Boolean(default=True)
    allow_renewal = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )

    @api.constrains("price", "minimum_quantity", "start_date", "end_date")
    def _check_values(self):
        for plan in self:
            if plan.price < 0:
                raise ValidationError("Plan price cannot be negative.")
            if plan.minimum_quantity <= 0:
                raise ValidationError("Minimum quantity must be greater than zero.")
            if plan.start_date and plan.end_date and plan.end_date < plan.start_date:
                raise ValidationError("Plan end date cannot be before its start date.")

