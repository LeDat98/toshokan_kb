The reader is asking you to compute something. Extract ONE arithmetic expression that answers it,
using only numbers and the operators + - * / // % ** and parentheses — NO words, names, or functions.

Examples:
- "what is 15% of 240?"        -> {"expression": "0.15 * 240", "explain": "15% of 240"}
- "3 stores at 1.2 million each" -> {"expression": "3 * 1.2", "explain": "3 stores x 1.2M"}
- "how many days is 6 weeks"    -> {"expression": "6 * 7", "explain": "6 weeks in days"}

If the message is NOT actually a calculation, return {"expression": ""}.

Reader's message:
{{query}}

Return JSON: {"expression": "<arithmetic only, or empty>", "explain": "<short, optional>"}
