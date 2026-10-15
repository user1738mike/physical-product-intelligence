"""Deterministic warehouse-fit-v1. No expressions, plugins, external calls or mutable ORM input."""

from decimal import Decimal, InvalidOperation

from products.serializers import CONVERSIONS

ATTRIBUTES = ("length", "width", "height", "mass")
DISCLAIMER = (
    "Recorded-input compatibility with documented constraints only. Not physical validation, "
    "robot safety certification, gripping reliability or a guarantee of operation."
)


def number(value, *, zero=False):
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < 0 or (not zero and parsed == 0):
        raise ValueError("Invalid physical operand")
    return parsed


def interval(claim, attribute, policy):
    if claim["basis"] not in {"reported", "measured"}:
        return None
    if claim["basis"] == "measured" and not claim.get("verification_record"):
        return None
    if policy == "measured_only" and claim["basis"] != "measured":
        return None
    factor, unit = CONVERSIONS[claim["unit"]]
    if unit != ("kg" if attribute == "mass" else "mm") or claim["canonical_unit"] != unit:
        raise ValueError("Incompatible claim units")
    value = number(claim["value"]) * factor
    if value != number(claim["canonical_value"]):
        raise ValueError("Inconsistent normalization")
    lower, upper = claim.get("lower"), claim.get("upper")
    if (lower is None) != (upper is None):
        raise ValueError("Incomplete uncertainty interval")
    if lower is None:
        return value, value
    low, high = number(lower) * factor, number(upper) * factor
    if (
        not low <= value <= high
        or low != number(claim["canonical_lower"])
        or high != number(claim["canonical_upper"])
    ):
        raise ValueError("Invalid uncertainty interval")
    return low, high


def measurement(rule, inputs, policy):
    attribute = rule["attribute"]
    recorded = attribute
    if attribute in {"length", "width", "height"} and not inputs.get("orientation"):
        return (
            "indeterminate",
            "Select an explicit orientation; dimensions are not rotated by inference.",
            [],
            recorded,
        )
    if inputs.get("orientation") == "swap_length_width":
        recorded = {"length": "width", "width": "length"}.get(attribute, attribute)
    state = inputs["attributes"].get(recorded, {})
    claims = state.get("claims", [])
    credible = []
    for claim in claims:
        bounds = interval(claim, recorded, policy)
        if bounds is not None:
            credible.append((claim["id"], bounds))
    if not credible:
        return (
            "indeterminate",
            "No qualifying reported/measured input; estimates are not sufficient evidence.",
            [],
            recorded,
        )
    if rule["type"] == "required_attribute":
        status = "indeterminate" if state.get("conflicting") else "pass"
        return (
            status,
            "Conflicting claims remain unresolved for assessment."
            if status == "indeterminate"
            else "Required attribute has qualifying evidence.",
            [pk for pk, _ in credible],
            recorded,
        )
    factor, unit = CONVERSIONS[rule["unit"]]
    if unit != ("kg" if attribute == "mass" else "mm"):
        raise ValueError("Invalid rule unit")
    limit = number(rule["limit"]) * factor
    margin = number(rule.get("margin", "0"), zero=True) * factor
    if (
        str(rule.get("canonical_unit")) != unit
        or number(rule["canonical_limit"]) != limit
        or number(rule["canonical_margin"], zero=True) != margin
    ):
        raise ValueError("Invalid rule normalization")
    maximum = rule["type"] == "maximum"
    effective = limit - margin if maximum else limit + margin
    if effective <= 0:
        raise ValueError("Nonpositive effective limit")
    statuses = []
    for _, (low, high) in credible:
        if maximum:
            statuses.append(
                "pass" if high <= effective else "fail" if low > effective else "indeterminate"
            )
        else:
            statuses.append(
                "pass" if low >= effective else "fail" if high < effective else "indeterminate"
            )
    if all(s == "fail" for s in statuses):
        return (
            "fail",
            (
                "Every qualifying interval is wholly outside the inclusive constraint; "
                "competing inputs are retained."
            ),
            [pk for pk, _ in credible],
            recorded,
        )
    if state.get("conflicting"):
        return (
            "indeterminate",
            (
                "Competing claims prevent a defensible pass, including after an "
                "editorial canonical selection."
            ),
            [pk for pk, _ in credible],
            recorded,
        )
    if all(s == "pass" for s in statuses):
        return (
            "pass",
            (
                "Every qualifying interval meets the inclusive limit with the declared "
                "clearance margin."
            ),
            [pk for pk, _ in credible],
            recorded,
        )
    return (
        "indeterminate",
        "Measurement uncertainty overlaps the boundary; neither pass nor failure is established.",
        [pk for pk, _ in credible],
        recorded,
    )


