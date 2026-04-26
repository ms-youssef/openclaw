# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    vendor_id = fields.Many2one('res.partner', required=False)
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
    online_tender_purchase_order_ids = fields.One2many('purchase.order', 'online_tender_requisition_id', string='Generated RFQs', readonly=True)

    @api.model
    def _get_online_tender_type(self):
        type_field = self._fields.get('type_id')
        type_model_name = type_field.comodel_name if type_field else False
        if not type_model_name or type_model_name not in self.env.registry.models:
            return self.env['ir.model'].browse()
        RequisitionType = self.env[type_model_name].sudo()
        for name in ('Purchase Template', 'Call for Tender', 'Tender'):
            requisition_type = RequisitionType.search([('name', 'ilike', name)], limit=1)
            if requisition_type:
                return requisition_type
        if 'exclusive' in RequisitionType._fields:
            requisition_type = RequisitionType.search([('exclusive', '=', 'multiple')], limit=1)
            if requisition_type:
                return requisition_type
        order = 'sequence, id' if 'sequence' in RequisitionType._fields else 'id'
        return RequisitionType.search([], order=order, limit=1)

    @api.onchange('is_online_tender')
    def _onchange_is_online_tender(self):
        if not self.is_online_tender:
            return
        online_tender_type = self._get_online_tender_type()
        if online_tender_type and 'type_id' in self._fields:
            self.type_id = online_tender_type
        self.vendor_id = False

    @api.model_create_multi
    def create(self, vals_list):
        online_tender_type = False
        for vals in vals_list:
            if vals.get('is_online_tender'):
                online_tender_type = online_tender_type or self._get_online_tender_type()
                if online_tender_type and 'type_id' in self._fields:
                    vals.setdefault('type_id', online_tender_type.id)
                vals.setdefault('vendor_id', False)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_online_tender') and 'type_id' in self._fields and not vals.get('type_id'):
            online_tender_type = self._get_online_tender_type()
            if online_tender_type:
                vals = dict(vals, type_id=online_tender_type.id, vendor_id=False)
        return super().write(vals)

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
                requisition._sync_online_tender_rfq(invitation)
                if template and not self.env.context.get('skip_online_tender_emails'):
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

    def action_live_dashboard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/online_tender/%s/dashboard' % self.id,
            'target': 'new',
        }

    def action_start_bidding(self, duration_minutes=60):
        template = self.env.ref('online_tender.mail_template_tender_live_bidding_open', raise_if_not_found=False)
        now = fields.Datetime.now()
        for requisition in self:
            if not requisition.invitation_ids:
                raise UserError(_('Send invitations before opening live bidding.'))
            if not requisition._get_submitted_invitations():
                raise UserError(_('At least one vendor must submit a quote before live bidding.'))
            approved_invitations = requisition._get_approved_invitations()
            if not approved_invitations:
                raise UserError(_('Approve at least one vendor technical offer before opening live bidding.'))
            requisition.write({
                'online_state': 'bidding_open',
                'bidding_duration_minutes': duration_minutes,
                'bidding_start_at': now,
                'bidding_end_at': now + timedelta(minutes=duration_minutes),
            })
            approved_invitations.filtered(lambda item: item.state in ('sent', 'submitted')).write({'state': 'live'})
            for invitation in approved_invitations:
                if template and not self.env.context.get('skip_online_tender_emails'):
                    template.sudo().send_mail(invitation.id, force_send=True)
            skipped = requisition.invitation_ids - approved_invitations
            if skipped:
                requisition.message_post(body=_('Live bidding opened for %s minutes. %s vendors were excluded because technical approval is not passed.') % (duration_minutes, len(skipped)))
            else:
                requisition.message_post(body=_('Live bidding opened for %s minutes.') % duration_minutes)

    def action_close_bidding(self):
        for requisition in self:
            requisition._close_bidding()

    def _close_bidding(self):
        self.ensure_one()
        if self.online_state not in ('bidding_open', 'invited', 'quote_entry'):
            return
        active_invitations = self._get_approved_invitations()
        if not active_invitations:
            did_not_win_tag = self.env.ref('online_tender.tender_tag_did_not_win', raise_if_not_found=False)
            if did_not_win_tag:
                self.invitation_ids.write({'tag_ids': [(4, did_not_win_tag.id)], 'state': 'lost'})
            self.online_state = 'awarded'
            self._create_online_tender_rfqs(self.invitation_ids)
            self.message_post(body=_('Online tender closed with no technically approved submitted bids.'))
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
        self.vendor_id = winning_invitation.partner_id
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
        self._create_online_tender_rfqs(self.invitation_ids)
        self.message_post(body=_('%s won the online tender with total %s.') % (winning_invitation.partner_id.display_name, winning_invitation.total_amount))

    def _create_online_tender_rfqs(self, invitations):
        for invitation in invitations:
            bid = invitation.active_bid_id
            order = self._sync_online_tender_rfq(invitation, bid)
            self.message_post(body=_('Draft RFQ %s was updated for %s.') % (order.name, invitation.partner_id.display_name))

    def _get_submitted_invitations(self):
        self.ensure_one()
        return self.invitation_ids.filtered(lambda invitation: invitation.active_bid_id)

    def _get_approved_invitations(self):
        self.ensure_one()
        return self._get_submitted_invitations().filtered(lambda invitation: invitation.technical_passed)

    def _sync_online_tender_rfq(self, invitation, bid=False, reset_technical_state=False):
        self.ensure_one()
        order_vals = self._prepare_online_tender_rfq_vals(invitation, bid)
        PurchaseOrder = self.env['purchase.order'].sudo()
        technical_state = 'approved' if bid and bid.submission_kind == 'live' else 'pending'
        if invitation.purchase_order_id:
            order = invitation.purchase_order_id.sudo()
            if order.state in ('draft', 'sent'):
                if reset_technical_state and 'online_tender_technical_state' in order._fields:
                    order_vals['online_tender_technical_state'] = technical_state
                order_vals['order_line'] = [(5, 0, 0)] + order_vals['order_line']
                order.write(order_vals)
        else:
            if 'online_tender_technical_state' in PurchaseOrder._fields:
                order_vals['online_tender_technical_state'] = technical_state
            order = PurchaseOrder.create(order_vals)
            invitation.purchase_order_id = order
        if invitation.tag_ids and 'online_tender_tag_ids' in order._fields:
            order.online_tender_tag_ids = [(6, 0, invitation.tag_ids.ids)]
        return order

    def _prepare_online_tender_rfq_vals(self, invitation, bid=False):
        self.ensure_one()
        vals = {
            'partner_id': invitation.partner_id.id,
            'origin': self.name,
            'requisition_id': self.id,
            'online_tender_requisition_id': self.id,
            'online_tender_invitation_id': invitation.id,
            'order_line': [],
        }
        for field_name in ('company_id', 'currency_id', 'picking_type_id'):
            if field_name in self._fields and self[field_name]:
                vals[field_name] = self[field_name].id
        source_lines = bid.line_ids if bid else self.env['tender.bid.line']
        if not source_lines:
            source_lines = self.line_ids
        for source_line in source_lines:
            is_bid_line = source_line._name == 'tender.bid.line'
            requisition_line = source_line.requisition_line_id if is_bid_line else source_line
            delivery_days = source_line.delivery_days if is_bid_line else requisition_line.tender_delivery_days
            planned_date = fields.Datetime.now() + timedelta(days=delivery_days or 0)
            line_vals = {
                'product_id': requisition_line.product_id.id,
                'name': requisition_line.product_id.display_name,
                'product_qty': source_line.qty if is_bid_line else requisition_line.product_qty,
                'product_uom_id': (requisition_line.product_uom_id or requisition_line.product_id.uom_id).id,
                'price_unit': source_line.price_unit if is_bid_line else requisition_line.price_unit,
                'date_planned': planned_date,
                'tender_delivery_days': delivery_days,
                'tender_technical_approved': source_line.technical_approved if is_bid_line else requisition_line.tender_technical_approved,
                'tender_technical_notes': source_line.technical_notes if is_bid_line else requisition_line.tender_technical_notes,
            }
            vals['order_line'].append((0, 0, line_vals))
        return vals

    @api.model
    def _cron_close_expired_biddings(self):
        expired = self.search([
            ('is_online_tender', '=', True),
            ('online_state', '=', 'bidding_open'),
            ('bidding_end_at', '<=', fields.Datetime.now()),
        ])
        for requisition in expired:
            requisition._close_bidding()

    def _get_live_dashboard_snapshot(self):
        self.ensure_one()
        invitations = self._get_approved_invitations()
        active_bids = invitations.mapped('active_bid_id')
        best_total = min(active_bids.mapped('total_amount')) if active_bids else 0.0
        delta_model = self.env['tender.bid.line']
        lines = []
        for requisition_line in self.line_ids:
            bid_lines = active_bids.mapped('line_ids').filtered(lambda line: line.requisition_line_id == requisition_line)
            best_price = min(bid_lines.mapped('price_unit')) if bid_lines else 0.0
            bidders = []
            for invitation in invitations:
                bid_line = invitation.active_bid_id.line_ids.filtered(lambda line: line.requisition_line_id == requisition_line)[:1]
                price = bid_line.price_unit if bid_line else 0.0
                bidders.append({
                    'invitation_id': invitation.id,
                    'vendor': invitation.partner_id.display_name,
                    'price_unit': price,
                    'delivery_days': bid_line.delivery_days if bid_line else 0,
                    'delta_percent': delta_model._get_delta_percent(price, best_price) if best_price else 0.0,
                    'is_best': bool(best_price) and price == best_price,
                })
            lines.append({
                'line_id': requisition_line.id,
                'product_name': requisition_line.product_id.display_name,
                'qty': requisition_line.product_qty,
                'best_price': best_price,
                'bidders': bidders,
            })
        bidders = []
        for invitation in invitations:
            total = invitation.active_bid_id.total_amount
            bidders.append({
                'invitation_id': invitation.id,
                'vendor': invitation.partner_id.display_name,
                'total_amount': total,
                'delta_percent': delta_model._get_delta_percent(total, best_total) if best_total else 0.0,
                'is_best': bool(best_total) and total == best_total,
                'bid_count': len(invitation.bid_ids),
                'last_bid_at': fields.Datetime.to_string(invitation.active_bid_id.submitted_at),
                'delivery_days': max(invitation.active_bid_id.line_ids.mapped('delivery_days') or [0]),
            })
        bidders.sort(key=lambda item: item['total_amount'])
        history = []
        bids = self.env['tender.bid'].search([
            ('requisition_id', '=', self.id),
            ('invitation_id', 'in', invitations.ids),
        ], order='submitted_at desc, id desc', limit=30)
        for bid in bids:
            history.append({
                'vendor': bid.partner_id.display_name,
                'submitted_at': fields.Datetime.to_string(bid.submitted_at),
                'submission_kind': bid.submission_kind,
                'total_amount': bid.total_amount,
            })
        return {
            'state': self.online_state,
            'server_now': fields.Datetime.to_string(fields.Datetime.now()),
            'ends_at': fields.Datetime.to_string(self.bidding_end_at) if self.bidding_end_at else False,
            'best_total': best_total,
            'bidders': bidders,
            'lines': lines,
            'history': history,
        }

    @api.constrains('bidding_duration_minutes')
    def _check_bidding_duration_minutes(self):
        for requisition in self:
            if requisition.bidding_duration_minutes <= 0:
                raise ValidationError(_('Bidding duration must be positive.'))


class PurchaseRequisitionLine(models.Model):
    _inherit = 'purchase.requisition.line'

    tender_delivery_days = fields.Integer(string='Expected Delivery Time (Days)')
    tender_technical_approved = fields.Boolean(string='Technically Approved')
    tender_technical_notes = fields.Text(string='Technical Notes')

    @api.constrains('tender_delivery_days')
    def _check_tender_delivery_days(self):
        for line in self:
            if line.tender_delivery_days < 0:
                raise ValidationError(_('Delivery time cannot be negative.'))
