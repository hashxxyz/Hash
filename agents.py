import json
import os
import re
import time
import requests

TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "40"))

DEFAULT_GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

SECRET_ENV_NAMES = [
    "GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY",
    "API_FOOTBALL_KEY", "TELEGRAM_BOT_TOKEN",
]


def scrub(text):
    """Remove API keys / tokens from any text before it is logged or shown."""
    text = str(text)
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "***")
    text = re.sub(r"([?&]key=)[^&\s'\"]+", r"\1***", text)
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", text)
    return text


def _timeout(deadline):
    """Per-request timeout that never runs past the overall deadline."""
    if deadline is None:
        return TIMEOUT
    left = deadline - time.time()
    if left < 6:
        raise RuntimeError("time budget exhausted")
    return min(TIMEOUT, left)


def _gemini_models():
    env = os.environ.get("GEMINI_MODELS", "")
    models = [m.strip() for m in env.split(",") if m.strip()]
    return models or DEFAULT_GEMINI_MODELS


def gemini(prompt, deadline=None, json_mode=False):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json", "temperature": 0.3}

    last_error = None
    for model in _gemini_models():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=body,
                    timeout=_timeout(deadline),
                )
                code = response.status_code
                if code in (429, 500, 502, 503, 504):
                    last_error = f"Gemini {model}: HTTP {code}"
                    if attempt == 0:
                        time.sleep(1.5)
                        continue
                    break
                if code in (400, 401, 403, 404):
                    last_error = f"Gemini {model}: HTTP {code} (check model name / key)"
                    break
                response.raise_for_status()
                parts = response.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
                last_error = f"Gemini {model}: empty response"
                break
            except RuntimeError:
                raise
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                last_error = f"Gemini {model}: {scrub(e)}"
                break

    raise RuntimeError("Gemini unavailable. " + scrub(last_error or "Unknown error"))


def _chat(name, url, key_env, model, prompt, deadline=None, json_mode=False):
    key = os.environ.get(key_env)
    if not key:
        raise RuntimeError(f"{key_env} is not configured.")
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if json_mode and name == "Groq":
        body["response_format"] = {"type": "json_object"}
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=_timeout(deadline),
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except RuntimeError:
        raise
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"{name} failed: {scrub(e)}")


def openrouter(prompt, deadline=None, json_mode=False):
    return _chat("OpenRouter", "https://openrouter.ai/api/v1/chat/completions",
                 "OPENROUTER_API_KEY", os.environ.get("OPENROUTER_MODEL", "openrouter/free"),
                 prompt, deadline, json_mode)


def groq(prompt, deadline=None, json_mode=False):
    return _chat("Groq", "https://api.groq.com/openai/v1/chat/completions",
                 "GROQ_API_KEY", os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                 prompt, deadline, json_mode)


PROVIDERS = {"gemini": gemini, "openrouter": openrouter, "groq": groq}


def extract_json(text):
    text = re.sub(r"```(?:json)?", "", str(text)).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def ask(prompt, order, deadline=None):
    """Try providers in order; return the first text reply."""
    errors = []
    for name in order:
        try:
            return PROVIDERS[name](prompt, deadline=deadline)
        except Exception as e:
            errors.append(f"{name}: {scrub(e)}")
    raise RuntimeError("All AI providers failed. " + " | ".join(errors))


def ask_json(prompt, order, deadline=None):
    """Try providers in order; return the first reply that parses as a JSON object."""
    errors = []
    for name in order:
        try:
            return extract_json(PROVIDERS[name](prompt, deadline=deadline, json_mode=True))
        except Exception as e:
            errors.append(f"{name}: {scrub(e)}")
    raise RuntimeError("All AI providers failed. " + " | ".join(errors))
