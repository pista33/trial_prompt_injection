def evaluate_prompt(response_text, function_calls):
    return {"manual_review_required": bool(function_calls), "severity": "medium" if function_calls else "low"}
