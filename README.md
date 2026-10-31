# Brightloop Subscription Management System

Brightloop is an Odoo 17 Community hackathon project for managing recurring
software subscriptions. It provides an Odoo addon for plans, subscriptions,
recurring billing periods, native customer invoices, discounts, access control,
portal views, and an operational dashboard.

This repository is prepared for local team development with Docker Compose.
Each teammate should use their own local PostgreSQL volume and Odoo database;
local databases and credentials must not be shared through Git.

## Problem and proposed solution

Software businesses need one workflow from product and plan setup through
subscription activation, recurring invoicing, payment tracking, and customer
self-service. Brightloop keeps that workflow inside Odoo's native ORM,
Sales, Accounting, Portal, and PostgreSQL integrations instead of introducing
a second billing or payment database.

## Current implementation status

### Implemented and Verified in the Addon

- **Subscription Plans:** Daily, weekly, monthly, and yearly recurring periods with configurable minimum order quantities and lifecycle flags (allow_pause, allow_cancel, allow_renewal, auto_close).
- **Subscription Lifecycle:** Draft, Quotation, Confirmed, Active, Paused, Closed, and Cancelled state transitions.
- **Native Sales Quotations:** Submitting a subscription creates and links an Odoo `sale.order` quotation with the customer, company, currency, payment terms, origin, products, quantities, descriptions, taxes, and eligible discounts. Existing quotations are reused to prevent duplicates.
- **Quotation Recovery:** Confirmed subscriptions without a linked Sales quotation can use **Generate Quotation**. The linked `sale_order_id` is visible and clickable when present.
- **Quotation Workflow & Templates:** Reusable `subscription.quotation.template` presets with validity dates, product onchange pricing/taxes, and one-click conversion to subscriptions via `action_convert_to_subscription()`.
- **Pricing & Variants:** Service products with brand attributes and dynamic variant extra pricing (e.g. +).
- **Subscription Lines:** Product, quantity, unit price, taxes, line discounts, currency, and computed subtotal with positive-quantity and 0–100% discount validation.
- **Discounts Engine:** Product-scoped fixed and percentage discounts with date, amount, quantity, and usage-limit eligibility checks. Fixed discounts are distributed across applicable lines and discount usage is incremented only after successful invoice posting.
- **Automated Recurring Invoicing:** Idempotent billing-period engine (`subscription.billing.period`) with dynamic Odoo 17 income-account and company sales-journal resolution, tax-inclusive totals, and transaction savepoints for failure resilience.
- **Idempotency Guarantee:** Unique compound SQL constraint unique(subscription_id, period_start, period_end) prevents duplicate invoices under repeated or concurrent execution.
- **Customer Portal Self-Service:** Customer portal integration on `/my`, breadcrumbs, subscription list, and subscription detail view (`/my/brightloop/subscriptions/<id>`) with pause, resume, cancel, renewal, billing-period, and invoice access.
- **JSON API:** `/api/v1` endpoints for authentication, user registration/profile, password reset requests, products, plans, customers, subscriptions, and quotations, with Brightloop staff/admin access checks for protected management operations.
- **High-Performance Executive Dashboard:** PostgreSQL SQL-aggregated MRR, ARR, operational status counts, and cash flow receivables executing in <50ms.
- **Security & Multi-Company:** Brightloop administrator, internal staff, and portal access groups; multi-company record rules; customer data isolation; and raw-password complexity validation for user creation, password changes, password resets, and explicit password updates.
- **Automated Test Suite:** 28 Odoo transaction tests covering billing, quotation creation/reuse/recovery, lifecycle, discounts, taxes, variants, portal permissions, dashboard aggregation, template tax propagation, and password validation.

### Planned or not fully runtime-verified

- Payment collection and reconciliation continue to use native Odoo Accounting; Brightloop does not implement a separate payment gateway.
- End-to-end customer portal journeys and every API endpoint should be rechecked in each teammate's local database before production use.
- Production deployment, email delivery, external payment integration, and load testing are outside the current local Docker setup.

## Technology stack

| Area | Technology |
|---|---|
| ERP | Odoo 17 Community |
| Backend | Python and Odoo ORM |
| UI | Odoo XML views and native web client |
| Accounting | Native Odoo Accounting |
| Sales | Native Odoo Sales |
| Portal | Native Odoo Portal controllers/templates |
| Database | PostgreSQL 16 |
| Local runtime | Docker Compose |
| Host examples | Windows 10/11 with Docker Desktop |

## Architecture

The custom addon is `brightloop_subscription`. It extends a native Odoo
database rather than duplicating native business records:

