import os
from pydantic import BaseModel
from dotenv import load_dotenv

class KeyManager(BaseModel):
    ANTHROPIC: str | None = ""
    GEMINI: str | None = ""
    OPENAI: str | None = ""
    PERPLEXITY: str | None = ""
    SEMANTIC_SCHOLAR: str | None = ""
    LANGFUSE_PUBLIC: str | None = ""
    LANGFUSE_SECRET: str | None = ""
    LANGFUSE_HOST: str | None = ""

    def get_keys_from_env(self) -> None:

        load_dotenv()

        self.OPENAI           = os.getenv("OPENAI_API_KEY")
        self.GEMINI           = os.getenv("GOOGLE_API_KEY")
        self.ANTHROPIC        = os.getenv("ANTHROPIC_API_KEY") #not strictly needed
        self.PERPLEXITY       = os.getenv("PERPLEXITY_API_KEY") #only for citations
        self.SEMANTIC_SCHOLAR = os.getenv("SEMANTIC_SCHOLAR_KEY") #only for fast semantic scholar
        # Optional observability — only consumed if `langfuse` is installed.
        self.LANGFUSE_PUBLIC  = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.LANGFUSE_SECRET  = os.getenv("LANGFUSE_SECRET_KEY")
        self.LANGFUSE_HOST    = os.getenv("LANGFUSE_HOST")

    def __getitem__(self, key: str) -> str:
        return getattr(self, key)

    def __setitem__(self, key: str, value: str) -> None:
        setattr(self, key, value)
