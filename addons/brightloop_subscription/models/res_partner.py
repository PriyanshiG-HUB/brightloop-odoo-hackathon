import re
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    subscription_count = fields.Integer(
        string="Subscriptions",
        compute="_compute_subscription_count",
    )

    def _compute_subscription_count(self):
        Subscription = self.env["subscription.subscription"]
        for partner in self:
            partner.subscription_count = Subscription.search_count([
                ("partner_id", "=", partner.id)
            ])

    @api.constrains("email", "company_id")
    def _check_unique_customer_email(self):
        for partner in self:
            if partner.email:
                domain = [
                    ("email", "=ilike", partner.email.strip()),
                    ("id", "!=", partner.id),
                    ("customer_rank", ">", 0),
                ]
                if partner.company_id:
                    domain.append(("company_id", "in", [False, partner.company_id.id]))
                existing = self.search(domain, limit=1)
                if existing and partner.customer_rank > 0:
                    raise ValidationError(
                        _("A customer with email '%s' already exists.") % partner.email
                    )

    def action_view_subscriptions(self):
        self.ensure_one()
        return {
            "name": _("Subscriptions"),
            "type": "ir.actions.act_window",
            "res_model": "subscription.subscription",
            "view_mode": "tree,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.constrains("password")
    def _check_password_complexity(self):
        for user in self:
            if not user.password:
                continue
            pwd = user.password
            # Password validation: more than eight characters, uppercase, lowercase, and special character
            if len(pwd) <= 8:
                raise ValidationError(
                    _("Password must be more than 8 characters long.")
                )
            if not re.search(r"[A-Z]", pwd):
                raise ValidationError(
                    _("Password must contain at least one uppercase letter.")
                )
            if not re.search(r"[a-z]", pwd):
                raise ValidationError(
                    _("Password must contain at least one lowercase letter.")
                )
            if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\\/\[\]~`\-+=;]", pwd):
                raise ValidationError(
                    _("Password must contain at least one special character.")
                )
