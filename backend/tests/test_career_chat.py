from app.data.demo_seed import seed_demo_data
from app.models.schemas import ChatMessage
from app.services.career_chat import converse_about_profile


def setup_module():
    seed_demo_data()


def test_teaching_intro_gets_constructive_response():
    result = converse_about_profile([ChatMessage(role="user", content="I teach programming at ITE")])
    assert "not ready to map" not in result.assistant_message.lower()
    assert result.follow_up_questions
    assert any(word in result.assistant_message.lower() for word in ["education", "training", "profile", "role"])


def test_definition_question_answers_without_remapping():
    messages = [
        ChatMessage(role="user", content="I teach programming at ITE"),
        ChatMessage(role="user", content="role is Lecturer i plan curriculum and design learning I use VS Code, Python"),
        ChatMessage(role="user", content="Whats Talent Capability Development?"),
    ]
    result = converse_about_profile(messages)
    assert "talent capability development means" in result.assistant_message.lower()
    assert "not treat it as the main signal" in result.assistant_message.lower()
