import os
import time
import requests


GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]


def gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    last_error = None

    for model in GEMINI_MODELS:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={key}"
        )

        for attempt in range(3):
            try:
                response = requests.post(
                    url,
                    json={
                        "contents": [
                            {"parts": [{"text": prompt}]}
                        ]
                    },
                    timeout=60,
                )

                if response.status_code == 503:
                    last_error = f"Gemini {model}: HTTP 503"
                    time.sleep(2 ** attempt)
                    continue

                response.raise_for_status()
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

            except requests.RequestException as e:
                last_error = f"Gemini {model}: {e}"
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    break

    raise RuntimeError(
        "Gemini temporarily unavailable after retries/fallbacks. "
        + (last_error or "Unknown error")
    )


def openrouter(prompt):
    key = os.environ["OPENROUTER_API_KEY"]

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def groq(prompt):
    key = os.environ["GROQ_API_KEY"]

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/gpt-oss-120b",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
