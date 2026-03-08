#!/usr/bin/env bash
set -euo pipefail

# session-overview.sh — Discover all Claude Code configuration affecting the current session.
# Usage: session-overview.sh [--raw|--formatted|--by-scope]

MODE="raw"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw)       MODE="raw"; shift ;;
    --formatted) MODE="formatted"; shift ;;
    --by-scope)  MODE="by-scope"; shift ;;
    *)           echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

PROJECT_DIR="${PWD}"
HOME_DIR="${HOME}"

# Helper: print a section header/footer
section_start() { echo "=== $1 ==="; }
section_end()   { echo "=== END_$1 ==="; echo; }

# Helper: print content block for LLM summarization
content_block() {
  local path="$1"
  local max_chars="${2:-500}"
  echo "--- ${path} ---"
  head -c "$max_chars" "$path" 2>/dev/null || true
  echo
  echo "--- END ---"
}

# Helper: safely read a JSON file with jq. Returns empty object if missing/invalid.
safe_jq() {
  local file="$1"
  shift
  if [[ -f "$file" ]]; then
    jq -r "$@" "$file" 2>/dev/null || true
  fi
}

###############################################################################
# 1. SETTINGS FILES
###############################################################################
section_start "SETTINGS"

declare -a settings_files=(
  "project:${PROJECT_DIR}/.claude/settings.json"
  "local:${PROJECT_DIR}/.claude/settings.local.json"
  "user:${HOME_DIR}/.claude/settings.json"
  "enterprise:/etc/claude/settings.json"
  "managed:${HOME_DIR}/.claude/managed/settings.json"
)

found_settings=0
for entry in "${settings_files[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    echo "[${scope}] settings ${path}"
    found_settings=1
  fi
done

if [[ $found_settings -eq 0 ]]; then
  echo "none"
fi

section_end "SETTINGS"

###############################################################################
# 2. CLAUDE.md FILES
###############################################################################
section_start "CLAUDE_MD"

declare -a claudemd_files=(
  "project:${PROJECT_DIR}/CLAUDE.md"
  "user:${HOME_DIR}/.claude/CLAUDE.md"
)

found_claudemd=0
claudemd_content_paths=()
for entry in "${claudemd_files[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    lines=$(wc -l < "$path" | tr -d ' ')
    echo "[${scope}] ${lines} lines ${path}"
    claudemd_content_paths+=("${path}")
    found_claudemd=1
  fi
done

if [[ $found_claudemd -eq 0 ]]; then
  echo "none"
fi

section_end "CLAUDE_MD"

