{
    'name': 'CRM Cost Sheet',
    'version': '1.0',
    'depends': ['crm', 'sale_crm', 'product'],
    'data': [
        'views/crm_lead_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
}