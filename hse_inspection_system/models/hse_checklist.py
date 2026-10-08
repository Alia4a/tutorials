from odoo import api, fields, models


class HseChecklist(models.Model):
    _name = 'hse.checklist'
    _description = 'HSE Inspection Checklist Template'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Checklist Name', required=True, tracking=True)
    code = fields.Char(string='Code', copy=False)
    category = fields.Selection(
        selection=[
            ('machine_safety', 'Machine Safety'),
            ('fire_safety', 'Fire Safety'),
            ('electrical', 'Electrical Safety'),
            ('environmental', 'Environmental'),
            ('general', 'General HSE'),
            ('other', 'Other'),
        ],
        string='Category', default='general', required=True, tracking=True,
    )
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('active', 'Active'), ('archived', 'Archived')],
        string='Status', default='draft', required=True, tracking=True,
    )
    question_ids = fields.One2many('hse.checklist.question', 'checklist_id', string='Questions')
    inspection_ids = fields.One2many('hse.inspection', 'checklist_id', string='Inspections')
    rule_ids = fields.One2many('hse.rule', 'checklist_id', string='Rules')

    question_count = fields.Integer(string='Questions', compute='_compute_counts', store=True)
    inspection_count = fields.Integer(string='Inspections', compute='_compute_counts', store=True)

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'Checklist name must be unique.'),
    ]

    @api.depends('question_ids', 'inspection_ids')
    def _compute_counts(self):
        for rec in self:
            rec.question_count = len(rec.question_ids)
            rec.inspection_count = len(rec.inspection_ids)

    def action_activate(self):
        self.write({'state': 'active', 'active': True})
        return True

    def action_archive_checklist(self):
        self.write({'state': 'archived', 'active': False})
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        return True
