import unittest

from app.services.external_forms import detect_provider, normalize_form_link


class ExternalFormLinkTests(unittest.TestCase):
    def test_google_forms_link_is_accepted(self) -> None:
        url = "https://docs.google.com/forms/d/e/ABC123/viewform"
        self.assertEqual(
            normalize_form_link(url),
            (url, "google"),
        )
        self.assertEqual(detect_provider(url), "google")

    def test_microsoft_forms_link_is_accepted(self) -> None:
        url = "https://forms.office.com/r/AbCdEf"
        self.assertEqual(normalize_form_link(url, "microsoft"), (url, "microsoft"))

    def test_provider_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_form_link(
                "https://docs.google.com/forms/d/e/ABC/viewform", "microsoft"
            )

    def test_unsupported_or_unsafe_links_are_rejected(self) -> None:
        for value in (
            "javascript:alert(1)",
            "https://example.com/forms/test",
            "not-a-url",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_form_link(value)

    def test_empty_link_is_optional(self) -> None:
        self.assertEqual(normalize_form_link(""), (None, None))
        self.assertEqual(normalize_form_link(None, "google"), (None, None))


if __name__ == "__main__":
    unittest.main()
