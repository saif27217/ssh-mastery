# Minimal litellm stub for proot Ubuntu container
# Only provides what fastapi_server.py actually imports and uses
import httpx
from typing import Any, Optional

class Choice:
    def __init__(self, message):
        self.message = message
        self.index = 0

class Message:
    def __init__(self, content):
        self.content = content
        self.role = "assistant"
        self.tool_calls = None

class CompletionResponse:
    def __init__(self, choices, model="stub"):
        self.choices = choices
        self.model = model
    
    def model_dump(self):
        return {
            "choices": [{"message": {"content": c.message.content, "role": c.message.role}} for c in self.choices],
            "model": self.model
        }

async def acompletion(
    model: str = "",
    messages: list = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    response_format: dict = None,
    extra_headers: dict = None,
    api_key: str = None,
    **kwargs
):
    """Stub acompletion that proxies to the local 1minAI server on port 9000."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "http://127.0.0.1:9000/v1/chat/completions",
            json={
                "model": model or "default",
                "messages": messages or [],
                "temperature": temperature,
                "max_tokens": max_tokens,
                **(response_format or {}),
            },
            headers=extra_headers or {},
        )
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return CompletionResponse([Choice(Message(content))], model=data.get("model", model))

# Also expose litellm API for compatibility
class _LiteLLM:
    acompletion = acompletion

litellm = _LiteLLM()
