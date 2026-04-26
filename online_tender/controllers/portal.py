# -*- coding: utf-8 -*-

import base64
import json
from hmac import compare_digest as consteq

from markupsafe import Markup
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
        current_bid = invitation.sudo()._portal_ensure_live_bid()
        values = {}
        for item in lines or []:
            if 'line_id' in item:
                values[int(item['line_id'])] = {
                    'price_unit': float(item.get('price_unit') or 0.0),
                    'delivery_days': int(item.get('delivery_days') or 0),
                }
        for bid_line in current_bid.line_ids:
            values.setdefault(bid_line.requisition_line_id.id, {
                'price_unit': bid_line.price_unit,
                'delivery_days': bid_line.delivery_days,
            })
        invitation.sudo().action_submit_quote(values, submission_kind='live')
        return invitation.sudo()._get_delta_snapshot()

    @http.route(['/online_tender/<int:requisition_id>/dashboard'], type='http', auth='user', website=True)
    def tender_manager_dashboard(self, requisition_id, **kw):
        requisition = request.env['purchase.requisition'].browse(requisition_id).exists()
        if not requisition or not request.env.user.has_group('online_tender.group_tender_manager'):
            raise NotFound()
        dashboard = {
            'requisition_id': requisition.id,
            'poll_url': '/online_tender/%s/dashboard/poll' % requisition.id,
        }
        return request.render('online_tender.tender_manager_dashboard', {
            'requisition': requisition,
            'page_name': 'tender_dashboard',
            'dashboard_json': Markup(json.dumps(dashboard)),
        })

    @http.route(['/online_tender/<int:requisition_id>/dashboard/poll'], type='json', auth='user', methods=['POST'], csrf=False)
    def tender_manager_dashboard_poll(self, requisition_id, **kw):
        requisition = request.env['purchase.requisition'].browse(requisition_id).exists()
        if not requisition or not request.env.user.has_group('online_tender.group_tender_manager'):
            raise NotFound()
        return requisition.sudo()._get_live_dashboard_snapshot()

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
            delivery_days = int(post.get('delivery_days_%s' % line.id) or line.tender_delivery_days or 0)
            if delivery_days < 0:
                raise ValidationError(_('Delivery time cannot be negative.'))
            line_values[line.id] = {
                'price_unit': price,
                'delivery_days': delivery_days,
            }
        self._post_portal_attachments(invitation, post)
        return line_values

    def _post_portal_attachments(self, invitation, post):
        message = post.get('message')
        files = request.httprequest.files.getlist('attachment')
        attachment_ids = []
        for upload in files:
            if not upload or not upload.filename:
                continue
            data = upload.read()
            attachment = request.env['ir.attachment'].sudo().create({
                'name': upload.filename,
                'datas': base64.b64encode(data).decode(),
                'res_model': invitation._name,
                'res_id': invitation.id,
                'mimetype': upload.mimetype,
            })
            attachment_ids.append(attachment.id)
        if message or attachment_ids:
            invitation.sudo().message_post(
                body=message or _('Vendor uploaded tender attachment.'),
                attachment_ids=attachment_ids,
            )

    def _get_live_values(self, invitation, access_token=None):
        if invitation.requisition_id.online_state != 'bidding_open':
            return request.redirect((invitation._get_token_url() if access_token else invitation.access_url))
        bid = invitation.sudo()._portal_ensure_live_bid()
        bootstrap = {
            'invitation_id': invitation.id,
            'access_token': access_token or '',
            'ends_at': fields.Datetime.to_string(invitation.requisition_id.bidding_end_at),
            'poll_url': '/my/tenders/%s/live/poll' % invitation.id,
            'submit_url': '/my/tenders/%s/live/submit' % invitation.id,
        }
        return {
            'invitation': invitation,
            'requisition': invitation.requisition_id,
            'bid': bid,
            'access_token': access_token,
            'page_name': 'tender',
            'bootstrap': bootstrap,
            'bootstrap_json': Markup(json.dumps(bootstrap)),
        }
