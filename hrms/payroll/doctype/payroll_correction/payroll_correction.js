// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payroll Correction", {
	lwp_array: [],
	refresh(frm) {
		frm.trigger("load_lwp_months");
	},
	employee(frm) {
		frm.trigger("load_lwp_months");
	},
	payroll_period(frm) {
		frm.trigger("load_lwp_months");
	},

	load_lwp_months(frm) {
		if (!(frm.doc.employee && frm.doc.payroll_period && frm.doc.company)) {
			frm.set_value("month_for_lwp_reversal", undefined);
			[
				"salary_slip_reference",
				"absent_days",
				"working_days",
				"lwp_days",
				"total_lwp_applied",
			].forEach((f) => frm.set_value(f, undefined));
			return;
		}

		frm.call({
			method: "fetch_salary_slip_details",
			doc: frm.doc,
			callback(res) {
				if (res.message) {
					const { months, slip_details } = res.message;
					frm.lwp_array = slip_details;
					frm.set_df_property(
						"month_for_lwp_reversal",
						"options",
						[""].concat(months).join("\n"),
					);
					frm.refresh_field("month_for_lwp_reversal");
				}
			},
		});
	},

	month_for_lwp_reversal(frm) {
		let selected_entry = frm.lwp_array.find(
			(e) => e.month_name === frm.doc.month_for_lwp_reversal,
		);

		if (selected_entry) {
			frm.set_value("salary_slip_reference", selected_entry.salary_slip_reference);
			frm.set_value("absent_days", selected_entry.absent_days);
			frm.set_value("working_days", selected_entry.working_days);
			frm.set_value("lwp_days", selected_entry.leave_without_pay);
			frm.set_value(
				"total_lwp_applied",
				selected_entry.absent_days + selected_entry.leave_without_pay,
			);
		}

		if (frm.doc.days_to_reverse && frm.doc.docstatus === 0) {
			frm.set_value("days_to_reverse", 0);
		}
	},
});
