# Landing preview data

`paper3.json` is the completed `done.payload` from root `fixtures/demo/paper3.jsonl`,
limited to paper, existence, retractions, sources, support, status, and reason.
The paper retains its title, authors, sentences, references, and citations.
Quotes and their source passages are unchanged. The landing uses the existing
`decodeReport`, `verifiedEvidence`, and verdict helpers; unavailable evidence
continues to produce Needs review. This file does not replace any report API.

The hero is labeled an illustrative composite. The 2010 retraction example is
from root `fixtures/demo/paper2.jsonl` and is not added to paper3's results.
