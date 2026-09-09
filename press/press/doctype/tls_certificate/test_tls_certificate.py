# Copyright (c) 2020, Frappe and Contributors
# See license.txt

from typing import Literal
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from press.press.doctype.agent_job.agent_job import AgentJob
from press.press.doctype.proxy_server.proxy_server import ProxyServer
from press.press.doctype.proxy_server.test_proxy_server import create_test_proxy_server
from press.press.doctype.root_domain.test_root_domain import create_test_root_domain
from press.press.doctype.tls_certificate.tls_certificate import (
	BaseCA,
	LetsEncrypt,
	ScmeSH,
	TLSCertificate,
)


@patch.object(TLSCertificate, "obtain_certificate", new=Mock())
def create_test_tls_certificate(
	domain: str, wildcard: bool = False, provider: Literal["Let's Encrypt", "Other"] = "Let's Encrypt"
) -> TLSCertificate:
	certificate = frappe.get_doc(
		{
			"doctype": "TLS Certificate",
			"domain": domain,
			"rsa_key_size": 2048,
			"wildcard": wildcard,
			"provider": provider,
		}
	).insert(ignore_if_duplicate=True)
	certificate.reload()
	return certificate


def none_init(self, settings):
	pass


def fake_extract(self):
	return "a", "b", "c", "d"


