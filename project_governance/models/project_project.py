# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError

class Project(models.Model):
    _inherit = 'project.project'

    is_governance_enabled = fields.Boolean(string='Enable Governance Gate', default=False)
    governance_state = fields.Selection([
        ('draft', 'Draft Stage'),
        ('ready', 'Ready for Approval'),
        ('approved', 'Approved for Progression')
    ], string='Governance Status', default='draft', tracking=True)

    def action_request_approval(self):
        """Request stage approval from Operations Director"""
        for project in self:
            # Check for incomplete deliverables (tasks marked as deliverables that are not closed)
            incomplete_deliverables = project.tasks.filtered(lambda t: t.is_deliverable and not t.is_closed)
            if incomplete_deliverables:
                raise UserError(_("Stage progression blocked. The following deliverables are incomplete: \n %s") % 
                    "\n".join(incomplete_deliverables.mapped('name')))
            project.governance_state = 'ready'

    def action_approve_governance(self):
        """Operations Director confirms the move to next stage"""
        if not self.env.user.has_group('project_governance.group_project_governance_approver'):
            raise UserError(_("Only an authorized Project Governance Approver can approve this stage gate."))
        self.governance_state = 'approved'

    def write(self, vals):
        """Block stage changes if governance is enabled and not approved"""
        if 'stage_id' in vals:
            for project in self:
                if project.is_governance_enabled and project.governance_state != 'approved':
                    raise UserError(_("Stage transition blocked. This project requires an approved Governance Gate to move forward."))
                # Reset governance state after successful transition
                project.governance_state = 'draft'
        return super(Project, self).write(vals)
