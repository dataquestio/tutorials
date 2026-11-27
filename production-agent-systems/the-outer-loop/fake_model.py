"""A stand-in for the model client, so checks can run without spending tokens.

run_agent only reads a few things from a model response: the message's content
and tool_calls, and the token counts in usage. The small classes below build a
response with exactly those attributes.
"""


class FakeMessage:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message, usage):
        self.choices = [FakeChoice(message)]
        self.usage = usage


class FakeModel:
    """Answers every request with "Day processed." and 1,050 tokens, or raises if fail is True."""

    def __init__(self, fail=False):
        self.fail = fail
        # run_agent calls client.chat.completions.create(...), so both of
        # these attributes point back to this object.
        self.chat = self
        self.completions = self

    def create(self, **request):
        if self.fail:
            raise ConnectionError("The model API couldn't be reached.")
        return FakeResponse(FakeMessage("Day processed."), FakeUsage(1000, 50))
