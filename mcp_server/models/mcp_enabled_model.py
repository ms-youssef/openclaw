# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

_BINARY_TYPES = ('binary',)
_NON_READABLE_TYPES = ('binary',)


class McpEnabledModel(models.Model):
    _name = 'mcp.enabled.model'
    _description = 'MCP Enabled Model'
    _rec_name = 'model_id'
    _order = 'model_name'

    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        required=True,
        ondelete='cascade',
    )
    model_name = fields.Char(
        related='model_id.model',
        string='Technical Name',
        store=True,
        index=True,
    )
    description = fields.Text(
        string='Description',
        help="Surfaced to the MCP bridge and on to the AI client as the tool "
             "description, so it influences how the LLM picks tools.",
    )
    allow_search = fields.Boolean(string='Allow Search', default=True)
    allow_read = fields.Boolean(string='Allow Read', default=True)
    allow_create = fields.Boolean(string='Allow Create', default=False)
    allow_write = fields.Boolean(string='Allow Write', default=False)
    allow_unlink = fields.Boolean(string='Allow Unlink', default=False)
    allowed_field_ids = fields.Many2many(
        'ir.model.fields',
        string='Allowed Fields',
        domain="[('model_id', '=', model_id)]",
        help="If empty, every readable non-binary stored field is allowed.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('model_uniq', 'unique(model_id)',
         'Only one MCP configuration per model is allowed.'),
    ]

    def _operation_field(self, op):
        return {
            'search': 'allow_search',
            'read': 'allow_read',
            'create': 'allow_create',
            'write': 'allow_write',
            'unlink': 'allow_unlink',
        }.get(op)

    def _check_operation(self, op):
        self.ensure_one()
        flag = self._operation_field(op)
        if not flag or not self[flag]:
            raise AccessError(_(
                "Operation '%(op)s' is not allowed for model '%(model)s' via MCP.",
                op=op, model=self.model_name,
            ))

    def _all_default_fields(self):
        self.ensure_one()
        Model = self.env[self.model_name]
        names = []
        for name, field in Model._fields.items():
            if field.type in _NON_READABLE_TYPES:
                continue
            if not field.store and not field.related:
                continue
            names.append(name)
        return names

    def _allowed_field_names(self):
        self.ensure_one()
        if self.allowed_field_ids:
            return self.allowed_field_ids.mapped('name')
        return self._all_default_fields()

    def _filter_fields(self, requested):
        self.ensure_one()
        allowed = set(self._allowed_field_names())
        if not requested:
            return list(allowed)
        return [name for name in requested if name in allowed]

    def _filter_values(self, values):
        self.ensure_one()
        if not isinstance(values, dict):
            return {}
        allowed = set(self._allowed_field_names())
        return {k: v for k, v in values.items() if k in allowed}

    @api.model
    def _resolve(self, model_name):
        return self.search([
            ('model_name', '=', model_name),
            ('active', '=', True),
        ], limit=1)