- `res.partner` and `res.users` provide customers and authentication.
- `product.product` provides subscription products and variants.
- `account.tax` provides tax configuration.
- `sale.order` provides native Sales quotations and confirmations generated from subscriptions.
- `account.move` provides customer invoices.
- `account.payment` and Odoo reconciliation provide payment state.
- Custom models store plans, subscriptions, lines, discounts, billing periods,
  and dashboard metrics.

The daily cron calls `subscription.subscription._cron_generate_invoices()`. It
finds due active subscriptions, creates or retries one
`subscription.billing.period` record, creates and posts one native invoice,
increments eligible discount usage after successful posting, and advances
`next_invoice_date`. The billing-period unique constraint is the
duplicate-billing boundary.

For a manual developer or administrator action, call
`subscription.subscription._generate_invoice()` on an active subscription with
`next_invoice_date` set. The normal user workflow is to activate the
subscription and let the scheduled action run; there is no separate manual
invoice button on the subscription form.

## Repository structure

```text
.
├── addons/
│   └── brightloop_subscription/
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── controllers/        # Portal and JSON API routes
│       ├── data/               # Sequence and scheduled action
│       ├── models/             # Plans, lines, quotations, billing, discounts
│       ├── security/           # Groups, record rules, model access CSV
│       ├── tests/              # Odoo transaction tests
│       └── views/              # Forms, trees, actions, menus, dashboard, portal XML
├── docs/                       # Architecture, schema, demo, audit, security notes
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Prerequisites

Install the following on Windows:

1. Git for Windows.
2. Docker Desktop with the Linux container engine enabled.
3. Internet access to pull the official `odoo:17.0` and `postgres:16` images.

The Compose stack supplies Python, Odoo, and PostgreSQL. A local Python
installation is not required to run the application. Python 3.14 and `lxml`
are used only for optional repository validation in this workspace.

## Clone the repository using Windows CMD

```cmd
git clone https://github.com/PriyanshiG-HUB/brightloop-odoo-hackathon.git
cd brightloop-odoo-hackathon
git switch main
```

If Git reports that `main` is already checked out after cloning, continue.
Confirm the configured remote with:

```cmd
git remote -v
git branch --show-current
```

## Configure local environment

Copy the safe template and edit the local password:

```cmd
copy .env.example .env
notepad .env
```

`.env.example` contains placeholders only. `.env` is ignored by Git and must
never be committed. The supported variables are:

| Variable | Purpose | Example placeholder |
|---|---|---|
| `POSTGRES_DB` | Initial PostgreSQL database name | `postgres` |
| `POSTGRES_USER` | PostgreSQL application user | `odoo` |
| `POSTGRES_PASSWORD` | Local PostgreSQL password | `change-this-local-password` |
| `ODOO_PORT` | Host port mapped to Odoo port 8069 | `8069` |

Use a different local password for each teammate. Do not copy a teammate's
`.env` file or database volume.

## Start the Docker environment

All commands in this section are Windows CMD-compatible:

```cmd
docker compose config --quiet
docker compose up -d
docker compose ps
```

The services are:

| Compose service | Image | Purpose | Port |
|---|---|---|---|
| `db` | `postgres:16` | PostgreSQL database | Internal 5432 |
| `odoo` | `odoo:17.0` | Odoo web/application server | Host 8069 to container 8069 |

The addon directory is mounted read-only into the Odoo container at
`/mnt/extra-addons`. Named volumes `postgres-data` and `odoo-data` persist
local database and Odoo filestore data.

Open the Odoo web interface at:

```text
http://localhost:8069
```

## Create and configure an Odoo database

1. Open `http://localhost:8069`.
2. On the database manager page, select **Create Database**.
3. Enter a local database name such as `brightloop_dev`.
4. Enter an administrator email and password for that Odoo database.
5. Select the appropriate language and country.
6. Finish database creation and sign in.
7. Enable developer mode from the Odoo settings menu.
8. Open **Apps**, select **Update Apps List**, and search for
   **Brightloop Subscription Management**.
9. Install the addon.
10. Add users to **Brightloop Administrator** or **Brightloop Internal Staff**
    under the user's access rights.

Database creation is local to the running teammate's PostgreSQL volume. It does
not create or modify another teammate's database.

## Logs, restart, and rebuild

Use the Compose service names, not hard-coded generated container names:

```cmd
docker compose logs -f odoo
docker compose logs -f db
docker compose restart odoo
docker compose restart db
docker compose up -d --force-recreate odoo
docker compose down
docker compose up -d
```

The normal development loop is:

1. Edit files under `addons\brightloop_subscription`.
2. Restart Odoo:

   ```cmd
   docker compose restart odoo
   ```

3. In Odoo, update the Apps list and upgrade the Brightloop module when XML,
   security, data, or model changes require it.

To reset the local environment completely, including local databases and
filestore, use the destructive command only when intentional:

