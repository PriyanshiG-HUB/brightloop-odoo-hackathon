import werkzeug
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.addons.portal.controllers.portal import CustomerPortal


class BrightloopPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        if "subscription_count" in counters:
            values["subscription_count"] = (
                request.env["subscription.subscription"].search_count([
                    ("partner_id", "=", partner.id),
                ])
                if partner
                else 0
            )
        if "quotation_count" in counters:
            values["quotation_count"] = (
                request.env["subscription.quotation"].search_count([
                    ("partner_id", "=", partner.id),
                ])
                if partner
                else 0
            )
        return values

    def _get_portal_subscription(self, sub_id):
        partner = request.env.user.partner_id
        subscription = request.env["subscription.subscription"].search([
            ("id", "=", sub_id),
            ("partner_id", "=", partner.id),
        ], limit=1)
        return subscription

    @http.route("/my/brightloop/subscriptions", type="http", auth="user", website=True)
    def portal_subscriptions(self, search="", **kwargs):
        partner = request.env.user.partner_id
        domain = [("partner_id", "=", partner.id)]
        if search:
            domain.extend([
                "|",
                ("name", "ilike", search),
                ("plan_id.name", "ilike", search),
            ])
        subscriptions = request.env["subscription.subscription"].search(
            domain, order="create_date desc"
        )
        return request.render("brightloop_subscription.portal_subscriptions", {
            "subscriptions": subscriptions,
            "page_name": "brightloop_subscription",
            "search": search,
        })

    @http.route("/my/brightloop/subscriptions/<int:sub_id>", type="http", auth="user", website=True)
    def portal_subscription_detail(self, sub_id, error=None, success=None, **kwargs):
        subscription = self._get_portal_subscription(sub_id)
        if not subscription:
            raise werkzeug.exceptions.NotFound()

        billing_periods = subscription.billing_period_ids.sorted(
            key=lambda p: (p.period_start or ""), reverse=True
        )
        invoices = subscription.invoice_ids.sorted(
            key=lambda m: (m.invoice_date or ""), reverse=True
        )

        return request.render("brightloop_subscription.portal_subscription_detail", {
            "subscription": subscription,
            "billing_periods": billing_periods,
            "invoices": invoices,
            "page_name": "brightloop_subscription_detail",
            "error_message": error,
            "success_message": success,
        })

    @http.route("/my/brightloop/subscriptions/<int:sub_id>/pause", type="http", auth="user", methods=["POST", "GET"], website=True, csrf=False)
    def portal_subscription_pause(self, sub_id, **kwargs):
        subscription = self._get_portal_subscription(sub_id)
        if not subscription:
            raise werkzeug.exceptions.NotFound()

        try:
            if not subscription.plan_id.allow_pause:
                raise UserError(_("Pausing is not allowed for your subscription plan."))
            if subscription.state != "active":
                raise UserError(_("Only active subscriptions can be paused."))
            subscription.sudo().action_pause()
            msg = "Subscription paused successfully."
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?success={msg}")
        except (UserError, ValidationError, AccessError) as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error={e.args[0]}")
        except Exception as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error=Unable+to+pause+subscription")

    @http.route("/my/brightloop/subscriptions/<int:sub_id>/resume", type="http", auth="user", methods=["POST", "GET"], website=True, csrf=False)
    def portal_subscription_resume(self, sub_id, **kwargs):
        subscription = self._get_portal_subscription(sub_id)
        if not subscription:
            raise werkzeug.exceptions.NotFound()

        try:
            if subscription.state != "paused":
                raise UserError(_("Only paused subscriptions can be resumed."))
            subscription.sudo().action_resume()
            msg = "Subscription resumed successfully."
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?success={msg}")
        except (UserError, ValidationError, AccessError) as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error={e.args[0]}")
        except Exception as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error=Unable+to+resume+subscription")

    @http.route("/my/brightloop/subscriptions/<int:sub_id>/cancel", type="http", auth="user", methods=["POST", "GET"], website=True, csrf=False)
    def portal_subscription_cancel(self, sub_id, **kwargs):
        subscription = self._get_portal_subscription(sub_id)
        if not subscription:
            raise werkzeug.exceptions.NotFound()

        try:
            if not subscription.plan_id.allow_cancel:
                raise UserError(_("Cancellation is not allowed for your subscription plan."))
            if subscription.state in ("closed", "cancelled"):
                raise UserError(_("Subscription is already %s.") % subscription.state)
            subscription.sudo().action_cancel()
            msg = "Subscription cancelled successfully."
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?success={msg}")
        except (UserError, ValidationError, AccessError) as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error={e.args[0]}")
        except Exception as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error=Unable+to+cancel+subscription")

    @http.route("/my/brightloop/subscriptions/<int:sub_id>/renew", type="http", auth="user", methods=["POST", "GET"], website=True, csrf=False)
    def portal_subscription_renew(self, sub_id, **kwargs):
        subscription = self._get_portal_subscription(sub_id)
        if not subscription:
            raise werkzeug.exceptions.NotFound()

        try:
            if not subscription.plan_id.allow_renewal:
                raise UserError(_("Renewal is not allowed for your subscription plan."))
            subscription.sudo().action_renew()
            msg = "Subscription renewed successfully."
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?success={msg}")
        except (UserError, ValidationError, AccessError) as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error={e.args[0]}")
        except Exception as e:
            return request.redirect(f"/my/brightloop/subscriptions/{sub_id}?error=Unable+to+renew+subscription")

    @http.route("/my/brightloop/invoices", type="http", auth="user", website=True)
    def portal_invoices(self, **kwargs):
        invoices = request.env["account.move"].search([
            ("partner_id", "=", request.env.user.partner_id.id),
            ("move_type", "=", "out_invoice"),
        ], order="invoice_date desc")
        return request.render("brightloop_subscription.portal_invoices", {
            "invoices": invoices,
            "page_name": "brightloop_invoices",
        })
