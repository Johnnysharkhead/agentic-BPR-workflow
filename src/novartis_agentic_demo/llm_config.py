"""Minimal LLM configuration."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


class LLMConfig:
    model = os.getenv("LLM_MODEL", "prisma_default")
    base_url = os.getenv("LLM_BASE_URL", "https://api-dev.ai.auth.axis.cloud/v1")
    api_key = os.getenv("OPENAI_API_KEY")
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "").lower() in ("1", "true", "yes")

    @classmethod
    def get_callbacks(cls) -> list:
        if not cls.langfuse_enabled:
            return []
        # Langfuse SDK reads LANGFUSE_HOST; map from LANGFUSE_BASE_URL if needed
        if not os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_BASE_URL"):
            os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]
        from langfuse.langchain import CallbackHandler
        return [CallbackHandler()]

    @classmethod
    def get_llm(cls) -> ChatOpenAI:
        return ChatOpenAI(
            model=cls.model,
            api_key=cls.api_key,
            base_url=cls.base_url,
            temperature=0.3,
            max_tokens=4096,
            streaming=True,
            callbacks=cls.get_callbacks(),
        )