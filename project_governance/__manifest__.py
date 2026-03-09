{
    'name': 'Project Governance',
    'version': '1.0',
    'category': 'Operations/Project',
    'summary': 'Multi-Stage Project Governance with Budget Control',
    'description': """
        This module introduces a governed stage-gate methodology for Odoo Projects:
        - Mandatory approval gates for stage transitions.
        - Deliverable tracking per stage.
        - Budget monitoring (Planned vs. Actual).
    """,
    'depends': ['project', 'hr_timesheet'],
    'data': [
        'security/project_governance_security.xml',
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
        'views/project_task_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
    'author': 'Mohamed Youssef',
}
