import os

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel

from schemas.output import Output

# env variables
load_dotenv()
ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY")

model = AnthropicModel("claude-3-5-haiku-20241022")


agent = Agent(
    model,
    instructions="Be concise and helpful.",
    output_type=Output,
)


class Client:
    def create_message(self, message):
        result = agent.run_sync(message)
        return result.output
