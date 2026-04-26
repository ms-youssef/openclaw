# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestTenderBiddingFlow(TransactionCase):

    def setUp(self):
        super().setUp()
        self.product = self.env['product.product'].create({'name': 'Widget'})
        self.vendor_a = self.env['res.partner'].create({'name': 'Acme', 'email': 'acme@test'})
        self.vendor_b = self.env['res.partner'].create({'name': 'Beta', 'email': 'beta@test'})
        self.requisition = self.env['purchase.requisition'].create({
            'name': 'Tender Flow Test',
            'is_online_tender': True,
            'vendor_partner_ids': [(6, 0, [self.vendor_a.id, self.vendor_b.id])],
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 10.0,
                'price_unit': 10.0,
            })],
        })
        self.line = self.requisition.line_ids[0]
        self.invitation_a = self.env['tender.invitation'].create({
            'requisition_id': self.requisition.id,
            'partner_id': self.vendor_a.id,
            'state': 'sent',
        })
        self.invitation_b = self.env['tender.invitation'].create({
            'requisition_id': self.requisition.id,
            'partner_id': self.vendor_b.id,
            'state': 'sent',
        })

    def _approve_invitation(self, invitation):
        invitation.purchase_order_id.action_online_tender_approve_technical()

    def test_bid_supersession_and_delta(self):
        first = self.invitation_a.action_submit_quote({self.line.id: 9.5})
        second = self.invitation_a.action_submit_quote({self.line.id: 9.0})
        self.invitation_b.action_submit_quote({self.line.id: 8.5})
        self._approve_invitation(self.invitation_a)
        self._approve_invitation(self.invitation_b)
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        snapshot = self.invitation_a._get_delta_snapshot()
        self.assertEqual(snapshot['lines'][0]['delta_percent'], 5.88)
        self.assertFalse(snapshot['lines'][0]['is_currently_winning'])
        self.assertNotIn('best_other_price', snapshot['lines'][0])

    def test_winner_computation(self):
        self.invitation_a.action_submit_quote({self.line.id: 9.0})
        self.invitation_b.action_submit_quote({self.line.id: 8.5})
        self._approve_invitation(self.invitation_a)
        self._approve_invitation(self.invitation_b)
        self.requisition.online_state = 'bidding_open'
        self.requisition.action_close_bidding()
        self.assertEqual(self.requisition.online_state, 'awarded')
        self.assertEqual(self.requisition.winning_invitation_id, self.invitation_b)
        self.assertTrue(self.invitation_b.active_bid_id.line_ids.is_winner)

    def test_rejected_rfq_is_excluded_from_live_bidding(self):
        self.invitation_a.action_submit_quote({self.line.id: 9.0})
        self.invitation_b.action_submit_quote({self.line.id: 8.5})
        self.invitation_a.purchase_order_id.action_online_tender_approve_technical()
        self.invitation_b.purchase_order_id.action_online_tender_reject_technical()

        self.requisition.action_start_bidding(duration_minutes=30)

        self.assertTrue(self.invitation_a.technical_passed)
        self.assertFalse(self.invitation_b.technical_passed)
        self.assertEqual(self.invitation_a.state, 'live')
        self.assertEqual(self.invitation_b.state, 'submitted')
