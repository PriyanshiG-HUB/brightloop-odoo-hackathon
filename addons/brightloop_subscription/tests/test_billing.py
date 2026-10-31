from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestBrightloopBilling(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_partner = cls.env.company.partner_id
        india = cls.env.ref("base.in")
        company_partner.write({
            "street": "100 Brightloop Avenue",
            "city": "New Delhi",
            "zip": "110001",
            "country_id": india.id,
            "state_id": cls.env["res.country.state"].search(
                [("country_id", "=", india.id)], limit=1
            ).id,
        })
        cls.income_account = cls.env["account.account"].create({
            "code": "400000",
            "name": "Brightloop Sales",
            "account_type": "income",
            "company_id": cls.env.company.id,
        })
        cls.receivable_account = cls.env["account.account"].create({
            "code": "110000",
            "name": "Brightloop Receivable",
            "account_type": "asset_receivable",
            "company_id": cls.env.company.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Brightloop Pro",
            "list_price": 100,
            "type": "service",
        })
        cls.product.product_tmpl_id.property_account_income_id = cls.income_account
        cls.plan = cls.env["subscription.plan"].create({
            "name": "Monthly Pro",
            "product_id": cls.product.id,
            "price": 100,
            "billing_period": "monthly",
        })
        cls.partner = cls.env["res.partner"].create({"name": "Demo Customer"})
        cls.partner.property_account_receivable_id = cls.receivable_account
        cls.env["account.journal"].create({
            "name": "Brightloop Sales",
            "code": "BLS",
            "type": "sale",
            "company_id": cls.env.company.id,
        })
        cls.tax_group = cls.env["account.tax.group"].create({
            "name": "Brightloop Taxes",
            "company_id": cls.env.company.id,
        })
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

    def test_submit_creates_and_links_sale_quotation(self):
        self.subscription.action_submit_quotation()
        order = self.subscription.sale_order_id
        self.assertTrue(order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(order.company_id, self.subscription.company_id)
        self.assertEqual(order.currency_id, self.subscription.currency_id)
        self.assertEqual(order.payment_term_id, self.subscription.payment_term_id)
        self.assertEqual(order.origin, self.subscription.name)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_id, self.product)
        self.assertEqual(order.order_line.product_uom_qty, 1)
        self.assertEqual(order.order_line.price_unit, 100)
        self.assertEqual(order.order_line.discount, 0)

    def test_quotation_transfers_taxes_and_eligible_discount_once(self):
        tax = self.env["account.tax"].create({
            "name": "Brightloop 10%",
            "amount": 10,
            "type_tax_use": "sale",
            "company_id": self.env.company.id,
            "tax_group_id": self.tax_group.id,
        })
        discount = self.env["subscription.discount"].create({
            "name": "Launch discount",
            "discount_type": "percentage",
            "discount_value": 10,
            "product_ids": [(6, 0, self.product.ids)],
        })
        line = self.subscription.line_ids
        line.write({"discount": 5, "tax_ids": [(6, 0, tax.ids)]})
        self.subscription.discount_ids = [(6, 0, discount.ids)]
        self.subscription.action_submit_quotation()
        order_line = self.subscription.sale_order_id.order_line
        self.assertEqual(order_line.discount, 15)
        self.assertEqual(order_line.price_unit, 100)
        self.assertEqual(order_line.tax_id, tax)

    def test_confirm_confirms_linked_sale_order(self):
        self.subscription.action_submit_quotation()
        self.subscription.action_confirm()
        self.assertEqual(self.subscription.state, "confirmed")
        self.assertEqual(self.subscription.sale_order_id.state, "sale")

    def test_quotation_creation_is_reused(self):
        self.subscription.action_submit_quotation()
        order = self.subscription.sale_order_id
        self.subscription.action_submit_quotation()
        self.assertEqual(self.subscription.sale_order_id, order)
        self.assertEqual(
            self.env["sale.order"].search_count([("origin", "=", self.subscription.name)]),
            1,
        )

    def test_confirmed_subscription_can_recover_missing_quotation(self):
        self.subscription.state = "confirmed"
        self.subscription.action_create_quotation()
        self.assertTrue(self.subscription.sale_order_id)
        self.assertEqual(self.subscription.sale_order_id.state, "draft")

    def test_recovery_button_is_present_for_confirmed_unlinked_subscription(self):
        view = self.env["subscription.subscription"].get_view(
            view_id=self.env.ref(
                "brightloop_subscription.view_subscription_form"
            ).id,
            view_type="form",
        )
        self.assertIn('name="action_create_quotation"', view["arch"])
        self.assertIn('string="Generate Quotation"', view["arch"])
        self.assertIn(
            "state != 'confirmed' or sale_order_id",
            view["arch"],
        )

    def test_billing_is_idempotent(self):
        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.subscription._generate_invoice()
        self.subscription.next_invoice_date = date(2024, 1, 31)
        self.subscription._generate_invoice()
        periods = self.env["subscription.billing.period"].search([
            ("subscription_id", "=", self.subscription.id),
        ])
        self.assertEqual(len(periods), 1)
        self.assertEqual(len(self.env["account.move"].search([
            ("invoice_origin", "=", self.subscription.name),
        ])), 1)

    def test_invoice_creation_posting_and_accounts(self):
        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.subscription._generate_invoice()

        period = self.env["subscription.billing.period"].search([
            ("subscription_id", "=", self.subscription.id),
        ])
        self.assertEqual(len(period), 1)
        self.assertEqual(period.state, "invoiced")
        self.assertTrue(period.invoice_id)

        invoice = period.invoice_id
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(invoice.invoice_origin, self.subscription.name)
        self.assertEqual(invoice.journal_id.type, "sale")
        self.assertEqual(invoice.company_id, self.subscription.company_id)

        line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == self.product)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.account_id, self.income_account)
        self.assertEqual(line.price_unit, 100)

    def test_failed_billing_period_retry(self):
        self.subscription.action_confirm()
        self.subscription.action_activate()
        period_start, period_end = self.subscription._billing_period()

        # Simulate a failed period from a previous attempt
        failed_period = self.env["subscription.billing.period"].create({
            "subscription_id": self.subscription.id,
            "period_start": period_start,
            "period_end": period_end,
            "state": "failed",
        })

        # Generate invoice again - should reuse failed period and succeed
        self.subscription._generate_invoice()

        periods = self.env["subscription.billing.period"].search([
            ("subscription_id", "=", self.subscription.id),
        ])
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods.id, failed_period.id)
        self.assertEqual(failed_period.state, "invoiced")
        self.assertTrue(failed_period.invoice_id)
        self.assertEqual(failed_period.invoice_id.state, "posted")

    def test_cron_batch_resilience_one_failure_does_not_block_others(self):
        partner2 = self.env["res.partner"].create({"name": "Second Customer"})
        partner2.property_account_receivable_id = self.receivable_account
        sub2 = self.env["subscription.subscription"].create({
            "partner_id": partner2.id,
            "plan_id": self.plan.id,
            "start_date": date.today(),
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": 1,
                "price_unit": 100,
            })],
        })

        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.subscription.next_invoice_date = date.today()

        sub2.action_confirm()
        sub2.action_activate()
        sub2.next_invoice_date = date.today()

        # Failing prepare invoice on subscription 1
        sub1_id = self.subscription.id
        original_prepare = type(self.subscription)._prepare_invoice

        def failing_prepare(record, period_start, period_end):
            if record.id == sub1_id:
                raise UserError("Simulated configuration error for subscription 1")
            return original_prepare(record, period_start, period_end)

        with patch.object(type(self.subscription), "_prepare_invoice", failing_prepare):
            self.env["subscription.subscription"]._cron_generate_invoices()

        # Verify sub2 succeeded despite subscription 1 failing
        sub2_period = self.env["subscription.billing.period"].search([
            ("subscription_id", "=", sub2.id),
        ])
        self.assertEqual(len(sub2_period), 1)
        self.assertEqual(sub2_period.state, "invoiced")
        self.assertTrue(sub2_period.invoice_id)
        self.assertEqual(sub2_period.invoice_id.state, "posted")

    def test_repeated_cron_execution_is_idempotent(self):
        self.subscription.action_confirm()
        self.subscription.action_activate()
        self.subscription.next_invoice_date = date.today()

        # Run cron first time
        self.env["subscription.subscription"]._cron_generate_invoices()
        invoices_1 = self.env["account.move"].search([("invoice_origin", "=", self.subscription.name)])
        self.assertEqual(len(invoices_1), 1)

        # Run cron second time immediately
        self.env["subscription.subscription"]._cron_generate_invoices()
        invoices_2 = self.env["account.move"].search([("invoice_origin", "=", self.subscription.name)])
        self.assertEqual(len(invoices_2), 1)

    def test_product_specific_discount_isolation(self):
        product_b = self.env["product.product"].create({
            "name": "Brightloop Addon",
            "list_price": 200,
            "type": "service",
        })
        product_b.product_tmpl_id.property_account_income_id = self.income_account

        discount_a = self.env["subscription.discount"].create({
            "name": "Product A Only 20%",
            "discount_type": "percentage",
            "discount_value": 20,
            "product_ids": [(6, 0, self.product.ids)],
        })

        sub = self.env["subscription.subscription"].create({
            "partner_id": self.partner.id,
            "plan_id": self.plan.id,
            "start_date": date.today(),
            "line_ids": [
                (0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": 100}),
                (0, 0, {"product_id": product_b.id, "quantity": 1, "price_unit": 200}),
            ],
            "discount_ids": [(6, 0, discount_a.ids)],
        })

        line_vals = sub._prepare_discounted_line_values()
        vals_by_prod = {v["product_id"]: v for v in line_vals}

        # Product A should have 20% discount
        self.assertEqual(vals_by_prod[self.product.id]["discount"], 20)
        self.assertEqual(vals_by_prod[self.product.id]["price_unit"], 100)

        # Product B should NOT have any discount
        self.assertEqual(vals_by_prod[product_b.id]["discount"], 0)
        self.assertEqual(vals_by_prod[product_b.id]["price_unit"], 200)

        # Verify amount_untaxed
        self.assertEqual(sub.amount_untaxed, 80 + 200)

    def test_fixed_discount_boundaries_and_capped_to_line(self):
        discount_excess = self.env["subscription.discount"].create({
            "name": "Excess Fixed Discount",
            "discount_type": "fixed",
            "discount_value": 150,
            "product_ids": [(6, 0, self.product.ids)],
        })

        sub = self.env["subscription.subscription"].create({
            "partner_id": self.partner.id,
            "plan_id": self.plan.id,
            "start_date": date.today(),
            "line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": 100})],
            "discount_ids": [(6, 0, discount_excess.ids)],
        })

        line_vals = sub._prepare_discounted_line_values()
        # Price should be 0, not negative
        self.assertEqual(line_vals[0]["price_unit"], 0)
        self.assertEqual(sub.amount_untaxed, 0)

    def test_fixed_discount_distributed_across_subscription(self):
        product_b = self.env["product.product"].create({
            "name": "Brightloop Standard",
            "list_price": 100,
            "type": "service",
        })
        product_b.product_tmpl_id.property_account_income_id = self.income_account

        global_fixed_discount = self.env["subscription.discount"].create({
            "name": "Global 40 Off",
            "discount_type": "fixed",
            "discount_value": 40,
        })

        sub = self.env["subscription.subscription"].create({
            "partner_id": self.partner.id,
            "plan_id": self.plan.id,
            "start_date": date.today(),
            "line_ids": [
                (0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": 100}),
                (0, 0, {"product_id": product_b.id, "quantity": 1, "price_unit": 100}),
            ],
            "discount_ids": [(6, 0, global_fixed_discount.ids)],
        })

        line_vals = sub._prepare_discounted_line_values()
        for val in line_vals:
            self.assertEqual(val["price_unit"], 80)
        self.assertEqual(sub.amount_untaxed, 160)

    def test_missing_income_account_raises_user_error(self):
        product_no_account = self.env["product.product"].create({
            "name": "Unconfigured Product",
            "list_price": 50,
            "type": "service",
        })
        product_no_account.product_tmpl_id.property_account_income_id = False
        product_no_account.categ_id.property_account_income_categ_id = False

        self.income_account.deprecated = True
        try:
            sub = self.env["subscription.subscription"].create({
                "partner_id": self.partner.id,
                "plan_id": self.plan.id,
                "start_date": date.today(),
                "line_ids": [(0, 0, {"product_id": product_no_account.id, "quantity": 1, "price_unit": 50})],
            })
            with self.assertRaises(UserError) as err:
                sub._prepare_invoice(date.today(), date.today())
            self.assertIn("No income account found", str(err.exception))
        finally:
            self.income_account.deprecated = False
