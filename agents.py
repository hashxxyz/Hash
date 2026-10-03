import os
import requests


def gemini(prompt):
    key = os.environ["GEMINI_API_KEY"]

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-3.5-flash:generateContent"
        f"?key={key}"
    )

    response = requests.post(
        url,
        json={
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]
