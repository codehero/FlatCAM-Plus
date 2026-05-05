# FlatCAM Plus AI Assistant Module
# License: FlatCAM Plus AI Assistant Module Non-Commercial License.
# See appPlugins/ai_assistant/LICENSE.

import json
import urllib.error
import urllib.parse
import urllib.request


PROVIDER_SPECS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_label": "API Key",
        "timeout": 45,
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "api_key_label": "API Key",
        "timeout": 45,
    },
    "lmstudio": {
        "label": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "",
        "api_key_label": "API Key (optional)",
        "timeout": 45,
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "",
        "api_key_label": "API Key (unused)",
        "timeout": 60,
    },
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "model": "gemini-2.0-flash",
        "api_key_label": "API Key",
        "timeout": 45,
    },
    "claude": {
        "label": "Claude",
        "base_url": "https://api.anthropic.com",
        "model": "claude-3-5-haiku-latest",
        "api_key_label": "API Key",
        "timeout": 45,
    },
}


def provider_ids():
    return list(PROVIDER_SPECS.keys())


def provider_spec(provider_id):
    return PROVIDER_SPECS[provider_id]


def default_settings(provider_id):
    spec = provider_spec(provider_id)
    return {
        "provider": provider_id,
        "base_url": spec["base_url"],
        "model": spec["model"],
        "api_key": "",
        "timeout": spec["timeout"],
        "temperature": 0.2,
    }


def test_connection(provider_id, settings):
    provider_id = (provider_id or "").strip().lower()
    settings = dict(settings or {})

    if provider_id in ("openai", "openrouter", "lmstudio"):
        models = _list_openai_compatible_models(provider_id, settings)
    elif provider_id == "ollama":
        models = _list_ollama_models(settings)
    elif provider_id == "gemini":
        models = _list_gemini_models(settings)
    elif provider_id == "claude":
        models = _list_claude_models(settings)
    else:
        raise RuntimeError("Unsupported provider: %s" % provider_id)

    preview = ", ".join(models[:3]) if models else "connected"
    return True, preview


def request_completion(provider_id, settings, system_prompt, context_text, history, user_prompt):
    provider_id = (provider_id or "").strip().lower()
    settings = dict(settings or {})
    history = list(history or [])
    full_system_prompt = (system_prompt or "").strip()
    context_text = (context_text or "").strip()
    if context_text:
        full_system_prompt = "%s\n\nFlatCAM context:\n%s" % (full_system_prompt, context_text)

    if provider_id in ("openai", "openrouter", "lmstudio"):
        return _request_openai_compatible(provider_id, settings, full_system_prompt, history, user_prompt)
    if provider_id == "ollama":
        return _request_ollama(settings, full_system_prompt, history, user_prompt)
    if provider_id == "gemini":
        return _request_gemini(settings, full_system_prompt, history, user_prompt)
    if provider_id == "claude":
        return _request_claude(settings, full_system_prompt, history, user_prompt)

    raise RuntimeError("Unsupported provider: %s" % provider_id)


def _request_openai_compatible(provider_id, settings, system_prompt, history, user_prompt):
    base_url = _normalized_base_url(settings, provider_id)
    model = _resolved_model(provider_id, settings)
    headers = _openai_compatible_headers(provider_id, settings)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_normalized_history(history))
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": _temperature(settings),
    }
    data = _json_request(
        "%s/chat/completions" % base_url,
        headers=headers,
        payload=payload,
        timeout=_timeout(settings)
    )
    try:
        message = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError("Unexpected response from %s: %s" % (provider_id, str(exc)))
    return _extract_text(message)


def _request_ollama(settings, system_prompt, history, user_prompt):
    base_url = _normalized_base_url(settings, "ollama")
    model = _resolved_model("ollama", settings)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_normalized_history(history))
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {
            "temperature": _temperature(settings),
        }
    }
    data = _json_request(
        "%s/api/chat" % base_url,
        headers={"Content-Type": "application/json"},
        payload=payload,
        timeout=_timeout(settings)
    )
    try:
        return data["message"]["content"]
    except Exception as exc:
        raise RuntimeError("Unexpected response from Ollama: %s" % str(exc))


def _request_gemini(settings, system_prompt, history, user_prompt):
    base_url = _normalized_base_url(settings, "gemini")
    model = _resolved_model("gemini", settings)
    api_key = (settings.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Gemini API key is required.")

    contents = []
    for item in _normalized_history(history):
        role = "model" if item.get("role") == "assistant" else "user"
        contents.append({
            "role": role,
            "parts": [{"text": item.get("content", "")}]
        })
    contents.append({
        "role": "user",
        "parts": [{"text": user_prompt}]
    })

    url = "%s/v1beta/models/%s:generateContent?key=%s" % (
        base_url,
        urllib.parse.quote(model, safe=""),
        urllib.parse.quote(api_key, safe="")
    )
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": _temperature(settings),
        }
    }
    data = _json_request(
        url,
        headers={"Content-Type": "application/json"},
        payload=payload,
        timeout=_timeout(settings)
    )
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except Exception as exc:
        raise RuntimeError("Unexpected response from Gemini: %s" % str(exc))
    return "\n".join(part.get("text", "") for part in parts if part.get("text"))


