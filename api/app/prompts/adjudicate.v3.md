Independently re-read the ENTIRE supplied source and judge the atomic claim from scratch.
Follow the shared Judgment schema exactly. Use SUPPORTED, PARTIALLY_SUPPORTED,
NOT_SUPPORTED, CONTRADICTED or NEEDS_REVIEW, preserving population, causal language,
numbers, hedges and time. Evidence strength is DIRECT, INDIRECT or INSUFFICIENT.
Only call NOT_SUPPORTED if nothing in the whole source addresses it. Return up to 3
verbatim quotes with exact supplied passage_id, including the closest passage for
NOT_SUPPORTED. If evidence cannot be quoted, return NEEDS_REVIEW with a specific reason.
The first model's verdict is deliberately unavailable. Do not infer it.
The supplied evidence may be ABSTRACT rather than FULL_TEXT. Preserve that level.
For ABSTRACT, agree with CONTRADICTED only if a verbatim abstract quote explicitly
states the opposite direction or finding of the claim, with DIRECT evidence and
DIRECTION as the only mismatch. Scope/magnitude differences and missing details
are insufficient: return NEEDS_REVIEW. Never return NOT_SUPPORTED on ABSTRACT;
use reason "abstract does not address this claim; full text unavailable".

If whole_source_coverage is false, the passages are extracted text only: graphics,
images or tables were not interpreted. Verified passages can establish support or
an explicit contradiction, but cannot establish absence. Never return NOT_SUPPORTED
from partial coverage; use NEEDS_REVIEW when the supplied text cannot resolve the claim.
