"""A stand-in for the model client, so checks can run without spending tokens."""

from types import SimpleNamespace


class FakeModel:
    """Answers every request with "Day processed." and 1,050 tokens, or raises if fail is True."""

    def __init__(self, fail=False):
        self.fail = fail
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        if self.fail:
            raise ConnectionError("The model API couldn't be reached.")
        message = SimpleNamespace(content="Day processed.", tool_calls=None)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=50)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
