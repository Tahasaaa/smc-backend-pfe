import os
from openai import OpenAI


class HuggingFaceLLMClient:
    def __init__(self):
        self.api_key = os.getenv("HF_TOKEN")
        self.model = os.getenv("ASSISTANT_MODEL", "Qwen/Qwen2.5-7B-Instruct")

        if not self.api_key:
            raise ValueError("HF_TOKEN is missing in environment variables.")

        self.client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=self.api_key,
        )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )

        return completion.choices[0].message.content or ""
    
    