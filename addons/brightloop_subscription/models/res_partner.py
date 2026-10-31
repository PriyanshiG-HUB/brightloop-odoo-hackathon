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

    @staticmethod
    def _validate_password(password):
        if not password:
            raise ValidationError(_("Password must not be empty."))
        if len(password) <= 8:
            raise ValidationError(_("Password must be more than 8 characters long."))
        if not re.search(r"[A-Z]", password):
            raise ValidationError(_("Password must contain at least one uppercase letter."))
        if not re.search(r"[a-z]", password):
            raise ValidationError(_("Password must contain at least one lowercase letter."))
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\\/\[\]~`\-+=;]", password):
            raise ValidationError(_("Password must contain at least one special character."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "password" in vals:
                self._validate_password(vals["password"])
        return super().create(vals_list)

    def write(self, vals):
        if "password" in vals:
            password = vals["password"]
            if not password or self._crypt_context().identify(password) == "plaintext":
                self._validate_password(password)
        return super().write(vals)

    def _change_password(self, new_passwd):
        self._validate_password(new_passwd.strip() if new_passwd else new_passwd)
        return super()._change_password(new_passwd)

    def _set_new_password(self):
        for user in self:
            if user.new_password:
                self._validate_password(user.new_password)
        return super()._set_new_password()
