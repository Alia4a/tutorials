from odoo import api, fields, models
from odoo.exceptions import UserError


FINDING_STATES = [
    ('open', 'Open'),
    ('in_progress', 'In Progress'),
    ('resolved', 'Resolved'),
    ('verified', 'Verified'),
    ('closed', 'Closed'),
]
SEVERITIES = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class HseFinding(models.Model):
    _name = 'hse.finding'
    _description = 'HSE Finding / Non-conformity'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    reference = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    name = fields.Char(string='Title', required=True, tracking=True)
    inspection_id = fields.Many2one('hse.inspection', string='Inspection', required=True, ondelete='cascade', tracking=True)
    inspection_line_id = fields.Many2one('hse.inspection.line', string='Triggering Answer')
    question_id = fields.Many2one('hse.checklist.question', string='Question')
    checklist_id = fields.Many2one(related='inspection_id.checklist_id', store=True, readonly=True)
    rule_id = fields.Many2one('hse.rule', string='Triggering Rule', ondelete='set null')
    description = fields.Text(string='Description')
    severity = fields.Selection(selection=SEVERITIES, string='Severity', default='medium', required=True, tracking=True)
    state = fields.Selection(selection=FINDING_STATES, string='Status', default='open', required=True, tracking=True, copy=False)
    responsible_id = fields.Many2one('res.users', string='Responsible')
    date_found = fields.Date(string='Date Found', default=fields.Date.context_today)
    action_ids = fields.One2many('hse.corrective.action', 'finding_id', string='Corrective Actions')
    action_count = fields.Integer(compute='_compute_action_count', store=True)
    active = fields.Boolean(default=True)

    @api.depends('action_ids')
    def _compute_action_count(self):
        for rec in self:
            rec.action_count = len(rec.action_ids)

    @api.model
    def create(self, vals):
        if vals.get('reference', 'New') == 'New':
            vals['reference'] = self.env['ir.sequence'].next_by_code('hse.finding') or 'New'
        rec = super().create(vals)
        # Auto-subscribe responsible for chatter notifications (UC-14).
        if rec.responsible_id:
            rec.message_subscribe(partner_ids=rec.responsible_id.partner_id.ids)
        return rec

    # UC-15 triage -----------------------------------------------------
    def action_start_progress(self):
        for rec in self:
            if rec.state != 'open':
                raise UserError('Only Open findings can be started.')
            rec.write({'state': 'in_progress'})
            rec.message_post(body='Finding triaged — moved to In Progress.')
        return True

    def action_resolve(self):
        for rec in self:
            if rec.state not in ('open', 'in_progress'):
                raise UserError('Only Open / In Progress findings can be resolved.')
            rec.write({'state': 'resolved'})
            rec.message_post(body='Finding marked as Resolved.')
        return True

    def action_verify(self):
        for rec in self:
            if rec.state != 'resolved':
                raise UserError('Only Resolved findings can be verified.')
            rec.write({'state': 'verified'})
            rec.message_post(body='Resolution verified on-site by supervisor.')
        return True

    def action_close(self):
        for rec in self:
            if rec.state != 'verified':
                raise UserError('Only Verified findings can be closed.')
            rec.write({'state': 'closed'})
            rec.message_post(body='Finding closed by HSE Manager.')
        return True

    def action_reopen(self):
        self.write({'state': 'open'})
        return True

    def action_view_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Corrective Actions',
            'res_model': 'hse.corrective.action',
            'view_mode': 'tree,kanban,form',
            'domain': [('finding_id', '=', self.id)],
            'context': {'default_finding_id': self.id},
        }
