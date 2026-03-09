# -*- coding: utf-8 -*-
from odoo import fields, models

class Lead(models.Model):
    _inherit = 'crm.lead'

    linkedin_profile = fields.Char(string='LinkedIn Profile')
    company_linkedin = fields.Char(string='Company LinkedIn')
