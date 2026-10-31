from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class BrightloopPortal(CustomerPortal):
    @http.route("/my/brightloop/subscriptions", type="http", auth="user", website=True)
    def portal_subscriptions(self, **kwargs):
        subscriptions = request.env["subscription.subscription"].search([
            ("partner_id", "=", request.env.user.partner_id.id),
        ])
        return request.render("brightloop_subscription.portal_subscriptions", {
            "subscriptions": subscriptions,
        })

    @http.route("/my/brightloop/invoices", type="http", auth="user", website=True)
    def portal_invoices(self, **kwargs):
        invoices = request.env["account.move"].search([
            ("partner_id", "=", request.env.user.partner_id.id),
            ("move_type", "=", "out_invoice"),
        ])
        return request.render("brightloop_subscription.portal_invoices", {
            "invoices": invoices,
        })

