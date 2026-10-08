from odoo import api, fields, models
from odoo.exceptions import UserError


ACTION_STATES = [
    ('open', 'Open'),
    ('in_progress', 'In Progress'),
    ('resolved', 'Resolved'),
    ('verified', 'Verified'),
    ('closed', 'Closed'),
]


class HseCorrectiveAction(models.Model):
    _name = 'hse.corrective.action'
    _description = 'HSE Corrective / Preventive Action (CAPA)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_due asc, id desc'

    reference = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    name = fields.Char(string='Title', required=True, tracking=True)
    finding_id = fields.Many2one('hse.finding', string='Finding', required=True, ondelete='cascade', tracking=True)
    inspection_id = fields.Many2one(
        related='finding_id.inspection_id', string='Inspection', store=True, readonly=True,
    )
    description = fields.Text(string='Action Required')
    responsible_id = fields.Many2one('res.users', string='Responsible', tracking=True)
    date_due = fields.Date(string='Due Date', tracking=True)
    date_resolved = fields.Date(string='Date Resolved', readonly=True)
    resolution_notes = fields.Text(string='Resolution Notes / Evidence')
    state = fields.Selection(selection=ACTION_STATES, string='Status', default='open', required=True, tracking=True, copy=False)
    priority = fields.Selection(
        selection=[('0', 'Low'), ('1', 'Medium'), ('2', 'High'), ('3', 'Urgent')],
        string='Priority', default='1',
    )
    severity = fields.Selection(related='finding_id.severity', store=True, readonly=True)
    is_overdue = fields.Boolean(string='Overdue', compute='_compute_overdue', store=True)
    active = fields.Boolean(default=True)

    @api.depends('date_due', 'state')
    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(rec.date_due and rec.date_due < today and rec.state not in ('verified', 'closed'))

    @api.model
    def create(self, vals):
        if vals.get('reference', 'New') == 'New':
            vals['reference'] = self.env['ir.sequence'].next_by_code('hse.corrective.action') or 'New'
        rec = super().create(vals)
        # UC-16: assignment triggers activity + chatter (mail.activity + mail.thread).
        if rec.responsible_id:
            rec.message_subscribe(partner_ids=rec.responsible_id.partner_id.ids)
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                summary='HSE corrective action assigned: %s' % rec.name,
                note=rec.description or '',
                date_deadline=rec.date_due,
                user_id=rec.responsible_id.id,
            )
            rec.message_post(body='Assigned to <b>%s</b> (due: %s).' % (rec.responsible_id.name, rec.date_due or '-'))
        if rec.finding_id and rec.finding_id.state == 'open':
            rec.finding_id.write({'state': 'in_progress'})
        return rec

    def write(self, vals):
        res = super().write(vals)
        if 'responsible_id' in vals:
            for rec in self:
                if rec.responsible_id:
                    rec.message_subscribe(partner_ids=rec.responsible_id.partner_id.ids)
                    rec.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary='HSE corrective action assigned: %s' % rec.name,
                        note=rec.description or '',
                        date_deadline=rec.date_due,
                        user_id=rec.responsible_id.id,
                    )
                if rec.finding_id and rec.finding_id.state == 'open' and rec.responsible_id:
                    rec.finding_id.write({'state': 'in_progress'})
        return res

    # UC-16..UC-19 lifecycle -------------------------------------------
    def action_start(self):
        for rec in self:
            if rec.state != 'open':
                raise UserError('Only Open actions can be started.')
            if not rec.responsible_id:
                raise UserError('Assign a responsible person before starting (UC-16).')
            rec.write({'state': 'in_progress'})
        return True

    def action_resolve(self):
        """UC-17: assignee implements remediation and submits resolution."""
        for rec in self:
            if rec.state not in ('open', 'in_progress'):
                raise UserError('Only Open / In Progress actions can be resolved.')
            if not (rec.resolution_notes or '').strip():
                raise UserError('Please record Resolution Notes / evidence before marking Resolved (UC-17).')
            rec.write({'state': 'resolved', 'date_resolved': fields.Date.context_today(rec)})
            rec.message_post(body='Marked Resolved with notes: %s' % rec.resolution_notes[:500])
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            if rec.finding_id and rec.finding_id.state in ('open', 'in_progress'):
                rec.finding_id.write({'state': 'resolved'})
        return True

    def action_verify(self):
        """UC-18: supervisor verifies on-site."""
        for rec in self:
            if rec.state != 'resolved':
                raise UserError('Only Resolved actions can be verified.')
            rec.write({'state': 'verified'})
            rec.message_post(body='Resolution verified by supervisor.')
            if rec.finding_id and rec.finding_id.state == 'resolved':
                rec.finding_id.write({'state': 'verified'})
        return True

    def action_close(self):
        """UC-19: manager final closure."""
        for rec in self:
            if rec.state != 'verified':
                raise UserError('Only Verified actions can be closed.')
            rec.write({'state': 'closed'})
            rec.message_post(body='Corrective action closed.')
            if rec.finding_id and rec.finding_id.state == 'verified':
                rec.finding_id.write({'state': 'closed'})
        return True

    def action_reopen(self):
        self.write({'state': 'open', 'date_resolved': False})
        return True
