# -*- coding: utf-8 -*-

from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestTenderPortalRoutes(HttpCase):

    def test_public_token_rejects_missing_invitation(self):
        response = self.url_open('/tender/999999/not-a-token')
        self.assertEqual(response.status_code, 404)
