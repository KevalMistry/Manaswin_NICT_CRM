import unittest

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        password = "correct horse battery staple"
        hashed = hash_password(password)

        self.assertNotEqual(password, hashed)
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("wrong password", hashed))

    def test_access_token_round_trip(self) -> None:
        token = create_access_token("42")

        self.assertEqual(decode_access_token(token), "42")
        self.assertIsNone(decode_access_token("not-a-token"))


if __name__ == "__main__":
    unittest.main()
