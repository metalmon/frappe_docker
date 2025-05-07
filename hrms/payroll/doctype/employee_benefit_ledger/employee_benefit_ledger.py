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
		if self.transaction_type == "Accrual" or self.accrual_component:
			accrual_component = (
				self.salary_component if self.transaction_type == "Accrual" else self.accrual_component
			)
			accrual_filters = {
				**filters_common,
				"transaction_type": "Accrual",
				"salary_component": accrual_component,
			}
			past_accruals = frappe.db.get_all(
				"Employee Benefit Ledger", filters=accrual_filters, pluck="amount"
			)
			current_amount = (
				self.amount if self.transaction_type == "Accrual" else 0
			)  # Add current amount to accrued benefits if it's an accrual transaction
			self.accrued_benefit = sum(past_accruals) + current_amount

		# Calculate unpaid benefit for all cases
		payout_filters = {**filters_common, "transaction_type": "Payout"}

		if self.transaction_type == "Accrual" or self.accrual_component:
			payout_filters["accrual_component"] = accrual_component
		else:
			payout_filters["salary_component"] = self.salary_component  # Direct payout without accrual

		past_payouts = frappe.db.get_all("Employee Benefit Ledger", filters=payout_filters, pluck="amount")

		current_amount = (
			self.amount if self.transaction_type == "Payout" else 0
		)  # Add current amount if it's a payout transaction
		total_paid = sum(past_payouts) + current_amount
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
		doc = frappe.get_doc(ledger_entry)
		doc.save()
		return ledger_entry

	(
		frappe.qb.from_(EmployeeBenefitLedger)
		.delete()
		.where(EmployeeBenefitLedger.salary_slip == ref_doc.name)
	).run()
