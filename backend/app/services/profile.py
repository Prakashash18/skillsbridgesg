from app.data.repository import get_role, get_role_skills
from app.models.schemas import ProfileEdit, ProfileResponse
from app.services.normalize import comparison_key


def build_profile(current_role_id: str, edits: list[ProfileEdit] | None = None) -> ProfileResponse:
    role = get_role(current_role_id)
    skills = get_role_skills(current_role_id)
    source = "role_template"
    if edits:
        source = "manual"
        edit_map = {comparison_key(edit.canonical_title): edit for edit in edits}
        updated = []
        for skill in skills:
            edit = edit_map.get(comparison_key(skill.canonical_title))
            if edit is None:
                updated.append(skill)
                continue
            if not edit.included:
                continue
            skill.proficiency_level = edit.proficiency_level
            updated.append(skill)
        skills = updated
    return ProfileResponse(role=role, skills=skills, profile_source=source)

