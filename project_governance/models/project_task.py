# -*- coding: utf-8 -*-
from odoo import fields, models

class Task(models.Model):
    _inherit = 'project.task'

    is_deliverable = fields.Boolean(string='Stage Deliverable', default=False)