```cmd
docker compose down -v
docker compose up -d
```

Never use `down -v` on a teammate's or production database.

## Validation and tests

Available static validation includes:

```cmd
python -m compileall addons\brightloop_subscription
```

If `lxml` is installed:

```cmd
python -c "from pathlib import Path; from lxml import etree; files=list(Path('addons/brightloop_subscription').glob('**/*.xml')); [etree.parse(str(path)) for path in files]; print(f'Validated {len(files)} XML files')"
```

For the Docker Odoo 17 environment, run the addon upgrade and transaction tests
without changing the long-running web port:

```cmd
docker compose exec -T odoo sh -c "odoo -d brightloop --update=brightloop_subscription --test-enable --stop-after-init --http-port=8070 --db_host=db --db_port=5432 --db_user=$USER --db_password=$PASSWORD --log-level=test"
```

On Windows CMD, `$USER` and `$PASSWORD` are expanded inside the container by
the shell invoked by `sh -c`; alternatively use the values from the running
container configuration. Runtime claims should be based on actual command
output. The repository contains Odoo transaction tests, but a full test run
requires the Odoo runtime, PostgreSQL database, and installed native
dependencies.

## Troubleshooting

### Docker engine is unavailable

Start Docker Desktop and wait for the Linux engine to become ready:

```cmd
docker version
docker compose ps
```

If the server section of `docker version` is unavailable, Compose cannot start
the services.

### Odoo image pull is slow or incomplete

Check Docker Hub connectivity and retry:

```cmd
docker pull odoo:17.0
docker pull postgres:16
docker compose up -d
```

### PostgreSQL is unhealthy

Inspect the database logs and readiness:

```cmd
docker compose logs db
docker compose exec db pg_isready -U odoo -d postgres
```

Confirm that `.env` contains a non-empty `POSTGRES_PASSWORD`, then recreate the
stack if the local volume was initialized with incorrect credentials:

```cmd
docker compose down -v
docker compose up -d
```

### Odoo cannot connect to PostgreSQL

Check that `db` is healthy and that the Odoo service uses the same credentials:

```cmd
docker compose ps
docker compose logs odoo
```

Do not change the database host to `localhost`; inside Compose, Odoo reaches
PostgreSQL using the service name `db`.

### The Brightloop app is not visible

Confirm the addon mount and update the Apps list in developer mode:

```cmd
docker compose exec odoo sh -c "ls -la /mnt/extra-addons/brightloop_subscription"
docker compose logs odoo
```

The module manifest must remain at
`addons\brightloop_subscription\__manifest__.py`. Upgrade or reinstall the
module after changing XML, security, or model definitions.

### XML or module installation errors

Read the first traceback in the Odoo log. Common causes include invalid XML,
duplicate external IDs, a missing manifest dependency, or a reference to an
action that loads later than its menu. Validate XML before restarting and keep
manifest data files ordered so referenced actions load before menus.

### Port 8069 is already in use

Change `ODOO_PORT` in `.env`, for example to `8070`, then recreate Odoo:

```cmd
docker compose up -d --force-recreate odoo
```

Open the corresponding host port, such as `http://localhost:8070`.

## Git collaboration workflow

The repository uses one shared branch: `main`. Do not create feature,
development, release, or force-pushed branches for this project.

Before starting work:

```cmd
git switch main
git pull --rebase origin main
git status
```

After completing a focused change:

```cmd
git diff --check
git add <files-you-changed>
git commit -m "type: concise description"
git pull --rebase origin main
git push origin main
```

If the remote contains work that is not present locally, stop and coordinate
before pushing. Never use `git push --force`. Never stage `.env`, Docker
volumes, database dumps, logs, or generated caches.

## Contribution guidelines

- Preserve native Odoo architecture and reuse native Accounting, Sales, Portal,
  products, partners, taxes, invoices, and payments.
- Passwords supplied through user creation, password changes, reset flows, or
  explicit password updates must contain more than eight characters, one
  uppercase letter, one lowercase letter, and one special character.
- Keep changes focused and avoid modifying unrelated business logic.
- Inspect the relevant model, view, security rule, and manifest before editing.
- Validate Python syntax and every addon XML file before committing.
- Test changes in each developer's own local Odoo database.
- Document any feature that is planned or not runtime-verified.
- Review `git diff --check` and `git status --short --untracked-files=all`
  before staging.
- Never commit credentials, private keys, local database files, or `.env`.

## Contributors and team status

The checked-out Git history identifies **PriyanshiG-HUB** as the verified
repository author. Add additional contributor names only after confirming them
from GitHub or committed repository history.

## License

The addon manifest declares the LGPL-3 license. Confirm project-level licensing
requirements with the team before distributing the repository.
