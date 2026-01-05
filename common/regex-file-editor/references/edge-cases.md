# Edge Cases & Troubleshooting

Consult when errors occur or backreferences behave unexpectedly.

## Group Numbering

Groups are numbered by **opening parenthesis order**, left-to-right:

```
Pattern: ((hello):(world))
         ^  ^      ^
         1  2      3

$!1 = "hello:world"  (outer group)
$!2 = "hello"        (first inner)
$!3 = "world"        (second inner)
```

## Non-Capturing Groups

Use `(?:...)` when you need grouping but don't want a backreference:

```
# With capturing (creates $!1):
(hello|world)

# Without capturing (no backreference):
(?:hello|world)

# Example: match console.log OR console.error, capture only the argument
Pattern: (?:console)\.(log|error)\((.*?)\)
$!1 = "log" or "error"
$!2 = the argument
```

## Common Errors

**"Backreference not expanding" ($!1 appears literally)**
- Cause: No capture group in pattern, or group number doesn't exist
- Fix: Add parentheses `(...)` around what you want to capture

**"Unexpected text in backreference"**
- Cause: Greedy matching (`.*` instead of `.*?`)
- Fix: Use non-greedy `.*?` to match minimally

**"Multiple matches found"**
- Cause: Pattern matches more than once
- Fix: Use `--allow-multiple` if intended, or make pattern more specific

**"Ambiguous pattern"**
- Cause: Pattern matches overlapping content
- Fix: Add more context to pattern boundaries

## Escaping Quick Reference

In patterns: `\.` `\(` `\)` `\[` `\]` `\{` `\}` `\$` `\\`

In replacements: `$!N` for backreference, literal `$` needs no escape (that's the point of `$!N` syntax).
