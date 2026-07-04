from src.core.logging import get_logger
from src.policypal.config import settings
from src.core.device import resolve_device
from .retrieval import RetrievedChunk

from transformers import AutoTokenizer, AutoModelForCasalLM
import torch

from functools import lru_cache

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are PolicyPal, an assistant that answers insurance questions. "
    "Answer ONLY using the provided context. If the context does not contain "
    "the answer, say you don't have enough information — do not guess. "
    "Keep answers clear and concise."
)


@lru_cache
def _llm():
    '''Load model + tokenizer once per process'''
    device = resolve_device()
    tokenizer = AutoTokenizer.from_pretrained(settings.llm_model)
    model = AutoModelForCasalLM.from_pretrained(
        settings.llm_model,
        torch_dtype=torch.float16 if device != "cpu" else torch.float32
    ).to(device)
    model.eval()

    return tokenizer, model, device


def _build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:

    context = "\n\n".join(
        f"[Source: {chunk.source}]\n Content:\n{chunk.content}\n Chunk ID: {chunk.chunk_id}" for chunk in chunks
    )

    content = (
        f"Question: {query}\n\n"
        f"Context:\n{context}"
    )


def answer(query: str, chunks: list[RetrievedChunk]) -> str:
    
    if not chunks:
        return ("I don't have enough information in my knowledge base "
                "to answer that question.")
    
    tokenizer, model, device = _llm()

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": _build_user_prompt(query, chunks)
        }
    ]

    inputs = tokenizer.apply_chat_template(
        messages, apply_generation_prompt=True, return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        output = model.generate(
            inputs,
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
            do_sample=settings.temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # slice off the prompt tokens; decode only the newly generated ones
    answer_text = tokenizer.decode(
        output[0][inputs.shape[1]:], skip_special_tokens=True
    ).strip()
    
    logger.info("generated answer (%d chars) for question (len=%d)",
                len(answer_text), len(query))
    
    return answer_text
    
