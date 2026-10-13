"""Run: python -m app.llm.check   (tells you if Gemini works from this machine)"""
import time

from app.llm.factory import get_llm


def main() -> None:
    t = time.time()
    try:
        out = get_llm().generate("Reply with one word.", "Say OK")
        print(f"WORKS in {time.time() - t:.1f}s -> {out.strip()[:40]}")
    except Exception as e:
        print(f"FAILED after {time.time() - t:.1f}s -> {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
