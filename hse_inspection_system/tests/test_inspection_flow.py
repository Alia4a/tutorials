from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHseInspectionFlow(TransactionCase):
    def _make_checklist(self):
        checklist = self.env['hse.checklist'].create({
            'name': 'Test Machine Safety',
            'category': 'machine_safety',
            'state': 'active',
        })
        self.q_estop = self.env['hse.checklist.question'].create({
            'name': 'Emergency Stop',
            'checklist_id': checklist.id,
            'sequence': 10,
            'question_type': 'pass_fail',
            'is_required': True,
        })
        self.q_notes = self.env['hse.checklist.question'].create({
            'name': 'Notes',
            'checklist_id': checklist.id,
            'sequence': 20,
            'question_type': 'text',
            'is_required': False,
        })
        rule = self.env['hse.rule'].create({
            'name': 'EStop fail rule',
            'checklist_id': checklist.id,
            'apply_on': 'any',
        })
        self.env['hse.rule.condition'].create({
            'rule_id': rule.id,
            'question_id': self.q_estop.id,
            'operator': 'equals',
            'value_target': 'fail',
        })
        self.env['hse.rule.action'].create({
            'rule_id': rule.id,
            'action_type': 'create_action',
            'severity': 'critical',
            'priority': '3',
            'due_days': 3,
        })
        return checklist

    def test_lines_generated_on_start(self):
        checklist = self._make_checklist()
        insp = self.env['hse.inspection'].create({'checklist_id': checklist.id})
        insp.action_start()
        self.assertEqual(insp.state, 'in_progress')
        self.assertEqual(len(insp.line_ids), 2)
        self.assertEqual(
            set(insp.line_ids.mapped('question_id.id')),
            {self.q_estop.id, self.q_notes.id},
        )

    def test_required_validation(self):
        checklist = self._make_checklist()
        insp = self.env['hse.inspection'].create({'checklist_id': checklist.id})
        insp.action_start()
        with self.assertRaises(ValidationError):
            insp.action_complete()

    def test_fail_triggers_finding_and_action(self):
        checklist = self._make_checklist()
        insp = self.env['hse.inspection'].create({'checklist_id': checklist.id})
        insp.action_start()
        estop_line = insp.line_ids.filtered(lambda l: l.question_id == self.q_estop)
        estop_line.write({'pass_fail': 'fail'})
        insp.action_complete()
        self.assertEqual(insp.state, 'completed')
        self.assertEqual(len(insp.finding_ids), 1)
        finding = insp.finding_ids[0]
        self.assertEqual(finding.severity, 'critical')
        self.assertEqual(len(finding.action_ids), 1)
        # CAPA lifecycle: open (created) -> in_progress auto? finding moves to in_progress on action create
        action = finding.action_ids[0]
        action.write({'responsible_id': self.env.user.id})
        action.action_start()
        action.write({'resolution_notes': 'Replaced E-Stop button, tested OK.'})
        action.action_resolve()
        action.action_verify()
        action.action_close()
        self.assertEqual(action.state, 'closed')
        self.assertEqual(finding.state, 'closed')
