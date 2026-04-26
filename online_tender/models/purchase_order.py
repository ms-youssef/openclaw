# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    online_tender_requisition_id = fields.Many2one('purchase.requisition', string='Online Tender', readonly=True, copy=False)
    online_tender_invitation_id = fields.Many2one('tender.invitation', string='Tender Invitation', readonly=True, copy=False)
    online_tender_tag_ids = fields.Many2many('tender.tag', 'purchase_order_tender_tag_rel', 'order_id', 'tag_id', string='Tender Tags', readonly=True, copy=False)
    online_tender_technical_state = fields.Selection([
        ('pending', 'Pending Technical Approval'),
        ('approved', 'Technically Approved'),
        ('rejected', 'Technically Rejected'),
    ], default='pending', tracking=True, copy=False)

    def write(self, vals):
        result = super().write(vals)
        if 'online_tender_technical_state' in vals:
            for order in self.filtered('online_tender_invitation_id'):
                order._sync_technical_state_to_tender_bid(vals['online_tender_technical_state'])
        return result

    def action_online_tender_approve_technical(self):
        self._set_online_tender_technical_state('approved')

    def action_online_tender_reject_technical(self):
        self._set_online_tender_technical_state('rejected')

    def action_online_tender_reset_technical(self):
        self._set_online_tender_technical_state('pending')

    def _set_online_tender_technical_state(self, technical_state):
        for order in self:
            order._check_online_tender_rfq()
            order.online_tender_technical_state = technical_state
            order.order_line.write({'tender_technical_approved': technical_state == 'approved'})
            if technical_state == 'approved':
                order.message_post(body=_('Technical offer approved for online tender.'))
                order.online_tender_requisition_id.message_post(
                    body=_('Technical offer approved for %s.') % order.partner_id.display_name
                )
            elif technical_state == 'rejected':
                order.message_post(body=_('Technical offer rejected for online tender.'))
                order.online_tender_requisition_id.message_post(
                    body=_('Technical offer rejected for %s. This vendor will be excluded from live bidding.') % order.partner_id.display_name
                )
            else:
                order.message_post(body=_('Technical offer reset to pending review.'))

    def _check_online_tender_rfq(self):
        self.ensure_one()
        if not self.online_tender_invitation_id:
            raise UserError(_('This RFQ is not linked to an online tender invitation.'))

    def _sync_technical_state_to_tender_bid(self, technical_state):
        self.ensure_one()
        bid = self.online_tender_invitation_id.active_bid_id
        if not bid:
            return
        bid.line_ids.write({'technical_status': technical_state})


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    tender_delivery_days = fields.Integer(string='Tender Delivery Time (Days)', readonly=True, copy=False)
    tender_technical_approved = fields.Boolean(string='Tender Technical Approved', readonly=True, copy=False)
    tender_technical_notes = fields.Text(string='Tender Technical Notes', readonly=True, copy=False)
