from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    brand = fields.Char(string="Brand", index=True, help="Brand or manufacturer of the product")


class ProductProduct(models.Model):
    _inherit = "product.product"

    variant_extra_price = fields.Monetary(
        string="Variant Additional Price",
        currency_field="currency_id",
        help="Additional markup or surcharge specific to this product variant for subscriptions",
    )
