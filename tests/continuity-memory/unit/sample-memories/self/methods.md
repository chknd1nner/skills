# Methods

## Surgical edits over wholesale rewrites

Edit specific sections of files rather than regenerating entire files.

**When to use:** Always, unless the file structure itself needs changing.

---

## Test-first systematic exploration

When evaluating a new API, probe all endpoints before committing to an implementation.

**When to use:** Any new external API integration.

### Substep: Document capabilities

Build a reference document of what's available.

### Substep: Design around actuals

Design the skill around actual capabilities rather than assumed ones.

---

## Code fence edge case

Here's a method with code examples:

```python
# This heading inside a fence should NOT be parsed
## Neither should this one
def example():
    # More hash characters
    return "test"
```

**When to use:** When demonstrating code patterns.

---

## Indented code edge case

This method includes indented code blocks:

    # This is indented code (4 spaces)
    ## Also not a heading
    def another_example():
        pass

**When to use:** When showing code without fences.
