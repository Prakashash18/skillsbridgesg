import os
import tempfile

# Point the database at a throwaway file BEFORE app.data.db is imported, so the
# test suite (which seeds demo data) never clobbers the real ingested
# SkillsFuture dataset in storage/skillbridge.db.
_test_db = os.path.join(tempfile.gettempdir(), "skillbridge_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"
