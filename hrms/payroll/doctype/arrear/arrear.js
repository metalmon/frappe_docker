// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Arrear", {
	setup(frm) {
		company_fliter = {
			filters: {
				company: frm.doc.company || "",
			},
		};
		frm.set_query("employee", () => {
			return company_fliter;
		});
		frm.set_query("payroll_period", () => {
			return company_fliter;
		});
		frm.set_query("salary_structure", () => {
			return company_fliter;
		});
	},
	refresh(frm) {},

	employee: (frm) => {
		if (frm.doc.employee) {
			frappe.run_serially([
				() => frm.trigger("get_employee_currency"),
				() => frm.trigger("set_company"),
			]);
		} else {
			frm.set_value("company", null);
		}
	},

	salary_structure: (frm) => {},

	get_employee_currency: (frm) => {
		frappe.call({
			method: "hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment.get_employee_currency",
			args: {
				employee: frm.doc.employee,
			},
			callback: function (r) {
				if (r.message) {
					console.log(r.message);
					frm.set_value("currency", r.message);
					// frm.refresh_field("currency");
				}
			},
		});
	},

	set_company: (frm) => {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Employee",
				fieldname: "company",
				filters: {
					name: frm.doc.employee,
				},
			},
			callback: (data) => {
				if (data.message) {
					frm.set_value("company", data.message.company);
				}
			},
		});
	},
});