def _request_claude(settings, system_prompt, history, user_prompt):
    base_url = _normalized_base_url(settings, "claude")
    model = _resolved_model("claude", settings)
    api_key = (settings.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Claude API key is required.")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "system": system_prompt,
        "max_tokens": 1200,
        "temperature": _temperature(settings),
        "messages": _normalized_history(history) + [{"role": "user", "content": user_prompt}],
    }
    data = _json_request(
        "%s/v1/messages" % base_url,
        headers=headers,
        payload=payload,
        timeout=_timeout(settings)
    )
    try:
        content = data["content"]
    except Exception as exc:
        raise RuntimeError("Unexpected response from Claude: %s" % str(exc))
    texts = [item.get("text", "") for item in content if item.get("type") == "text" and item.get("text")]
    return "\n".join(texts)


def _list_openai_compatible_models(provider_id, settings):
    base_url = _normalized_base_url(settings, provider_id)
    data = _json_request(
        "%s/models" % base_url,
        headers=_openai_compatible_headers(provider_id, settings),
        timeout=_timeout(settings)
    )
    models = []
    for item in data.get("data", []):
        model_id = item.get("id")
        if model_id:
            models.append(model_id)
    return models


def _list_ollama_models(settings):
    base_url = _normalized_base_url(settings, "ollama")
    data = _json_request(
        "%s/api/tags" % base_url,
        timeout=_timeout(settings)
    )
    models = []
    for item in data.get("models", []):
        name = item.get("name")
        if name:
            models.append(name)
    return models


def _list_gemini_models(settings):
    base_url = _normalized_base_url(settings, "gemini")
    api_key = (settings.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Gemini API key is required.")
    url = "%s/v1beta/models?key=%s" % (
        base_url,
        urllib.parse.quote(api_key, safe="")
    )
    data = _json_request(url, timeout=_timeout(settings))
    models = []
    for item in data.get("models", []):
        name = item.get("name", "")
        if name:
            models.append(name.split("/", 1)[-1])
    return models


def _list_claude_models(settings):
    base_url = _normalized_base_url(settings, "claude")
    api_key = (settings.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Claude API key is required.")
    data = _json_request(
        "%s/v1/models" % base_url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout=_timeout(settings)
    )
    models = []
    for item in data.get("data", []):
        model_id = item.get("id")
        if model_id:
            models.append(model_id)
    return models


def _openai_compatible_headers(provider_id, settings):
    headers = {"Content-Type": "application/json"}
    api_key = (settings.get("api_key") or "").strip()
    if provider_id != "lmstudio" or api_key:
        if not api_key:
            raise RuntimeError("%s API key is required." % provider_spec(provider_id)["label"])
        headers["Authorization"] = "Bearer %s" % api_key
    if provider_id == "openrouter":
        headers["HTTP-Referer"] = "https://flatcam.local"
        headers["X-Title"] = "FlatCAM AI Assistant"
    return headers


def _normalized_base_url(settings, provider_id):
    base_url = (settings.get("base_url") or provider_spec(provider_id)["base_url"]).strip().rstrip("/")
    if not base_url:
        raise RuntimeError("Base URL is required.")
    return base_url


def _resolved_model(provider_id, settings):
    model = (settings.get("model") or "").strip()
    if model:
        return model

    if provider_id == "ollama":
        models = _list_ollama_models(settings)
        if models:
            return models[0]
    elif provider_id == "lmstudio":
        models = _list_openai_compatible_models(provider_id, settings)
        if models:
            return models[0]

    raise RuntimeError("Model is required for %s." % provider_spec(provider_id)["label"])


def _normalized_history(history):
    normalized = []
    for item in history:
        role = item.get("role", "")
        if role not in ("user", "assistant"):
            continue
        text = (item.get("content") or "").strip()
        if not text:
            continue
        normalized.append({"role": role, "content": text})
    return normalized[-10:]


def _extract_text(message):
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for item in message:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, dict) and item.get("text"):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    return str(message)


def _json_request(url, headers=None, payload=None, timeout=45):
    headers = dict(headers or {})
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        details = ""
        try:
            details = exc.read().decode("utf-8")
        except Exception:
            details = str(exc)
        raise RuntimeError("HTTP %s: %s" % (exc.code, details))
    except urllib.error.URLError as exc:
        raise RuntimeError("Connection failed: %s" % getattr(exc, "reason", exc))


def _timeout(settings):
    try:
        return max(5, int(settings.get("timeout", 45)))
    except (TypeError, ValueError):
        return 45


def _temperature(settings):
    try:
        value = float(settings.get("temperature", 0.2))
    except (TypeError, ValueError):
        value = 0.2
    return max(0.0, min(1.5, value))
