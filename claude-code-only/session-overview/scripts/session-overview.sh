#!/usr/bin/env bash
set -euo pipefail

# session-overview.sh — Discover all Claude Code configuration affecting the current session.
# Usage: session-overview.sh [--raw|--formatted|--by-scope]

MODE="formatted"
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

# Shared settings file locations (scope:path)
declare -a ALL_SETTINGS_FILES=(
  "project:${PROJECT_DIR}/.claude/settings.json"
  "local:${PROJECT_DIR}/.claude/settings.local.json"
  "user:${HOME_DIR}/.claude/settings.json"
  "enterprise:/etc/claude/settings.json"
  "managed:${HOME_DIR}/.claude/managed/settings.json"
)

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
# Raw output collection — produces the machine-parseable format
###############################################################################
collect_raw() {

###############################################################################
# 1. SETTINGS FILES
###############################################################################
section_start "SETTINGS"

found_settings=0
for entry in "${ALL_SETTINGS_FILES[@]}"; do
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
  "project:${PROJECT_DIR}/.claude/CLAUDE.md"
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

found_hooks=0
for entry in "${ALL_SETTINGS_FILES[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    has_hooks=$(jq -r 'has("hooks")' "$path" 2>/dev/null || echo "false")
    if [[ "$has_hooks" == "true" ]]; then
      # Schema: .hooks.EventType[i].matcher, .hooks.EventType[i].hooks[j].{type,command}
      while IFS= read -r event_type; do
        [[ -z "$event_type" ]] && continue
        group_count=$(jq -r ".hooks[\"${event_type}\"] | length" "$path" 2>/dev/null || echo "0")
        for ((i=0; i<group_count; i++)); do
          matcher=$(jq -r ".hooks[\"${event_type}\"][$i].matcher // \"*\"" "$path" 2>/dev/null || echo "*")
          inner_count=$(jq -r ".hooks[\"${event_type}\"][$i].hooks | length" "$path" 2>/dev/null || echo "0")
          for ((j=0; j<inner_count; j++)); do
            hook_type=$(jq -r ".hooks[\"${event_type}\"][$i].hooks[$j].type // \"command\"" "$path" 2>/dev/null || echo "command")
            command=$(jq -r ".hooks[\"${event_type}\"][$i].hooks[$j].command // .hooks[\"${event_type}\"][$i].hooks[$j].url // \"\"" "$path" 2>/dev/null || echo "")
            cmd_short="${command:0:60}"
            echo "[${scope}] ${event_type} matcher=${matcher} type=${hook_type} cmd=${cmd_short} source=${path}"
            found_hooks=1
          done
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

found_mcp=0
for entry in "${ALL_SETTINGS_FILES[@]}"; do
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
        echo "[${scope}] ${server_name} transport=${transport} source=${path}"
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
for entry in "${ALL_SETTINGS_FILES[@]}"; do
  scope="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    has_agents=$(jq -r 'has("agents")' "$path" 2>/dev/null || echo "false")
    if [[ "$has_agents" == "true" ]]; then
      while IFS= read -r agent_name; do
        [[ -z "$agent_name" ]] && continue
        echo "[${scope}] ${agent_name} source=settings ${path}"
        found_agents=1
      done < <(jq -r '.agents // {} | keys[]' "$path" 2>/dev/null)
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
      # Count skills in this plugin
      skill_count=0
      if [[ -d "$plugin_dir$skill_name" ]]; then
        skill_count=$(find "$plugin_dir$skill_name" -name "SKILL.md" 2>/dev/null | grep -cv 'template/SKILL.md' || echo "0")
      fi
      echo "[user] ${plugin_id} status=${status} skills=${skill_count} ${plugin_dir}${skill_name}/"
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

# 7c. Plugin skills — only from enabled plugins
# Build list of enabled plugin IDs from settings
enabled_plugins=""
if [[ -f "$user_settings" ]]; then
  enabled_plugins=$(jq -r '.enabledPlugins // {} | to_entries[] | select(.value == true) | .key' "$user_settings" 2>/dev/null || true)
fi

if [[ -d "$plugin_cache_dir" ]]; then
  for repo_dir in "$plugin_cache_dir"/*/; do
    [[ -d "$repo_dir" ]] || continue
    repo_name=$(basename "$repo_dir")
    for plugin_dir in "$repo_dir"/*/; do
      [[ -d "$plugin_dir" ]] || continue
      plugin_name=$(basename "$plugin_dir")
      plugin_id="${plugin_name}@${repo_name}"
      # Skip disabled plugins
      if [[ -n "$enabled_plugins" ]] && ! echo "$enabled_plugins" | grep -qF "$plugin_id"; then
        continue
      fi
      # Find SKILL.md files within this plugin, excluding template dirs
      while IFS= read -r skill_md; do
        [[ -f "$skill_md" ]] || continue
        # Skip template SKILL.md files
        case "$skill_md" in */template/SKILL.md) continue ;; esac
        parent_dir=$(basename "$(dirname "$skill_md")")
        grandparent_dir=$(basename "$(dirname "$(dirname "$skill_md")")")
        if [[ "$grandparent_dir" == "skills" ]]; then
          skill_name="$parent_dir"
        else
          skill_name="$grandparent_dir"
        fi
        echo "[plugin:${plugin_id}] ${skill_name} ${skill_md}"
        found_skills=1
      done < <(find "$plugin_dir" -name "SKILL.md" 2>/dev/null | sort)
    done
  done
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

