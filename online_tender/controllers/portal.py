# -*- coding: utf-8 -*-

import json
from hmac import compare_digest as consteq

from werkzeug.exceptions import NotFound

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class OnlineTenderPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        partner = request.env.user.partner_id.commercial_partner_id
        values['tender_count'] = request.env['tender.invitation'].search_count([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', ('sent', 'submitted', 'live')),
        ]) if not request.env.user._is_public() else 0
        return values

    def _get_invitation_or_404(self, invitation_id, access_token=None):
        Invitation = request.env['tender.invitation']
        try:
            if access_token:
                invitation = Invitation.sudo().browse(int(invitation_id)).exists()
                readable_states = ('sent', 'submitted', 'live', 'closed', 'won', 'lost')
                if not invitation or not invitation.access_token or not consteq(access_token, invitation.access_token) or invitation.state not in readable_states:
                    raise NotFound()
                return invitation
            invitation = Invitation.browse(int(invitation_id)).exists()
            if not invitation:
                raise NotFound()
            invitation.check_access_rights('read')
            invitation.check_access_rule('read')
            return invitation
        except (AccessError, MissingError, ValueError):
            raise NotFound()

    def _get_portal_values(self, invitation, access_token=None, **kw):
        return {
            'invitation': invitation,
            'requisition': invitation.requisition_id,
            'access_token': access_token,
            'page_name': 'tender',
            'submitted': kw.get('submitted'),
            'error': kw.get('error'),
        }

    @http.route(['/my/tenders', '/my/tenders/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_tenders(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        Invitation = request.env['tender.invitation']
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [('partner_id.commercial_partner_id', '=', partner.id)]
        tender_count = Invitation.search_count(domain)
        pager = portal_pager(url='/my/tenders', total=tender_count, page=page, step=self._items_per_page)
        invitations = Invitation.search(domain, order='id desc', limit=self._items_per_page, offset=pager['offset'])
        values.update({
            'invitations': invitations,
            'page_name': 'tenders',
            'pager': pager,
            'default_url': '/my/tenders',
        })
        return request.render('online_tender.portal_my_tenders', values)

    @http.route(['/my/tenders/<int:invitation_id>'], type='http', auth='user', website=True)
    def portal_tender_page(self, invitation_id, **kw):
        invitation = self._get_invitation_or_404(invitation_id)
        return request.render('online_tender.portal_tender_page', self._get_portal_values(invitation, **kw))

    @http.route(['/tender/<int:invitation_id>/<string:access_token>'], type='http', auth='public', website=True)
    def portal_tender_token_page(self, invitation_id, access_token, **kw):
        invitation = self._get_invitation_or_404(invitation_id, access_token)
        return request.render('online_tender.portal_tender_page', self._get_portal_values(invitation, access_token, **kw))

    @http.route(['/my/tenders/<int:invitation_id>/submit', '/tender/<int:invitation_id>/<string:access_token>/submit'], type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def portal_tender_submit(self, invitation_id, access_token=None, **post):
        invitation = self._get_invitation_or_404(invitation_id, access_token)
        try:
            line_values = self._extract_line_values(invitation, post)
            invitation.sudo().action_submit_quote(line_values, submission_kind='initial')
        except (UserError, ValidationError) as error:
            values = self._get_portal_values(invitation, access_token)
            values['error'] = str(error)
            return request.render('online_tender.portal_tender_page', values)
        url = invitation._get_token_url() if access_token else invitation.access_url
        return request.redirect('%s?submitted=1' % url)

    @http.route(['/my/tenders/<int:invitation_id>/live'], type='http', auth='user', website=True)
    def portal_tender_live(self, invitation_id, **kw):
        invitation = self._get_invitation_or_404(invitation_id)
        return request.render('online_tender.portal_tender_live', self._get_live_values(invitation))

    @http.route(['/tender/<int:invitation_id>/<string:access_token>/live'], type='http', auth='public', website=True)
    def portal_tender_token_live(self, invitation_id, access_token, **kw):
        invitation = self._get_invitation_or_404(invitation_id, access_token)
        return request.render('online_tender.portal_tender_live', self._get_live_values(invitation, access_token))

    @http.route(['/my/tenders/<int:invitation_id>/live/poll'], type='json', auth='public', methods=['POST'], csrf=False)
    def portal_tender_live_poll(self, invitation_id, access_token=None, **kw):
        invitation = self._get_invitation_or_404(invitation_id, access_token)
        return invitation.sudo()._get_delta_snapshot()

    @http.route(['/my/tenders/<int:invitation_id>/live/submit'], type='json', auth='public', methods=['POST'], csrf=False)
    def portal_tender_live_submit(self, invitation_id, access_token=None, lines=None, **kw):
        invitation = self._get_invitation_or_404(invitation_id, access_token)
        requisition = invitation.sudo().requisition_id
        if requisition.online_state != 'bidding_open' or (requisition.bidding_end_at and fields.Datetime.now() >= requisition.bidding_end_at):
            raise UserError(_('Live bidding is closed.'))
        bid = invitation.sudo()._portal_ensure_live_bid()
        values = {}
        for item in lines or []:
            if 'line_id' in item:
                values[int(item['line_id'])] = float(item.get('price_unit') or 0.0)
        for line in bid.line_ids:
            if line.requisition_line_id.id in values:
                line.price_unit = values[line.requisition_line_id.id]
        bid.write({'submission_kind': 'live', 'submitted_at': fields.Datetime.now()})
        requisition.message_post(body=_('Vendor %s adjusted a live bid.') % invitation.partner_id.display_name)
        return invitation.sudo()._get_delta_snapshot()

    def _extract_line_values(self, invitation, post):
        line_values = {}
        for line in invitation.requisition_id.line_ids:
            key = 'price_unit_%s' % line.id
            value = post.get(key)
            if value in (None, ''):
                raise ValidationError(_('Missing price for %s.') % line.product_id.display_name)
            price = float(value)
            if price < 0:
                raise ValidationError(_('Price cannot be negative.'))
            line_values[line.id] = price
        return line_values

    def _get_live_values(self, invitation, access_token=None):
        if invitation.requisition_id.online_state != 'bidding_open':
            return request.redirect((invitation._get_token_url() if access_token else invitation.access_url))
        bid = invitation.sudo()._portal_ensure_live_bid()
        return {
            'invitation': invitation,
            'requisition': invitation.requisition_id,
            'bid': bid,
            'access_token': access_token,
            'page_name': 'tender',
            'bootstrap': {
                'invitation_id': invitation.id,
                'access_token': access_token or '',
                'ends_at': fields.Datetime.to_string(invitation.requisition_id.bidding_end_at),
                'poll_url': '/my/tenders/%s/live/poll' % invitation.id,
                'submit_url': '/my/tenders/%s/live/submit' % invitation.id,
            },
            'bootstrap_json': json.dumps({
                'invitation_id': invitation.id,
                'access_token': access_token or '',
                'ends_at': fields.Datetime.to_string(invitation.requisition_id.bidding_end_at),
                'poll_url': '/my/tenders/%s/live/poll' % invitation.id,
                'submit_url': '/my/tenders/%s/live/submit' % invitation.id,
            }),
        }
