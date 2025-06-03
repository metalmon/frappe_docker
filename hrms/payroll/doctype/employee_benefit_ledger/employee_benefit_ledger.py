# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeBenefitLedger(Document):
	pass


def create_employee_benefit_ledger_entry(ref_doc, args=None, delete=False):
	EmployeeBenefitLedger = frappe.qb.DocType("Employee Benefit Ledger")
	if not delete:
		ledger_entry = frappe._dict(
			doctype="Employee Benefit Ledger",
			employee=ref_doc.employee,
			employee_name=ref_doc.employee_name,
			company=ref_doc.company,
			posting_date=ref_doc.posting_date,
			salary_slip=ref_doc.name,
		)
		ledger_entry.update(args)
		if not args.get("yearly_benefit"):
			ledger_entry.yearly_benefit = (
				frappe.db.get_value(
					"Employee Benefit Detail",
					{
						"parent": args.get("salary_structure_assignment"),
						"salary_component": args.get("salary_component"),
					},
					"amount",
				)
				or 0
			)
		doc = frappe.get_doc(ledger_entry)
		doc.insert()
		return ledger_entry
	(
		frappe.qb.from_(EmployeeBenefitLedger)
		.delete()
		.where(EmployeeBenefitLedger.salary_slip == ref_doc.name)
	).run()
