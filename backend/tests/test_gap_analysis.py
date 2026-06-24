from app.data.demo_seed import seed_demo_data
from app.models.schemas import GapSkill, NormalizedSkill
from app.services.gap_analysis import _weighted_overlap, analyse_gap
from app.services.profile import build_profile


def setup_module():
    seed_demo_data()


def test_gap_classifies_matched_proficiency_gap_and_missing():
    profile = build_profile("project-manager")
    gap = analyse_gap(profile, "business-analyst")
    assert any(item.status == "Matched" for item in gap.matched)
    assert any(item.status == "Proficiency Gap" for item in gap.proficiency_gaps)
    assert any(item.status == "Missing" for item in gap.missing)
    assert 0 <= gap.match_score <= 1


def test_weighted_overlap_credits_ccs_less_than_tsc():
    tsc = NormalizedSkill(raw_title="Data Analytics", canonical_title="Data Analytics", skill_type="TSC", proficiency_level=3)
    ccs = NormalizedSkill(raw_title="Communication", canonical_title="Communication", skill_type="CCS", proficiency_level=3)
    tsc_score = _weighted_overlap([GapSkill(skill=tsc, status="Matched")], [], [tsc, ccs])
    ccs_score = _weighted_overlap([GapSkill(skill=ccs, status="Matched")], [], [tsc, ccs])
    assert tsc_score > ccs_score
