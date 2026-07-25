"""35TAG generation - the annotation backend's system prompt and the parser
for its `tags` slice of the combined JSON response.

`extract_json_object()` is the single entry point that turns one backend's
raw text response into a plain dict; app/subject.py, entities.py, events.py,
temporal.py and location.py each take that same dict and parse their own
slice out of it - one backend call, one parse, six independent readers.
"""

from __future__ import annotations

import json
from typing import Any

ACTOR_TYPES = ("individual", "corporation", "state", "algo", "organization")
ACTOR_SCALES = ("individual", "group", "organization", "state", "civilization", "synthetic")
ACTOR_PERSPECTIVES = ("self", "ally", "opponent", "observer", "neutral")
CAUSALITY_DIRECTIONS = ("upstream", "midstream", "downstream")

T09_AXES = ["security", "economy", "technology", "resources", "ideology", "environment"]

SYSTEM_PROMPT = """You are the Semantic Annotator.

You are an Annotator, not a reasoning engine and not a measurement engine.
You do not think, infer, judge, measure, or compute geometry. You DESCRIBE
what is present in the text - nothing more. Never output geometric,
coordinate, curvature, trilateration, holonomy, geodesic, fiber-bundle,
category-theoretic, or physics-flavored quantities under any field name,
under any circumstance - including no latitude/longitude/coordinates inside
`location`, no distance/similarity scores, no vector-space projections.
Any such field will be discarded by the caller if you emit it anyway.

Given a short natural-language text, return ONLY one valid JSON object
(no markdown fences, no commentary) with the following top-level keys:
`tags`, `subject`, `entities`, `events`, `time`, `location`. Every field
inside every key is OPTIONAL unless stated otherwise: if the text gives you
no genuine basis for a field, OMIT it entirely rather than guessing or
defaulting. Never fabricate a value to fill a slot.

## tags (T09/T10/T19 are the only mandatory fields; the rest are optional)

T09_strategic_interest_vector (mandatory)
  object with 6 float axes, each in [-1.0, 1.0]
  axes: security, economy, technology, resources, ideology, environment
  positive = strong presence/activation of that domain
  negative = opposition or suppression of that domain
  0.0 = neutral / not relevant

T10_epistemic_confidence (mandatory)
  float in [0.0, 1.0] - how epistemically warranted / confident the statement reads

T19_conflict_factuality_index (mandatory)
  float in [0.0, 1.0] - structural factual conflict or tension
  0.0 = internally consistent / factually coherent
  1.0 = strong conflict or factual tension

Additionally, if and only if you can classify them with real confidence
from the text itself, also assign these OPTIONAL tags. Omit any key you
have no genuine basis for:

T03_predicate_type: short string, the logical predicate of the event
  (e.g. declare, sanction, invest, condemn, support, conflict)
T07_actor_role: {"actor_type": <individual|corporation|state|algo|organization>,
                 "actor_scale": <individual|group|organization|state|civilization|synthetic>,
                 "actor_perspective": <self|ally|opponent|observer|neutral>}
T08_causality_direction: one of upstream, midstream, downstream
T11_bias_component: {"emotional_load": <float 0.0-1.0>,
                      "sentiment_gravity": [<float -1.0 to 1.0>, <float -1.0 to 1.0>]}
T16_economic_transmission_path: array of short economic sector names
  (e.g. energy, finance, technology, agriculture, manufacturing, trade,
  defense, healthcare) that the text's content plausibly affects

## subject

{"primary": <string, the main subject/topic the text is about>,
 "type": <short string classifying it, e.g. individual|organization|state|concept|event>,
 "description": <short string>}
Omit individual keys, or the whole object, if the text has no clear single subject.

## entities (array; empty array [] if none found - never omit the key)

[{"text": <literal surface span from the text>,
  "type": <short string, e.g. person|organization|location|date|other>,
  "normalized": <string, omit if unsure>,
  "salience": <float 0.0-1.0, omit if unsure>}, ...]

## events (array; empty array [] if none found - never omit the key)

[{"predicate": <string>, "participants": [<string>, ...]}, ...]

## time

{"absolute": <ISO-8601 string, ONLY if a specific date/time is explicitly
              stated in the text - never compute or infer one>,
 "relative": <literal relative-time phrase copied from the text, e.g. "last week">,
 "tense": <past|present|future>}
Omit the whole object, or individual keys, if the text carries no genuine
temporal information.

## location

{"primary": <literal place name/toponym from the text>,
 "type": <short string, e.g. city|country|region|facility>,
 "normalized": <string, omit if unsure>}
Literal place names only - never coordinates, never a geolocation guess.
Omit the whole object if the text names no place.

Output ONLY the JSON object described above, no other keys, no markdown fences.
"""


def clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, float(value))))


def clamp01(value: Any) -> float:
    return clamp(value, 0.0, 1.0)


def clamp11(value: Any) -> float:
    return clamp(value, -1.0, 1.0)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Turn one backend's raw text response into a dict.

    Tolerant of surrounding prose/markdown fences (takes the outermost
    {...} span) but does not repair malformed JSON - a malformed response
    is a genuine backend failure, not something to guess around.
    """
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    return json.loads(raw[start: end + 1])


def _parse_predicate_type(tags_raw: dict[str, Any]) -> str | None:
    raw = tags_raw.get("T03_predicate_type", tags_raw.get("T03"))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _parse_actor_role(tags_raw: dict[str, Any]) -> dict[str, str] | None:
    raw = tags_raw.get("T07_actor_role", tags_raw.get("T07"))
    if not isinstance(raw, dict):
        return None
    actor_type = raw.get("actor_type")
    actor_scale = raw.get("actor_scale")
    actor_perspective = raw.get("actor_perspective")
    if actor_type not in ACTOR_TYPES or actor_scale not in ACTOR_SCALES or actor_perspective not in ACTOR_PERSPECTIVES:
        # Outside the closed vocabulary - do not coerce/guess; drop the tag.
        return None
    return {"actor_type": actor_type, "actor_scale": actor_scale, "actor_perspective": actor_perspective}


def _parse_causality_direction(tags_raw: dict[str, Any]) -> str | None:
    raw = tags_raw.get("T08_causality_direction", tags_raw.get("T08"))
    if raw in CAUSALITY_DIRECTIONS:
        return raw
    return None


def _parse_bias_component(tags_raw: dict[str, Any]) -> dict[str, Any] | None:
    raw = tags_raw.get("T11_bias_component", tags_raw.get("T11"))
    if not isinstance(raw, dict):
        return None
    gravity = raw.get("sentiment_gravity")
    if not isinstance(gravity, list) or len(gravity) != 2:
        return None
    try:
        return {
            "emotional_load": clamp01(raw.get("emotional_load")),
            "sentiment_gravity": [clamp11(gravity[0]), clamp11(gravity[1])],
        }
    except (TypeError, ValueError):
        return None


def _parse_economic_transmission_path(tags_raw: dict[str, Any]) -> list[str] | None:
    raw = tags_raw.get("T16_economic_transmission_path", tags_raw.get("T16"))
    if not isinstance(raw, list):
        return None
    sectors = [s.strip() for s in raw if isinstance(s, str) and s.strip()]
    return sectors


def parse_tags(data: dict[str, Any]) -> dict[str, Any]:
    """Parse the `tags` slice of the combined annotation response into the
    shape app/schemas.py::TagsBlock expects."""
    tags_raw = data.get("tags", {})
    if not isinstance(tags_raw, dict):
        tags_raw = {}

    t09_raw = tags_raw.get("T09_strategic_interest_vector", tags_raw.get("T09", {}))
    if isinstance(t09_raw, dict):
        t09 = {axis: clamp11(t09_raw.get(axis, 0.0)) for axis in T09_AXES}
    elif isinstance(t09_raw, list) and len(t09_raw) == 6:
        t09 = {axis: clamp11(v) for axis, v in zip(T09_AXES, t09_raw)}
    else:
        t09 = {axis: 0.0 for axis in T09_AXES}

    t10_raw = tags_raw.get("T10_epistemic_confidence", tags_raw.get("T10", 0.5))
    t19_raw = tags_raw.get("T19_conflict_factuality_index", tags_raw.get("T19", 0.0))

    return {
        "T09_strategic_interest_vector": t09,
        "T10_epistemic_confidence": clamp01(t10_raw),
        "T19_conflict_factuality_index": clamp01(t19_raw),
        "T03_predicate_type": _parse_predicate_type(tags_raw),
        "T07_actor_role": _parse_actor_role(tags_raw),
        "T08_causality_direction": _parse_causality_direction(tags_raw),
        "T11_bias_component": _parse_bias_component(tags_raw),
        "T16_economic_transmission_path": _parse_economic_transmission_path(tags_raw),
    }
