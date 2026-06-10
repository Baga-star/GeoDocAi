import httpx

from app.config import Settings
from app.prompts.geology import GEOLOGY_SYSTEM_PROMPT


class QwenClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = str(settings.qwen_base_url).rstrip("/")
        self.chat_url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"

    async def complete(self, user_prompt: str) -> str:
        if not self.settings.qwen_api_key or self.settings.qwen_api_key == "replace-me":
            raise RuntimeError("Qwen API key is not configured")
        payload = {
            "model": self.settings.qwen_model,
            "messages": [
                {"role": "system", "content": GEOLOGY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.settings.qwen_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(self.chat_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]
