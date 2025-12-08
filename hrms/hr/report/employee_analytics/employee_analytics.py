# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	if not filters["company"]:
		frappe.throw(_("{0} is mandatory").format(_("Company")))

	columns = get_columns()
	employees = get_employees(filters)
	parameters = get_parameters(filters)

	chart = get_chart_data(parameters, employees, filters)
	return columns, employees, None, chart


def get_columns():
	return [
		_("Employee") + ":Link/Employee:120",
		_("Name") + ":Data:200",
		_("Date of Birth") + ":Date:100",
		_("Branch") + ":Link/Branch:120",
		_("Department") + ":Link/Department:120",
		_("Designation") + ":Link/Designation:120",
		_("Gender") + "::100",
		_("Company") + ":Link/Company:120",
	]


def get_employees(filters):
	filters = frappe._dict(filters or {})
	filters["status"] = "Active"
	filters[filters.get("parameter").lower().replace(" ", "_")] = ["is", "set"]
	filters.pop("parameter")
	return frappe.get_list(
		"Employee",
		filters=filters,
		fields=[
			"name",
			"employee_name",
			"date_of_birth",
			"branch",
			"department",
			"designation",
			"gender",
			"company",
		],
		as_list=True,
	)


def get_parameters(filters):
	if filters.get("parameter") == "Grade":
		parameter = "Employee Grade"
	else:
		parameter = filters.get("parameter")
	return frappe.get_all(parameter, pluck="name")


def get_chart_data(parameters, employees, filters):
	if not parameters:
		parameters = []
	datasets = []
	parameter_field_name = filters.get("parameter").lower().replace(" ", "_")
	label = []
	for parameter in parameters:
		if parameter:
			total_employee = frappe.get_list(
				"Employee",
				filters={parameter_field_name: parameter, "company": filters.get("company")},
				fields=[{"COUNT": "name", "as": "count"}],
				as_list=1,
			)
			if total_employee[0][0]:
				label.append(parameter)
			datasets.append(total_employee[0][0])

	values = [value for value in datasets if value != 0]

	total_employee = frappe.db.count("Employee", {"status": "Active"})
	others = total_employee - sum(values)

	label.append("Not Set")
	values.append(others)
	chart = {"data": {"labels": label, "datasets": [{"name": "Employees", "values": values}]}}
	chart["type"] = "donut"
	return chart
