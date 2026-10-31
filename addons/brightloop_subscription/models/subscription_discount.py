from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SubscriptionDiscount(models.Model):
    _name = "subscription.discount"
    _description = "Subscription Discount"
    _order = "name"

    name = fields.Char(required=True)
    discount_type = fields.Selection(
        [("fixed", "Fixed Amount"), ("percentage", "Percentage")],
        required=True,
        default="percentage",
    )
    discount_value = fields.Float(required=True)
    minimum_quantity = fields.Float(default=0)
    minimum_amount = fields.Monetary(default=0, currency_field="currency_id")
    start_date = fields.Date()
    end_date = fields.Date()
    usage_limit = fields.Integer(default=0)
    used_count = fields.Integer(default=0, readonly=True)
    product_ids = fields.Many2many("product.product", string="Products")
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id, required=True
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )

    @api.constrains("discount_value", "minimum_quantity", "minimum_amount", "usage_limit")
    def _check_values(self):
        for discount in self:
            if discount.discount_value < 0:
                raise ValidationError("Discount value cannot be negative.")
            if discount.discount_type == "percentage" and discount.discount_value > 100:
                raise ValidationError("Percentage discounts cannot exceed 100.")
            if discount.usage_limit < 0:
                raise ValidationError("Usage limit cannot be negative.")

    def is_eligible(self, lines, amount, today):
        self.ensure_one()
        if not self.active or (
            self.start_date and today < self.start_date
        ) or (self.end_date and today > self.end_date):
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        if sum(lines.mapped("quantity")) < self.minimum_quantity or amount < self.minimum_amount:
            return False
        return not self.product_ids or bool(lines.filtered(lambda line: line.product_id in self.product_ids))
