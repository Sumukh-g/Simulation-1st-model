"""Check LLM provider configuration and reachability.

Run:  python -m scripts.check_llm

Prints which providers are configured and whether each responds. Never prints
API keys. Useful for verifying OpenAI / Groq / Gemini credentials.
"""
from __future__ import annotations

from services.common import llm


def main() -> int:
    print("LLM enabled:", llm.is_enabled())
    configured = llm.available_providers()
    print("Configured providers:", configured or "(none)")
    if not configured:
        print("\nNo providers configured. Set OPENAI_API_KEY / GROQ_API_KEY / GEMINI_API_KEY in .env")
        return 1

    print("\nReachability check (short timeout, no secrets):")
    status = llm.preflight()
    for name, state in status.items():
        model = llm._providers().get(name)
        model_name = model.model if model else "?"
        print(f"  - {name:<8} [{model_name}]: {state}")

    ok = [n for n, s in status.items() if s == "ok"]
    if not ok:
        print("\nNo provider is currently reachable. Check billing/quota and key validity.")
        return 1
    print(f"\nUsable now: {ok}. Tiers will route to these (with automatic fallback).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
