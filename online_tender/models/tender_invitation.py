# -*- coding: utf-8 -*-

import secrets

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TenderInvitation(models.Model):
    _name = 'tender.invitation'
    _description = 'Tender Invitation'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, default=lambda self: _('New Tender Invitation'))
    requisition_id = fields.Many2one('purchase.requisition', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('submitted', 'Submitted'),
        ('live', 'Live'),
        ('closed', 'Closed'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ], default='draft', required=True, tracking=True, index=True)
    bid_ids = fields.One2many('tender.bid', 'invitation_id', string='Bid History')
    active_bid_id = fields.Many2one('tender.bid', compute='_compute_active_bid_id', inverse='_inverse_active_bid_id', store=True)
    technical_passed = fields.Boolean(compute='_compute_technical_passed', store=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Draft RFQ', readonly=True, copy=False)
    purchase_order_technical_state = fields.Selection(
        related='purchase_order_id.online_tender_technical_state',
        string='RFQ Technical State',
        store=True,
    )
    tag_ids = fields.Many2many('tender.tag', 'tender_invitation_tag_rel', 'invitation_id', 'tag_id', string='Tags')
    total_amount = fields.Monetary(related='active_bid_id.total_amount', currency_field='currency_id', store=True)
    currency_id = fields.Many2one(related='requisition_id.currency_id', store=True)
    access_url = fields.Char(compute='_compute_access_url')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('requisition_partner_unique', 'unique(requisition_id, partner_id)', 'Each vendor can only be invited once per tender.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('access_token'):
                vals['access_token'] = secrets.token_urlsafe(32)
        invitations = super().create(vals_list)
        for invitation in invitations.filtered(lambda item: item.name == _('New Tender Invitation')):
            invitation.name = '%s - %s' % (invitation.requisition_id.name, invitation.partner_id.display_name)
        return invitations

    @api.depends('bid_ids.is_active')
    def _compute_active_bid_id(self):
        for invitation in self:
            invitation.active_bid_id = invitation.bid_ids.filtered('is_active')[:1]

    def _inverse_active_bid_id(self):
        for invitation in self:
            if invitation.active_bid_id:
                invitation.bid_ids.filtered(lambda bid: bid != invitation.active_bid_id).write({'is_active': False})
                invitation.active_bid_id.is_active = True

    @api.depends(
        'active_bid_id',
        'active_bid_id.line_ids',
        'active_bid_id.line_ids.technical_status',
        'purchase_order_id.online_tender_technical_state',
    )
    def _compute_technical_passed(self):
        for invitation in self:
            if invitation.purchase_order_id:
                invitation.technical_passed = invitation.purchase_order_id.online_tender_technical_state == 'approved'
                continue
            lines = invitation.active_bid_id.line_ids
            invitation.technical_passed = bool(lines) and all(line.technical_status == 'approved' for line in lines)

    def _compute_access_url(self):
        for invitation in self:
            invitation.access_url = '/my/tenders/%s' % invitation.id

    def _get_token_url(self):
        self.ensure_one()
        return '/tender/%s/%s' % (self.id, self.access_token)

    def action_regenerate_token(self):
        for invitation in self:
            invitation.access_token = secrets.token_urlsafe(32)

    def action_view_portal(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.access_url,
            'target': 'self',
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Draft RFQ'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
            'target': 'current',
        }

    def action_submit_quote(self, line_values, submission_kind='initial'):
        self.ensure_one()
        if submission_kind == 'initial' and self.requisition_id.online_state in ('bidding_open', 'awarded', 'cancelled'):
            raise UserError(_('Quote entry is closed for this tender.'))
        self.bid_ids.filtered('is_active').write({'is_active': False})
        values_by_line = {}
        for line_id, value in line_values.items():
            if isinstance(value, dict):
                values_by_line[int(line_id)] = value
            else:
                values_by_line[int(line_id)] = {'price_unit': value, 'delivery_days': 0}
        bid = self.env['tender.bid'].sudo().create({
            'invitation_id': self.id,
            'submission_kind': submission_kind,
            'is_active': True,
            'line_ids': [(0, 0, {
                'requisition_line_id': line.id,
                'price_unit': values_by_line.get(line.id, {}).get('price_unit', 0.0),
                'delivery_days': values_by_line.get(line.id, {}).get('delivery_days', 0),
                'technical_status': 'approved' if submission_kind == 'live' else 'pending',
            }) for line in self.requisition_id.line_ids],
        })
        self.active_bid_id = bid
        if self.state in ('draft', 'sent', 'submitted'):
            self.state = 'submitted'
        if self.requisition_id.online_state in ('draft', 'invited'):
            self.requisition_id.online_state = 'quote_entry'
        if submission_kind == 'initial':
            self.requisition_id.message_post(body=_('Vendor %s submitted a bid.') % self.partner_id.display_name)
        else:
            self.requisition_id.message_post(body=_('Vendor %s adjusted a live bid.') % self.partner_id.display_name)
        self.requisition_id._sync_online_tender_rfq(self, bid, reset_technical_state=True)
        return bid

    def _portal_ensure_live_bid(self):
        self.ensure_one()
        if self.active_bid_id:
            return self.active_bid_id
        line_values = {line.id: line.price_unit for line in self.requisition_id.line_ids}
        return self.action_submit_quote(line_values, submission_kind='live')

    def _get_delta_snapshot(self):
        self.ensure_one()
        bid = self._portal_ensure_live_bid()
        BidLine = self.env['tender.bid.line'].sudo()
        lines = []
        for bid_line in bid.line_ids:
            best_other = bid_line._get_best_other_price()
            delta_percent = bid_line._get_delta_percent(bid_line.price_unit, best_other)
            lines.append({
                'line_id': bid_line.requisition_line_id.id,
                'product_name': bid_line.product_id.display_name,
                'qty': bid_line.qty,
                'price_unit': bid_line.price_unit,
                'delivery_days': bid_line.delivery_days,
                'delta_percent': delta_percent,
                'is_currently_winning': not bool(best_other) or bid_line.price_unit <= best_other,
            })
        other_totals = self.search([
            ('requisition_id', '=', self.requisition_id.id),
            ('id', '!=', self.id),
            ('technical_passed', '=', True),
            ('active_bid_id', '!=', False),
        ]).mapped('active_bid_id.total_amount')
        best_other_total = min(other_totals) if other_totals else 0.0
        total_amount = bid.total_amount
        return {
            'state': self.requisition_id.online_state,
            'ends_at': fields.Datetime.to_string(self.requisition_id.bidding_end_at) if self.requisition_id.bidding_end_at else False,
            'server_now': fields.Datetime.to_string(fields.Datetime.now()),
            'lines': lines,
            'overall': {
                'total_amount': total_amount,
                'delta_percent': BidLine._get_delta_percent(total_amount, best_other_total),
                'is_currently_winning': not bool(best_other_total) or total_amount <= best_other_total,
            },
        }
