import json
import re

from pydantic import BaseModel
from deepeval.models import DeepEvalBaseLLM
from langchain_groq import ChatGroq


def read_json_from_text(text):
    # Models sometimes wrap the JSON in ```json fences or add words around it.
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def schema_prompt(prompt, schema):
    return (
        prompt
        + "\n\nReturn ONLY one valid JSON object that follows this JSON schema. "
        + "Do not add any words before or after the JSON and do not use markdown.\n"
        + json.dumps(schema.model_json_schema())
    )


class GroqJudge(DeepEvalBaseLLM):
    def __init__(self, api_key, model_name="openai/gpt-oss-20b", tries=3):
        self.api_key = api_key
        self.model_name = model_name
        self.tries = tries

    def load_model(self):
        return ChatGroq(model=self.model_name, api_key=self.api_key, temperature=0)

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        model = self.load_model()
        if not schema:
            return model.invoke(prompt).content
        full_prompt = schema_prompt(prompt, schema)
        for attempt in range(self.tries):
            text = model.invoke(full_prompt).content
            try:
                return schema.model_validate(read_json_from_text(text))
            except ValueError:
                # Bad JSON from the model: try again. A Groq limit error is NOT caught here,
                # so it still reaches run_deepeval.py and stops the run politely.
                if attempt == self.tries - 1:
                    raise

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        model = self.load_model()
        if not schema:
            response = await model.ainvoke(prompt)
            return response.content
        full_prompt = schema_prompt(prompt, schema)
        for attempt in range(self.tries):
            response = await model.ainvoke(full_prompt)
            try:
                return schema.model_validate(read_json_from_text(response.content))
            except ValueError:
                if attempt == self.tries - 1:
                    raise

    def get_model_name(self):
        return self.model_name