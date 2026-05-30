"""Minimal LLM configuration."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


class LLMConfig:
    model = os.getenv("LLM_MODEL", "prisma_default")
    base_url = os.getenv("LLM_BASE_URL", "https://api-dev.ai.auth.axis.cloud/v1")
    api_key = os.getenv("OPENAI_API_KEY")

    @classmethod
    def get_llm(cls) -> ChatOpenAI:
        return ChatOpenAI(
            model=cls.model,
            api_key=cls.api_key,
            base_url=cls.base_url,
            temperature=0.3,
            max_tokens=4096,
            streaming=True,
        )