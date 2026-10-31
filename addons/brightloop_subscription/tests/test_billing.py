from datetime import date

from odoo.tests.common import TransactionCase


class TestBrightloopBilling(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Brightloop Pro",
            "list_price": 100,
            "type": "service",
        })
        cls.plan = cls.env["subscription.plan"].create({
            "name": "Monthly Pro",
            "product_id": cls.product.id,
            "price": 100,
            "billing_period": "monthly",
        })
        cls.partner = cls.env["res.partner"].create({"name": "Demo Customer"})
        cls.subscription = cls.env["subscription.subscription"].create({
            "partner_id": cls.partner.id,
            "plan_id": cls.plan.id,
            "start_date": date(2024, 1, 31),
            "line_ids": [(0, 0, {
                "product_id": cls.product.id,
                "quantity": 1,
                "price_unit": 100,
            })],
        })

    def test_lifecycle_and_month_end(self):
        self.subscription.action_submit_quotation()
        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.assertEqual(self.subscription.state, "active")
        self.assertEqual(self.subscription._next_date(date(2024, 1, 31), "monthly"), date(2024, 2, 29))

    def test_billing_is_idempotent(self):
        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.subscription._generate_invoice()
        self.subscription._generate_invoice()
        periods = self.env["subscription.billing.period"].search([
            ("subscription_id", "=", self.subscription.id),
        ])
        self.assertEqual(len(periods), 1)
        self.assertEqual(len(self.env["account.move"].search([
            ("invoice_origin", "=", self.subscription.name),
        ])), 1)

