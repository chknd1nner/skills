# Common Regex Patterns by Language

Quick reference for frequently-used regex patterns in various programming languages.

## Table of Contents

1. [General Programming Patterns](#general-programming-patterns)
2. [JavaScript/TypeScript](#javascripttypescript)
3. [Python](#python)
4. [Java](#java)
5. [Go](#go)
6. [Ruby](#ruby)
7. [PHP](#php)
8. [Rust](#rust)
9. [Configuration Files](#configuration-files)

---

## General Programming Patterns

### Comments

```regex
# Single-line comment (Python, Ruby, Bash)
#.*$

# Multi-line comment (C-style)
/\*.*?\*/

# Single-line comment (JavaScript, Java, C++)
//.*$

# Documentation comment (JSDoc, JavaDoc)
/\*\*.*?\*/
```

### String Literals

```regex
# Double-quoted string
"([^"\\]|\\.)*"

# Single-quoted string
'([^'\\]|\\.)*'

# Template literal (JavaScript)
`([^`\\]|\\.)*`

# Triple-quoted string (Python)
""".*?"""
```

### Identifiers

```regex
# Variable/function name (most languages)
[a-zA-Z_][a-zA-Z0-9_]*

# Constant name (uppercase with underscores)
[A-Z][A-Z0-9_]*

# Camel case
[a-z][a-zA-Z0-9]*

# Pascal case
[A-Z][a-zA-Z0-9]*

# Kebab case
[a-z][-a-z0-9]*
```

---

## JavaScript/TypeScript

### Function Declarations

```regex
# Named function
function ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\).*?\{

# Arrow function
(?:const|let|var) ([a-zA-Z_][a-zA-Z0-9_]*) = \((.*?)\) =>

# Async function
async function ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)

# Class method
([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\).*?\{
```

### Import/Export Statements

```regex
# ES6 import
import (.*?) from ['"]([^'"]+)['"]

# Named import
import \{(.*?)\} from ['"]([^'"]+)['"]

# Default export
export default (class|function|const)

# Named export
export \{(.*?)\}
```

### React/JSX Patterns

```regex
# Component definition
(?:function|const) ([A-Z][a-zA-Z0-9]*)\(.*?\).*?\{

# useState hook
const \[(.*?), set.*?\] = useState\((.*?)\)

# useEffect hook
useEffect\(\(\) => \{.*?\}, \[(.*?)\]\)

# JSX element
<([A-Z][a-zA-Z0-9]*)(.*?)>

# Props destructuring
function.*?\(\{(.*?)\}\)
```

### Error Handling

```regex
# Try-catch block
try \{.*?\} catch \((.*?)\) \{.*?\}

# Promise catch
\.catch\((.*?)\)

# Promise then
\.then\((.*?)\)
```

### Console Methods

```regex
# Console.log/error/warn/debug
console\.(log|error|warn|debug|info)\((.*?)\)

# Template literal in console
console\..*?\(`.*?\$\{.*?\}.*?`\)
```

---

## Python

### Function Definitions

```regex
# Function definition
def ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\):

# Async function
async def ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\):

# Function with type hints
def ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\) -> (.*?):

# Method definition
def ([a-zA-Z_][a-zA-Z0-9_]*)\(self(, .*?)?\):
```

### Class Definitions

```regex
# Class definition
class ([A-Z][a-zA-Z0-9]*)\((.*?)\):

# Class with no inheritance
class ([A-Z][a-zA-Z0-9]*):

# Constructor
def __init__\(self(, .*?)?\):

# Property decorator
@property\s+def ([a-zA-Z_][a-zA-Z0-9_]*)\(self\):
```

### Import Statements

```regex
# Simple import
import ([a-zA-Z_][a-zA-Z0-9_.]*)

# From import
from ([a-zA-Z_][a-zA-Z0-9_.]*) import (.*?)

# Import as
import ([a-zA-Z_][a-zA-Z0-9_.]*) as ([a-zA-Z_][a-zA-Z0-9_]*)

# Star import
from ([a-zA-Z_][a-zA-Z0-9_.]*) import \*
```

### Decorators

```regex
# Simple decorator
@([a-zA-Z_][a-zA-Z0-9_.]*)

# Decorator with arguments
@([a-zA-Z_][a-zA-Z0-9_.]*)\((.*?)\)

# Multiple decorators
(@[a-zA-Z_][a-zA-Z0-9_.]*.*?\n)+def
```

### Error Handling

```regex
# Try-except block
try:.*?except (.*?):

# Try-except with alias
try:.*?except (.*?) as (.*?):

# Finally clause
finally:.*?$

# Raise statement
raise ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)
```

### Type Hints

```regex
# Variable with type hint
([a-zA-Z_][a-zA-Z0-9_]*): (.*?) =

# Function parameter with type
([a-zA-Z_][a-zA-Z0-9_]*): (.*?)(?:,|\))

# Generic type
([A-Z][a-zA-Z0-9]*)\[(.*?)\]
```

---

## Java

### Class Declarations

```regex
# Class definition
(?:public |private |protected )?class ([A-Z][a-zA-Z0-9]*)\s*(?:extends (.*?) )?(?:implements (.*?) )?\{

# Interface definition
(?:public )?interface ([A-Z][a-zA-Z0-9]*)\s*(?:extends (.*?) )?\{

# Enum definition
(?:public )?enum ([A-Z][a-zA-Z0-9]*)\s*\{
```

### Method Declarations

```regex
# Method with access modifier
(public|private|protected) (?:static )?(.*?) ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\).*?\{

# Constructor
(public|private|protected) ([A-Z][a-zA-Z0-9]*)\((.*?)\).*?\{

# Getter method
public (.*?) get([A-Z][a-zA-Z0-9]*)\(\).*?\{

# Setter method
public void set([A-Z][a-zA-Z0-9]*)\((.*?) (.*?)\).*?\{
```

### Annotations

```regex
# Simple annotation
@([A-Z][a-zA-Z0-9]*)

# Annotation with parameters
@([A-Z][a-zA-Z0-9]*)\((.*?)\)

# Override annotation
@Override\s+(?:public|private|protected)
```

### Exception Handling

```regex
# Try-catch block
try \{.*?\} catch \((.*?) (.*?)\) \{.*?\}

# Throws clause
throws ([A-Z][a-zA-Z0-9]*(?:, [A-Z][a-zA-Z0-9]*)*)

# Throw statement
throw new ([A-Z][a-zA-Z0-9]*)\((.*?)\);
```

---

## Go

### Function Declarations

```regex
# Function definition
func ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)(.*?)\{

# Method definition
func \((.*?) \*?([A-Z][a-zA-Z0-9]*)\) ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)(.*?)\{

# Function with multiple return values
func ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\) \((.*?)\) \{
```

### Struct Definitions

```regex
# Struct definition
type ([A-Z][a-zA-Z0-9]*) struct \{

# Struct field
([a-zA-Z_][a-zA-Z0-9_]*)\s+(.*?)(?:\s+`.*?`)?

# Interface definition
type ([A-Z][a-zA-Z0-9]*) interface \{
```

### Error Handling

```regex
# Error check pattern
if err != nil \{.*?\}

# Error return
return .*?, err

# Error creation
errors\.New\("(.*?)"\)

# Formatted error
fmt\.Errorf\("(.*?)"(, .*?)?\)
```

### Import Statements

```regex
# Single import
import "(.*?)"

# Multiple imports
import \((.*?)\)

# Aliased import
import ([a-zA-Z_][a-zA-Z0-9_]*) "(.*?)"
```

---

## Ruby

### Method Definitions

```regex
# Method definition
def ([a-zA-Z_][a-zA-Z0-9_?!]*)\(?([^)]*)\)?

# Class method
def self\.([a-zA-Z_][a-zA-Z0-9_?!]*)

# Private method
private.*?def ([a-zA-Z_][a-zA-Z0-9_?!]*)
```

### Class Definitions

```regex
# Class definition
class ([A-Z][a-zA-Z0-9]*)\s*(?:< (.*?))?

# Module definition
module ([A-Z][a-zA-Z0-9]*)

# Include statement
include ([A-Z][a-zA-Z0-9]*)
```

### Blocks and Iterators

```regex
# Block with do-end
\.([a-zA-Z_][a-zA-Z0-9_]*) do \|(.*?)\|.*?end

# Block with braces
\.([a-zA-Z_][a-zA-Z0-9_]*) \{.*?\}

# Map/select/each
\.(map|select|each|filter)\s*\{.*?\}
```

---

## PHP

### Function Declarations

```regex
# Function definition
function ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\).*?\{

# Function with type hint
function ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\): (.*?)\{

# Method definition
(?:public|private|protected) function ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)
```

### Class Definitions

```regex
# Class definition
class ([A-Z][a-zA-Z0-9]*)\s*(?:extends (.*?) )?(?:implements (.*?) )?\{

# Property definition
(?:public|private|protected) \$([a-zA-Z_][a-zA-Z0-9_]*)

# Constructor
(?:public|private|protected) function __construct\((.*?)\)
```

### Variables

```regex
# Variable assignment
\$([a-zA-Z_][a-zA-Z0-9_]*) = (.*?);

# Array access
\$([a-zA-Z_][a-zA-Z0-9_]*)\[(.*?)\]
```

---

## Rust

### Function Declarations

```regex
# Function definition
fn ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)(?: -> (.*?))?\{

# Public function
pub fn ([a-zA-Z_][a-zA-Z0-9_]*)\((.*?)\)

# Method definition
(?:pub )?fn ([a-zA-Z_][a-zA-Z0-9_]*)(?:&(?:mut )?self)?\((.*?)\)
```

### Struct and Impl Blocks

```regex
# Struct definition
(?:pub )?struct ([A-Z][a-zA-Z0-9]*)\s*\{

# Impl block
impl\s*(?:<.*?>)?\s*([A-Z][a-zA-Z0-9]*)\s*(?:<.*?>)?\s*\{

# Trait definition
(?:pub )?trait ([A-Z][a-zA-Z0-9]*)\s*\{
```

### Error Handling

```regex
# Result type
Result<(.*?), (.*?)>

# Option type
Option<(.*?)>

# Match expression
match (.*?) \{.*?\}

# Unwrap/expect
\.(?:unwrap|expect)\((.*?)\)
```

---

## Configuration Files

### JSON

```regex
# Key-value pair
"([^"]+)": (".*?"|[0-9.]+|true|false|null)

# Array
"([^"]+)": \[(.*?)\]

# Nested object
"([^"]+)": \{(.*?)\}
```

### YAML

```regex
# Key-value pair
([a-zA-Z_][a-zA-Z0-9_-]*): (.*?)$

# Array item
- (.*?)$

# Environment variable
\$\{([A-Z_][A-Z0-9_]*)\}
```

### Environment Files (.env)

```regex
# Environment variable
([A-Z_][A-Z0-9_]*)=(.*?)$

# Commented line
#.*?$

# Variable reference
\$\{?([A-Z_][A-Z0-9_]*)\}?
```

### XML

```regex
# Opening tag
<([a-zA-Z][a-zA-Z0-9]*)(.*?)>

# Self-closing tag
<([a-zA-Z][a-zA-Z0-9]*)(.*?)/>

# Closing tag
</([a-zA-Z][a-zA-Z0-9]*)>

# Attribute
([a-zA-Z][a-zA-Z0-9-]*)="([^"]*)"
```

---

## Regular Expression Metacharacters Reference

### Basic Metacharacters

- `.` - Any character (except newline, unless DOTALL flag)
- `^` - Start of line (MULTILINE mode)
- `$` - End of line (MULTILINE mode)
- `*` - Zero or more (greedy)
- `+` - One or more (greedy)
- `?` - Zero or one (greedy)
- `*?` - Zero or more (non-greedy)
- `+?` - One or more (non-greedy)
- `??` - Zero or one (non-greedy)

### Character Classes

- `[abc]` - Any of a, b, or c
- `[^abc]` - Not a, b, or c
- `[a-z]` - Any lowercase letter
- `[A-Z]` - Any uppercase letter
- `[0-9]` - Any digit
- `\d` - Digit (same as `[0-9]`)
- `\D` - Non-digit
- `\w` - Word character (`[a-zA-Z0-9_]`)
- `\W` - Non-word character
- `\s` - Whitespace (space, tab, newline)
- `\S` - Non-whitespace

### Grouping and Capturing

- `(...)` - Capture group (use `$!1` in replacement)
- `(?:...)` - Non-capturing group
- `(?P<name>...)` - Named capture group (Python)
- `$!1`, `$!2` - Backreferences in replacement (custom syntax)

### Anchors

- `\b` - Word boundary
- `\B` - Non-word boundary
- `^` - Start of string/line
- `$` - End of string/line

### Lookahead/Lookbehind (if needed)

- `(?=...)` - Positive lookahead
- `(?!...)` - Negative lookahead
- `(?<=...)` - Positive lookbehind
- `(?<!...)` - Negative lookbehind

---

## Tips for Writing Patterns

1. **Use Non-Greedy Quantifiers**: `.*?` instead of `.*` to match the smallest possible text
2. **Escape Special Characters**: Use `\.` for literal dots, `\(` for literal parentheses
3. **Use Character Classes**: `[a-zA-Z]` is more specific than `.`
4. **Anchor When Possible**: Use `^` and `$` to anchor patterns to line boundaries
5. **Test Incrementally**: Build patterns step-by-step, testing each addition
6. **Use Capture Groups Wisely**: Only capture what you need to reuse
7. **Consider Word Boundaries**: `\b` helps match whole words only
8. **Remember DOTALL Mode**: `.` matches newlines in this tool
