{
    'name': "HSE Inspection System",
    'summary': "Health, Safety & Environment Inspection, dynamic checklists, rules engine, findings and corrective actions",
    'description': """
HSE Inspection & Dynamic Checklist Prototype (Odoo 15)
=====================================================
* Dynamic checklist & question configuration (UC-01..UC-04)
* Inspection execution with validation & evidence (UC-07..UC-11)
* Configurable IF-THEN rules engine (UC-05/UC-06, UC-12..UC-14)
* Findings & corrective action lifecycle (UC-15..UC-19)
* KPI dashboard & PDF audit reports (UC-20/UC-21)

Implements the technical plan in
``hse_inspection_plan.md`` (brain 28e687b9-8a2e-46c5-b2bb-908b93c6091b).
Design reuses Odoo CE patterns from ``survey`` (dynamic questions),
``base_automation`` (rules engine), OCA ``mgmtsystem_action /
mgmtsystem_nonconformity`` (CAPA lifecycle) and core
``maintenance`` / ``hr`` / ``mail`` models.
    """,
    'author': "HSE Prototype Team",
    'website': "",
    'category': "Health and Safety",
    'version': "15.0.1.0.0",
    'license': "LGPL-3",
    'application': True,
    'installable': True,
    'depends': ['base', 'mail', 'hr', 'maintenance'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/hse_sequence_data.xml',
        'data/mail_template_data.xml',
        'views/hse_checklist_views.xml',
        'views/hse_inspection_views.xml',
        'views/hse_rule_views.xml',
        'views/hse_finding_views.xml',
        'views/hse_corrective_action_views.xml',
        'views/hse_dashboard_views.xml',
        'views/menu_views.xml',
        'report/reports.xml',
        'report/inspection_report_templates.xml',
        'demo/demo_data.xml',
    ],
    'demo': [],
    'assets': {
        'web.assets_backend': [
            'hse_inspection_system/static/src/js/condition_operator.js',
        ],
    },
}
