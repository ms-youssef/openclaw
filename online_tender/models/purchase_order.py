# -*- coding: utf-8 -*-

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    online_tender_requisition_id = fields.Many2one('purchase.requisition', string='Online Tender', readonly=True, copy=False)
    online_tender_invitation_id = fields.Many2one('tender.invitation', string='Tender Invitation', readonly=True, copy=False)
    online_tender_tag_ids = fields.Many2many('tender.tag', 'purchase_order_tender_tag_rel', 'order_id', 'tag_id', string='Tender Tags', readonly=True, copy=False)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    tender_delivery_days = fields.Integer(string='Tender Delivery Time (Days)', readonly=True, copy=False)
    tender_technical_approved = fields.Boolean(string='Tender Technical Approved', readonly=True, copy=False)
    tender_technical_notes = fields.Text(string='Tender Technical Notes', readonly=True, copy=False)
