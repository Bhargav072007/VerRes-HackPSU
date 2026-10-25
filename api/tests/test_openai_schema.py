import inspect
import json

import pydantic

import api.app.graph.service as graph_service
import api.app.review.panel as review_panel
import api.app.verify.models as verify_models
from api.app.verify import model


def test_strict_schemas_have_no_tuple_prefix_items():
    for module in (verify_models, review_panel, graph_service):
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, pydantic.BaseModel) and cls is not pydantic.BaseModel:
                schema = model.strict_schema(cls.model_json_schema())
                assert "prefixItems" not in json.dumps(schema), cls.__name__
