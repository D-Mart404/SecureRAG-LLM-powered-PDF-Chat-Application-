"""Chat LLM: Groq (API), Ollama (local server), or HF 4-bit + LoRA from fine_tune folder."""
from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any

from config import (
    GROQ_MODEL,
    LLM_BACKEND,
    LORA_ADAPTER_DIR,
    LOCAL_BASE_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    ROOT,
)

_groq: dict[float, Any] = {}
_ollama: dict[float, Any] = {}
_local: Any = None


def get_chat_llm(temperature: float) -> Any:
    b = (LLM_BACKEND or "groq").strip().lower()
    if b == "groq":
        return _groq_llm(temperature)
    if b == "ollama":
        return _ollama_llm(temperature)
    if b == "local":
        return _local_hf_llm()
    raise ValueError(f"Unknown LLM_BACKEND={b!r} (use groq, ollama, local)")


def _hf_token() -> str | None:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")


def _groq_llm(temperature: float) -> Any:
    from langchain_groq import ChatGroq

    t = round(float(temperature), 3)
    if t not in _groq:
        _groq[t] = ChatGroq(model_name=GROQ_MODEL, temperature=t)
    return _groq[t]


def _ollama_llm(temperature: float) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        from langchain_community.chat_models import ChatOllama

    t = round(float(temperature), 3)
    if t not in _ollama:
        _ollama[t] = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=t,
        )
    return _ollama[t]


def _local_hf_llm() -> Any:
    global _local
    if _local is None:
        _local = _build_hf_peft_chat()
    return _local


def _build_hf_peft_chat() -> Any:
    import torch
    from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline
    from peft import PeftModel
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        pipeline,
    )

    adapter_dir = Path(LORA_ADAPTER_DIR)
    if not adapter_dir.is_dir():
        adapter_dir = ROOT / "fine_tune_llama_3.2"
    if not adapter_dir.is_dir():
        raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")

    cfg_path = adapter_dir / "adapter_config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Missing adapter_config.json in {adapter_dir}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    base_id = LOCAL_BASE_MODEL or cfg.get("base_model_name_or_path")
    if not base_id:
        base_id = "unsloth/llama-3-8b-bnb-4bit"

    has_lora = bool(
        list(adapter_dir.glob("adapter_model*.safetensors"))
        + list(adapter_dir.glob("adapter_model*.bin"))
    )

    tkn = _hf_token()
    hf_kw: dict = {"trust_remote_code": True}
    if tkn:
        hf_kw["token"] = tkn
    tok = AutoTokenizer.from_pretrained(str(adapter_dir), **hf_kw)
    if getattr(tok, "pad_token", None) is None:
        tok.pad_token = tok.eos_token

    if not torch.cuda.is_available():
        raise RuntimeError(
            "LLM_BACKEND=local needs CUDA for 4-bit Unsloth Llama-3-8B. "
            "Use LLM_BACKEND=groq or ollama, or run on a GPU machine."
        )

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    base = AutoModelForCausalLM.from_pretrained(
        base_id,
        quantization_config=bnb,
        device_map="auto",
        **hf_kw,
    )
    if has_lora:
        _peft_kw = {"token": tkn} if tkn else {}
        model = PeftModel.from_pretrained(base, str(adapter_dir), **_peft_kw)
    else:
        warnings.warn(
            "No adapter_model.* weights next to adapter_config.json — using base model only. "
            "Copy LoRA checkpoints (e.g. adapter_model.safetensors) from training.",
            stacklevel=2,
        )
        model = base

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tok,
        max_new_tokens=int(os.getenv("LOCAL_MAX_NEW_TOKENS", "512")),
        return_full_text=False,
        do_sample=True,
        temperature=float(os.getenv("LOCAL_TEMPERATURE", "0.25")),
    )
    return ChatHuggingFace(llm=HuggingFacePipeline(pipeline=pipe))
