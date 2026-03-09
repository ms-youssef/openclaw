{
    'name': 'CRM Cost Sheet',
    'version': '1.0',
    'depends': ['crm'],
    'application': False,
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
}