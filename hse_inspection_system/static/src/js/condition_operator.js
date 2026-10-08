/* Hide invalid rule-condition operators based on the question type.
 *
 * Boolean-like questions (pass_fail, yes_no) only support exact match
 * and empty checks. Other operators (contains, numeric comparisons)
 * are removed from the dropdown for those rows.
 *
 * The view must include the invisible `question_type` field in the same
 * row so `recordData.question_type` is available.
 */
odoo.define('hse_inspection_system.condition_operator', function (require) {
    'use strict';

    var BasicFields = require('web.basic_fields');
    var fieldRegistry = require('web.field_registry');

    var ALLOWED_BY_TYPE = {
        pass_fail: ['equals', 'not_equals', 'is_empty', 'is_not_empty'],
        yes_no: ['equals', 'not_equals', 'is_empty', 'is_not_empty'],
        numeric: ['equals', 'not_equals', 'greater_than', 'less_than', 'greater_equal', 'less_equal', 'is_empty', 'is_not_empty'],
        text: ['equals', 'not_equals', 'contains', 'not_contains', 'is_empty', 'is_not_empty'],
        selection: ['equals', 'not_equals', 'contains', 'not_contains', 'is_empty', 'is_not_empty'],
        date: ['equals', 'not_equals', 'greater_than', 'less_than', 'greater_equal', 'less_equal', 'is_empty', 'is_not_empty'],
        file: ['is_empty', 'is_not_empty'],
    };

    var HseConditionOperator = BasicFields.FieldSelection.extend({
        _renderEdit: function () {
            this._super.apply(this, arguments);
            try {
                var qtype = this.recordData && this.recordData.question_type;
                var allowed = ALLOWED_BY_TYPE[qtype];
                if (!allowed) {
                    return;
                }
                var self = this;
                this.$el.find('option').each(function () {
                    var val = $(this).attr('value');
                    // Keep the empty placeholder option (value "" / false).
                    if (!val) {
                        return;
                    }
                    if (allowed.indexOf(val) === -1) {
                        $(this).remove();
                    }
                });
                // If the current value became invalid, switch to the first allowed one.
                var current = self.value;
                if (current && allowed.indexOf(current) === -1) {
                    self._setValue(allowed[0]);
                }
            } catch (e) {
                // Never break the form if recordData is unexpected.
                console.warn('[hse] operator filter skipped:', e);
            }
        },
    });

    fieldRegistry.add('hse_condition_operator', HseConditionOperator);

    return HseConditionOperator;
});
