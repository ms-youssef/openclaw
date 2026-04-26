# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class TenderOpenBiddingWizard(models.TransientModel):
    _name = 'tender.open.bidding.wizard'
    _description = 'Open Tender Live Bidding'

    requisition_id = fields.Many2one('purchase.requisition', required=True)
    duration_minutes = fields.Integer(default=60, required=True)

    def action_open_bidding(self):
        self.ensure_one()
        if self.duration_minutes <= 0:
            raise UserError(_('Duration must be positive.'))
        self.requisition_id.action_start_bidding(self.duration_minutes)
        return {'type': 'ir.actions.act_window_close'}
