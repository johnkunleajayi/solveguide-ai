import base64
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.schemas import QuestionObservation


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
            create_app(Settings(_env_file=None, openai_api_key=None), provider or FakeProvider()),
            base_url="http://127.0.0.1",
            headers={"Origin": "http://127.0.0.1:1420"},
        )

    return factory
