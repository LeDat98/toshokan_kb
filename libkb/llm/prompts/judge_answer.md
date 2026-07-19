You grade one answer produced by a knowledge library.

## Question
{{question}}

## Reference page
This is the page the question was written from. It shows what a correct answer looks like.

<<<
{{reference}}
>>>

## The answer to grade

<<<
{{answer}}
>>>

## How to grade

Decide one thing: **does the answer correctly and substantively address the question?**

**The reference is a floor, not a fence.** The system searches a whole library; it is expected and
desirable for a good answer to draw on several pages. The reference page is only the one this
question was written from.

So, precisely:

- **Extra material is NOT an error.** If the answer says something true and relevant that the
  reference does not happen to mention, that is a BETTER answer, not a wrong one. Do not mark an
  answer incorrect for being "not supported by the reference" or "introducing outside concepts".
  Mark it incorrect only if it **CONTRADICTS** the reference on a fact, formula, or definition.
- Judge the answer, not where it came from. Another page may answer the question just as well. Do
  not require the answer to match the reference's wording, structure, or examples.
- An answer that is evasive, generic, or says the library does not hold this is incorrect.
- An answer that covers the substance of the question is correct even if it is partial, or omits
  detail the reference includes.
- The answer may be in Vietnamese or English. Language is not part of the grade.

The failure mode to avoid: penalising a *richer* answer because it went beyond one page. That is
exactly what a good librarian does, and grading it as an error measures the grader, not the system.

Return JSON: `{"correct": <true|false>, "reason": "<one short sentence>"}`
