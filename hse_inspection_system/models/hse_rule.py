from odoo import api, fields, models
from odoo.exceptions import ValidationError


OPERATORS = [
    ('equals', 'Equals'),
    ('not_equals', 'Not Equals'),
    ('contains', 'Contains'),
    ('not_contains', 'Does Not Contain'),
    ('greater_than', 'Greater Than (>)'),
    ('less_than', 'Less Than (<)'),
    ('greater_equal', 'Greater or Equal (>=)'),
    ('less_equal', 'Less or Equal (<=)'),
    ('is_empty', 'Is Empty / Unanswered'),
    ('is_not_empty', 'Is Not Empty / Answered'),
]


class HseRule(models.Model):
    _name = 'hse.rule'
    _description = 'HSE Business Rule (IF conditions THEN actions)'
    _order = 'checklist_id, name'

    name = fields.Char(string='Rule Name', required=True)
    checklist_id = fields.Many2one(
        'hse.checklist', string='Checklist',
        help='Leave empty to apply this rule to ALL checklists.',
        ondelete='cascade',
    )
    apply_on = fields.Selection(
        selection=[('any', 'ANY condition matches'), ('all', 'ALL conditions match')],
        string='Match When', default='any', required=True,
    )
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')
    condition_ids = fields.One2many('hse.rule.condition', 'rule_id', string='Conditions (IF)')
    action_ids = fields.One2many('hse.rule.action', 'rule_id', string='Actions (THEN)')
    triggered_count = fields.Integer(string='Times Triggered', default=0, readonly=True)

    @api.constrains('condition_ids', 'action_ids')
    def _check_conditions_actions(self):
        for rec in self:
            if not rec.condition_ids:
                raise ValidationError('Rule "%s" needs at least one condition.' % rec.name)
            if not rec.action_ids:
                raise ValidationError('Rule "%s" needs at least one action.' % rec.name)

    # ------------------------------------------------------------------
    # Engine entry point — called from hse.inspection.action_complete()
    # Contract: evaluate_inspection(inspection_recordset)
    # ------------------------------------------------------------------
    @api.model
    def evaluate_inspection(self, inspection):
        """Evaluate all applicable rules for an inspection and execute actions."""
        if not inspection or not inspection.exists():
            return []
        Rule = self.env['hse.rule']
        rules = Rule.search([
            ('active', '=', True),
            '|', ('checklist_id', '=', False), ('checklist_id', '=', inspection.checklist_id.id),
        ])
        triggered_rules = []
        lines_by_question = {l.question_id.id: l for l in inspection.line_ids}
        for rule in rules:
            results = []
            for cond in rule.condition_ids:
                line = lines_by_question.get(cond.question_id.id)
                results.append((cond, line, cond.evaluate(line)))
            matched = (
                any(r for _, _, r in results) if rule.apply_on == 'any'
                else (bool(results) and all(r for _, _, r in results))
            )
            if matched:
                rule._execute_actions(inspection, results)
                rule.sudo().write({'triggered_count': rule.triggered_count + 1})
                triggered_rules.append(rule)
        return triggered_rules

    def _execute_actions(self, inspection, evaluated):
        """Create findings / corrective actions / notifications for a matched rule."""
        triggering = [(c, l) for c, l, ok in evaluated if ok and l]
        if not triggering:
            # Rule matched on empty-answer conditions without a line — attach to inspection generally.
            triggering = [(c, None) for c, l, ok in evaluated if ok]
        for action in self.action_ids:
            if action.action_type == 'notify':
                action._do_notify(inspection, triggering)
            elif action.action_type in ('create_finding', 'create_action'):
                for cond, line in triggering:
                    finding = action._ensure_finding(inspection, self, cond, line)
                    if action.action_type == 'create_action':
                        action._ensure_corrective_action(finding, inspection)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def test_rule_on_inspection(self, inspection_id):
        inspection = self.env['hse.inspection'].browse(inspection_id)
        return bool(self.evaluate_inspection(inspection))


class HseRuleCondition(models.Model):
    _name = 'hse.rule.condition'
    _description = 'HSE Rule Condition (IF part)'

    rule_id = fields.Many2one('hse.rule', string='Rule', required=True, ondelete='cascade')
    # Note: no static domain here so global rules (checklist_id=False) can still
    # pick questions from any checklist; the form view guides selection.
    question_id = fields.Many2one(
        'hse.checklist.question', string='Question', required=True, ondelete='cascade',
    )
    operator = fields.Selection(selection=OPERATORS, string='Operator', default='equals', required=True)
    value_target = fields.Char(
        string='Expected Value',
        help='For Pass/Fail use pass/fail, for Yes/No use yes/no, for numeric use a number, '
             'for text/selection use the text to compare.',
    )

    def evaluate(self, line):
        """Return True when this condition matches the given inspection line (or lack of one)."""
        self.ensure_one()
        op = self.operator
        if op == 'is_empty':
            return (not line) or (not line.is_answered)
        if op == 'is_not_empty':
            return bool(line) and bool(line.is_answered)
        if not line or not line.is_answered:
            return False
        actual = line.get_comparable_value() or ''
        expected = (self.value_target or '').strip()
        actual_cmp = actual.strip().lower()
        expected_cmp = expected.lower()
        if op in ('equals', 'not_equals'):
            result = actual_cmp == expected_cmp
            return result if op == 'equals' else not result
        if op in ('contains', 'not_contains'):
            result = expected_cmp in actual_cmp
            return result if op == 'contains' else not result
        # Numeric comparisons
        try:
            actual_num = float(actual.strip())
            expected_num = float(expected)
        except (ValueError, TypeError):
            return False
        if op == 'greater_than':
            return actual_num > expected_num
        if op == 'less_than':
            return actual_num < expected_num
        if op == 'greater_equal':
            return actual_num >= expected_num
        if op == 'less_equal':
            return actual_num <= expected_num
        return False


