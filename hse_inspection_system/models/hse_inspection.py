from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HseInspection(models.Model):
    _name = 'hse.inspection'
    _description = 'HSE Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_inspection desc, id desc'

    reference = fields.Char(string='Reference', copy=False, readonly=True, default='New')
    name = fields.Char(string='Title', compute='_compute_name', store=True)
    checklist_id = fields.Many2one('hse.checklist', string='Checklist', required=True, tracking=True, ondelete='restrict')
    category = fields.Selection(related='checklist_id.category', string='Category', store=True, readonly=True)
    inspector_id = fields.Many2one(
        'hr.employee', string='Inspector',
        default=lambda self: self._default_inspector(),
        tracking=True,
    )
    department_id = fields.Many2one('hr.department', string='Department / Location')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment / Machine')
    date_inspection = fields.Date(string='Inspection Date', default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('canceled', 'Canceled'),
        ],
        string='Status', default='draft', required=True, tracking=True, copy=False,
    )
    line_ids = fields.One2many('hse.inspection.line', 'inspection_id', string='Answers / Checklist Lines')
    finding_ids = fields.One2many('hse.finding', 'inspection_id', string='Findings')
    action_ids = fields.One2many('hse.corrective.action', 'inspection_id', string='Corrective Actions')
    notes = fields.Text(string='General Notes')

    compliance_rate = fields.Float(string='Compliance %', compute='_compute_compliance', store=True)
    line_count = fields.Integer(compute='_compute_counts', store=True)
    finding_count = fields.Integer(compute='_compute_counts', store=True)
    action_count = fields.Integer(compute='_compute_counts', store=True)
    overdue_action_count = fields.Integer(compute='_compute_counts', store=True)

    active = fields.Boolean(default=True)

    @api.model
    def _default_inspector(self):
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        return employee.id if employee else False

    @api.depends('reference', 'checklist_id', 'date_inspection')
    def _compute_name(self):
        for rec in self:
            if rec.reference and rec.reference != 'New':
                rec.name = '%s - %s' % (rec.reference, rec.checklist_id.name or '')
            elif rec.checklist_id:
                rec.name = 'New - %s' % rec.checklist_id.name
            else:
                rec.name = 'New Inspection'

    @api.depends('line_ids.pass_fail', 'line_ids.yes_no', 'line_ids.is_answered')
    def _compute_compliance(self):
        for rec in self:
            scored = rec.line_ids.filtered(
                lambda l: l.question_type in ('pass_fail', 'yes_no') and l.is_answered
            )
            if not scored:
                rec.compliance_rate = 100.0 if rec.line_ids and all(l.is_answered for l in rec.line_ids) else 0.0
                continue
            passed = scored.filtered(
                lambda l: (l.question_type == 'pass_fail' and l.pass_fail == 'pass')
                or (l.question_type == 'yes_no' and l.yes_no == 'yes')
            )
            rec.compliance_rate = round(100.0 * len(passed) / len(scored), 2)

    @api.depends('line_ids', 'finding_ids', 'action_ids', 'action_ids.date_due', 'action_ids.state')
    def _compute_counts(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.finding_count = len(rec.finding_ids)
            rec.action_count = len(rec.action_ids)
            rec.overdue_action_count = len(rec.action_ids.filtered(
                lambda a: a.date_due and a.date_due < today and a.state not in ('verified', 'closed')
            ))

    @api.model
    def create(self, vals):
        if vals.get('reference', 'New') == 'New':
            vals['reference'] = self.env['ir.sequence'].next_by_code('hse.inspection') or 'New'
        return super().create(vals)

    # ------------------------------------------------------------------
    # Lifecycle (UC-07 / UC-10 / UC-11)
    # ------------------------------------------------------------------
    def action_start(self):
        """Draft -> In Progress. Populates dynamic answer lines from the checklist template."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only Draft inspections can be started.')
            if not rec.checklist_id.question_ids:
                raise UserError('Checklist has no questions. Ask the HSE Manager to configure questions first.')
            existing_q = set(rec.line_ids.mapped('question_id.id'))
            to_create = []
            for q in rec.checklist_id.question_ids.sorted('sequence'):
                if q.id in existing_q:
                    continue
                to_create.append({'inspection_id': rec.id, 'question_id': q.id})
            if to_create:
                self.env['hse.inspection.line'].create(to_create)
            rec.write({'state': 'in_progress'})
            rec.message_post(body='Inspection started. Dynamic questions generated from checklist <b>%s</b>.' % rec.checklist_id.name)
        return True

    def action_complete(self):
        """In Progress -> Completed. Validates mandatory answers then triggers the rules engine."""
        for rec in self:
            if rec.state not in ('draft', 'in_progress'):
                raise UserError('Only Draft / In Progress inspections can be completed.')
            if rec.state == 'draft':
                rec.action_start()
            missing = rec.line_ids.filtered(lambda l: l.is_required and not l.is_answered)
            if missing:
                names = '\n- '.join(missing.mapped('question_id.name'))
                raise ValidationError(
                    'All mandatory questions must be answered before completing:\n- %s' % names
                )
            rec.write({'state': 'completed'})
            rec.message_post(body='Inspection submitted. Evaluating business rules...')
            # UC-12/13: trigger hook — contract shared with Dev B (rules engine).
            self.env['hse.rule'].evaluate_inspection(rec)
            rec.message_post(body='Rule evaluation finished. Compliance: <b>%s%%</b>.' % rec.compliance_rate)
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'completed':
                raise UserError('Completed inspections cannot be canceled. Create a new inspection instead.')
            rec.write({'state': 'canceled'})
            rec.message_post(body='Inspection canceled.')
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_view_findings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Findings',
            'res_model': 'hse.finding',
            'view_mode': 'tree,form',
            'domain': [('inspection_id', '=', self.id)],
            'context': {'default_inspection_id': self.id},
        }

    def action_view_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Corrective Actions',
            'res_model': 'hse.corrective.action',
            'view_mode': 'tree,kanban,form',
            'domain': [('inspection_id', '=', self.id)],
            'context': {'default_inspection_id': self.id},
        }
