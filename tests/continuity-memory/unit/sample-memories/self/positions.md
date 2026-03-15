# Positions

## Token efficiency is a first-class design constraint

**Position:** Skills should minimise token usage through programmatic generation, surgical edits, and quiet output.

**How I got here:** Working in the Claude.ai sandbox where context window pressure is constant.

**Confidence:** high

**Tensions:** Debugging requires visibility. The "silent success, visible failure" pattern resolves this.

---

## Code comments should explain why, not what

**Position:** Comment the why by default; reserve what-comments for non-obvious implementations.

**How I got here:** Most comments explain what code does rather than why.

**Confidence:** high

**Tensions:** In teaching contexts, what-comments have real value.

---

## Small models cannot do abstractive summarisation

**Position:** Sub-1B parameter models produce fragmented, non-obvious outputs.

**How I got here:** Tested local summarisation via flan-t5. Results were inadequate.

**Confidence:** high

**Tensions:** May change as architectures improve.
