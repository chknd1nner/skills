# Backreference Guide

Complete guide to using the custom `$!N` backreference syntax in the regex file editor.

## Table of Contents

1. [Why Custom Backreference Syntax?](#why-custom-backreference-syntax)
2. [Basic Syntax](#basic-syntax)
3. [Comparison with Standard Syntax](#comparison-with-standard-syntax)
4. [Common Use Cases](#common-use-cases)
5. [Advanced Patterns](#advanced-patterns)
6. [Troubleshooting](#troubleshooting)

---

## Why Custom Backreference Syntax?

### The Problem with Standard Backreferences

Standard regex backreferences use `\1`, `\2`, `\3`, etc. However, this creates conflicts when working with code that contains:

- **Dollar signs**: Common in JavaScript, PHP, Bash, and other languages
- **Template literals**: JavaScript/TypeScript templates use `${variable}` syntax
- **Variable references**: Shell scripts use `$variable` and `${variable}`
- **Currency symbols**: Financial code with price calculations

### Example Conflict

**Code to Edit**:
```javascript
const price = $10.00;
const tax = $1.50;
```

**With Standard Syntax** (`\1`):
```bash
# Pattern: \$([0-9.]+)
# Replacement: \$\1 USD
# Problem: Backslashes can be ambiguous in replacement strings
```

**With Custom Syntax** (`$!1`):
```bash
# Pattern: \$([0-9.]+)
# Replacement: \$$!1 USD
# Clear: $!1 is unambiguous backreference, $ is literal dollar sign
```

### The Solution: `$!N` Syntax

The custom syntax uses `$!1`, `$!2`, `$!3`, etc., which:

- ✅ Never conflicts with dollar signs in code
- ✅ Clearly distinguishes backreferences from literal text
- ✅ Easy to read and understand
- ✅ Compatible with all programming languages

---

## Basic Syntax

### Creating Capture Groups

Use parentheses `(...)` in your pattern to create capture groups:

```regex
Pattern: function (.*?)\((.*?)\)
         ^^^^^^^^ ^^^^^ ^^^^^^^^
         Group 1  Group 2
```

### Referencing Capture Groups

In the replacement string, use `$!N` where N is the group number:

```
Replacement: async function $!1($!2)
                           ^^^^  ^^^^
                           Group 1  Group 2
```

### Complete Example

**Original Code**:
```javascript
function fetchData(url) {
  return fetch(url);
}
```

**Command**:
```bash
python scripts/regex_edit.py replace api.js \
  "function (.*?)\((.*?)\)" \
  "async function $!1($!2)"
```

**Result**:
```javascript
async function fetchData(url) {
  return fetch(url);
}
```

---

## Comparison with Standard Syntax

| Feature | Standard (`\1`) | Custom (`$!1`) |
|---------|----------------|----------------|
| Backreference syntax | `\1`, `\2`, `\3` | `$!1`, `$!2`, `$!3` |
| Conflicts with `$` | ⚠️ Yes (requires escaping) | ✅ No |
| Readability | ⚠️ Can be unclear | ✅ Very clear |
| Works in all contexts | ⚠️ Sometimes needs doubling | ✅ Always works |
| Example replacement | `Price: \$\1` (confusing) | `Price: $$!1` (clear) |

### Side-by-Side Example

**Task**: Add currency symbol to prices

**Standard Syntax** (potentially confusing):
```bash
# Pattern: price = ([0-9.]+)
# Replacement: price = \$\1
# Unclear: Is \$ an escape sequence or backreference?
```

**Custom Syntax** (crystal clear):
```bash
# Pattern: price = ([0-9.]+)
# Replacement: price = $$!1
# Clear: $ is literal, $!1 is backreference
```

---

## Common Use Cases

### 1. Reordering Captured Groups

**Swap function parameters**:

```bash
# Original: function foo(config, data)
# Pattern: function (.*?)\((.*?), (.*?)\)
# Replacement: function $!1($!3, $!2)
# Result: function foo(data, config)
```

### 2. Preserving Parts of Matched Text

**Update imports while keeping the imported items**:

```bash
# Original: import { User, Post } from 'old-package'
# Pattern: import \{(.*?)\} from 'old-package'
# Replacement: import {$!1} from 'new-package'
# Result: import { User, Post } from 'new-package'
```

### 3. Adding Context Around Captured Text

**Wrap error handling**:

```bash
# Original: throw new Error("Invalid input")
# Pattern: throw new Error\((.*?)\)
# Replacement: throw new CustomError($!1, { code: 'VALIDATION_ERROR' })
# Result: throw new CustomError("Invalid input", { code: 'VALIDATION_ERROR' })
```

### 4. Duplicating Captured Groups

**Create symmetric patterns**:

```bash
# Original: <div>Content</div>
# Pattern: <(.*?)>(.*?)</\1>
# Replacement: <$!1 class="wrapper">$!2</$!1>
# Result: <div class="wrapper">Content</div>
```

### 5. Conditional Text with Capture Groups

**Add optional parameters**:

```bash
# Original: function getData()
# Pattern: function (.*?)\(\)
# Replacement: function $!1(options = {})
# Result: function getData(options = {})
```

---

## Advanced Patterns

### Multiple Nested Groups

**Pattern with nested captures**:

```javascript
// Original:
const response = await fetch(url, { method: 'GET' });

// Pattern:
const (.*?) = await fetch\((.*?), \{(.*?)\}\);

// Replacement:
const $!1 = await apiClient.request($!2, {$!3, timeout: 5000});

// Result:
const response = await apiClient.request(url, { method: 'GET', timeout: 5000});
```

### Selective Preservation

**Keep class name but change inheritance**:

```python
# Original:
class UserService(BaseService):
    pass

# Pattern:
class (.*?)\(BaseService\):

# Replacement:
class $!1(APIService):

# Result:
class UserService(APIService):
    pass
```

### Format Transformation

**Reformat date strings**:

```bash
# Original: Date: 12/31/2023
# Pattern: Date: (\d{2})/(\d{2})/(\d{4})
# Replacement: Date: $!3-$!1-$!2
# Result: Date: 2023-12-31
```

### Wrapping with Additional Context

**Add try-catch around async operations**:

```javascript
// Original:
const data = await fetchUser(userId);

// Pattern:
const (.*?) = await (.*?);

// Replacement:
let $!1;
try {
  $!1 = await $!2;
} catch (error) {
  logger.error('Failed to fetch', error);
  $!1 = null;
}

// Result:
let data;
try {
  data = await fetchUser(userId);
} catch (error) {
  logger.error('Failed to fetch', error);
  data = null;
}
```

---

## Complex Examples

### Example 1: Extract and Restructure

**Transform object destructuring**:

```javascript
// Original:
const { name, email, phone } = user;

// Pattern:
const \{ (.*?) \} = (.*?);

// Replacement:
const userName = $!2.name;
const userEmail = $!2.email;
const userPhone = $!2.phone;

// Note: This is simplified; for actual multi-line replacements,
// you'd need to handle each property separately
```

### Example 2: Add Decorators/Annotations

**Add Python type hints**:

```python
# Original:
def process_data(data):
    return data

# Pattern:
def (.*?)\((.*?)\):

# Replacement:
def $!1($!2: dict[str, Any]) -> dict[str, Any]:

# Result:
def process_data(data: dict[str, Any]) -> dict[str, Any]:
    return data
```

### Example 3: Refactor Error Handling

**Update error messages with variable names**:

```python
# Original:
if not user:
    raise ValueError("Not found")

# Pattern:
if not (.*?):\s*raise ValueError\((.*?)\)

# Replacement:
if not $!1:
    raise ValueError(f"$!1 not found: {$!2}")

# Result:
if not user:
    raise ValueError(f"user not found: {"Not found"}")
```

---

## Working with Special Characters

### Escaping in Patterns

When your pattern needs to match literal special characters:

- `\.` - Literal dot
- `\(` and `\)` - Literal parentheses
- `\[` and `\]` - Literal brackets
- `\{` and `\}` - Literal braces
- `\$` - Literal dollar sign
- `\\` - Literal backslash

### Escaping in Replacements

In replacement strings:

- `$$` - Literal dollar sign (if needed before other text)
- `$!1` - Backreference to group 1
- No need to escape most other characters

### Example with Many Special Characters

```bash
# Original: const price = $10.99;
# Pattern: const (.*?) = \$([0-9.]+);
# Replacement: const $!1 = { amount: $!2, currency: 'USD' };
# Result: const price = { amount: 10.99, currency: 'USD' };
```

---

## Numbered Group Reference

Groups are numbered by the order of their **opening parenthesis**:

```regex
Pattern: ((.*?):(.*?))
         ^^^^^  ^^^^^
         Group 1
                ^^^^ Group 2
                     ^^^^ Group 3
```

Example:
```bash
# Pattern: ((hello):(world))
# Text: hello:world
# $!1 = hello:world (entire outer group)
# $!2 = hello (first inner group)
# $!3 = world (second inner group)
```

---

## Non-Capturing Groups

Use `(?:...)` for grouping without capturing:

```regex
# Capturing group (creates $!1):
(hello|world)

# Non-capturing group (no backreference):
(?:hello|world)
```

**Example**:

```bash
# Pattern: (?:console)\.(log|error)\((.*?)\)
#          ^^^^^^^^^^^  ^^^^^^^^^^^  ^^^^^^^
#          Not captured Group 1      Group 2

# Only $!1 and $!2 are available, no $!3
# $!1 = log or error
# $!2 = the argument to console.log/error
```

---

## Troubleshooting

### Issue: Backreference Not Expanding

**Problem**: `$!1` appears literally in the output

**Causes**:
1. No capture group in pattern
2. Group number doesn't exist
3. Typo in backreference syntax

**Solution**:
```bash
# ❌ Wrong (no capture group):
Pattern: function.*?\(.*?\)

# ✅ Correct (with capture group):
Pattern: function (.*?)\((.*?)\)
```

### Issue: Unexpected Text in Backreference

**Problem**: `$!1` contains more text than expected

**Causes**:
1. Greedy matching (`.*` instead of `.*?`)
2. Pattern too broad

**Solution**:
```bash
# ❌ Wrong (greedy, matches too much):
Pattern: function (.*)\((.*)\)

# ✅ Correct (non-greedy):
Pattern: function (.*?)\((.*?)\)
```

### Issue: Group Number Confusion

**Problem**: `$!2` contains unexpected content

**Cause**: Groups are numbered by opening parenthesis order

**Solution**:
```bash
# Count the opening parentheses:
Pattern: ((group1)(group2))
         ^ ^^^^^^  ^^^^^^
         1    2       3

# $!1 = entire match (outer group)
# $!2 = group1 content
# $!3 = group2 content
```

### Issue: Special Characters in Backreference

**Problem**: Backreference contains escaped characters

**Cause**: Pattern matched escaped characters

**Solution**:
```bash
# If pattern is: \$([0-9.]+)
# And text is: $10.00
# Then $!1 = 10.00 (without the $)
# Because \$ in pattern matches literal $, not captured
```

---

## Best Practices

1. **Use Descriptive Patterns**: Make capture groups obvious
2. **Test with Search First**: Preview what will be captured
3. **Use Non-Greedy Quantifiers**: `.*?` instead of `.*`
4. **Count Your Groups**: Double-check group numbering
5. **Use Non-Capturing Groups**: `(?:...)` when you don't need backreference
6. **Escape Special Chars**: Remember `\(` for literal parentheses
7. **Validate Captures**: Check that `$!N` refers to existing group N

---

## Quick Reference Table

| Task | Pattern | Replacement | Result |
|------|---------|-------------|--------|
| Swap two words | `(hello) (world)` | `$!2 $!1` | `world hello` |
| Add prefix | `(function.*)` | `async $!1` | `async function...` |
| Wrap in quotes | `name: (.*?)` | `name: "$!1"` | `name: "value"` |
| Duplicate | `<(.*?)>` | `<$!1><$!1>` | `<div><div>` |
| Reformat | `(\d+)/(\d+)` | `$!2-$!1` | `12-31` |
| Extract and use | `\{(.*?)\}` | `const x = {$!1};` | `const x = {...};` |

---

## Summary

The `$!N` backreference syntax:

- ✅ **Clear and unambiguous** - No conflicts with dollar signs
- ✅ **Easy to use** - `$!1`, `$!2`, `$!3` for groups 1, 2, 3
- ✅ **Compatible** - Works with all code containing `$` symbols
- ✅ **Powerful** - Enables complex transformations with minimal tokens

**Remember**:
1. Capture with `(...)` in pattern
2. Reference with `$!N` in replacement
3. Test with search before replacing
