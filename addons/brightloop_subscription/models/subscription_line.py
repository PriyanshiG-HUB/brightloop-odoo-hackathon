from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SubscriptionLine(models.Model):
    _name = "subscription.subscription.line"
    _description = "Subscription Line"

    subscription_id = fields.Many2one(
        "subscription.subscription", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1)
    price_unit = fields.Monetary(required=True, currency_field="currency_id")
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    discount = fields.Float(default=0)
    currency_id = fields.Many2one(related="subscription_id.currency_id", store=True)
    subtotal = fields.Monetary(compute="_compute_subtotal", store=True)

    @api.depends("quantity", "price_unit", "discount")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit * (1 - line.discount / 100)

    @api.constrains("quantity", "discount")
    def _check_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Subscription quantity must be greater than zero.")
            if not 0 <= line.discount <= 100:
                raise ValidationError("Line discount must be between 0 and 100.")