# Content blocks for CLAUDE.md files
if [[ ${#claudemd_content_paths[@]} -gt 0 ]]; then
  section_start "CLAUDE_MD_CONTENT"
  for path in "${claudemd_content_paths[@]}"; do
    content_block "$path" 500
  done
  section_end "CLAUDE_MD_CONTENT"
fi

###############################################################################
# 3. HOOKS
###############################################################################
section_start "HOOKS"

declare -a hook_settings_files=(
  "project:${PROJECT_DIR}/.claude/settings.json"
  "local:${PROJECT_DIR}/.claude/settings.local.json"
  "user:${HOME_DIR}/.claude/settings.json"
  "enterprise:/etc/claude/settings.json"
  "managed:${HOME_DIR}/.claude/managed/settings.json"
)

found_hooks=0
for entry in "${hook_settings_files[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    # Check if hooks key exists
    has_hooks=$(jq -r 'has("hooks")' "$path" 2>/dev/null || echo "false")
    if [[ "$has_hooks" == "true" ]]; then
      # Iterate over hook event types
      while IFS= read -r event_type; do
        [[ -z "$event_type" ]] && continue
        # Each event type has an array of hook configs
        hook_count=$(jq -r ".hooks[\"${event_type}\"] | length" "$path" 2>/dev/null || echo "0")
        for ((i=0; i<hook_count; i++)); do
          matcher=$(jq -r ".hooks[\"${event_type}\"][$i].matcher // \"*\"" "$path" 2>/dev/null || echo "*")
          command=$(jq -r ".hooks[\"${event_type}\"][$i].command // \"\"" "$path" 2>/dev/null || echo "")
          # Truncate command to 60 chars
          cmd_short="${command:0:60}"
          echo "[${scope}] ${event_type} matcher=${matcher} cmd=${cmd_short}"
          found_hooks=1
        done
      done < <(jq -r '.hooks | keys[]' "$path" 2>/dev/null)
    fi
  fi
done

if [[ $found_hooks -eq 0 ]]; then
  echo "none"
fi

section_end "HOOKS"

###############################################################################
# 4. MCP SERVERS
###############################################################################
section_start "MCP_SERVERS"

declare -a mcp_settings_files=(
  "project:${PROJECT_DIR}/.claude/settings.json"
  "local:${PROJECT_DIR}/.claude/settings.local.json"
  "user:${HOME_DIR}/.claude/settings.json"
  "enterprise:/etc/claude/settings.json"
  "managed:${HOME_DIR}/.claude/managed/settings.json"
)

found_mcp=0
for entry in "${mcp_settings_files[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    has_mcp=$(jq -r 'has("mcpServers")' "$path" 2>/dev/null || echo "false")
    if [[ "$has_mcp" == "true" ]]; then
      while IFS= read -r server_name; do
        [[ -z "$server_name" ]] && continue
        transport=$(jq -r ".mcpServers[\"${server_name}\"].transport // \"stdio\"" "$path" 2>/dev/null || echo "stdio")
        # Also check for type field (some configs use "type" instead of "transport")
        if [[ "$transport" == "stdio" ]]; then
          alt_type=$(jq -r ".mcpServers[\"${server_name}\"].type // \"\"" "$path" 2>/dev/null || echo "")
          if [[ -n "$alt_type" ]]; then
            transport="$alt_type"
          fi
        fi
        echo "[${scope}] ${server_name} transport=${transport}"
        found_mcp=1
      done < <(jq -r '.mcpServers | keys[]' "$path" 2>/dev/null)
    fi
  fi
done

if [[ $found_mcp -eq 0 ]]; then
  echo "none"
fi

section_end "MCP_SERVERS"

###############################################################################
# 5. AGENTS
###############################################################################
section_start "AGENTS"

found_agents=0
agent_md_paths=()

# 5a. Agents from settings files
for entry in "${settings_files[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    has_agents=$(jq -r 'has(".agents") or has("agents")' "$path" 2>/dev/null || echo "false")
    if [[ "$has_agents" == "true" ]]; then
      # Try both ".agents" and "agents" keys
      for key in ".agents" "agents"; do
        while IFS= read -r agent_name; do
          [[ -z "$agent_name" ]] && continue
          echo "[${scope}] ${agent_name} source=settings ${path}"
          found_agents=1
        done < <(jq -r ".[\"${key}\"] // {} | keys[]" "$path" 2>/dev/null)
      done
    fi
  fi
done

# 5b. Agent markdown files
agents_dir="${HOME_DIR}/.claude/agents"
if [[ -d "$agents_dir" ]]; then
  for md_file in "$agents_dir"/*.md; do
    [[ -f "$md_file" ]] || continue
    agent_name=$(basename "$md_file" .md)
    echo "[user] ${agent_name} source=file ${md_file}"
    agent_md_paths+=("${md_file}")
    found_agents=1
  done
fi

if [[ $found_agents -eq 0 ]]; then
  echo "none"
fi

section_end "AGENTS"

# Content blocks for agent .md files
if [[ ${#agent_md_paths[@]} -gt 0 ]]; then
  section_start "AGENTS_CONTENT"
  for path in "${agent_md_paths[@]}"; do
    content_block "$path" 200
  done
  section_end "AGENTS_CONTENT"
fi

###############################################################################
# 6. PLUGINS
###############################################################################
section_start "PLUGINS"

plugin_cache_dir="${HOME_DIR}/.claude/plugins/cache"
found_plugins=0

# Load enabledPlugins from user settings
user_settings="${HOME_DIR}/.claude/settings.json"

# Helper to look up plugin enabled status (compatible with bash 3)
plugin_status() {
  local plugin_id="$1"
  if [[ -f "$user_settings" ]]; then
    local val
    val=$(jq -r "if .enabledPlugins | has(\"${plugin_id}\") then .enabledPlugins[\"${plugin_id}\"] | tostring else \"unset\" end" "$user_settings" 2>/dev/null || echo "unset")
    if [[ "$val" == "true" ]]; then
      echo "enabled"
    elif [[ "$val" == "false" ]]; then
      echo "disabled"
    else
      echo "unknown"
    fi
  else
    echo "unknown"
  fi
}

if [[ -d "$plugin_cache_dir" ]]; then
  for plugin_dir in "$plugin_cache_dir"/*/; do
    [[ -d "$plugin_dir" ]] || continue
    repo_name=$(basename "$plugin_dir")
    # Look for skill subdirectories to find plugin names
    for skill_dir in "$plugin_dir"/*/; do
      [[ -d "$skill_dir" ]] || continue
      skill_name=$(basename "$skill_dir")
      plugin_id="${skill_name}@${repo_name}"
      status=$(plugin_status "$plugin_id")
      echo "[user] ${plugin_id} status=${status} ${plugin_dir}${skill_name}/"
      found_plugins=1
    done
  done
fi

if [[ $found_plugins -eq 0 ]]; then
  echo "none"
fi

section_end "PLUGINS"

###############################################################################
# 7. SKILLS
###############################################################################
section_start "SKILLS"

found_skills=0

# 7a. Project skills — look in common skill directories
for skill_md in "${PROJECT_DIR}"/claude-code-only/*/SKILL.md \
                "${PROJECT_DIR}"/common/*/SKILL.md \
                "${PROJECT_DIR}"/claude-web-only/*/SKILL.md \
                "${PROJECT_DIR}"/.claude/skills/*/SKILL.md; do
  [[ -f "$skill_md" ]] || continue
  skill_name=$(basename "$(dirname "$skill_md")")
  echo "[project] ${skill_name} ${skill_md}"
  found_skills=1
done

# 7b. User skills
for skill_md in "${HOME_DIR}"/.claude/skills/*/SKILL.md; do
  [[ -f "$skill_md" ]] || continue
  skill_name=$(basename "$(dirname "$skill_md")")
  echo "[user] ${skill_name} ${skill_md}"
  found_skills=1
done

# 7c. Plugin skills
if [[ -d "$plugin_cache_dir" ]]; then
  while IFS= read -r skill_md; do
    [[ -f "$skill_md" ]] || continue
    # Extract skill name: for .../skills/<name>/SKILL.md use <name>,
    # for .../<plugin>/<version>/SKILL.md use <plugin>
    parent_dir=$(basename "$(dirname "$skill_md")")
    grandparent_dir=$(basename "$(dirname "$(dirname "$skill_md")")")
    if [[ "$grandparent_dir" == "skills" ]]; then
      skill_name="$parent_dir"
    else
      # Version-dir pattern: <plugin>/<version>/SKILL.md
      skill_name="$grandparent_dir"
    fi
    echo "[plugin] ${skill_name} ${skill_md}"
    found_skills=1
  done < <(find "$plugin_cache_dir" -name "SKILL.md" 2>/dev/null | sort -u)
fi

if [[ $found_skills -eq 0 ]]; then
  echo "none"
fi

section_end "SKILLS"

###############################################################################
# 8. AUTO-MEMORY
###############################################################################
section_start "AUTO_MEMORY"

# Encode project path: replace / with -
encoded_path=$(echo "$PROJECT_DIR" | sed 's|/|-|g')
memory_dir="${HOME_DIR}/.claude/projects/${encoded_path}/memory"

found_memory=0
if [[ -d "$memory_dir" ]]; then
  for mem_file in "$memory_dir"/*; do
    [[ -f "$mem_file" ]] || continue
    lines=$(wc -l < "$mem_file" | tr -d ' ')
    echo "[project] ${lines} lines $(basename "$mem_file") ${mem_file}"
    found_memory=1
  done
fi

if [[ $found_memory -eq 0 ]]; then
  echo "none"
fi

section_end "AUTO_MEMORY"

###############################################################################
# 9. MODEL
###############################################################################
section_start "MODEL"

model="default"
if [[ -f "$user_settings" ]]; then
  model_val=$(jq -r '.model // "default"' "$user_settings" 2>/dev/null || echo "default")
  if [[ -n "$model_val" && "$model_val" != "null" ]]; then
    model="$model_val"
  fi
fi

echo "[user] model=${model}"

section_end "MODEL"
