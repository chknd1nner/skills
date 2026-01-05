# Real-World Examples

Practical examples of using the regex file editor skill for common coding tasks.

## Table of Contents

1. [JavaScript/TypeScript Examples](#javascripttypescript-examples)
2. [Python Examples](#python-examples)
3. [Multi-Language Examples](#multi-language-examples)
4. [API and Configuration Updates](#api-and-configuration-updates)
5. [Refactoring Examples](#refactoring-examples)

---

## JavaScript/TypeScript Examples

### Example 1: Update Error Handling Pattern

**Task**: Replace `console.error` with proper logger in error handlers

**Before**:
```javascript
try {
  await connectToDatabase();
} catch (error) {
  console.error("Failed to connect:", error);
  throw error;
}
```

**Command**:
```bash
python scripts/regex_edit.py search database.js "catch \(error\) \{.*?console\.error.*?\}"

# If match looks good:
python scripts/regex_edit.py replace database.js \
  "catch \((.*?)\) \{\s*console\.error\((.*?)\);.*?\}" \
  "catch ($!1) { logger.error($!2); return null; }"
```

**After**:
```javascript
try {
  await connectToDatabase();
} catch (error) {
  logger.error("Failed to connect:", error);
  return null;
}
```

**Token Savings**: ~70% (avoided quoting entire try-catch block)

---

### Example 2: Convert Callbacks to Async/Await

**Task**: Update callback-style function to use promises

**Before**:
```javascript
function fetchData(callback) {
  db.query("SELECT * FROM users", (err, results) => {
    if (err) callback(err);
    else callback(null, results);
  });
}
```

**Command**:
```bash
python scripts/regex_edit.py replace api.js \
  "function (.*?)\(callback\) \{.*?db\.query\((.*?), \(err, results\).*?\}.*?\}" \
  "async function $!1() { const results = await db.query($!2); return results; }"
```

**After**:
```javascript
async function fetchData() {
  const results = await db.query("SELECT * FROM users");
  return results;
}
```

---

### Example 3: Update Import Statements

**Task**: Replace old package imports with new package across multiple files

**Search Command**:
```bash
python scripts/regex_edit.py search-files \
  "import .* from ['\"]old-package['\"]" \
  --include="**/*.{js,ts,jsx,tsx}"
```

**Replace Command** (per file):
```bash
python scripts/regex_edit.py replace src/components/Button.tsx \
  "import (.*?) from ['\"]old-package['\"]" \
  "import $!1 from 'new-package'"
```

---

## Python Examples

### Example 4: Update Function Decorators

**Task**: Add caching decorator to multiple functions

**Before**:
```python
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
```

**Command**:
```bash
python scripts/regex_edit.py replace utils.py \
  "def (calculate_.*?)\((.*?)\):" \
  "@lru_cache(maxsize=128)\ndef $!1($!2):"
```

**After**:
```python
@lru_cache(maxsize=128)
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
```

---

### Example 5: Update Class Constructor

**Task**: Add type hints to constructor while preserving initialization logic

**Before**:
```python
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.results = []
```

**Command**:
```bash
python scripts/regex_edit.py replace processor.py \
  "def __init__\(self, (.*?)\):" \
  "def __init__(self, $!1: dict[str, Any]) -> None:"
```

**After**:
```python
class DataProcessor:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.results = []
```

---

### Example 6: Replace Multiple Print Statements with Logger

**Task**: Convert all print statements to use proper logging

**Search Command**:
```bash
python scripts/regex_edit.py search app.py "print\((.*?)\)" --context=2
```

**Replace Command**:
```bash
python scripts/regex_edit.py replace app.py \
  "print\((.*?)\)" \
  "logger.info($!1)" \
  --allow-multiple
```

---

## Multi-Language Examples

### Example 7: Find Hardcoded Secrets

**Task**: Locate potential hardcoded API keys or secrets

**Command**:
```bash
python scripts/regex_edit.py search-files \
  "(API_KEY|SECRET_KEY|PASSWORD)\s*=\s*['\"].*?['\"]" \
  --include="**/*.{py,js,ts,java,go}" \
  --exclude="**/test_*" \
  --context=2
```

**Output Analysis**: Review each match to determine if it's a real secret or a placeholder

---

### Example 8: Update Copyright Years

**Task**: Update copyright year in all source files

**Command**:
```bash
python scripts/regex_edit.py search-files "Copyright.*?2023" --include="**/*.{py,js,ts}"

# For each file:
python scripts/regex_edit.py replace src/main.py \
  "Copyright (.*?) 2023" \
  "Copyright $!1 2024"
```

---

## API and Configuration Updates

### Example 9: Update API Endpoints

**Task**: Change API version from v1 to v2 in all endpoint URLs

**Search Command**:
```bash
python scripts/regex_edit.py search-files \
  "https?://api\..*?/v1/" \
  --include="**/*.{js,ts,py}"
```

**Replace Command** (per file):
```bash
python scripts/regex_edit.py replace config.js \
  "(https?://api\..*?)/v1/" \
  "$!1/v2/" \
  --allow-multiple
```

---

### Example 10: Update Environment Variable Access

**Task**: Change from direct `process.env` access to config service

**Before**:
```javascript
const apiKey = process.env.API_KEY;
const dbHost = process.env.DB_HOST;
```

**Command**:
```bash
python scripts/regex_edit.py replace config.js \
  "const (.*?) = process\.env\.(.*?);" \
  "const $!1 = config.get('$!2');" \
  --allow-multiple
```

**After**:
```javascript
const apiKey = config.get('API_KEY');
const dbHost = config.get('DB_HOST');
```

---

## Refactoring Examples

### Example 11: Extract Magic Numbers to Constants

**Task**: Replace hardcoded timeout values with named constants

**Before**:
```python
response = requests.get(url, timeout=30)
await asyncio.sleep(30)
```

**Command**:
```bash
# First, add constant at top of file
python scripts/regex_edit.py replace api.py \
  "^(import.*?\n\n)" \
  "$!1REQUEST_TIMEOUT = 30\n\n"

# Then replace usage
python scripts/regex_edit.py replace api.py \
  "timeout=30" \
  "timeout=REQUEST_TIMEOUT" \
  --allow-multiple
```

---

### Example 12: Rename Class Method Across Files

**Task**: Rename method `getData()` to `fetchData()` across codebase

**Search Command**:
```bash
python scripts/regex_edit.py search-files "\.getData\(" --include="**/*.ts"
```

**Replace Commands**:
```bash
# In class definition
python scripts/regex_edit.py replace DataService.ts \
  "(async )?(getData)\(" \
  "$!1fetchData("

# In method calls
python scripts/regex_edit.py replace components/Table.tsx \
  "\.getData\(" \
  ".fetchData(" \
  --allow-multiple
```

---

### Example 13: Add Error Boundary to React Components

**Task**: Wrap component return with error boundary

**Before**:
```jsx
function UserProfile({ userId }) {
  const user = useUser(userId);
  return <div>{user.name}</div>;
}
```

**Command**:
```bash
python scripts/regex_edit.py replace UserProfile.tsx \
  "return (<div>.*?</div>);" \
  "return <ErrorBoundary>$!1</ErrorBoundary>;"
```

**After**:
```jsx
function UserProfile({ userId }) {
  const user = useUser(userId);
  return <ErrorBoundary><div>{user.name}</div></ErrorBoundary>;
}
```

---

## Advanced Pattern Matching

### Example 14: Swap Function Parameters

**Task**: Reverse parameter order in function signature

**Before**:
```python
def process_data(config, data):
    pass
```

**Command**:
```bash
python scripts/regex_edit.py replace utils.py \
  "def process_data\((.*?), (.*?)\):" \
  "def process_data($!2, $!1):"
```

**After**:
```python
def process_data(data, config):
    pass
```

---

### Example 15: Extract Inline Styles to CSS Classes

**Task**: Replace inline styles with CSS class names

**Before**:
```html
<div style="display: flex; justify-content: center;">Content</div>
```

**Command**:
```bash
python scripts/regex_edit.py replace template.html \
  '<div style="display: flex; justify-content: center;">(.*?)</div>' \
  '<div class="flex-center">$!1</div>'
```

**After**:
```html
<div class="flex-center">Content</div>
```

---

## Performance Comparison

### Token Usage: Traditional vs Regex Approach

**Task**: Replace a 50-line function body while keeping function signature

**Traditional Approach** (quoting entire function):
```
tokens_used = function_signature (20) + old_body (500) + new_body (500) = 1,020 tokens
```

**Regex Approach** (using wildcards):
```
tokens_used = pattern (30) + new_body (500) = 530 tokens
```

**Savings**: ~48% token reduction

---

## Best Practices Learned

1. **Always Search First**: Preview matches before replacing to avoid mistakes
2. **Use Non-Greedy Wildcards**: `.*?` is almost always better than `.*`
3. **Escape Special Characters**: Use `\.` for literal dots, `\(` for literal parentheses
4. **Test on One File First**: For multi-file operations, validate on a single file before applying to all
5. **Capture Groups Strategically**: Only capture what you need to reuse with `$!N`
6. **Check for Ambiguity**: If you get ambiguity errors, make your pattern more specific
7. **Use Literal Mode for Exact Strings**: When pattern contains many special chars, use `--mode=literal`
8. **Leverage Context Lines**: Use `--context=3` to see surrounding code when searching
