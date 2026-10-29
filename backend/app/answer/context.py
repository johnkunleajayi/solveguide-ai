from app.schemas import StrictModel


class LearningContext(StrictModel):
    purpose: str
    objective: str
