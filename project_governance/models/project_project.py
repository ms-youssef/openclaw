# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from datetime import date

class Project(models.Model):
    _inherit = 'project.project'

    is_governance_enabled = fields.Boolean(string='Enable Governance Gate', default=False)
    governance_state = fields.Selection([
        ('draft', 'Draft Stage'),
        ('ready', 'Ready for Approval'),
        ('approved', 'Approved for Progression')
    ], string='Governance Status', default='draft', tracking=True)

    # Phase 2: Budget Monitoring Fields
    utilization_rate = fields.Float(string='Effort Utilization (%)', compute='_compute_budget_metrics', store=True)
    budget_status = fields.Selection([
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('over_budget', 'Over Budget')
    ], string='Budget Health', compute='_compute_budget_metrics', store=True)

    # Phase 3: Escalation & Health Status
    stage_deadline = fields.Date(string='Stage Target Date', tracking=True)
    governance_health = fields.Selection([
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('critical', 'Critical / Escalated')
    ], string='Project Health', compute='_compute_governance_health', store=True, tracking=True)
    is_escalated = fields.Boolean(string='Escalation Active', compute='_compute_governance_health', store=True)

    @api.depends('allocated_hours', 'effective_hours')
    def _compute_budget_metrics(self):
        for project in self:
            rate = 0.0
            status = 'on_track'
            if project.allocated_hours > 0:
                rate = (project.effective_hours / project.allocated_hours) * 100
                if rate >= 100:
                    status = 'over_budget'
                elif rate >= 80:
                    status = 'at_risk'
            project.utilization_rate = rate
            project.budget_status = status

    @api.depends('budget_status', 'stage_deadline', 'governance_state')
    def _compute_governance_health(self):
        today = date.today()
        for project in self:
            health = 'on_track'
            escalated = False
            
            # Check for overdue stage
            is_overdue = project.stage_deadline and project.stage_deadline < today and project.governance_state != 'approved'
            
            if project.budget_status == 'over_budget' or is_overdue:
                health = 'critical'
                escalated = True
            elif project.budget_status == 'at_risk':
                health = 'at_risk'
                
            project.governance_health = health
            project.is_escalated = escalated

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
