import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))
import profile_db


class ProfileTests(unittest.TestCase):
    def test_mounted_identity_is_required_and_cannot_be_overridden(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "database"
            with patch.object(profile_db, "IDENTITY", marker):
                with self.assertRaises(FileNotFoundError):
                    profile_db.database()
                marker.write_text("keiba_nlp_trial")
                with patch.dict(os.environ, {"NLP_DATABASE": "keiba_nlp"}):
                    with self.assertRaises(ValueError):
                        profile_db.credentials()
                with patch.dict(os.environ, {"NLP_DATABASE": "keiba_nlp_trial"}):
                    self.assertTrue(profile_db.trial())
                    self.assertEqual(
                        profile_db.PROFILES[profile_db.database()][:2],
                        ("nlp_trial_app", "nlp_trial_viewer"),
                    )


if __name__ == "__main__":
    unittest.main()
