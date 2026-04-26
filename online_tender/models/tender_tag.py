# -*- coding: utf-8 -*-

from odoo import fields, models


class TenderTag(models.Model):
    _name = 'tender.tag'
    _description = 'Tender Tag'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
