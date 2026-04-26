# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    is_online_tender = fields.Boolean(string='Online Tender', tracking=True)
    online_state = fields.Selection([
        ('draft', 'Draft'),
        ('invited', 'Invited'),
        ('quote_entry', 'Quote Entry'),
        ('bidding_open', 'Live Bidding'),
        ('awarded', 'Awarded'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    vendor_partner_ids = fields.Many2many('res.partner', 'purchase_requisition_tender_vendor_rel', 'requisition_id', 'partner_id', string='Vendor Partners')
    bidding_duration_minutes = fields.Integer(default=60)
    bidding_start_at = fields.Datetime(readonly=True)
    bidding_end_at = fields.Datetime(readonly=True)
    invitation_ids = fields.One2many('tender.invitation', 'requisition_id', string='Tender Invitations')
    winning_invitation_id = fields.Many2one('tender.invitation', readonly=True, copy=False)

    def action_send_invitations(self):
        template = self.env.ref('online_tender.mail_template_tender_invitation', raise_if_not_found=False)
        for requisition in self:
            if not requisition.is_online_tender:
                raise UserError(_('Enable Online Tender before sending invitations.'))
            if not requisition.line_ids:
                raise UserError(_('Add at least one product line before inviting vendors.'))
            if not requisition.vendor_partner_ids:
                raise UserError(_('Add at least one vendor partner.'))
            for partner in requisition.vendor_partner_ids:
                invitation = requisition.invitation_ids.filtered(lambda item: item.partner_id == partner)[:1]
                if not invitation:
                    invitation = self.env['tender.invitation'].create({
                        'requisition_id': requisition.id,
                        'partner_id': partner.id,
                        'state': 'sent',
                    })
                else:
                    invitation.state = 'sent'
                if template:
                    template.sudo().send_mail(invitation.id, force_send=True)
            requisition.online_state = 'invited'
            requisition.message_post(body=_('Online tender invitations were sent to %s vendors.') % len(requisition.vendor_partner_ids))

    def action_open_bidding(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Open Live Bidding'),
            'res_model': 'tender.open.bidding.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_requisition_id': self.id, 'default_duration_minutes': self.bidding_duration_minutes or 60},
        }

    def action_start_bidding(self, duration_minutes=60):
        template = self.env.ref('online_tender.mail_template_tender_live_bidding_open', raise_if_not_found=False)
        now = fields.Datetime.now()
        for requisition in self:
            if not requisition.invitation_ids:
                raise UserError(_('Send invitations before opening live bidding.'))
            if not requisition.invitation_ids.filtered(lambda invitation: invitation.active_bid_id):
                raise UserError(_('At least one vendor must submit a quote before live bidding.'))
            requisition.write({
                'online_state': 'bidding_open',
                'bidding_duration_minutes': duration_minutes,
                'bidding_start_at': now,
                'bidding_end_at': now + timedelta(minutes=duration_minutes),
            })
            requisition.invitation_ids.filtered(lambda item: item.state in ('sent', 'submitted')).write({'state': 'live'})
            for invitation in requisition.invitation_ids:
                if template:
                    template.sudo().send_mail(invitation.id, force_send=True)
            requisition.message_post(body=_('Live bidding opened for %s minutes.') % duration_minutes)

    def action_close_bidding(self):
        for requisition in self:
            requisition._close_bidding()

    def _close_bidding(self):
        self.ensure_one()
        if self.online_state not in ('bidding_open', 'invited', 'quote_entry'):
            return
        active_invitations = self.invitation_ids.filtered(lambda invitation: invitation.active_bid_id)
        if not active_invitations:
            self.online_state = 'awarded'
            self.message_post(body=_('Online tender closed with no submitted bids.'))
            return
        self.env['tender.bid.line'].search([('requisition_id', '=', self.id)]).write({'is_winner': False})
        best_line_tag = self.env.ref('online_tender.tender_tag_best_on_line', raise_if_not_found=False)
        winner_tag = self.env.ref('online_tender.tender_tag_winner', raise_if_not_found=False)
        best_overall_tag = self.env.ref('online_tender.tender_tag_best_overall', raise_if_not_found=False)
        did_not_win_tag = self.env.ref('online_tender.tender_tag_did_not_win', raise_if_not_found=False)
        for requisition_line in self.line_ids:
            candidate_lines = active_invitations.mapped('active_bid_id.line_ids').filtered(lambda line: line.requisition_line_id == requisition_line)
            if candidate_lines:
                winning_line = min(candidate_lines, key=lambda line: line.price_unit)
                winning_line.is_winner = True
                if best_line_tag:
                    winning_line.invitation_id.tag_ids = [(4, best_line_tag.id)]
        winning_invitation = min(active_invitations, key=lambda invitation: invitation.total_amount)
        self.winning_invitation_id = winning_invitation
        for invitation in self.invitation_ids:
            if invitation == winning_invitation:
                invitation.state = 'won'
                if winner_tag:
                    invitation.tag_ids = [(4, winner_tag.id)]
                if best_overall_tag:
                    invitation.tag_ids = [(4, best_overall_tag.id)]
            else:
                invitation.state = 'lost'
                if did_not_win_tag:
                    invitation.tag_ids = [(4, did_not_win_tag.id)]
        self.online_state = 'awarded'
        self.message_post(body=_('%s won the online tender with total %s.') % (winning_invitation.partner_id.display_name, winning_invitation.total_amount))

    @api.model
    def _cron_close_expired_biddings(self):
        expired = self.search([
            ('is_online_tender', '=', True),
            ('online_state', '=', 'bidding_open'),
            ('bidding_end_at', '<=', fields.Datetime.now()),
        ])
        for requisition in expired:
            requisition._close_bidding()

    @api.constrains('bidding_duration_minutes')
    def _check_bidding_duration_minutes(self):
        for requisition in self:
            if requisition.bidding_duration_minutes <= 0:
                raise ValidationError(_('Bidding duration must be positive.'))