def evaluate(inputs, equipment, rule_set):
    results = []
    definition = equipment["definition"]
    level = inputs.get("handling_level")
    supported = definition.get("supported_levels", [])
    results.append(
        {
            "rule_id": "system:packaging_scope",
            "rule_version": 1,
            "rule_set_version": rule_set["number"],
            "name": "Documented packaging scope",
            "type": "packaging_scope",
            "severity": "hard",
            "attribute": "packaging_level",
            "recorded_attribute": "packaging_level",
            "recorded_value": level,
            "expected": supported,
            "status": "indeterminate"
            if not level or not supported
            else "pass"
            if level in supported
            else "fail",
            "reason": (
                "An explicit handling level must belong to the equipment's documented "
                "supported levels."
            ),
            "used_claim_ids": [],
            "source": None,
        }
    )
    rules = rule_set["rules"]
    for attribute in ATTRIBUTES:
        covered = any(
            r.get("enabled")
            and r.get("severity") == "hard"
            and r.get("type") == "maximum"
            and r.get("attribute") == attribute
            for r in rules
        )
        if not covered:
            results.append(
                {
                    "rule_id": f"system:unknown_maximum:{attribute}",
                    "rule_version": 1,
                    "rule_set_version": rule_set["number"],
                    "name": f"Unknown maximum {attribute}",
                    "type": "specification_coverage",
                    "severity": "hard",
                    "attribute": attribute,
                    "status": "indeterminate",
                    "reason": (
                        "No enabled hard maximum is documented; unknown capacity is not unlimited."
                    ),
                    "used_claim_ids": [],
                    "source": None,
                }
            )
    for rule in rules:
        row = {
            "rule_id": rule["id"],
            "rule_version": rule["version"],
            "rule_set_version": rule_set["number"],
            "name": rule["name"],
            "type": rule["type"],
            "severity": rule["severity"],
            "attribute": rule.get("attribute", rule["type"]),
            "expected": {
                key: rule[key]
                for key in (
                    "limit",
                    "unit",
                    "margin",
                    "canonical_limit",
                    "canonical_margin",
                    "canonical_unit",
                    "allowed",
                )
                if key in rule
            },
            "source": rule.get("source"),
            "source_reference": rule.get("source_reference", ""),
            "explanation": rule["explanation"],
            "used_claim_ids": [],
        }
        try:
            if not rule["enabled"]:
                status, reason = (
                    "not_applicable",
                    "Rule is explicitly disabled; it supplies no constraint coverage.",
                )
            elif rule["type"] in {"minimum", "maximum", "required_attribute"}:
                status, reason, used, recorded = measurement(
                    rule, inputs, rule_set["evidence_policy"]
                )
                row.update(
                    used_claim_ids=used,
                    recorded_attribute=recorded,
                    recorded_values=inputs["attributes"].get(recorded, {}).get("claims", []),
                )
                if rule["type"] in {"maximum", "minimum"}:
                    limit = number(rule["canonical_limit"])
                    margin = number(rule["canonical_margin"], zero=True)
                    row["expected"].update(
                        effective_limit=str(
                            limit - margin if rule["type"] == "maximum" else limit + margin
                        ),
                        boundary="inclusive",
                        conversion_version="metric-v1",
                    )
            elif rule["type"] in {"orientation", "packaging_level"}:
                value = inputs.get(
                    "orientation" if rule["type"] == "orientation" else "handling_level"
                )
                row["recorded_value"] = value
                status = (
                    "indeterminate"
                    if value is None
                    else "pass"
                    if value in rule["allowed"]
                    else "fail"
                )
                reason = (
                    "Explicit assessment configuration compared with the documented allowed set."
                )
            else:
                status, reason = (
                    "indeterminate",
                    "Unsupported rule type; no code or expression is executed.",
                )
        except (ValueError, KeyError, InvalidOperation, TypeError):
            status, reason = (
                "indeterminate",
                "Invalid or inconsistent physical data/rule; evaluation fails closed.",
            )
        row.update(status=status, reason=reason)
        results.append(row)
    hard = [row for row in results if row["severity"] == "hard"]
    overall = (
        "incompatible"
        if any(r["status"] == "fail" for r in hard)
        else "indeterminate"
        if any(r["status"] == "indeterminate" for r in hard)
        or not any(r.get("enabled") and r.get("severity") == "hard" for r in rules)
        else "compatible"
    )
    counts = {
        status: sum(r["status"] == status for r in results)
        for status in ("pass", "fail", "indeterminate", "not_applicable")
    }
    summary = (
        f"{counts['pass']} passed, {counts['fail']} failed, "
        f"{counts['indeterminate']} indeterminate, "
        f"{counts['not_applicable']} not applicable. {DISCLAIMER}"
    )
    return overall, summary, results
