# -*- coding: utf-8 -*-
{
    'name': 'Online Tender',
    'version': '1.0',
    'category': 'Inventory/Purchase',
    'summary': 'Vendor portal RFQ submission with live competitive bidding',
    'description': """
        Vendor-facing online RFQ system with real-time competitive bidding:
        - Purchasing agents create RFQs, invite vendors, receive price quotes.
        - Vendors access quotes via secure portal link (signed-in or anonymous token).
        - Live bidding window allows vendors to adjust prices in real-time.
        - Each vendor sees only their pricing delta vs. best competitor (+/- %).
        - System awards winners, notifies agent via chatter.
    """,
    'author': 'Mohamed Youssef',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'portal',
        'purchase_requisition',
    ],
    'data': [
        'security/online_tender_security.xml',
        'security/ir.model.access.csv',
        'data/tender_tags.xml',
        'data/mail_templates.xml',
        'data/ir_cron.xml',
        'wizards/tender_open_bidding_wizard_views.xml',
        'views/tender_tag_views.xml',
        'views/tender_bid_views.xml',
        'views/tender_invitation_views.xml',
        'views/purchase_requisition_views.xml',
        'views/online_tender_menus.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'online_tender/static/src/js/live_bidding.js',
            'online_tender/static/src/scss/live_bidding.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
