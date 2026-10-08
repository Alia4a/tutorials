from odoo import api, fields, models
from odoo.exceptions import ValidationError


QUESTION_TYPES = [
    ('pass_fail', 'Pass / Fail'),
    ('yes_no', 'Yes / No'),
    ('numeric', 'Numeric Measurement'),
    ('text', 'Text'),
    ('selection', 'Selection (list)'),
    ('date', 'Date'),
    ('file', 'Photo / File Evidence'),
]


class HseChecklistQuestion(models.Model):
    _name = 'hse.checklist.question'
    _description = 'HSE Checklist Dynamic Question'
    _order = 'checklist_id, sequence, id'

    name = fields.Char(string='Question', required=True)
    checklist_id = fields.Many2one('hse.checklist', string='Checklist', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    question_type = fields.Selection(selection=QUESTION_TYPES, string='Answer Type', default='pass_fail', required=True)
    is_required = fields.Boolean(string='Mandatory', default=True)
    selection_options = fields.Char(
        string='Selection Options',
        help='Comma-separated options, used only when Answer Type is Selection. e.g. "Good, Damaged, Missing"',
    )
    min_value = fields.Float(string='Min Value (numeric)')
    max_value = fields.Float(string='Max Value (numeric)')
    has_min_max = fields.Boolean(string='Enforce Min/Max', default=False)
    help_text = fields.Char(string='Help / Guidance')
    active = fields.Boolean(string='Active', default=True)

    @api.constrains('selection_options', 'question_type')
    def _check_selection_options(self):
        for rec in self:
            if rec.question_type == 'selection' and not (rec.selection_options or '').strip():
                raise ValidationError('Selection questions require comma-separated Selection Options.')

    @api.constrains('min_value', 'max_value', 'has_min_max')
    def _check_min_max(self):
        for rec in self:
            if rec.has_min_max and rec.max_value < rec.min_value:
                raise ValidationError('Max Value cannot be lower than Min Value.')

    def get_selection_list(self):
        self.ensure_one()
        if not self.selection_options:
            return []
        return [o.strip() for o in self.selection_options.split(',') if o.strip()]
