# Regex Patterns by Language

Quick lookup table for common patterns. Use with `$!N` backreferences.

## JavaScript/TypeScript

```
# Function
function ([a-zA-Z_]\w*)\((.*?)\).*?\{
async function ([a-zA-Z_]\w*)\((.*?)\)

# Arrow function
(?:const|let) ([a-zA-Z_]\w*) = \((.*?)\) =>

# Import/Export
import (.*?) from ['"]([^'"]+)['"]
import \{(.*?)\} from ['"]([^'"]+)['"]
export default (class|function|const)

# React hooks
const \[(.*?), set.*?\] = useState\((.*?)\)
useEffect\(\(\) => \{.*?\}, \[(.*?)\]\)

# Console methods
console\.(log|error|warn|debug)\((.*?)\)

# Error handling
try \{.*?\} catch \((.*?)\) \{.*?\}
\.catch\((.*?)\)
```

## Python

```
# Function
def ([a-zA-Z_]\w*)\((.*?)\):
async def ([a-zA-Z_]\w*)\((.*?)\):
def ([a-zA-Z_]\w*)\((.*?)\) -> (.*?):

# Class
class ([A-Z]\w*)\((.*?)\):
class ([A-Z]\w*):
def __init__\(self(, .*?)?\):

# Import
import ([a-zA-Z_][\w.]*)
from ([a-zA-Z_][\w.]*) import (.*?)

# Decorator
@([a-zA-Z_][\w.]*)
@([a-zA-Z_][\w.]*)\((.*?)\)

# Error handling
try:.*?except (.*?):
raise ([A-Z]\w*)\((.*?)\)
```

## Java

```
# Class
(?:public |private )?class ([A-Z]\w*)\s*(?:extends (.*?) )?(?:implements (.*?) )?\{

# Method
(public|private|protected) (?:static )?(.*?) ([a-zA-Z_]\w*)\((.*?)\).*?\{

# Annotation
@([A-Z]\w*)
@([A-Z]\w*)\((.*?)\)

# Exception
try \{.*?\} catch \((.*?) (.*?)\) \{.*?\}
throw new ([A-Z]\w*)\((.*?)\);
```

## Go

```
# Function
func ([a-zA-Z_]\w*)\((.*?)\)(.*?)\{

# Method
func \((.*?) \*?([A-Z]\w*)\) ([a-zA-Z_]\w*)\((.*?)\)(.*?)\{

# Struct/Interface
type ([A-Z]\w*) struct \{
type ([A-Z]\w*) interface \{

# Error handling
if err != nil \{.*?\}
errors\.New\("(.*?)"\)
fmt\.Errorf\("(.*?)"(, .*?)?\)
```

## Rust

```
# Function
fn ([a-zA-Z_]\w*)\((.*?)\)(?: -> (.*?))?\{
pub fn ([a-zA-Z_]\w*)\((.*?)\)

# Struct/Impl
(?:pub )?struct ([A-Z]\w*)\s*\{
impl\s*(?:<.*?>)?\s*([A-Z]\w*)\s*(?:<.*?>)?\s*\{

# Error handling
Result<(.*?), (.*?)>
Option<(.*?)>
\.(?:unwrap|expect)\((.*?)\)
```

## Config Files

```
# JSON key-value
"([^"]+)": (".*?"|[0-9.]+|true|false|null)

# YAML key-value
([a-zA-Z_][\w-]*): (.*?)$

# Environment variable
([A-Z_][A-Z0-9_]*)=(.*?)$
\$\{([A-Z_][A-Z0-9_]*)\}

# XML element
<([a-zA-Z]\w*)(.*?)>
<([a-zA-Z]\w*)(.*?)/>
```

## Common Operations

```
# String literals
"([^"\\]|\\.)*"
'([^'\\]|\\.)*'

# Comments
//.*$
/\*.*?\*/
#.*$

# Identifiers
[a-zA-Z_]\w*
[A-Z][A-Z0-9_]*
```
