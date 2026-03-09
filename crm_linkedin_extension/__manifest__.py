{
    'name': 'CRM LinkedIn Extension',
    'version': '1.0',
    'category': 'Sales/CRM',
    'summary': 'Add LinkedIn fields to CRM Leads',
    'description': """
        This module extends the CRM Lead form view to include:
        - LinkedIn Profile (Contact)
        - Company LinkedIn
    """,
    'depends': ['crm'],
    'data': [
        'views/crm_lead_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
