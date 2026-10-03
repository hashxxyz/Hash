import os, requests

def call_gemini(prompt):
    key=os.getenv("GEMINI_API_KEY")
    if not key: return "Gemini API key is not configured."
    r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",json={"contents":[{"parts":[{"text":prompt}]}]},timeout=60)
    r.raise_for_status(); return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def call_openrouter(prompt):
    key=os.getenv("OPENROUTER_API_KEY")
    if not key: return "OpenRouter API key is not configured."
    r=requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":"openrouter/free","messages":[{"role":"user","content":prompt}]},timeout=60)
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]

def call_groq(prompt):
    key=os.getenv("GROQ_API_KEY")
    if not key: return "Groq API key is not configured."
    r=requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":prompt}]},timeout=60)
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]
