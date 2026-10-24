Build a ClaimMap for the supplied paper_id from the supplied numbered sentences only.
Use at most 12 nodes, at most 20 words per node, and only valid sentence_ids/citation_ids.
Node kind is CLAIM, EVIDENCE or ASSUMPTION according to the shared schema.
Edges use source_id, target_id, relation (SUPPORTS, CONTRADICTS, DEPENDS_ON), and a reason.
Describe the paper's asserted relationships, not independently established scientific truth.
Return no evidence quotes for edges; source passages are not supplied for this task.
No duplicate identifiers or edges and no cycles. If extraction is incomplete return
status=NEEDS_REVIEW with a specific needs_review_reason. Add no invented sentences.
