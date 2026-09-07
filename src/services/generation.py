from src.core.logging import get_logger
from src.policypal.config import settings
from src.core.device import resolve_device
from .retrieval import RetrievedChunk, search

from transformers import AutoTokenizer, AutoModelForCausalLM
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

    logger.info("LLM will be run on: %s", device)

    tokenizer = AutoTokenizer.from_pretrained(settings.llm_model)
    model = AutoModelForCausalLM.from_pretrained(
        settings.llm_model,
        # fp16 is only reliable on CUDA; MPS's fp16 kernels are known to
        # stall/misbehave on generation ops, so fall back to fp32 there.
        dtype=torch.float16 if device == "cuda" else torch.float32
    ).to(device)

    model.eval() # Switching to Inference mode.

    return tokenizer, model, device


def _build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:

    context = "\n\n".join(f"[Source: {chunk.source}]\nContent:\n{chunk.content}" for chunk in chunks)

    content = (
        f"Question: {query}\n\n"
        f"Context:\n{context}\n\n"
        "Think step by step to obtain the answer"
    )

    return content


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
        messages, add_generation_prompt=True, return_tensors="pt",
        enable_thinking=False, return_dict=True,
    ).to(device)

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
            do_sample=settings.temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # slice off the prompt tokens; decode only the newly generated ones
    answer_text = tokenizer.decode(
        output[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
    ).strip()
    
    logger.info("generated answer (%d chars) for question (len=%d)",
                len(answer_text), len(query))

    return answer_text


def answer_query(query: str, top_k: int | None = None) -> tuple[str, list[RetrievedChunk]]:
    """Run the full RAG pipeline: retrieve relevant chunks, then generate a grounded answer."""
    chunks = search(query, top_k)
    return answer(query, chunks), chunks

