import re

import frappe
import razorpay
import stripe
from frappe.utils import fmt_money

from press.exceptions import CentralServerNotSet, FrappeioServerNotSet
from press.utils import get_current_team, log_error

states_with_tin = {
	"Andaman and Nicobar Islands": "35",
	"Andhra Pradesh": "37",
	"Arunachal Pradesh": "12",
	"Assam": "18",
	"Bihar": "10",
	"Chandigarh": "04",
	"Chhattisgarh": "22",
	"Dadra and Nagar Haveli and Daman and Diu": "26",
	"Delhi": "07",
	"Goa": "30",
	"Gujarat": "24",
	"Haryana": "06",
	"Himachal Pradesh": "02",
	"Jammu and Kashmir": "01",
	"Jharkhand": "20",
	"Karnataka": "29",
	"Kerala": "32",
	"Ladakh": "38",
	"Lakshadweep Islands": "31",
	"Madhya Pradesh": "23",
	"Maharashtra": "27",
	"Manipur": "14",
	"Meghalaya": "17",
	"Mizoram": "15",
	"Nagaland": "13",
	"Odisha": "21",
	"Other Territory": "97",
	"Puducherry": "34",
	"Punjab": "03",
	"Rajasthan": "08",
	"Sikkim": "11",
	"Tamil Nadu": "33",
	"Telangana": "36",
	"Tripura": "16",
	"Uttar Pradesh": "09",
	"Uttarakhand": "05",
	"West Bengal": "19",
}

GSTIN_FORMAT = re.compile("^[0-9]{2}[A-Z]{4}[0-9A-Z]{1}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[1-9A-Z]{1}[0-9A-Z]{1}$")


def format_stripe_money(amount, currency):
	return fmt_money(amount / 100, 2, currency)


def get_erpnext_com_connection():
	from frappe.frappeclient import FrappeClient

	press_settings = frappe.get_single("Press Settings")
	erpnext_api_secret = press_settings.get_password("erpnext_api_secret", raise_exception=False)

	if not (press_settings.erpnext_api_key and press_settings.erpnext_url and erpnext_api_secret):
		frappe.throw("ERPNext.com URL not set up in Press Settings", exc=CentralServerNotSet)

	return FrappeClient(
		press_settings.erpnext_url,
		api_key=press_settings.erpnext_api_key,
		api_secret=erpnext_api_secret,
	)


def get_frappe_io_connection():
	if hasattr(frappe.local, "press_frappeio_conn"):
		return frappe.local.press_frappeio_conn

	from frappe.frappeclient import FrappeClient

	press_settings = frappe.get_single("Press Settings")
	frappe_api_key = press_settings.frappeio_api_key
	frappe_api_secret = press_settings.get_password("frappeio_api_secret", raise_exception=False)

	if not (frappe_api_key and frappe_api_secret and press_settings.frappe_url):
		frappe.throw("Frappe.io URL not set up in Press Settings", exc=FrappeioServerNotSet)

	frappe.local.press_frappeio_conn = FrappeClient(
		press_settings.frappe_url, api_key=frappe_api_key, api_secret=frappe_api_secret
	)

	return get_frappe_io_connection()


def is_frappe_auth_disabled():
	return frappe.db.get_single_value("Press Settings", "disable_frappe_auth", cache=True)


def make_formatted_doc(doc, fieldtypes=None):
	formatted = {}
	filters = None
	if fieldtypes:
		filters = {"fieldtype": ["in", fieldtypes]}

	for df in doc.meta.get("fields", filters):
		formatted[df.fieldname] = doc.get_formatted(df.fieldname)

	for tf in doc.meta.get_table_fields():
		formatted[tf.fieldname] = []
		for row in doc.get(tf.fieldname):
			formatted[tf.fieldname].append(make_formatted_doc(row))

	return formatted


def clear_setup_intent():
	team = get_current_team()
	frappe.cache().hdel("setup_intent", team)


def get_publishable_key():
	return frappe.db.get_single_value("Press Settings", "stripe_publishable_key")


def get_setup_intent(team):
	from frappe.utils import random_string

	intent = frappe.cache().hget("setup_intent", team)
	if not intent:
		data = frappe.db.get_value("Team", team, ["stripe_customer_id", "currency"])
		customer_id = data[0]
		currency = data[1]
		stripe = get_stripe()
		hash = random_string(10)
		intent = stripe.SetupIntent.create(
			customer=customer_id,
			payment_method_types=["card"],
			payment_method_options={
				"card": {
					"request_three_d_secure": "automatic",
					"mandate_options": {
						"reference": f"Mandate-team:{team}-{hash}",
						"amount_type": "maximum",
						"amount": 1500000,
						"currency": currency.lower(),
						"start_date": int(frappe.utils.get_timestamp()),
						"interval": "sporadic",
						"supported_types": ["india"],
					},
				}
			},
		)
		frappe.cache().hset("setup_intent", team, intent)

	return intent