# Check permissions mode — .permissions can be a string or object
permissions="default"
for entry in "${ALL_SETTINGS_FILES[@]}"; do
  scope="${entry%%:*}"
  fpath="${entry#*:}"
  if [[ -f "$fpath" ]]; then
    perm_type=$(jq -r '.permissions | type // "null"' "$fpath" 2>/dev/null || echo "null")
    if [[ "$perm_type" == "string" ]]; then
      permissions=$(jq -r '.permissions' "$fpath" 2>/dev/null || echo "default")
      break
    elif [[ "$perm_type" == "object" ]]; then
      permissions="custom"
      break
    fi
  fi
done

echo "[user] model=${model} permissions=${permissions}"

section_end "MODEL"

} # end collect_raw

###############################################################################
# Formatting helpers
###############################################################################
HEADER_WIDTH=55

# Print the main title bar
print_title() {
  local title="$1"
  local prefix="═══ ${title} "
  local pad_len=$(( HEADER_WIDTH - ${#prefix} ))
  if (( pad_len < 3 )); then pad_len=3; fi
  local pad=""
  for ((k=0; k<pad_len; k++)); do pad+="═"; done
  echo "${prefix}${pad}"
  echo
}

# Print a section header: ── Name (count) ──────────────
print_section_header() {
  local title="$1"
  local prefix="── ${title} "
  local pad_len=$(( HEADER_WIDTH - ${#prefix} ))
  if (( pad_len < 3 )); then pad_len=3; fi
  local pad=""
  for ((k=0; k<pad_len; k++)); do pad+="─"; done
  echo "${prefix}${pad}"
}

###############################################################################
# Extract a section from raw output (lines between === SECTION === and === END_SECTION ===)
###############################################################################
extract_section() {
  local raw="$1"
  local section="$2"
  local in_section=0
  local result=""
  while IFS= read -r line; do
    if [[ "$line" == "=== ${section} ===" ]]; then
      in_section=1
      continue
    fi
    if [[ "$line" == "=== END_${section} ===" ]]; then
      in_section=0
      continue
    fi
    if [[ $in_section -eq 1 ]]; then
      if [[ -n "$result" ]]; then
        result+=$'\n'"$line"
      else
        result="$line"
      fi
    fi
  done <<< "$raw"
  echo "$result"
}

###############################################################################
# Formatted output mode
###############################################################################
output_formatted() {
  local raw="$1"

  print_title "Session Overview"

  # -- Model (always shown) --
  local model_data
  model_data=$(extract_section "$raw" "MODEL")
  local model_str="" permissions_str=""
  if [[ -n "$model_data" && "$model_data" != "none" ]]; then
    # Parse: [user] model=X permissions=Y
    model_str=$(echo "$model_data" | sed -n 's/.*model=\([^ ]*\).*/\1/p' | head -1)
    permissions_str=$(echo "$model_data" | sed -n 's/.*permissions=\([^ ]*\).*/\1/p' | head -1)
  fi
  model_str="${model_str:-default}"
  permissions_str="${permissions_str:-default}"
  print_section_header "Model"
  echo " ${model_str} | permissions: ${permissions_str}"
  echo

  # -- CLAUDE.md Files --
  local claudemd_data
  claudemd_data=$(extract_section "$raw" "CLAUDE_MD")
  if [[ -n "$claudemd_data" && "$claudemd_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$claudemd_data"
    print_section_header "CLAUDE.md Files (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] N lines /path
      local scope line_count fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      line_count=$(echo "$line" | sed -n 's/.*\] \([0-9]*\) lines.*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*lines //p')
      echo " [${scope}] (${line_count} lines)"
      echo "   ${fpath}"
    done <<< "$claudemd_data"
    echo
  fi

  # -- Hooks --
  local hooks_data
  hooks_data=$(extract_section "$raw" "HOOKS")
  if [[ -n "$hooks_data" && "$hooks_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$hooks_data"
    print_section_header "Hooks (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] EventType matcher=X type=Y cmd=Z source=/path
      local scope event_type hook_type cmd_short source_path
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      event_type=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      hook_type=$(echo "$line" | sed -n 's/.*type=\([^ ]*\).*/\1/p')
      cmd_short=$(echo "$line" | sed -n 's/.*cmd=\(.*\) source=.*/\1/p')
      source_path=$(echo "$line" | sed -n 's/.*source=\(.*\)/\1/p')
      echo " [${scope}] ${event_type} → type:${hook_type} cmd:${cmd_short}"
      if [[ -n "$source_path" ]]; then
        echo "   ${source_path}"
      fi
    done <<< "$hooks_data"
    echo
  fi

  # -- MCP Servers --
  local mcp_data
  mcp_data=$(extract_section "$raw" "MCP_SERVERS")
  if [[ -n "$mcp_data" && "$mcp_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$mcp_data"
    print_section_header "MCP Servers (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] name transport=X source=/path
      local scope server_name transport source_path
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      server_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      transport=$(echo "$line" | sed -n 's/.*transport=\([^ ]*\).*/\1/p')
      source_path=$(echo "$line" | sed -n 's/.*source=\(.*\)/\1/p')
      echo " [${scope}] ${server_name} (${transport})"
      if [[ -n "$source_path" ]]; then
        echo "   ${source_path}"
      fi
    done <<< "$mcp_data"
    echo
  fi

  # -- Skills --
  local skills_data
  skills_data=$(extract_section "$raw" "SKILLS")
  if [[ -n "$skills_data" && "$skills_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$skills_data"
    print_section_header "Skills (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] skill_name /path
      local scope skill_name fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      skill_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      fpath=$(echo "$line" | sed -n 's/^\[[^]]*\] [^ ]* //p')
      echo " [${scope}] ${skill_name}"
      echo "   ${fpath}"
    done <<< "$skills_data"
    echo
  fi

  # -- Plugins --
  local plugins_data
  plugins_data=$(extract_section "$raw" "PLUGINS")
  if [[ -n "$plugins_data" && "$plugins_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$plugins_data"
    print_section_header "Plugins (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [user] plugin_id status=X skills=N /path
      local plugin_id status fpath
      plugin_id=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      status=$(echo "$line" | sed -n 's/.*status=\([^ ]*\).*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*skills=[0-9]* //p')
      echo " ${plugin_id} (${status})"
      if [[ -n "$fpath" ]]; then
        echo "   ${fpath}"
      fi
    done <<< "$plugins_data"
    echo
  fi

  # -- Agents --
  local agents_data
  agents_data=$(extract_section "$raw" "AGENTS")
  if [[ -n "$agents_data" && "$agents_data" != "none" ]]; then
    local count=0
    while IFS= read -r line; do
      [[ -n "$line" ]] && (( count++ )) || true
    done <<< "$agents_data"
    print_section_header "Agents (${count})"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] name source=file|settings /path
      local scope agent_name source_type fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      agent_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      source_type=$(echo "$line" | sed -n 's/.*source=\([^ ]*\).*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*source=[^ ]* //p')
      echo " [${scope}] ${agent_name} (${source_type})"
      if [[ -n "$fpath" ]]; then
        echo "   ${fpath}"
      fi
    done <<< "$agents_data"
    echo
  fi

  # -- Auto-Memory --
  local memory_data
  memory_data=$(extract_section "$raw" "AUTO_MEMORY")
  if [[ -n "$memory_data" && "$memory_data" != "none" ]]; then
    print_section_header "Auto-Memory"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [project] N lines filename /path
      local line_count filename fpath
      line_count=$(echo "$line" | sed -n 's/.*\] \([0-9]*\) lines.*/\1/p')
      filename=$(echo "$line" | sed -n 's/.*lines \([^ ]*\) .*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*lines [^ ]* //p')
      echo " ${filename} (${line_count} lines)"
      echo "   ${fpath}"
    done <<< "$memory_data"
    echo
  fi

  # -- Settings Files --
  local settings_data
  settings_data=$(extract_section "$raw" "SETTINGS")
  if [[ -n "$settings_data" && "$settings_data" != "none" ]]; then
    print_section_header "Settings Files"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # Parse: [scope] settings /path
      local scope fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*settings //p')
      printf " [%-10s %s\n" "${scope}]" "${fpath}"
    done <<< "$settings_data"
    echo
  fi
}

###############################################################################
# By-scope output mode
###############################################################################
output_by_scope() {
  local raw="$1"

  print_title "Session Overview"

  # Collect items per scope. We use temp files for bash 3 compat.
  local tmpdir
  tmpdir=$(mktemp -d)
  trap "rm -rf '$tmpdir'" EXIT

  # Initialize scope files
  touch "$tmpdir/project" "$tmpdir/user" "$tmpdir/local" "$tmpdir/enterprise" "$tmpdir/managed" "$tmpdir/plugins"

  # Helper to append to scope file
  append_scope() {
    local scope="$1"
    shift
    echo "$*" >> "$tmpdir/$scope"
  }

  # -- Model info (goes to user scope) --
  local model_data
  model_data=$(extract_section "$raw" "MODEL")
  local model_str="" permissions_str=""
  if [[ -n "$model_data" && "$model_data" != "none" ]]; then
    model_str=$(echo "$model_data" | sed -n 's/.*model=\([^ ]*\).*/\1/p' | head -1)
    permissions_str=$(echo "$model_data" | sed -n 's/.*permissions=\([^ ]*\).*/\1/p' | head -1)
  fi
  model_str="${model_str:-default}"
  permissions_str="${permissions_str:-default}"
  append_scope "user" "MODEL|Model: ${model_str}, permissions: ${permissions_str}"

  # -- CLAUDE.md --
  local claudemd_data
  claudemd_data=$(extract_section "$raw" "CLAUDE_MD")
  if [[ -n "$claudemd_data" && "$claudemd_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope line_count fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      line_count=$(echo "$line" | sed -n 's/.*\] \([0-9]*\) lines.*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*lines //p')
      append_scope "$scope" "CLAUDEMD|CLAUDE.md (${line_count} lines)|${fpath}"
    done <<< "$claudemd_data"
  fi

  # -- Hooks --
  local hooks_data
  hooks_data=$(extract_section "$raw" "HOOKS")
  if [[ -n "$hooks_data" && "$hooks_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope event_type cmd_short source_path
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      event_type=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      cmd_short=$(echo "$line" | sed -n 's/.*cmd=\(.*\) source=.*/\1/p')
      source_path=$(echo "$line" | sed -n 's/.*source=\(.*\)/\1/p')
      append_scope "$scope" "HOOKS|Hooks: ${event_type} → ${cmd_short}|${source_path}"
    done <<< "$hooks_data"
  fi

  # -- MCP Servers --
  local mcp_data
  mcp_data=$(extract_section "$raw" "MCP_SERVERS")
  if [[ -n "$mcp_data" && "$mcp_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope server_name transport source_path
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      server_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      transport=$(echo "$line" | sed -n 's/.*transport=\([^ ]*\).*/\1/p')
      source_path=$(echo "$line" | sed -n 's/.*source=\(.*\)/\1/p')
      append_scope "$scope" "MCP|MCP: ${server_name} (${transport})|${source_path}"
    done <<< "$mcp_data"
  fi

  # -- Agents --
  local agents_data
  agents_data=$(extract_section "$raw" "AGENTS")
  if [[ -n "$agents_data" && "$agents_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope agent_name source_type fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      agent_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      source_type=$(echo "$line" | sed -n 's/.*source=\([^ ]*\).*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*source=[^ ]* //p')
      append_scope "$scope" "AGENTS|Agents: ${agent_name}|${fpath}"
    done <<< "$agents_data"
  fi

  # -- Skills (project and user only; plugin skills go to plugins scope) --
  local skills_data
  skills_data=$(extract_section "$raw" "SKILLS")
  if [[ -n "$skills_data" && "$skills_data" != "none" ]]; then
    # Collect skill names per scope for compact display
    local project_skills="" user_skills=""
    declare -A plugin_skills_map 2>/dev/null || true
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope skill_name
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      skill_name=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      if [[ "$scope" == "project" ]]; then
        if [[ -n "$project_skills" ]]; then
          project_skills+=", ${skill_name}"
        else
          project_skills="${skill_name}"
        fi
      elif [[ "$scope" == "user" ]]; then
        if [[ -n "$user_skills" ]]; then
          user_skills+=", ${skill_name}"
        else
          user_skills="${skill_name}"
        fi
      fi
      # Plugin skills counted separately via PLUGINS section
    done <<< "$skills_data"
    if [[ -n "$project_skills" ]]; then
      append_scope "project" "SKILLS|Skills: ${project_skills}"
    fi
    if [[ -n "$user_skills" ]]; then
      append_scope "user" "SKILLS|Skills: ${user_skills}"
    fi
  fi

  # -- Settings --
  local settings_data
  settings_data=$(extract_section "$raw" "SETTINGS")
  if [[ -n "$settings_data" && "$settings_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local scope fpath
      scope=$(echo "$line" | sed -n 's/^\[\([^]]*\)\].*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*settings //p')
      append_scope "$scope" "SETTINGS|Settings: ${fpath}"
    done <<< "$settings_data"
  fi

  # -- Auto-Memory (goes to project scope) --
  local memory_data
  memory_data=$(extract_section "$raw" "AUTO_MEMORY")
  if [[ -n "$memory_data" && "$memory_data" != "none" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local line_count filename fpath
      line_count=$(echo "$line" | sed -n 's/.*\] \([0-9]*\) lines.*/\1/p')
      filename=$(echo "$line" | sed -n 's/.*lines \([^ ]*\) .*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*lines [^ ]* //p')
      append_scope "project" "MEMORY|Memory: ${filename} (${line_count} lines)|${fpath}"
    done <<< "$memory_data"
  fi

  # -- Render each non-empty scope --
  local scope_label
  for scope_key in project local user enterprise managed; do
    [[ -s "$tmpdir/$scope_key" ]] || continue
    case "$scope_key" in
      project)    scope_label="Project" ;;
      local)      scope_label="Local (.claude/settings.local.json)" ;;
      user)       scope_label="User (~/.claude/)" ;;
      enterprise) scope_label="Enterprise (/etc/claude/)" ;;
      managed)    scope_label="Managed" ;;
    esac
    print_section_header "$scope_label"
    while IFS= read -r entry; do
      [[ -z "$entry" ]] && continue
      local category rest fpath
      # Split on | delimiter — field1|field2|field3
      category="${entry%%|*}"
      local after_cat="${entry#*|}"
      if [[ "$after_cat" == *"|"* ]]; then
        rest="${after_cat%%|*}"
        fpath="${after_cat#*|}"
      else
        rest="$after_cat"
        fpath=""
      fi
      echo " ${rest}"
      if [[ -n "$fpath" ]]; then
        echo "   ${fpath}"
      fi
    done < "$tmpdir/$scope_key"
    echo
  done

  # -- Plugins scope --
  local plugins_data
  plugins_data=$(extract_section "$raw" "PLUGINS")
  if [[ -n "$plugins_data" && "$plugins_data" != "none" ]]; then
    print_section_header "Plugins"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local plugin_id status skill_count fpath
      plugin_id=$(echo "$line" | sed -n 's/^\[[^]]*\] \([^ ]*\) .*/\1/p')
      status=$(echo "$line" | sed -n 's/.*status=\([^ ]*\).*/\1/p')
      skill_count=$(echo "$line" | sed -n 's/.*skills=\([0-9]*\).*/\1/p')
      fpath=$(echo "$line" | sed -n 's/.*skills=[0-9]* //p')
      if [[ -n "$skill_count" && "$skill_count" != "0" ]]; then
        echo " ${plugin_id} (${status}) — ${skill_count} skills"
      else
        echo " ${plugin_id} (${status})"
      fi
      if [[ -n "$fpath" ]]; then
        echo "   ${fpath}"
      fi
    done <<< "$plugins_data"
    echo
  fi

  rm -rf "$tmpdir"
  trap - EXIT
}

###############################################################################
# Main: collect raw, then output in requested mode
###############################################################################

RAW_OUTPUT=$(collect_raw)

case "$MODE" in
  raw)
    echo "$RAW_OUTPUT"
    ;;
  formatted)
    output_formatted "$RAW_OUTPUT"
    ;;
  by-scope)
    output_by_scope "$RAW_OUTPUT"
    ;;
esac
