from datetime import date, timedelta
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBrightloopCoreModules(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 1. Product & Variants
        cls.product_tmpl = cls.env["product.template"].create({
            "name": "Cloud Storage",
            "detailed_type": "service",
            "list_price": 50,
            "standard_price": 20,
            "brand": "BrightCloud",
            "description": "Scalable cloud storage for businesses",
        })
        cls.product = cls.product_tmpl.product_variant_ids[0]
        cls.product.variant_extra_price = 15.0

        # 2. Plan
        cls.plan = cls.env["subscription.plan"].create({
            "name": "Cloud Pro Plan",
            "product_id": cls.product.id,
            "price": 65,
            "billing_period": "monthly",
            "minimum_quantity": 2,
            "allow_pause": True,
            "allow_early_close": True,
            "allow_renewal": True,
            "allow_cancel": True,
        })

        # 3. Customer
        cls.customer = cls.env["res.partner"].create({
            "name": "Acme Global",
            "email": "contact@acmeglobal.test",
            "phone": "+1 555 0199",
            "street": "123 Market St",
            "city": "Metropolis",
            "customer_rank": 1,
        })

    def test_01_product_and_variant_pricing(self):
        """Test product creation, brand attribute and variant extra price."""
        self.assertEqual(self.product_tmpl.brand, "BrightCloud")
        self.assertEqual(self.product.variant_extra_price, 15.0)

    def test_02_plan_creation_and_availability(self):
        """Test plan creation, billing period, and status computation."""
        self.assertEqual(self.plan.billing_period, "monthly")
        self.assertEqual(self.plan.minimum_quantity, 2)
        self.assertEqual(self.plan.availability_status, "available")
        self.assertTrue(self.plan.allow_cancel)

    def test_03_customer_creation_and_duplicate_prevention(self):
        """Test customer record creation and email duplicate constraint."""
        self.assertEqual(self.customer.email, "contact@acmeglobal.test")
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Acme Imposter",
                "email": "contact@acmeglobal.test",
                "customer_rank": 1,
            })

    def test_04_subscription_creation_and_lifecycle(self):
        """Test subscription lines, line totals, cancellation, and pause/resume."""
        product2 = self.env["product.product"].create({
            "name": "Add-on Compute",
            "list_price": 30,
            "type": "service",
        })
        subscription = self.env["subscription.subscription"].create({
            "partner_id": self.customer.id,
            "plan_id": self.plan.id,
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 2,
                    "price_unit": 65,
                    "discount": 0,
                }),
                (0, 0, {
                    "product_id": product2.id,
                    "quantity": 2,
                    "price_unit": 30,
                    "discount": 10,
                }),
            ],
        })
        # Check totals: (2*65) + (2*30*0.9) = 130 + 54 = 184
        self.assertEqual(subscription.amount_untaxed, 184.0)
        self.assertEqual(subscription.amount_total, 184.0)
        self.assertTrue(subscription.name.startswith("BL/SUB/"))

        # Lifecycle transitions
        subscription.action_submit_quotation()
        self.assertEqual(subscription.state, "quotation")
        subscription.action_confirm()
        self.assertEqual(subscription.state, "confirmed")
        subscription.action_activate()
        self.assertEqual(subscription.state, "active")
        subscription.action_pause()
        self.assertEqual(subscription.state, "paused")
        subscription.action_resume()
        self.assertEqual(subscription.state, "active")
        subscription.action_cancel()
        self.assertEqual(subscription.state, "cancelled")

    def test_05_quotation_and_conversion(self):
        """Test quotation template, quotation creation, and conversion into subscription."""
        template = self.env["subscription.quotation.template"].create({
            "name": "Standard Enterprise Template",
            "plan_id": self.plan.id,
            "validity_days": 15,
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 3,
                    "price_unit": 65,
                })
            ],
        })
        self.assertEqual(template.validity_days, 15)

        quotation = self.env["subscription.quotation"].create({
            "partner_id": self.customer.id,
            "template_id": template.id,
            "plan_id": self.plan.id,
            "quotation_date": date.today(),
            "validity_date": date.today() + timedelta(days=15),
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 3,
                    "price_unit": 65,
                })
            ],
        })
        self.assertEqual(quotation.state, "draft")
        self.assertTrue(quotation.name.startswith("BL/QUO/"))
        self.assertEqual(quotation.amount_total, 195.0)

        # Cannot convert unless accepted
        with self.assertRaises(UserError):
            quotation.action_convert_to_subscription()

        quotation.action_send()
        self.assertEqual(quotation.state, "sent")
        quotation.action_accept()
        self.assertEqual(quotation.state, "accepted")

        # Convert to subscription
        action = quotation.action_convert_to_subscription()
        self.assertTrue(quotation.subscription_id)
        self.assertEqual(quotation.subscription_id.id, action["res_id"])
        sub = quotation.subscription_id
        self.assertEqual(sub.partner_id.id, self.customer.id)
        self.assertEqual(sub.plan_id.id, self.plan.id)
        self.assertEqual(sub.amount_total, 195.0)
        self.assertEqual(len(sub.line_ids), 1)
        self.assertEqual(sub.line_ids[0].quantity, 3)

    def test_06_password_validation(self):
        """Test password complexity requirement enforcement."""
        # Valid password (8+ chars, upper, lower, special)
        valid_user = self.env["res.users"].create({
            "name": "Staff Alice",
            "login": "alice@brightloop.test",
            "password": "SecurePassword123!",
        })
        self.assertEqual(valid_user.login, "alice@brightloop.test")

        # Too short
        with self.assertRaises(ValidationError):
            self.env["res.users"].create({
                "name": "Short",
                "login": "short@brightloop.test",
                "password": "Ab1!",
            })

        # Missing uppercase
        with self.assertRaises(ValidationError):
            self.env["res.users"].create({
                "name": "NoUpper",
                "login": "noupper@brightloop.test",
                "password": "securepassword123!",
            })

        # Missing special character
        with self.assertRaises(ValidationError):
            self.env["res.users"].create({
                "name": "NoSpecial",
                "login": "nospecial@brightloop.test",
                "password": "SecurePassword123",
            })


    def test_07_dashboard_sql_aggregation(self):
        """Test subscription dashboard SQL KPI computation."""
        dashboard = self.env["subscription.dashboard"].create({"name": "Test Dashboard"})
        sub = self.env["subscription.subscription"].create({
            "partner_id": self.customer.id,
            "plan_id": self.plan.id,
            "state": "active",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 2,
                    "price_unit": 65,
                })
            ],
        })
        self.assertEqual(sub.state, "active")

        dashboard._compute_metrics()
        self.assertGreaterEqual(dashboard.total_subscriptions, 1)
        self.assertGreaterEqual(dashboard.active_subscriptions, 1)
        self.assertGreaterEqual(dashboard.total_customers, 1)
        self.assertGreaterEqual(dashboard.monthly_recurring_revenue, 130.0)
        self.assertGreaterEqual(dashboard.annual_recurring_revenue, 130.0 * 12.0)

    def test_08_subscription_portal_permissions_and_helpers(self):
        """Test portal helper methods and lifecycle transitions."""
        sub = self.env["subscription.subscription"].create({
            "partner_id": self.customer.id,
            "plan_id": self.plan.id,
            "state": "active",
            "line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 1,
                    "price_unit": 65,
                })
            ],
        })
        self.assertEqual(sub.state, "active")

        sub.action_pause()
        self.assertEqual(sub.state, "paused")
        sub.action_resume()
        self.assertEqual(sub.state, "active")

        self.assertEqual(sub.invoice_count, 0)
        self.assertEqual(len(sub.invoice_ids), 0)
        action = sub.action_view_invoices()
        self.assertEqual(action["type"], "ir.actions.act_window")
