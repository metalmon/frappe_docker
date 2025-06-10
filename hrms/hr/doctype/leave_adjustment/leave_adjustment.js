// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Leave Adjustment", {
	refresh(frm) {
		hrms.leave_utils.add_view_ledger_button(frm);
	},
});
