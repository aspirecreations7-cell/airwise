import pytest

from app.services import llm


@pytest.fixture(autouse=True)
def reset_llm_state():
    llm.clear_state()
    yield
    llm.clear_state()
