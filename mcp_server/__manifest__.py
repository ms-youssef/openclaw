{
    'name': 'MCP Server',
    'version': '1.0',
    'category': 'Technical',
    'summary': 'Expose Odoo to AI assistants via the Model Context Protocol',
    'description': """
        Server-side half of the MCP Server for Odoo. Lets an external MCP bridge
        (e.g. mcp-server-odoo run via uvx on the AI client) read and write Odoo
        records through the Model Context Protocol:
        - Configurable per-model exposure (search / read / create / write / unlink)
        - Optional per-field allowlist per model
        - Authenticates with Odoo's native API Keys; calls run with that user's ACLs
    """,
    'author': 'Mohamed Youssef',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/mcp_server_security.xml',
        'security/ir.model.access.csv',
        'views/mcp_server_menus.xml',
        'views/mcp_enabled_model_views.xml',
        'data/mcp_default_models.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