class HseRuleAction(models.Model):
    _name = 'hse.rule.action'
    _description = 'HSE Rule Action (THEN part)'
    _order = 'sequence, id'

    rule_id = fields.Many2one('hse.rule', string='Rule', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    action_type = fields.Selection(
        selection=[
            ('create_finding', 'Create Finding'),
            ('create_action', 'Create Finding + Corrective Action'),
            ('notify', 'Send Notification / Chatter Alert'),
        ],
        string='Action', default='create_finding', required=True,
    )
    severity = fields.Selection(
        selection=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')],
        string='Finding Severity', default='medium',
    )
    priority = fields.Selection(
        selection=[('0', 'Low'), ('1', 'Medium'), ('2', 'High'), ('3', 'Urgent')],
        string='Action Priority', default='1',
    )
    responsible_id = fields.Many2one('res.users', string='Assign To (user)')
    due_days = fields.Integer(string='Due In (days)', default=7)
    message = fields.Text(
        string='Message / Finding Description',
        help='Used as finding description and notification body. Leave empty for an auto-generated text.',
    )

    # ------------------------------------------------------------------
    # Action executors
    # ------------------------------------------------------------------
    def _finding_values(self, inspection, rule, condition, line):
        question = condition.question_id if condition else (line.question_id if line else False)
        base_msg = (self.message or '').strip()
        if not base_msg:
            base_msg = 'Rule "%s" triggered by answer "%s" to question "%s".' % (
                rule.name,
                line.answer_display if line else '(no answer)',
                question.name if question else '(unknown question)',
            )
        return {
            'name': 'Finding: %s' % (question.name[:60] if question else rule.name[:60]),
            'inspection_id': inspection.id,
            'inspection_line_id': line.id if line else False,
            'question_id': question.id if question else False,
            'rule_id': rule.id,
            'description': base_msg,
            'severity': self.severity or 'medium',
        }

    def _ensure_finding(self, inspection, rule, condition, line):
        """Create the finding unless the same rule/question/inspection already produced one."""
        Finding = self.env['hse.finding']
        domain = [
            ('inspection_id', '=', inspection.id),
            ('rule_id', '=', rule.id),
        ]
        if line and line.question_id:
            domain.append(('question_id', '=', line.question_id.id))
            if line.id:
                # Prefer exact line match to avoid duplicates on re-evaluation.
                existing = Finding.search(domain + [('inspection_line_id', '=', line.id)], limit=1)
                if existing:
                    return existing
        else:
            existing = Finding.search(domain, limit=1)
            if existing:
                return existing
        finding = Finding.create(self._finding_values(inspection, rule, condition, line))
        inspection.message_post(
            body='Rule <b>%s</b> created finding <b>%s</b> (severity: %s).' % (
                rule.name, finding.reference or finding.name, finding.severity)
        )
        return finding

    def _ensure_corrective_action(self, finding, inspection):
        Action = self.env['hse.corrective.action']
        existing = Action.search([('finding_id', '=', finding.id)], limit=1)
        if existing:
            return existing
        due = False
        if self.due_days:
            due = fields.Date.add(fields.Date.context_today(self), days=self.due_days)
        responsible = self.responsible_id
        if not responsible and finding.inspection_id.inspector_id.user_id:
            responsible = finding.inspection_id.inspector_id.user_id
        action = Action.create({
            'name': 'Corrective action for %s' % (finding.reference or finding.name),
            'finding_id': finding.id,
            'description': self.message or finding.description,
            'responsible_id': responsible.id if responsible else False,
            'date_due': due,
            'priority': self.priority or '1',
        })
        return action

    def _do_notify(self, inspection, triggering):
        body = (self.message or '').strip() or 'Rule <b>%s</b> triggered.' % self.rule_id.name
        details = '<ul>%s</ul>' % ''.join(
            '<li>%s: <b>%s</b></li>' % (
                (c.question_id.name if c and c.question_id else '?'),
                (l.answer_display if l else '(no answer)'),
            ) for c, l in triggering
        )
        inspection.message_post(body='%s<br/>%s' % (body, details))
        # Also notify followers / responsible via activity if a user is set.
        if self.responsible_id:
            inspection.activity_schedule(
                'mail.mail_activity_data_todo',
                summary='HSE rule triggered: %s' % self.rule_id.name,
                note=body,
                user_id=self.responsible_id.id,
            )
        return True
