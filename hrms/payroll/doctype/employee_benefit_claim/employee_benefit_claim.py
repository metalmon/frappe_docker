# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form, getdate

from hrms.payroll.doctype.payroll_period.payroll_period import get_payroll_period
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	get_assigned_salary_structure,
)


class EmployeeBenefitClaim(Document):
	def validate(self):
		self.validate_date_and_benefit_claim_amount()
		self.validate_duplicate_claim()

	def validate_date_and_benefit_claim_amount(self):
		if getdate(self.payroll_date) < getdate():
			frappe.throw(
				_(
					"Payroll date cannot be in the past. This is to ensure that claims are made for the current or future payroll cycles."
				)
			)

		if self.claimed_amount <= 0:
			frappe.throw(_("Claimed amount of employee {0} should be greater than 0").format(self.employee))

		if self.claimed_amount > self.max_amount_eligible:
			frappe.throw(
				_("Claimed amount of employee {0} exceeds maximum amount eligible for claim {1}").format(
					self.employee, self.max_amount_eligible
				)
			)

	def validate_duplicate_claim(self):
		"""
		Since Employee Benefit Ledger entries are only created upon Salary Slip submission, there is a risk of mulitple claims being created for the same benefit component within one payroll cycle, and combined claim amount exceeding the maximum eligible amount. So limit the claim to one per month or payroll cycle.
		"""
		month_start_date = frappe.utils.get_first_day(self.payroll_date)
		month_end_date = frappe.utils.get_last_day(self.payroll_date)
		existing_benefit_claim = frappe.db.get_value(
			"Employee Benefit Claim",
			{
				"employee": self.employee,
				"earning_component": self.earning_component,
				"payroll_date": ["between", [month_start_date, month_end_date]],
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing_benefit_claim:
			msg = _(
				"Employee {0} has already claimed the benefit '{1}' for {2} ({3}).<br>To prevent overpayments, only one claim per benefit type is allowed in each payroll cycle."
			).format(
				frappe.bold(self.employee),
				frappe.bold(self.earning_component),
				frappe.bold(frappe.utils.formatdate(self.payroll_date, "MMMM yyyy")),
				frappe.bold(get_link_to_form("Employee Benefit Claim", existing_benefit_claim)),
			)
			frappe.throw(msg, title=_("Duplicate Claim Detected"))

	def on_submit(self):
		self.create_additional_salary()

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
		# Fetch amx benefit amount and claimable amount for the employee based on the earning component chosen
		from hrms.payroll.doctype.employee_benefit_ledger.employee_benefit_ledger import (
			get_max_claim_eligible,
		)

		payroll_period = get_payroll_period(self.payroll_date, self.payroll_date, self.company).get("name")
		assigned_salary_structure = get_assigned_salary_structure(self.employee, self.payroll_date)

		yearly_benefit = 0
		claimable_benefit = 0
		current_month_amount = 0

		EmployeeBenefitDetail = frappe.qb.DocType("Employee Benefit Detail")
		SalaryComponent = frappe.qb.DocType("Salary Component")
		component_details = (
			frappe.qb.from_(EmployeeBenefitDetail)
			.join(SalaryComponent)
			.on(SalaryComponent.name == EmployeeBenefitDetail.salary_component)
			.select(
				SalaryComponent.name,
				SalaryComponent.payout_method,
				SalaryComponent.depends_on_payment_days,
				EmployeeBenefitDetail.amount,
			)
			.where(SalaryComponent.name == self.earning_component)
			.where(EmployeeBenefitDetail.parent == assigned_salary_structure)
		).run(as_dict=True)
		if component_details:
			component_details = component_details[0]
			current_month_amount = self.preview_salary_slip_and_fetch_current_month_benefit_amount()
			yearly_benefit = component_details.get("amount", 0)
			claimable_benefit = get_max_claim_eligible(
				self.employee, payroll_period, component_details, current_month_amount
			)

		self.yearly_benefit = yearly_benefit
		self.max_amount_eligible = claimable_benefit

	def preview_salary_slip_and_fetch_current_month_benefit_amount(self):
		from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

		payout_method = frappe.get_cached_value("Salary Component", self.earning_component, "payout_method")
		calculate_current_month_benefit_amount = payout_method == "Accrue per cycle, pay only on claim"
		current_month_amount = 0

		if calculate_current_month_benefit_amount:
			salary_structure = get_assigned_salary_structure(self.employee, self.payroll_date)
			if not salary_structure:
				frappe.throw(
					_("No salary structure assigned for employee {0} on date {1}").format(
						self.employee, self.payroll_date
					)
				)
			ss = make_salary_slip(
				salary_structure, employee=self.employee, posting_date=self.payroll_date, for_preview=1
			)
			accrued_benefits = ss.get("accrued_benefits", [])
			for benefit in accrued_benefits:
				if benefit.get("salary_component") == self.earning_component:
					current_month_amount = benefit.get("amount", 0)
					break

		return current_month_amount


@frappe.whitelist()
def get_benefit_components(doctype, txt, searchfield, start, page_len, filters):
	# Fetch benefit components to choose from based on employee and date filters
	employee = filters.get("employee")
	date = filters.get("date")
	if not employee or not date:
		return []

	salary_structure_assignment = get_salary_structure_assignment(employee, date)

	EmployeeBenefitDetail = frappe.qb.DocType("Employee Benefit Detail")
	SalaryComponent = frappe.qb.DocType("Salary Component")
	components = (
		frappe.qb.from_(EmployeeBenefitDetail)
		.join(SalaryComponent)
		.on(SalaryComponent.name == EmployeeBenefitDetail.salary_component)
		.select(EmployeeBenefitDetail.salary_component)
		.where(EmployeeBenefitDetail.parent == salary_structure_assignment)
		.where(
			(SalaryComponent.payout_method == "Accrue per cycle, pay only on claim")
			| (SalaryComponent.payout_method == "Allow claim for full benefit amount")
		)
	).run()

	return components


def get_benefit_amount(employee, date, salary_component):
	if not employee or not date:
		return 0

	salary_structure_assignment = get_assigned_salary_structure(employee, date)
	EmployeeBenefitDetail = frappe.qb.DocType("Employee Benefit Detail")
	result = (
		frappe.qb.from_(EmployeeBenefitDetail)
		.select(EmployeeBenefitDetail.amount)
		.where(EmployeeBenefitDetail.salary_component == salary_component)
		.where(EmployeeBenefitDetail.parent == salary_structure_assignment)
	).run(pluck="amount")

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
