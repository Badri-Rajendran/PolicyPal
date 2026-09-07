from unittest.mock import MagicMock, patch

import torch

from src.policypal.config import settings
from src.services.generation import _build_user_prompt, answer, answer_query
from src.services.retrieval import RetrievedChunk


class _FakeBatchEncoding(dict):
    """Minimal stand-in for a HF BatchEncoding: dict (for **unpacking) + attribute access."""

    def __init__(self, input_ids):
        super().__init__(input_ids=input_ids)
        self.input_ids = input_ids

    def to(self, device):
        return self


def _make_chunk(chunk_id="c1", score=0.9):
    return RetrievedChunk(chunk_id=chunk_id, content="A deductible is the amount you pay first.",
                           source="Health_insurance", score=score)


def test_answer_returns_fallback_when_no_chunks():
    result = answer("what is a deductible", [])
    assert "don't have enough information" in result.lower()


def test_build_user_prompt_includes_question_context_and_source():
    prompt = _build_user_prompt("What is a deductible?", [_make_chunk()])

    assert "What is a deductible?" in prompt
    assert "Health_insurance" in prompt
    assert "A deductible is the amount you pay first." in prompt


def test_answer_generates_text_using_configured_sampling_params():
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = _FakeBatchEncoding(torch.tensor([[1, 2, 3]]))
    tokenizer.eos_token_id = 0
    tokenizer.decode.return_value = "It's the amount you pay first."

    model = MagicMock()
    model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5]])

    with patch("src.services.generation._llm", return_value=(tokenizer, model, "cpu")):
        result = answer("What is a deductible?", [_make_chunk()])

    assert result == "It's the amount you pay first."
    _, kwargs = model.generate.call_args
    assert kwargs["temperature"] == settings.temperature
    assert kwargs["do_sample"] == (settings.temperature > 0)


def test_answer_query_runs_retrieval_then_generation():
    chunk = _make_chunk()

    with patch("src.services.generation.search", return_value=[chunk]) as mock_search, \
         patch("src.services.generation.answer", return_value="text") as mock_answer:
        result, chunks = answer_query("what is a deductible", top_k=10)

    mock_search.assert_called_once_with("what is a deductible", 10)
    mock_answer.assert_called_once_with("what is a deductible", [chunk])
    assert result == "text"
    assert chunks == [chunk]
