# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeBenefitLedger(Document):
	def before_save(self):
		self.accrued_benefit = 0
		self.unpaid_benefit = 0

		filters_common = {"employee": self.employee, "payroll_period": self.payroll_period}

		# Calculate accrued benefits if applicable
		if self.is_accrual_component or self.transaction_type == "Accrual":
			accrual_filters = {
				**filters_common,
				"transaction_type": "Accrual",
				"salary_component": self.salary_component,
			}
			past_accruals = frappe.db.get_all(
				"Employee Benefit Ledger", filters=accrual_filters, pluck="amount"
			)
			# Add current amount to accrued benefits if it's an accrual transaction
			current_amount = self.amount if self.transaction_type == "Accrual" else 0
			self.accrued_benefit = sum(past_accruals) + current_amount

		# Calculate paid benefit for all cases
		payout_filters = {
			**filters_common,
			"transaction_type": "Payout",
			"salary_component": self.salary_component,
		}
		past_payouts = frappe.db.get_all("Employee Benefit Ledger", filters=payout_filters, pluck="amount")
		current_amount = self.amount if self.transaction_type == "Payout" else 0
		total_paid = sum(past_payouts) + current_amount

		self.paid_benefit = total_paid
		self.unpaid_benefit = self.yearly_benefit - total_paid


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
					"yearly_amount",
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