def get_stripe():
	from frappe.utils.password import get_decrypted_password

	if not hasattr(frappe.local, "press_stripe_object"):
		secret_key = get_decrypted_password(
			"Press Settings",
			"Press Settings",
			"stripe_secret_key",
			raise_exception=False,
		)

		if not secret_key:
			frappe.throw("Setup stripe via Press Settings before using press.api.billing.get_stripe")

		stripe.api_key = secret_key
		# Set the maximum number of retries for network requests
		# https://docs.stripe.com/rate-limits?lang=python#object-lock-timeouts
		stripe.max_network_retries = 2
		frappe.local.press_stripe_object = stripe

	return frappe.local.press_stripe_object


def convert_stripe_money(amount):
	return (amount / 100) if amount else 0


def validate_gstin_check_digit(gstin, label="GSTIN"):
	"""Function to validate the check digit of the GSTIN."""
	factor = 1
	total = 0
	code_point_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	mod = len(code_point_chars)
	input_chars = gstin[:-1]
	for char in input_chars:
		digit = factor * code_point_chars.find(char)
		digit = (digit // mod) + (digit % mod)
		total += digit
		factor = 2 if factor == 1 else 1
	if gstin[-1] != code_point_chars[((mod - (total % mod)) % mod)]:
		frappe.throw(
			f"""Invalid {label}! The check digit validation has failed. Please ensure you've typed the {label} correctly."""
		)


def get_razorpay_client():
	from frappe.utils.password import get_decrypted_password

	if not hasattr(frappe.local, "press_razorpay_client_object"):
		key_id = frappe.db.get_single_value("Press Settings", "razorpay_key_id")
		key_secret = get_decrypted_password(
			"Press Settings", "Press Settings", "razorpay_key_secret", raise_exception=False
		)

		if not (key_id and key_secret):
			frappe.throw(
				"Setup razorpay via Press Settings before using press.api.billing.get_razorpay_client"
			)

		frappe.local.press_razorpay_client_object = razorpay.Client(auth=(key_id, key_secret))

	return frappe.local.press_razorpay_client_object

def get_bitiwallet_client():
	from frappe.utils.password import get_decrypted_password

	if not hasattr(frappe.local, "press_bitiwallet_client_object"):
		key_id = frappe.db.get_single_value("Press Settings", "razorpay_key_id")
		key_secret = get_decrypted_password(
			"Press Settings", "Press Settings", "razorpay_key_secret", raise_exception=False
		)

		if not (key_id and key_secret):
			frappe.throw(
				"Setup razorpay via Press Settings before using"
				" press.api.billing.get_razorpay_client"
			)

		frappe.local.press_bitiwallet_client_object = razorpay.Client(auth=(key_id, key_secret))

	return frappe.local.press_bitiwallet_client_object


def process_micro_debit_test_charge(stripe_event):
	try:
		payment_intent = stripe_event["data"]["object"]
		metadata = payment_intent.get("metadata")
		payment_method_name = metadata.get("payment_method_name")

		frappe.db.set_value(
			"Stripe Payment Method", payment_method_name, "is_verified_with_micro_charge", True
		)

		frappe.get_doc(
			doctype="Stripe Micro Charge Record",
			stripe_payment_method=payment_method_name,
			stripe_payment_intent_id=payment_intent.get("id"),
		).insert(ignore_permissions=True)
	except Exception:
		log_error("Error Processing Stripe Micro Debit Charge", body=stripe_event)


def get_gateway_details(payment_record):
	partner_team = frappe.db.get_value("Mpesa Payment Record", payment_record, "payment_partner")
	return frappe.db.get_value(
		"Payment Gateway", {"team": partner_team}, ["gateway_controller", "print_format"]
	)


# Get partners external connection
def get_partner_external_connection(mpesa_setup):
	# check if connection is already established
	if hasattr(frappe.local, "_external_conn"):
		return frappe.local.press_external_conn

	from frappe.frappeclient import FrappeClient

	# Fetch API from gateway
	payment_gateway = frappe.get_all(
		"Payment Gateway",
		filters={"gateway_controller": mpesa_setup, "gateway_settings": "Mpesa Setup"},
		fields=["name", "url", "api_key", "api_secret"],
	)
	if not payment_gateway:
		frappe.throw("Mpesa Setup not set up in Payment Gateway")
	# Fetch API key and secret
	pg = frappe.get_doc("Payment Gateway", payment_gateway[0].name)
	api_key = pg.api_key
	api_secret = pg.get_password("api_secret")
	url = pg.url

	site_name = url.split("/api/method")[0]
	# Establish connection
	frappe.local._external_conn = FrappeClient(site_name, api_key=api_key, api_secret=api_secret)
	return frappe.local._external_conn
