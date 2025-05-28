# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class BitipayPaymentRecord(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		failure_reason: DF.SmallText | None
		order_id: DF.Data | None
		payment_id: DF.Data | None
		signature: DF.Data | None
		status: DF.Literal["Captured", "Failed", "Pending"]
		team: DF.Link | None
		type: DF.Literal["Prepaid Credits", "Partnership Fee"]
	# end: auto-generated types
	pass
