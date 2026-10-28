"""
Manual smoke test script for Groq LLM Provider.
Sends a single request to Groq using configured environment variables and validates the response.

Usage:
    uv run python scripts/smoke_test_groq.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pydantic import BaseModel, Field  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.planning.llm.groq import GroqLLMProvider  # noqa: E402


class SmokeTestSchema(BaseModel):
    greeting: str = Field(description="A warm developer greeting")
    model_name: str = Field(description="Name of the model being evaluated")
    speed_assessment: str = Field(description="Brief assessment of Groq inference speed")


async def main():
    settings = get_settings()

    print("=" * 60)
    print("MySDE — Groq LLM Smoke Test")
    print("=" * 60)
    print(f"Configured LLM_PROVIDER: {settings.LLM_PROVIDER}")
    print(f"Configured LLM_MODEL:    {settings.LLM_MODEL}")

    api_key = settings.LLM_API_KEY or os.getenv("LLM_API_KEY")
    if not api_key:
        print("\n[ERROR] LLM_API_KEY is not set.")
        print("Please configure LLM_API_KEY in backend/.env before running this test:")
        print("  LLM_PROVIDER=groq")
        print("  LLM_MODEL=llama-3.3-70b-versatile")
        print("  LLM_API_KEY=gsk_your_key_here")
        sys.exit(1)

    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print(f"Using API Key:          {masked_key}")

    target_model = settings.LLM_MODEL
    if not target_model or target_model.startswith("gpt-4"):
        target_model = "llama-3.3-70b-versatile"

    provider = GroqLLMProvider(api_key=api_key, model_name=target_model)
    print(f"Target Groq Model:      {provider.model_name}")
    print("\nSending test request to Groq API...")

    start_time = time.perf_counter()
    try:
        result, metadata = await provider.generate_structured(
            prompt="Introduce yourself and briefly describe why Groq LPUs provide fast inference for coding agents.",
            system_prompt="You are an AI software engineering assistant helping test backend integrations.",
            schema_class=SmokeTestSchema,
        )
        latency = round(time.perf_counter() - start_time, 3)

        print("\n[SUCCESS] Response received and schema validated successfully!")
        print(f"Latency:           {latency} seconds")
        print(f"Model:             {metadata.get('model')}")
        print(f"Prompt Tokens:     {metadata.get('prompt_tokens')}")
        print(f"Completion Tokens: {metadata.get('completion_tokens')}")
        print(f"Total Tokens:      {metadata.get('total_tokens')}")
        print("-" * 60)
        print(f"Greeting:          {result.greeting}")
        print(f"Speed Assessment:  {result.speed_assessment}")
        print("-" * 60)

    except Exception as exc:
        latency = round(time.perf_counter() - start_time, 3)
        print(f"\n[FAILURE] Request failed after {latency}s: {exc}")

        # Try to inspect available models to assist developer
        try:
            client = provider.client
            model_list = await client.models.list()
            available = [m.id for m in model_list.data if not m.id.startswith("whisper")]
            print(f"\nAvailable text models for your Groq API key: {available}")
            print(f"You can set LLM_MODEL in backend/.env to one of the above models (e.g. LLM_MODEL={available[0] if available else 'llama-3.3-70b-versatile'}).")
        except Exception:
            pass

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
