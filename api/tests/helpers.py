import json

from api.app.verify.models import Judgment, Quote


def judgment(
    label="SUPPORTED",
    quote="The treatment reduced inflammation in mice by 20 percent.",
    passage_id="p00001",
    **kwargs,
):
    return Judgment(
        label=label,
        reason="The source directly states this result.",
        mismatch_types=[],
        evidence=[Quote(passage_id=passage_id, quote=quote)],
        evidence_strength="DIRECT",
        **kwargs,
    )


class FixtureModel:
    def __init__(self, responses, model_id="fixture-model", family="fixture-family", vendor=None):
        self.responses = responses
        self.model_id, self.family = model_id, family
        self.vendor = family if vendor is None else vendor
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.responses[kwargs["task"]]
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(kwargs)
        return answer if isinstance(answer, str) else json.dumps(answer)
