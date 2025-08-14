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
	if not delete:
		if args.get("benefit_ledger_components"):
			ledger_entry = frappe._dict(
				doctype="Employee Benefit Ledger",
				employee=ref_doc.employee,
				employee_name=ref_doc.employee_name,
				company=ref_doc.company,
				posting_date=ref_doc.posting_date,
				salary_slip=ref_doc.name,
				payroll_period=args.get("payroll_period"),
			)
			for component in args.get("benefit_ledger_components"):
				args["salary_component"] = component.get("salary_component")
				args["amount"] = component.get("amount")
				args["transaction_type"] = component.get("transaction_type")
				args["yearly_benefit"] = component.get("yearly_benefit", 0)
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
		return
	(
		frappe.qb.from_(EmployeeBenefitLedger)
		.delete()
		.where(EmployeeBenefitLedger.salary_slip == ref_doc.name)
	).run()


def get_max_claim_eligible(employee, payroll_period, benefit_component):
	payout_method = benefit_component.payout_method
	precision = frappe.get_precision("Employee Benefit Detail", "amount")
	claim_eligible = 0
	if payout_method == "Accrue per cycle, pay only on claim":
		accrued = get_benefit_amount(employee, payroll_period, benefit_component.name, "Accrual")
		paid = get_benefit_amount(employee, payroll_period, benefit_component.name, "Payout")
		if accrued >= paid:
			claim_eligible = flt((accrued - paid), precision)
		else:
			frappe.throw(
				_(
					"Accrued amount {0} is less than paid amount {1} for Benefit {2} in payroll period {3}"
				).format(accrued, paid, benefit_component.name, payroll_period)
			)
	elif payout_method == "Allow claim up to full period limit":
		claim_eligible = benefit_component.amount

	return claim_eligible


def get_benefit_amount(employee, payroll_period, salary_component, transaction_type):
	from frappe.query_builder.functions import Sum

	EmployeeBenefitLedger = frappe.qb.DocType("Employee Benefit Ledger")
	query = (
		frappe.qb.from_(EmployeeBenefitLedger)
		.select(Sum(EmployeeBenefitLedger.amount).as_("total"))
		.where(
			(EmployeeBenefitLedger.employee == employee)
			& (EmployeeBenefitLedger.salary_component == salary_component)
			& (EmployeeBenefitLedger.transaction_type == transaction_type)
			& (EmployeeBenefitLedger.payroll_period == payroll_period)
		)
	)
	result = query.run(as_dict=True)
	return flt(result[0].get("total"), 2) or 0
