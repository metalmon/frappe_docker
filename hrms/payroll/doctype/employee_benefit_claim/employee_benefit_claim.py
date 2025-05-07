# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from hrms.hr.utils import get_previous_claimed_amount, validate_active_employee
from hrms.payroll.doctype.employee_benefit_application.employee_benefit_application import get_max_benefits
from hrms.payroll.doctype.payroll_period.payroll_period import get_payroll_period
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	get_assigned_salary_structure,
)


class EmployeeBenefitClaim(Document):
	def validate(self):
		validate_active_employee(self.employee)
		self.get_benefit_details()
		self.validate_benefit_claim_amount()

	def on_submit(self):
		self.create_additional_salary()

	def validate_benefit_claim_amount(self):
		if self.claimed_amount <= 0:
			frappe.throw(_("Claimed amount of employee {0} should be greater than 0").format(self.employee))

		if self.claimed_amount > self.max_amount_eligible:
			frappe.throw(
				_("Claimed amount of employee {0} exceeds the maximum amount eligible {1}").format(
					self.employee, self.max_amount_eligible
				)
			)

	def create_additional_salary(self):
		frappe.get_doc(
			{
				"doctype": "Additional Salary",
				"company": self.company,
				"employee": self.employee,
				"currency": self.currency,
				"salary_component": self.earning_component,
				"payroll_date": self.payroll_date,
				"amount": self.claimed_amount,
				"overwrite_salary_structure_amount": 0,
				"ref_doctype": self.doctype,
				"ref_docname": self.name,
			}
		).submit()

	@frappe.whitelist()
	def get_benefit_details(self):
		self.payroll_period = get_payroll_period(self.payroll_date, self.payroll_date, self.company)
		if not self.payroll_period:
			frappe.throw(
				_("{0} is not in a valid Payroll Period").format(
					frappe.format(self.claim_date, dict(fieldtype="Date"))
				)
			)
		self.yearly_benefit = 0
		self.accrued_benefit = 0
		self.paid_benefit = 0

		latest_benefit_ledger = frappe.db.get_all(
			"Employee Benefit Ledger",
			filters={
				"employee": self.employee,
				"payroll_period": self.payroll_period.name,
				"salary_component": self.earning_component,
			},
			fields=["yearly_benefit", "accrued_benefit", "paid_benefit"],
			order_by="posting_date desc",
			limit=1,
		)

		if latest_benefit_ledger:
			entry = latest_benefit_ledger[0]
			self.yearly_benefit = entry.yearly_benefit or 0
			self.accrued_benefit = entry.accrued_benefit or 0
			self.paid_benefit = entry.paid_benefit or 0
		else:
			self.yearly_benefit = get_benefit_amount(self.employee, self.payroll_date, self.earning_component)

		if self.pay_against_benefit_claim:
			self.max_amount_eligible = self.yearly_benefit - self.paid_benefit
		else:
			self.max_amount_eligible = self.accrued_benefit - self.paid_benefit


@frappe.whitelist()
def get_benefit_components(doctype, txt, searchfield, start, page_len, filters):
	employee = filters.get("employee")
	date = filters.get("date")
	if not employee or not date:
		return []

	assigned_salary_structure = get_salary_structure_assignment(employee, date)

	EmployeeBenefitDetail = frappe.qb.DocType("Employee Benefit Detail")
	SalaryComponent = frappe.qb.DocType("Salary Component")

	components = (
		frappe.qb.from_(EmployeeBenefitDetail)
		.join(SalaryComponent)
		.on(SalaryComponent.name == EmployeeBenefitDetail.salary_component)
		.select(EmployeeBenefitDetail.salary_component)
		.where(EmployeeBenefitDetail.parent == assigned_salary_structure)
		.where((SalaryComponent.pay_against_benefit_claim == 1) | (SalaryComponent.is_accrual == 1))
	).run(as_dict=True)

	return [(row.salary_component,) for row in components]


def get_benefit_amount(employee, date, salary_component):
	if not employee or not date:
		return 0

	assigned_salary_structure = get_salary_structure_assignment(employee, date)

	EmployeeBenefitDetail = frappe.qb.DocType("Employee Benefit Detail")
	result = (
		frappe.qb.from_(EmployeeBenefitDetail)
		.select(EmployeeBenefitDetail.yearly_amount)
		.where(EmployeeBenefitDetail.salary_component == salary_component)
		.where(EmployeeBenefitDetail.parent == assigned_salary_structure)
	).run(pluck="yearly_amount")

	return result[0] if result else 0


def get_salary_structure_assignment(employee, date):
	SalaryStructureAssignment = frappe.qb.DocType("Salary Structure Assignment")
	result = (
		frappe.qb.from_(SalaryStructureAssignment)
		.select(SalaryStructureAssignment.name)
		.where(SalaryStructureAssignment.employee == employee)
		.where(SalaryStructureAssignment.docstatus == 1)
		.where(SalaryStructureAssignment.from_date <= date)
		.orderby(SalaryStructureAssignment.from_date, order=frappe.qb.desc)
		.limit(1)
	).run(pluck="name")

	if not result:
		frappe.throw(
			_("Salary Structure Assignment not found for employee {0} on date {1}").format(employee, date)
		)

	return result[0]
