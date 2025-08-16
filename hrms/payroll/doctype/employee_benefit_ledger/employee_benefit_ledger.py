# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class EmployeeBenefitLedger(Document):
	pass


def create_employee_benefit_ledger_entry(ref_doc, args=None, delete=False):
	EmployeeBenefitLedger = frappe.qb.DocType("Employee Benefit Ledger")

	if delete:
		(
			frappe.qb.from_(EmployeeBenefitLedger)
			.delete()
			.where(EmployeeBenefitLedger.salary_slip == ref_doc.name)
		).run()
		return

	components = (args or {}).get("benefit_ledger_components") or []
	if not components:
		return

	base_entry = {
		"doctype": "Employee Benefit Ledger",
		"employee": ref_doc.employee,
		"employee_name": ref_doc.employee_name,
		"company": ref_doc.company,
		"posting_date": ref_doc.posting_date,
		"salary_slip": ref_doc.name,
		"payroll_period": args.get("payroll_period"),
	}

	for component in components:
		entry = base_entry.copy()
		entry.update(
			{
				"salary_component": component.get("salary_component"),
				"amount": component.get("amount"),
				"transaction_type": component.get("transaction_type"),
				"yearly_benefit": component.get("yearly_benefit", 0),
			}
		)

		if not entry["yearly_benefit"]:
			entry["yearly_benefit"] = (
				frappe.db.get_value(
					"Employee Benefit Detail",
					{
						"parent": args.get("salary_structure_assignment"),
						"salary_component": entry["salary_component"],
					},
					"amount",
				)
				or 0
			)

		frappe.get_doc(entry).insert()


def get_max_claim_eligible(employee, payroll_period, benefit_component, current_month_benefit_amount=0):
	payout_method = benefit_component.payout_method
	precision = frappe.get_precision("Employee Benefit Detail", "amount")
	claim_eligible = 0

	amounts = get_benefit_amount(employee, payroll_period, benefit_component.name)
	accrued = flt(amounts.get("Accrual", 0), precision)
	paid = flt(amounts.get("Payout", 0), precision)

	if payout_method == "Accrue per cycle, pay only on claim":
		accrued += current_month_benefit_amount
		if accrued >= paid:
			claim_eligible = flt((accrued - paid), precision)
		else:
			frappe.throw(
				_(
					"Accrued amount {0} is less than paid amount {1} for Benefit {2} in payroll period {3}"
				).format(accrued, paid, benefit_component.name, payroll_period)
			)
	elif payout_method == "Allow claim up to full period limit":
		claim_eligible = benefit_component.amount - paid

	return claim_eligible


def get_benefit_amount(employee, payroll_period, salary_component):
	from collections import defaultdict

	EmployeeBenefitLedger = frappe.qb.DocType("Employee Benefit Ledger")
	query = (
		frappe.qb.from_(EmployeeBenefitLedger)
		.select(EmployeeBenefitLedger.transaction_type, EmployeeBenefitLedger.amount)
		.where(
			(EmployeeBenefitLedger.employee == employee)
			& (EmployeeBenefitLedger.salary_component == salary_component)
			& (EmployeeBenefitLedger.payroll_period == payroll_period)
		)
	)
	result = query.run(as_dict=True)

	amounts = defaultdict(float)
	for row in result:
		amounts[row["transaction_type"]] += row["amount"]

	return amounts
