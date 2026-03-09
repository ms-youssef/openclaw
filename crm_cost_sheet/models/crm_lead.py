from odoo import models, fields

class CRMLead(models.Model):
    _inherit = 'crm.lead'

    global_margin_percent = fields.Float(string='Global Margin (%)')
    cost_sheet_line_ids = fields.One2many('crm.lead.cost.line', 'lead_id', string='Cost Sheet Lines')

    def action_create_quotation(self):
        SaleOrder = self.env['sale.order']
        for lead in self:
            if not lead.cost_sheet_line_ids:
                continue
            order_vals = {
                'partner_id': lead.partner_id.id,
                'opportunity_id': lead.id
            }
            order = SaleOrder.create(order_vals)
            for line in lead.cost_sheet_line_ids:
                order_line_vals = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'price_unit': line.sale_price,
                    'order_id': order.id
                }
                self.env['sale.order.line'].create(order_line_vals)
            lead.write({'sale_order_ids': [(4, order.id)]})