from odoo import models, fields

class CRMLead(models.Model):
    _inherit = 'crm.lead'

    opportunity_cost_sheet_ids = fields.One2many('opportunity.cost.sheet', 'opportunity_id', string='Cost Sheet')
    
    def action_create_quotation(self):
        # Sample logic for transferring data to a new quotation
        quotation_vals = []
        for line in self.opportunity_cost_sheet_ids:
            quotation_vals.append({
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'price_unit': line.sale_price
            })
        # Assume sale_order is the model for quotations
        self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'order_line': [(0, 0, vals) for vals in quotation_vals]
        })
        return True  # Replace with actual call to super() if needed