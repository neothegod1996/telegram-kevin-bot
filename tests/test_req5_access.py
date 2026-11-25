import os
import unittest

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("BOT_TOKEN", "12345:test_token")
os.environ.setdefault("OWNER_ID", "12345")

from bot.security.login_portal import issue_login_token, login_portal_url, submit_otp, start_challenge
from bot.security.session_crypto import decrypt_session, encrypt_session


class AccessControlTests(unittest.TestCase):
    def test_session_roundtrip(self):
        os.environ["SESSION_ENCRYPTION_KEY"] = "unit-test-secret"
        enc = encrypt_session("session-data")
        self.assertTrue(enc.startswith("enc:"))
        self.assertEqual(decrypt_session(enc), "session-data")

    def test_login_portal_url(self):
        os.environ["WEB_URL"] = "https://example.test"
        url = login_portal_url(99, issue_login_token(99, "hash"))
        self.assertIn("/login/99/", url)

    def test_submit_otp_sets_challenge(self):
        ch = start_challenge(7, "+1", "hash")
        self.assertTrue(submit_otp(7, "12345"))
        self.assertEqual(ch.otp, "12345")


if __name__ == "__main__":
    unittest.main()