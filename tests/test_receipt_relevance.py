"""Receipt business-relevance checks (no Gemini API)."""

import unittest

from receipt_ocr import check_business_relevance, _keyword_irrelevance_hit


class ReceiptRelevanceTests(unittest.TestCase):
    def test_flags_blind_box_keyword(self):
        extracted = {
            "merchant_name": "POP MART",
            "line_items": [{"description": "Labubu blind box series 4", "amount": 18.99}],
            "business_relevant": True,
        }
        hits = check_business_relevance(extracted)
        self.assertTrue(any(v["type"] == "non_business_expense" for v in hits))

    def test_ai_non_business_field(self):
        extracted = {
            "merchant_name": "HOBBY STORE",
            "business_relevant": False,
            "business_relevance": "non_business",
            "relevance_note": "Collectible figurine purchase",
        }
        hits = check_business_relevance(extracted)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["type"], "non_business_expense")
        self.assertIn("Collectible", hits[0]["description"])

    def test_clear_business_fuel(self):
        extracted = {
            "merchant_name": "SHELL",
            "expense_category": "Fuel",
            "business_relevant": True,
            "business_relevance": "clear_business",
        }
        self.assertEqual(check_business_relevance(extracted), [])

    def test_keyword_helper(self):
        self.assertEqual(_keyword_irrelevance_hit("pop mart labubu blind box"), "blind box")


if __name__ == "__main__":
    unittest.main()