@patch.object(AgentJob, "after_insert", new=Mock())
@patch.object(LetsEncrypt, "_obtain", new=Mock())
@patch.object(BaseCA, "_extract", new=fake_extract)
@patch.object(TLSCertificate, "_extract_certificate_details", new=Mock())
class TestTLSCertificate(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	@patch.object(ScmeSH, "_obtain", new=Mock())
	def test_renewal_of_secondary_wildcard_domains_updates_server(self):
		erpnext_domain = create_test_root_domain("erpnext.xyz")
		fc_domain = create_test_root_domain("fc.dev")
		create_test_proxy_server(  # creates n1.fc.dev by default
			"n1", domains=[{"domain": fc_domain.name}, {"domain": erpnext_domain.name}]
		)

		cert = create_test_tls_certificate(erpnext_domain.name, wildcard=True)

		with (
			patch.object(LetsEncrypt, "__init__", new=none_init),
			patch.object(ProxyServer, "setup_wildcard_hosts") as mock_setup_wildcard_hosts,
		):
			cert._obtain_certificate()
		mock_setup_wildcard_hosts.assert_called_once()

	@patch.object(ScmeSH, "_obtain", new=Mock())
	def test_renewal_of_primary_wildcard_domains_doesnt_call_setup_wildcard_domains(self):
		erpnext_domain = create_test_root_domain("erpnext.xyz")
		fc_domain = create_test_root_domain("fc.dev")
		create_test_proxy_server("n1", domains=[{"domain": fc_domain.name}, {"domain": erpnext_domain.name}])

		cert = create_test_tls_certificate(fc_domain.name, wildcard=True)
		cert.reload()  # already created with proxy server

		with (
			patch.object(LetsEncrypt, "__init__", new=none_init),
			patch.object(TLSCertificate, "trigger_server_tls_setup_callback", new=Mock()),
			patch.object(ProxyServer, "setup_wildcard_hosts") as mock_setup_wildcard_hosts,
		):
			cert._obtain_certificate()

		mock_setup_wildcard_hosts.assert_not_called()

	def test_private_key_is_encrypted_at_rest_and_readable_via_accessor(self):
		cert = create_test_tls_certificate("enc-test.dev")
		private_key = "-----BEGIN PRIVATE KEY-----\nMIItestkeymaterial\n-----END PRIVATE KEY-----"  # pragma: allowlist secret

		cert.private_key = private_key
		cert.save(ignore_permissions=True)

		# The raw DB column must never hold the plaintext key.
		stored = frappe.db.get_value("TLS Certificate", cert.name, "private_key")
		self.assertNotEqual(stored, private_key)
		self.assertEqual(set(stored), {"*"})  # dummy mask that Password fields store

		# The accessor is the only supported way to read it back.
		cert.reload()
		self.assertEqual(cert.get_private_key(), private_key)

	def test_patch_moves_existing_plaintext_private_key_into_encrypted_store(self):
		from frappe.utils.password import get_decrypted_password, remove_encrypted_password

		from press.patches.v0_8_0.encrypt_tls_private_keys_at_rest import execute

		cert = create_test_tls_certificate("patch-test.dev")
		private_key = "-----BEGIN PRIVATE KEY-----\nplaintextkeyfrombeforemigration\n-----END PRIVATE KEY-----"  # pragma: allowlist secret

		# Simulate the pre-migration state: plaintext sits in the column and
		# nothing is in the encrypted store.
		frappe.db.set_value("TLS Certificate", cert.name, "private_key", private_key, update_modified=False)
		remove_encrypted_password("TLS Certificate", cert.name, "private_key")

		with patch.object(frappe.db, "commit", new=Mock()):
			execute()

		stored = frappe.db.get_value("TLS Certificate", cert.name, "private_key")
		self.assertEqual(set(stored), {"*"})
		self.assertEqual(get_decrypted_password("TLS Certificate", cert.name, "private_key"), private_key)

	@patch.object(ScmeSH, "_obtain", new=Mock())
	def test_renewal_of_primary_domain_calls_update_tls_certificates(self):
		# Use a diffferent domain to avoid any chance of
		# Reusing same non wildcard domain in tests
		# Because, in create_test_tls_certificate, we ignore certificate creation if it already exists
		create_test_root_domain("fc2.dev")
		cert = create_test_tls_certificate("fc2.dev", wildcard=True)
		create_test_proxy_server("n2", domain="fc2.dev")
		with (
			patch.object(LetsEncrypt, "__init__", new=none_init),
			patch.object(
				TLSCertificate, "trigger_server_tls_setup_callback"
			) as mock_trigger_server_tls_setup,
			patch.object(ProxyServer, "setup_wildcard_hosts", new=Mock()),
		):
			cert._obtain_certificate()
		mock_trigger_server_tls_setup.assert_called()

	def test_selects_acmesh_for_wildcard_when_20i_bearer_is_configured(self):
		cert = create_test_tls_certificate("fc2.dev", wildcard=True)
		settings = frappe._dict(
			certbot_directory=".certbot",
			webroot_directory=".well-known/acme-challenge",
			eff_registration_email="ops@example.com",
			dns_20i_bearer="token",
		)

		ca = cert._get_certificate_authority(settings)

		self.assertIsInstance(ca, ScmeSH)

	def test_falls_back_to_letsencrypt_without_20i_bearer(self):
		cert = create_test_tls_certificate("fc2.dev", wildcard=True)
		settings = frappe._dict(
			certbot_directory=".certbot",
			webroot_directory=".well-known/acme-challenge",
			eff_registration_email="ops@example.com",
		)

		ca = cert._get_certificate_authority(settings)

		self.assertIsInstance(ca, LetsEncrypt)

	@patch("subprocess.check_output")
	def test_acmesh_command_uses_dns_20i_and_challenge_alias(self, mock_check_output):
		settings = frappe._dict(
			certbot_directory=".certbot",
			webroot_directory=".well-known/acme-challenge",
			eff_registration_email="ops@example.com",
			dns_20i_bearer="token",
			challenge_alias="_acme-challenge.validation.example.com",
			acme_sh_path="/usr/local/acme.sh/acme.sh",
			use_staging_ca=1,
		)
		ca = ScmeSH(settings)

		ca.obtain(domain="example.com", rsa_key_size=2048, wildcard=True)

		command = " ".join(mock_check_output.call_args.args[0])
		self.assertIn("/usr/local/acme.sh/acme.sh", command)
		self.assertIn("--dns dns_20i", command)
		self.assertIn("--bearer token", command)
		self.assertIn("--challenge-alias _acme-challenge.validation.example.com", command)
		if frappe.conf.developer_mode:
			self.assertIn("--server letsencrypt_test", command)
		else:
			self.assertIn("--server letsencrypt", command)

