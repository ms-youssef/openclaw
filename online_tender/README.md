# Online Tender

Vendor portal RFQ submission with live competitive bidding for Odoo 19 Enterprise.

## Requirements

- Odoo 19 Enterprise.
- The Enterprise `purchase_requisition` addon installed and available.
- The custom addons directory containing `online_tender` included in `addons_path`.
- Outgoing email configured if vendor invitation emails should be sent.

## Install

Copy or keep this module inside an Odoo addons directory, for example:

```bash
/home/user/openclaw/online_tender
```

Make sure the parent directory is in `addons_path`:

```ini
addons_path = /path/to/odoo/addons,/path/to/enterprise,/home/user/openclaw
```

Restart Odoo, update the apps list, then install the module:

```bash
odoo-bin -c /path/to/odoo.conf -d <db_name> -u online_tender --stop-after-init
```

Or from the UI:

1. Apps > Update Apps List.
2. Search for `Online Tender`.
3. Install.

## Access

Assign internal buyers to:

- `Online Tender / User` for day-to-day tender operation.
- `Online Tender / Manager` for tag management and token regeneration.

Portal vendors only need a portal user if they will use `/my/tenders`. Public token links work without login.

## First Tender

1. Open Purchase > Purchase Agreements.
2. Create a new purchase agreement.
3. Enable `Online Tender`.
4. Add product lines.
5. Add vendors in `Vendor Partners`.
6. Click `Send Invitations`.
7. Vendors use the emailed `/tender/<id>/<token>` links to submit quotes.
8. Click `Open Live Bidding`, choose a duration, and confirm.
9. Vendors use the live page to adjust prices.
10. Click `Close Bidding`, or wait for the cron to close expired bidding windows.

The module does not create purchase orders automatically and does not email award results.

## Vendor Privacy

Live bidding JSON only returns each vendor's own price and relative delta percentages. Competitor names and competitor absolute prices are not included in portal responses.

## Test

Run on an Odoo 19 Enterprise environment:

```bash
odoo-bin -c /path/to/odoo.conf -d <db_name> --test-enable --stop-after-init -i online_tender
```
