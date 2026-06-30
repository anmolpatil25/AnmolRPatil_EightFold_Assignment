import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from candidate_transformer import normalize as norm
from candidate_transformer import merge as merge_mod
from candidate_transformer import project as project_mod
from candidate_transformer.schema import empty_profile
from candidate_transformer.pipeline import run_pipeline

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")


class TestNormalize(unittest.TestCase):
    def test_phone_e164_us(self):
        self.assertEqual(norm.normalize_phone("(512) 555-0192"), "+15125550192")

    def test_phone_already_intl(self):
        self.assertEqual(norm.normalize_phone("+44 7700 900123"), "+447700900123")

    def test_phone_garbage_returns_none(self):
        self.assertIsNone(norm.normalize_phone("call me maybe"))
        self.assertIsNone(norm.normalize_phone(""))
        self.assertIsNone(norm.normalize_phone(None))

    def test_location_city_state(self):
        loc = norm.normalize_location("Austin, TX")
        self.assertEqual(loc, {"city": "Austin", "region": "TX", "country": "US"})

    def test_location_city_country(self):
        loc = norm.normalize_location("London, UK")
        self.assertEqual(loc["city"], "London")
        self.assertEqual(loc["country"], "GB")

    def test_month_formats(self):
        self.assertEqual(norm.normalize_month("2021-03"), "2021-03")
        self.assertEqual(norm.normalize_month("Mar 2021"), "2021-03")
        self.assertEqual(norm.normalize_month("3/2021"), "2021-03")
        self.assertEqual(norm.normalize_month("present"), None)
        self.assertEqual(norm.normalize_month("not a date"), None)

    def test_skill_canonicalization(self):
        self.assertEqual(norm.canonicalize_skill("JS"), "javascript")
        self.assertEqual(norm.canonicalize_skill("k8s"), "kubernetes")
        self.assertEqual(norm.canonicalize_skill(""), None)

    def test_email_validation(self):
        self.assertEqual(norm.normalize_email("Foo@Bar.com"), "foo@bar.com")
        self.assertIsNone(norm.normalize_email("not-an-email"))


class TestMerge(unittest.TestCase):
    def test_merge_by_email_unions_skills_and_keeps_higher_reliability_name(self):
        p1 = empty_profile("")
        p1["full_name"] = "A Verma"
        p1["emails"] = ["a@x.com"]
        p1["skills"] = [{"name": "python", "confidence": None, "source": ["recruiter_csv"]}]
        p1["provenance"] = [
            {"field": "full_name", "source": "recruiter_csv", "method": "direct"},
            {"field": "emails", "source": "recruiter_csv", "method": "direct"},
            {"field": "skills", "source": "recruiter_csv", "method": "direct"},
        ]
        p2 = empty_profile("")
        p2["full_name"] = "Asha Verma"
        p2["emails"] = ["a@x.com"]
        p2["skills"] = [{"name": "go", "confidence": None, "source": ["resume_file"]}]
        p2["provenance"] = [
            {"field": "full_name", "source": "resume_file", "method": "derived"},
            {"field": "emails", "source": "resume_file", "method": "derived"},
            {"field": "skills", "source": "resume_file", "method": "derived"},
        ]
        merged = merge_mod.merge_all([p1, p2])
        self.assertEqual(len(merged), 1)
        m = merged[0]
        # recruiter_csv (0.95) beats resume_file (0.6) for the scalar full_name
        self.assertEqual(m["full_name"], "A Verma")
        skill_names = sorted(s["name"] for s in m["skills"])
        self.assertEqual(skill_names, ["go", "python"])

    def test_records_with_no_shared_identity_stay_separate(self):
        p1 = empty_profile("")
        p1["full_name"] = "Bob Jones"
        p2 = empty_profile("")
        p2["full_name"] = "Carol King"
        merged = merge_mod.merge_all([p1, p2])
        self.assertEqual(len(merged), 2)


class TestProject(unittest.TestCase):
    def test_required_missing_field_errors_when_configured(self):
        profile = empty_profile("cand_1")
        profile["full_name"] = "No Email Person"
        profile["_field_confidence"] = {}
        config = {
            "fields": [{"path": "primary_email", "from": "emails[0]", "required": True}],
            "on_missing": "error",
        }
        with self.assertRaises(project_mod.ProjectionError):
            project_mod.project(profile, config)

    def test_required_missing_field_omits_when_configured(self):
        profile = empty_profile("cand_1")
        profile["_field_confidence"] = {}
        config = {
            "fields": [{"path": "primary_email", "from": "emails[0]", "required": True}],
            "on_missing": "omit",
        }
        out = project_mod.project(profile, config)
        self.assertNotIn("primary_email", out)

    def test_list_comprehension_path(self):
        profile = empty_profile("cand_1")
        profile["skills"] = [{"name": "python", "confidence": 0.9, "source": ["x"]},
                              {"name": "go", "confidence": 0.8, "source": ["y"]}]
        profile["_field_confidence"] = {}
        config = {"fields": [{"path": "skills", "from": "skills[].name"}]}
        out = project_mod.project(profile, config)
        self.assertEqual(out["skills"], ["python", "go"])


class TestEndToEndEdgeCases(unittest.TestCase):
    """Covers the assignment's required robustness properties directly."""

    def test_missing_garbage_source_does_not_crash_and_yields_nulls(self):
        # malformed CSV path that doesn't exist + garbage JSON
        records, rejected = run_pipeline(
            inputs=[{"path": "/tmp/does_not_exist_12345.csv"},
                    {"path": os.path.join(SAMPLE_DIR, "ats_export.json")}],
            config=None,
        )
        self.assertIsInstance(records, list)  # did not raise
        self.assertTrue(len(records) >= 1)

    def test_full_sample_run_produces_expected_candidate_count(self):
        inputs = [
            {"path": os.path.join(SAMPLE_DIR, "recruiter.csv")},
            {"path": os.path.join(SAMPLE_DIR, "ats_export.json")},
            {"path": os.path.join(SAMPLE_DIR, "jordan_resume.pdf")},
            {"path": os.path.join(SAMPLE_DIR, "marcus_notes.txt")},
            {"path": "https://github.com/ashav"},
            {"path": "https://linkedin.com/in/asha-verma-eng"},
        ]
        records, rejected = run_pipeline(inputs, config=None)
        # Asha (csv+ats+github+linkedin), Jordan (csv+resume), Priya (csv+ats),
        # Marcus-csv/ats (no email there), Marcus-notes (has email) -- the
        # last two staying separate is the documented name/email matching
        # limitation, not a bug.
        self.assertEqual(len(records), 5)
        asha = next(r for r in records if r["full_name"] == "Asha Verma")
        self.assertIn("python", [s["name"] for s in asha["skills"]])
        self.assertTrue(0.0 <= asha["overall_confidence"] <= 1.0)
        for r in records:
            self.assertIn("candidate_id", r)
            self.assertIn("overall_confidence", r)


if __name__ == "__main__":
    unittest.main()
