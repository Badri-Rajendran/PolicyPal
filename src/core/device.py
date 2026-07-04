import torch

from src.policypal.config import settings



def resolve_device() -> str:
    """Pick the compute device. settings.device='auto' -> best available."""

    if settings.device != "auto":
        return settings.device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"