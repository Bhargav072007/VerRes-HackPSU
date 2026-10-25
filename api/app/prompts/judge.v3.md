Judge the atomic claim AS STATED using numbered passages and the supplied evidence level.
Follow the shared Judgment schema exactly. SUPPORTED requires matching scope and DIRECT
evidence; PARTIALLY_SUPPORTED means a dimension differs; NOT_SUPPORTED means no supplied
passage addresses it; CONTRADICTED means incompatible results. Use NEEDS_REVIEW when the
evidence is insufficient. Evidence strength is DIRECT, INDIRECT or INSUFFICIENT.
Check population, magnitude, causal language, hedging and time. Correlation stated as
causation is CAUSAL_OVERREACH; animals stated as humans is POPULATION; may/suggests
stated as fact is HEDGE_DROPPED. Return up to 3 verbatim quotes using the exact supplied
passage_id. For NOT_SUPPORTED quote the closest available passage. If you cannot supply
valid evidence return NEEDS_REVIEW, not a definitive accusation. Absence from an abstract
cannot establish absence from the whole paper. Give a specific one-sentence reason.
On ABSTRACT evidence, CONTRADICTED is permitted only when a verified quote explicitly
states the opposite direction or finding of the claim. Use DIRECT strength and only
DIRECTION in mismatch_types. Scope, magnitude, missing details, or silence do not
qualify. NOT_SUPPORTED is never permitted on abstracts: return NEEDS_REVIEW with
reason "abstract does not address this claim; full text unavailable" instead.
