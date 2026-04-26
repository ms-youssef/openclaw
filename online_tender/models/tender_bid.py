# -*- coding: utf-8 -*-

from odoo import api, fields, models


class TenderBid(models.Model):
    _name = 'tender.bid'
    _description = 'Tender Bid'
    _inherit = ['mail.thread']
    _order = 'submitted_at desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    invitation_id = fields.Many2one('tender.invitation', required=True, ondelete='cascade', index=True)
    requisition_id = fields.Many2one(related='invitation_id.requisition_id', store=True, index=True)
    partner_id = fields.Many2one(related='invitation_id.partner_id', store=True, index=True)
    submitted_at = fields.Datetime(default=fields.Datetime.now, required=True)
    submission_kind = fields.Selection([
        ('initial', 'Initial Quote'),
        ('live', 'Live Bid'),
    ], default='initial', required=True, tracking=True)
    line_ids = fields.One2many('tender.bid.line', 'bid_id', string='Bid Lines', copy=True)
    total_amount = fields.Monetary(compute='_compute_total_amount', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='requisition_id.currency_id', store=True)
    is_active = fields.Boolean(default=True, index=True)

    @api.depends('invitation_id.name', 'partner_id.name', 'submitted_at')
    def _compute_name(self):
        for bid in self:
            label = bid.invitation_id.name or bid.requisition_id.name or 'Tender'
            bid.name = '%s - %s' % (label, bid.partner_id.display_name or 'Vendor')

    @api.depends('line_ids.subtotal')
    def _compute_total_amount(self):
        for bid in self:
            bid.total_amount = sum(bid.line_ids.mapped('subtotal'))

    def action_make_active(self):
        for bid in self:
            bid.invitation_id.bid_ids.filtered(lambda item: item != bid).write({'is_active': False})
            bid.is_active = True
            bid.invitation_id.active_bid_id = bid


class TenderBidLine(models.Model):
    _name = 'tender.bid.line'
    _description = 'Tender Bid Line'
    _order = 'bid_id, requisition_line_id'

    bid_id = fields.Many2one('tender.bid', required=True, ondelete='cascade', index=True)
    invitation_id = fields.Many2one(related='bid_id.invitation_id', store=True, index=True)
    requisition_id = fields.Many2one(related='bid_id.requisition_id', store=True, index=True)
    requisition_line_id = fields.Many2one('purchase.requisition.line', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(related='requisition_line_id.product_id', store=True)
    product_uom_id = fields.Many2one(related='requisition_line_id.product_uom_id', store=True)
    qty = fields.Float(related='requisition_line_id.product_qty', store=True)
    price_unit = fields.Float(required=True, digits='Product Price')
    delivery_days = fields.Integer(string='Delivery Time (Days)')
    technical_status = fields.Selection([
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True, string='Technical Status')
    technical_approved = fields.Boolean(compute='_compute_technical_approved', store=True)
    technical_notes = fields.Text(string='Technical Notes')
    subtotal = fields.Monetary(compute='_compute_subtotal', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='bid_id.currency_id', store=True)
    best_other_price = fields.Monetary(compute='_compute_competitive_fields', currency_field='currency_id')
    delta_percent = fields.Float(compute='_compute_competitive_fields')
    is_winner = fields.Boolean(default=False, index=True)

    @api.depends('price_unit', 'qty')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.price_unit * line.qty

    @api.depends('technical_status')
    def _compute_technical_approved(self):
        for line in self:
            line.technical_approved = line.technical_status == 'approved'

    @api.depends('price_unit', 'bid_id.is_active', 'requisition_line_id', 'invitation_id')
    def _compute_competitive_fields(self):
        for line in self:
            best_other = line._get_best_other_price()
            line.best_other_price = best_other
            line.delta_percent = line._get_delta_percent(line.price_unit, best_other)

    def _get_best_other_price(self):
        self.ensure_one()
        domain = [
            ('requisition_line_id', '=', self.requisition_line_id.id),
            ('bid_id.is_active', '=', True),
            ('bid_id.invitation_id.technical_passed', '=', True),
            ('bid_id.invitation_id', '!=', self.invitation_id.id),
        ]
        prices = self.search(domain).mapped('price_unit')
        return min(prices) if prices else 0.0

    @api.model
    def _get_delta_percent(self, own_price, other_price):
        if not other_price:
            return 0.0
        return round(((own_price - other_price) / other_price) * 100.0, 2)
