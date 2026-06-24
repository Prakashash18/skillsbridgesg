from app.data.demo_seed import seed_demo_data
from app.data import repository
from app.services.profile import build_profile
from app.services.recommend import recommend_roles


def setup_module():
    seed_demo_data()


def test_recommendations_include_realism_tiers():
    profile = build_profile("project-manager")
    result = recommend_roles(profile, top_k=4)
    tiers = {item.tier for item in result.recommendations}
    assert tiers
    assert all(item.tier_note for item in result.recommendations)


def test_recommendations_do_not_build_full_skill_index(monkeypatch):
    def fail_if_called():
        raise AssertionError("recommend_roles should not build the full role-skill index")

    monkeypatch.setattr(repository, "get_all_role_skills_index", fail_if_called)
    profile = build_profile("project-manager")
    result = recommend_roles(profile, top_k=2)
    assert result.recommendations
