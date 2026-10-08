from odoo import api, fields, models


class HseInspectionLine(models.Model):
    _name = 'hse.inspection.line'
    _description = 'HSE Inspection Answer Line'
    _order = 'sequence, id'

    inspection_id = fields.Many2one('hse.inspection', string='Inspection', required=True, ondelete='cascade')
    question_id = fields.Many2one('hse.checklist.question', string='Question', required=True, ondelete='restrict')
    sequence = fields.Integer(related='question_id.sequence', store=True, readonly=True)
    question_type = fields.Selection(related='question_id.question_type', store=True, readonly=True)
    is_required = fields.Boolean(related='question_id.is_required', store=True, readonly=True)
    help_text = fields.Char(related='question_id.help_text', readonly=True)
    checklist_id = fields.Many2one(related='inspection_id.checklist_id', store=True, readonly=True)
    inspection_state = fields.Selection(related='inspection_id.state', store=True, readonly=True)

    # Answer fields (UC-08). One family per question type.
    pass_fail = fields.Selection(
        selection=[('pass', 'Pass'), ('fail', 'Fail'), ('na', 'N/A')],
        string='Pass / Fail',
    )
    yes_no = fields.Selection(
        selection=[('yes', 'Yes'), ('no', 'No'), ('na', 'N/A')],
        string='Yes / No',
    )
    number_value = fields.Float(string='Measurement', default=0.0)
    number_set = fields.Boolean(string='Measurement Entered', default=False)
    text_value = fields.Text(string='Text Answer')
    selection_value = fields.Char(string='Selected Option')
    date_value = fields.Date(string='Date Answer')
    attachment = fields.Binary(string='Photo / File', attachment=True)
    attachment_filename = fields.Char(string='Filename')
    notes = fields.Text(string='Notes')

    is_answered = fields.Boolean(string='Answered', compute='_compute_is_answered', store=True)
    answer_display = fields.Char(string='Answer', compute='_compute_answer_display', store=True)

    @api.depends(
        'question_type', 'pass_fail', 'yes_no', 'number_value', 'number_set',
        'text_value', 'selection_value', 'date_value', 'attachment',
    )
    def _compute_is_answered(self):
        for rec in self:
            t = rec.question_type
            if t == 'pass_fail':
                rec.is_answered = rec.pass_fail in ('pass', 'fail', 'na')
            elif t == 'yes_no':
                rec.is_answered = rec.yes_no in ('yes', 'no', 'na')
            elif t == 'numeric':
                rec.is_answered = bool(rec.number_set)
            elif t == 'text':
                rec.is_answered = bool((rec.text_value or '').strip())
            elif t == 'selection':
                rec.is_answered = bool((rec.selection_value or '').strip())
            elif t == 'date':
                rec.is_answered = bool(rec.date_value)
            elif t == 'file':
                # Evidence itself is the answer; notes alone do not count.
                rec.is_answered = bool(rec.attachment)
            else:
                rec.is_answered = False

    @api.depends(
        'question_type', 'pass_fail', 'yes_no', 'number_value',
        'text_value', 'selection_value', 'date_value', 'attachment_filename',
    )
    def _compute_answer_display(self):
        for rec in self:
            t = rec.question_type
            if t == 'pass_fail':
                rec.answer_display = dict(rec._fields['pass_fail'].selection).get(rec.pass_fail, '')
            elif t == 'yes_no':
                rec.answer_display = dict(rec._fields['yes_no'].selection).get(rec.yes_no, '')
            elif t == 'numeric':
                rec.answer_display = str(rec.number_value) if rec.number_set else ''
            elif t == 'text':
                rec.answer_display = (rec.text_value or '')[:200]
            elif t == 'selection':
                rec.answer_display = rec.selection_value or ''
            elif t == 'date':
                rec.answer_display = str(rec.date_value) if rec.date_value else ''
            elif t == 'file':
                rec.answer_display = rec.attachment_filename or ('Attached' if rec.attachment else '')
            else:
                rec.answer_display = ''

    @api.onchange('number_value')
    def _onchange_number_value(self):
        # Any manual edit counts as "entered", so 0.0 remains a valid measurement.
        self.number_set = True

    def get_comparable_value(self):
        """Normalized string used by the rules engine for equals/contains comparisons."""
        self.ensure_one()
        t = self.question_type
        if t == 'pass_fail':
            return (self.pass_fail or '').lower()
        if t == 'yes_no':
            return (self.yes_no or '').lower()
        if t == 'numeric':
            return str(self.number_value)
        if t == 'text':
            return (self.text_value or '').strip()
        if t == 'selection':
            return (self.selection_value or '').strip()
        if t == 'date':
            return str(self.date_value) if self.date_value else ''
        if t == 'file':
            return 'attached' if self.attachment else ''
        return self.answer_display or ''
