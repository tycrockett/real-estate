from __future__ import annotations

import json
import sys

from realestate.models import ScoredProperty
from realestate.output import register


@register("json")
class JsonFormatter:
    name = "json"

    def format(self, results: list[ScoredProperty], dest: str | None = None) -> None:
        data = [r.model_dump(mode="json") for r in results]
        output = json.dumps(data, indent=2)

        if dest:
            with open(dest, "w") as f:
                f.write(output)
        else:
            sys.stdout.write(output + "\n")
