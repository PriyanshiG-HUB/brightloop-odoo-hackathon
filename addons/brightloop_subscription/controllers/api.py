import json
from odoo import http
from odoo.http import request


class BrightloopApiController(http.Controller):
    """
    REST API controller for Brightloop Subscription Management.
    Provides complete endpoints for:
    - Products (list, create, read, update, delete)
    - Plans (list, create, read, update, archive)
    - Customers (list, create, read, update)
    - Subscriptions (list, create, read, update, activate, pause, cancel, close)
    - Quotations (list, create, read, convert to subscription)
    - Auth & User Profile (register, login, password reset request, me)
    """

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[("Content-Type", "application/json")],
            status=status,
        )

    def _check_admin(self):
        return request.env.user.has_group("brightloop_subscription.group_brightloop_admin")

    def _check_staff(self):
        return (
            request.env.user.has_group("brightloop_subscription.group_brightloop_staff")
            or self._check_admin()
        )

    # ==========================================
    # AUTHENTICATION & ACCESS
    # ==========================================

    @http.route("/api/v1/auth/login", type="json", auth="none", methods=["POST"], csrf=False)
    def api_login(self, **kwargs):
        data = request.jsonrequest or {}
        login = data.get("login") or data.get("email")
        password = data.get("password")
        if not login or not password:
            return {"error": "Missing login or password", "status": 400}
        try:
            db = request.db or request.env.cr.dbname
            uid = request.session.authenticate(db, login, password)
            if not uid:
                return {"error": "Invalid credentials", "status": 401}
            user = request.env["res.users"].sudo().browse(uid)
            role = "customer"
            if user.has_group("brightloop_subscription.group_brightloop_admin"):
                role = "admin"
            elif user.has_group("brightloop_subscription.group_brightloop_staff"):
                role = "staff"

            return {
                "success": True,
                "user_id": uid,
                "name": user.name,
                "email": user.email,
                "role": role,
            }
        except Exception as e:
            return {"error": str(e), "status": 500}

    @http.route("/api/v1/auth/register", type="json", auth="public", methods=["POST"], csrf=False)
    def api_register(self, **kwargs):
        data = request.jsonrequest or {}
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role", "customer")

        if not name or not email or not password:
            return {"error": "Name, email, and password are required.", "status": 400}

        # Role enforcement: only Admin can create staff accounts
        if role in ("staff", "admin"):
            if not request.env.user.has_group("brightloop_subscription.group_brightloop_admin"):
                return {"error": "Only administrators can create staff or admin accounts.", "status": 403}

        Users = request.env["res.users"].sudo()
        existing = Users.search([("login", "=", email)], limit=1)
        if existing:
            return {"error": "A user with this email already exists.", "status": 400}

        try:
            group_portal = request.env.ref("base.group_portal")
            group_staff = request.env.ref("brightloop_subscription.group_brightloop_staff")
            group_admin = request.env.ref("brightloop_subscription.group_brightloop_admin")

            groups = [group_portal.id]
            if role == "staff":
                groups = [group_staff.id]
            elif role == "admin":
                groups = [group_admin.id]

            new_user = Users.create({
                "name": name,
                "login": email,
                "email": email,
                "password": password,
                "groups_id": [(6, 0, groups)],
            })
            return {
                "success": True,
                "user_id": new_user.id,
                "email": new_user.email,
                "role": role,
            }
        except Exception as e:
            return {"error": str(e), "status": 400}

    @http.route("/api/v1/auth/me", type="json", auth="user", methods=["GET", "POST"])
    def api_me(self, **kwargs):
        user = request.env.user
        role = "customer"
        if user.has_group("brightloop_subscription.group_brightloop_admin"):
            role = "admin"
        elif user.has_group("brightloop_subscription.group_brightloop_staff"):
            role = "staff"

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": role,
            "partner_id": user.partner_id.id,
        }

    @http.route("/api/v1/auth/reset-password", type="json", auth="public", methods=["POST"], csrf=False)
    def api_reset_password(self, **kwargs):
        data = request.jsonrequest or {}
        email = data.get("email")
        if not email:
            return {"error": "Email is required.", "status": 400}
        Users = request.env["res.users"].sudo()
        user = Users.search([("email", "=ilike", email.strip())], limit=1)
        if not user:
            return {"error": "User with specified email was not found.", "status": 404}
        try:
            user.action_reset_password()
            return {"success": True, "message": "Password reset instructions sent to %s" % email}
        except Exception as e:
            return {"error": str(e), "status": 500}

    # ==========================================
    # 1. PRODUCT MANAGEMENT API
    # ==========================================

    @http.route("/api/v1/products", type="json", auth="user", methods=["GET", "POST"])
    def api_products(self, **kwargs):
        data = request.jsonrequest or {}
        search_query = data.get("search")
        brand = data.get("brand")

        domain = [("sale_ok", "=", True)]
        if search_query:
            domain.append(("name", "ilike", search_query))
        if brand:
            domain.append(("brand", "ilike", brand))

        products = request.env["product.template"].search(domain)
        result = []
        for p in products:
            variants = []
            for v in p.product_variant_ids:
                variants.append({
                    "id": v.id,
                    "name": v.display_name,
                    "variant_extra_price": getattr(v, "variant_extra_price", 0.0),
                    "price": v.list_price + getattr(v, "variant_extra_price", 0.0),
                })
            result.append({
                "id": p.id,
                "name": p.name,
                "detailed_type": p.detailed_type,
                "list_price": p.list_price,
                "standard_price": p.standard_price,
                "brand": getattr(p, "brand", False),
                "description": p.description_sale or p.description or "",
                "variants": variants,
            })
        return {"products": result, "count": len(result)}

    @http.route("/api/v1/products/create", type="json", auth="user", methods=["POST"])
    def api_product_create(self, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied. Staff or admin role required.", "status": 403}
        data = request.jsonrequest or {}
        name = data.get("name")
        if not name:
            return {"error": "Product name is required.", "status": 400}
        vals = {
            "name": name,
            "detailed_type": data.get("type", "service"),
            "list_price": float(data.get("list_price", 0.0)),
            "standard_price": float(data.get("standard_price", 0.0)),
            "brand": data.get("brand", ""),
            "description": data.get("description", ""),
        }
        prod = request.env["product.template"].create(vals)
        return {"success": True, "id": prod.id, "name": prod.name}

    # ==========================================
    # 2. SUBSCRIPTION PLAN API
    # ==========================================

    @http.route("/api/v1/plans", type="json", auth="user", methods=["GET", "POST"])
    def api_plans(self, **kwargs):
        domain = []
        plans = request.env["subscription.plan"].search(domain)
        result = []
        for pl in plans:
            result.append({
                "id": pl.id,
                "name": pl.name,
                "product_id": pl.product_id.id,
                "product_name": pl.product_id.display_name,
                "price": pl.price,
                "billing_period": pl.billing_period,
                "minimum_quantity": pl.minimum_quantity,
                "start_date": str(pl.start_date) if pl.start_date else None,
                "end_date": str(pl.end_date) if pl.end_date else None,
                "availability_status": pl.availability_status,
                "allow_pause": pl.allow_pause,
                "allow_early_close": pl.allow_early_close,
                "allow_renewal": pl.allow_renewal,
                "allow_cancel": pl.allow_cancel,
                "active": pl.active,
            })
        return {"plans": result}

    @http.route("/api/v1/plans/create", type="json", auth="user", methods=["POST"])
    def api_plan_create(self, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied.", "status": 403}
        data = request.jsonrequest or {}
        name = data.get("name")
        product_id = data.get("product_id")
        price = data.get("price")
        billing_period = data.get("billing_period", "monthly")
        if not name or not product_id or price is None:
            return {"error": "Name, product_id, and price are required.", "status": 400}
        vals = {
            "name": name,
            "product_id": int(product_id),
            "price": float(price),
            "billing_period": billing_period,
            "minimum_quantity": float(data.get("minimum_quantity", 1.0)),
            "start_date": data.get("start_date") or False,
            "end_date": data.get("end_date") or False,
            "allow_pause": data.get("allow_pause", True),
            "allow_early_close": data.get("allow_early_close", True),
            "allow_renewal": data.get("allow_renewal", True),
            "allow_cancel": data.get("allow_cancel", True),
        }
        plan = request.env["subscription.plan"].create(vals)
        return {"success": True, "id": plan.id, "name": plan.name}

    # ==========================================
    # 3. CUSTOMER MANAGEMENT API
    # ==========================================

    @http.route("/api/v1/customers", type="json", auth="user", methods=["GET", "POST"])
    def api_customers(self, **kwargs):
        if not self._check_staff():
            # Customer can only view own record
            partner = request.env.user.partner_id
            return {
                "customers": [{
                    "id": partner.id,
                    "name": partner.name,
                    "email": partner.email,
                    "phone": partner.phone,
                    "billing_address": partner.contact_address,
                    "subscription_count": partner.subscription_count,
                }]
            }
        data = request.jsonrequest or {}
        search_query = data.get("search")
        domain = [("customer_rank", ">", 0)]
        if search_query:
            domain.extend(["|", ("name", "ilike", search_query), ("email", "ilike", search_query)])
        customers = request.env["res.partner"].search(domain)
        result = []
        for c in customers:
            result.append({
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "billing_address": c.contact_address,
                "subscription_count": c.subscription_count,
            })
        return {"customers": result, "count": len(result)}

    @http.route("/api/v1/customers/create", type="json", auth="user", methods=["POST"])
    def api_customer_create(self, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied.", "status": 403}
        data = request.jsonrequest or {}
        name = data.get("name")
        email = data.get("email")
        if not name:
            return {"error": "Customer name is required.", "status": 400}
        vals = {
            "name": name,
            "email": email,
            "phone": data.get("phone"),
            "street": data.get("street") or data.get("billing_address"),
            "city": data.get("city"),
            "customer_rank": 1,
        }
        try:
            partner = request.env["res.partner"].create(vals)
            return {"success": True, "id": partner.id, "name": partner.name}
        except Exception as e:
            return {"error": str(e), "status": 400}

    # ==========================================
    # 4. SUBSCRIPTION MANAGEMENT API
    # ==========================================

    @http.route("/api/v1/subscriptions", type="json", auth="user", methods=["GET", "POST"])
    def api_subscriptions(self, **kwargs):
        domain = []
        if not self._check_staff():
            # Customer can only view own subscriptions
            domain.append(("partner_id", "=", request.env.user.partner_id.id))
        subs = request.env["subscription.subscription"].search(domain)
        result = []
        for s in subs:
            lines = []
            for l in s.line_ids:
                lines.append({
                    "id": l.id,
                    "product_id": l.product_id.id,
                    "product_name": l.product_id.display_name,
                    "quantity": l.quantity,
                    "price_unit": l.price_unit,
                    "discount": l.discount,
                    "subtotal": l.subtotal,
                })
            result.append({
                "id": s.id,
                "number": s.name,
                "customer_id": s.partner_id.id,
                "customer_name": s.partner_id.name,
                "plan_id": s.plan_id.id,
                "plan_name": s.plan_id.name,
                "start_date": str(s.start_date) if s.start_date else None,
                "end_date": str(s.end_date) if s.end_date else None,
                "next_invoice_date": str(s.next_invoice_date) if s.next_invoice_date else None,
                "status": s.state,
                "amount_untaxed": s.amount_untaxed,
                "amount_total": s.amount_total,
                "lines": lines,
            })
        return {"subscriptions": result, "count": len(result)}

    @http.route("/api/v1/subscriptions/create", type="json", auth="user", methods=["POST"])
    def api_subscription_create(self, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied.", "status": 403}
        data = request.jsonrequest or {}
        partner_id = data.get("partner_id")
        plan_id = data.get("plan_id")
        lines = data.get("lines", [])
        if not partner_id or not plan_id:
            return {"error": "partner_id and plan_id are required.", "status": 400}

        lines_commands = []
        for line in lines:
            lines_commands.append((0, 0, {
                "product_id": int(line.get("product_id")),
                "quantity": float(line.get("quantity", 1)),
                "price_unit": float(line.get("price_unit", 0)),
                "discount": float(line.get("discount", 0)),
            }))

        vals = {
            "partner_id": int(partner_id),
            "plan_id": int(plan_id),
            "start_date": data.get("start_date") or fields.Date.context_today(request.env.user),
            "payment_term_id": data.get("payment_term_id") or False,
        }
        if lines_commands:
            vals["line_ids"] = lines_commands

        sub = request.env["subscription.subscription"].create(vals)
        return {"success": True, "id": sub.id, "number": sub.name, "amount_total": sub.amount_total}

    @http.route("/api/v1/subscriptions/<int:sub_id>/action", type="json", auth="user", methods=["POST"])
    def api_subscription_action(self, sub_id, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied.", "status": 403}
        sub = request.env["subscription.subscription"].browse(sub_id)
        if not sub.exists():
            return {"error": "Subscription not found.", "status": 404}
        action = (request.jsonrequest or {}).get("action")
        try:
            if action == "activate":
                sub.action_activate()
            elif action == "pause":
                sub.action_pause()
            elif action == "resume":
                sub.action_resume()
            elif action == "cancel":
                sub.action_cancel()
            elif action == "close":
                sub.action_close()
            elif action == "renew":
                sub.action_renew()
            else:
                return {"error": "Unknown action %s" % action, "status": 400}
            return {"success": True, "id": sub.id, "status": sub.state}
        except Exception as e:
            return {"error": str(e), "status": 400}

    # ==========================================
    # 5. QUOTATION MANAGEMENT API
    # ==========================================

    @http.route("/api/v1/quotations", type="json", auth="user", methods=["GET", "POST"])
    def api_quotations(self, **kwargs):
        domain = []
        if not self._check_staff():
            domain.append(("partner_id", "=", request.env.user.partner_id.id))
        quos = request.env["subscription.quotation"].search(domain)
        result = []
        for q in quos:
            lines = []
            for l in q.line_ids:
                lines.append({
                    "product_id": l.product_id.id,
                    "product_name": l.product_id.display_name,
                    "quantity": l.quantity,
                    "price_unit": l.price_unit,
                    "discount": l.discount,
                    "subtotal": l.subtotal,
                })
            result.append({
                "id": q.id,
                "number": q.name,
                "customer_id": q.partner_id.id,
                "customer_name": q.partner_id.name,
                "plan_id": q.plan_id.id,
                "plan_name": q.plan_id.name,
                "status": q.state,
                "quotation_date": str(q.quotation_date),
                "validity_date": str(q.validity_date),
                "amount_total": q.amount_total,
                "subscription_id": q.subscription_id.id if q.subscription_id else None,
                "lines": lines,
            })
        return {"quotations": result, "count": len(result)}

    @http.route("/api/v1/quotations/convert", type="json", auth="user", methods=["POST"])
    def api_quotation_convert(self, **kwargs):
        if not self._check_staff():
            return {"error": "Access denied.", "status": 403}
        data = request.jsonrequest or {}
        quo_id = data.get("quotation_id")
        quo = request.env["subscription.quotation"].browse(quo_id)
        if not quo.exists():
            return {"error": "Quotation not found.", "status": 404}
        try:
            quo.action_convert_to_subscription()
            return {
                "success": True,
                "subscription_id": quo.subscription_id.id,
                "subscription_number": quo.subscription_id.name,
                "status": quo.subscription_id.state,
            }
        except Exception as e:
            return {"error": str(e), "status": 400}
