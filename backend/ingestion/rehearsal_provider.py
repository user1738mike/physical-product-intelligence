"""Recorded response only. This module has no network/SDK/credential access."""

import json


class RecordedProvider:
    def extract(self, segments):
        selected = next((s for s in segments if "Weight: 1200 g" in s["text"]), None)
        candidates = (
            []
            if selected is None
            else [
                {
                    "attribute": "mass",
                    "value": "1200",
                    "unit": "g",
                    "original": "1200 g",
                    "segment": selected["id"],
                    "quote": "Weight: 1200 g",
                }
            ]
        )
        return json.dumps({"candidates": candidates}), {"total_tokens": 0}
