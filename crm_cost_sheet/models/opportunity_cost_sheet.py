from odoo import models, fields, api

class OpportunityCostSheet(models.Model):
    _name = 'opportunity.cost.sheet'
    _description = 'Opportunity Cost Sheet'

    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    product_id = fields.Many2one('product.product', string='Product')
    quantity = fields.Float(string='Quantity')
    for_price = fields.Float(string='For Price')
    margin = fields.Float(string='Margin (%)')
    sale_price = fields.Float(string='Sale Price', compute='_compute_sale_price')

    @api.depends('for_price', 'margin')
    def _compute_sale_price(self):
        for record in self:
            record.sale_price = record.for_price * (1 + record.margin / 100.0)
