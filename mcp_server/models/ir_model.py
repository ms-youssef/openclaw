# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IrModel(models.Model):
    _inherit = 'ir.model'

    mcp_enabled = fields.Boolean(
        string='Exposed via MCP',
        compute='_compute_mcp_enabled',
        inverse='_inverse_mcp_enabled',
        search='_search_mcp_enabled',
    )

    def _compute_mcp_enabled(self):
        Enabled = self.env['mcp.enabled.model'].sudo()
        existing = Enabled.with_context(active_test=False).search([
            ('model_id', 'in', self.ids),
        ])
        active_by_model = {rec.model_id.id: rec.active for rec in existing}
        for record in self:
            record.mcp_enabled = active_by_model.get(record.id, False)

    def _inverse_mcp_enabled(self):
        Enabled = self.env['mcp.enabled.model'].sudo()
        for record in self:
            existing = Enabled.with_context(active_test=False).search([
                ('model_id', '=', record.id),
            ], limit=1)
            if record.mcp_enabled:
                if existing:
                    if not existing.active:
                        existing.active = True
                else:
                    Enabled.create({'model_id': record.id})
            elif existing and existing.active:
                existing.active = False

    def _search_mcp_enabled(self, operator, value):
        Enabled = self.env['mcp.enabled.model'].sudo()
        active = Enabled.search([]).mapped('model_id').ids
        if operator in ('=', '!=') and isinstance(value, bool):
            wants_enabled = (operator == '=' and value) or (operator == '!=' and not value)
            return [('id', 'in' if wants_enabled else 'not in', active)]
        return [('id', 'in', active)]
