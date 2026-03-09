from odoo import models, fields, api

class CRMCostLine(models.Model):
    _name = 'crm.lead.cost.line'

    lead_id = fields.Many2one('crm.lead', string='Lead')
    product_id = fields.Many2one('product.product', string='Product')
    quantity = fields.Float(string='Quantity')
    cost_price = fields.Float(string='Cost Price', readonly=True, compute='_compute_cost_price')
    sale_price = fields.Float(string='Sale Price', compute='_compute_sale_price')
    margin_percent = fields.Float(string='Margin (%)')

    @api.depends('product_id')
    def _compute_cost_price(self):
        for line in self:
            line.cost_price = line.product_id.standard_price

    @api.depends('cost_price', 'margin_percent')
    def _compute_sale_price(self):
        for line in self:
            line.sale_price = line.cost_price * (1 + line.margin_percent / 100)