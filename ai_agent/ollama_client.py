import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def generate_text(prompt, model, max_tokens=2048):
    host = os.getenv(
        "OLLAMA_HOST", "http://localhost:11434"
    ).rstrip("/")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": max_tokens,
        },
    }

    request = Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Ollama HTTP error {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot connect to Ollama at {host}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Ollama returned an invalid API response."
        ) from exc
    if result.get("done_reason") == "length":
        raise RuntimeError(
            "Ollama reached the generation token limit "
            f"after {result.get('eval_count', 'unknown')} tokens. "
            "The JSON response may be incomplete."
        )

    content = result.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            "Ollama returned an empty model response."
        )

    return content.strip()
