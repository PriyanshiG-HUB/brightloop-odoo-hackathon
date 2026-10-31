
{
    "name": "Brightloop Subscription Management",
    "version": "17.0.1.0.0",
    "category": "Sales/Subscriptions",
    "summary": "Subscription plans, lifecycle management and recurring billing",
    "license": "LGPL-3",

    "depends": [
        "account",
        "portal",
        "sale_management",
    ],

    "data": [
        # Security
        "security/security.xml",
        "security/ir.model.access.csv",

        # Data
        "data/sequence.xml",
        "data/cron.xml",

        # Views and actions must load before menus
        "views/product_views.xml",
        "views/customer_views.xml",
        "views/plan_views.xml",
        "views/quotation_views.xml",
        "views/subscription_views.xml",
        "views/discount_views.xml",
        "views/dashboard_views.xml",

        # Menus load after all referenced actions
        "views/menu_views.xml",
    ],

    "demo": [],

    "installable": True,
    "application": True,
}
