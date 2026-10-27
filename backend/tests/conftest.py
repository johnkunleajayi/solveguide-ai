import base64
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.auth.dependencies import required_current_user
from app.auth.models import User
from app.config import Settings
from app.main import create_app
from app.schemas import QuestionObservation


def authorized_test_app(app):
    """Provider contract tests explicitly bypass only auth; enforcement tests do not."""

    async def user():
        return User(
            id=uuid4(),
            google_subject="test-subject",
            email="test@example.com",
            email_verified=True,
            display_name="Test",
            avatar_url=None,
        )

    app.dependency_overrides[required_current_user] = user
    return app


@pytest.fixture
def observation_data():
    return {
        "status": "detected",
        "question_type": "multiple_choice",
        "question_text": "Which symbol appears in the diagram?",
        "options": [{"label": "A", "text": "Circle"}, {"label": "B", "text": "Square"}],
        "instructions": ["Choose one answer."],
        "required_selection_count": 1,
        "visible_context": [],
        "visual_elements": [],
        "extraction_confidence": 0.94,
        "warnings": [],
    }


@pytest.fixture
def image_payload():
    buffer = BytesIO()
    Image.new("RGB", (24, 16), "white").save(buffer, format="PNG")
    return {"media_type": "image/png", "image_base64": base64.b64encode(buffer.getvalue()).decode()}


@pytest.fixture
def api_factory(observation_data):
    class FakeProvider:
        calls = 0

        async def observe(self, image):
            self.calls += 1
            assert image.width == 24 and image.height == 16
            return QuestionObservation.model_validate(observation_data)

    def factory(provider=None):
        return TestClient(
            authorized_test_app(
                create_app(
                    Settings(_env_file=None, openai_api_key=None), provider or FakeProvider()
                )
            ),
            base_url="http://127.0.0.1",
            headers={"Origin": "http://127.0.0.1:1420"},
        )

    return factory


@pytest.fixture
def answer_data():
    return {
        "status": "answered",
        "question_type": "multiple_choice",
        "selected_options": ["A"],
        "answer_text": "A circle.",
        "true_false_answer": None,
        "code_answer": None,
        "explanation": "The observed figure is round without corners.",
        "key_points": [],
        "confidence": 0.88,
        "warnings": [],
    }
