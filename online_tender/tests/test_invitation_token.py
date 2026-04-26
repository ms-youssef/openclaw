# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestTenderInvitationToken(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Acme', 'email': 'acme@test'})
        self.requisition = self.env['purchase.requisition'].create({
            'name': 'Tender Token Test',
            'is_online_tender': True,
            'vendor_partner_ids': [(6, 0, [self.partner.id])],
        })

    def test_token_is_generated_and_regenerated(self):
        invitation = self.env['tender.invitation'].create({
            'requisition_id': self.requisition.id,
            'partner_id': self.partner.id,
            'state': 'sent',
        })
        self.assertTrue(invitation.access_token)
        first_token = invitation.access_token
        invitation.action_regenerate_token()
        self.assertTrue(invitation.access_token)
        self.assertNotEqual(first_token, invitation.access_token)
        self.assertIn(str(invitation.id), invitation._get_token_url())
