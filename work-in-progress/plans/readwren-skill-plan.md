# ReadWren Skill Implementation Plan

## Purpose

Convert the ReadWren literary interview project into a Claude Web/Code skill that conducts 12-turn adaptive interviews to extract reading preferences and generate detailed reader profiles. The skill embodies "Wren," a warm but precise literary profiler who uses shadow analysis to build comprehensive reader profiles.

**Location:** `/common/readwren/` (works both Claude Web and Claude Code)

---

## Skill Directory Structure

```
/common/readwren/
├── SKILL.md                           # Main skill file (~400 lines)
└── references/
    ├── profile-rubric.md              # Full scoring rubric (0-100 style, 0-1 implicit)
    ├── profile-schema.md              # JSON schema with field explanations
    ├── interview-methodology.md       # Shadow analysis and adaptive questioning
    └── prompts/
        ├── system-prompt.md           # Core interviewer system prompt
        ├── initial-question.md        # Opening question
        └── profile-generation.md      # Profile generation prompt template
```

---

## Variables Section (Top of SKILL.md)

```
OUTPUT_DIR: "./readwren_profile_{timestamp}.json" (Claude Code) or "/mnt/output/readwren_profile_{timestamp}.json" (Claude Web)
STATE_FILE: "./readwren_state.json" (Claude Code) or "/mnt/user-data/uploads/wren_state.json" (Claude Web)
PROMPTS_DIR: "references/prompts/" (location of prompt templates)
MAX_TURNS: 12 (maximum interview length)
EARLY_EXIT_TURN: 8 (earliest turn for early exit offer)
EARLY_EXIT_COVERAGE: 0.75 (minimum coverage for early exit eligibility)
```

Users can override these by specifying different paths when invoking the skill.

---

## Instructions

1. **Using prompts**: Read `references/prompts/system-prompt.md` at session start to establish Wren's voice and interviewing approach. Read `references/prompts/initial-question.md` for the opening question. Read `references/prompts/profile-generation.md` only when the interview completes.

2. **Using references**: Consult `references/interview-methodology.md` when deciding which question type to ask next based on coverage gaps. Consult `references/profile-rubric.md` only during final profile generation to ensure accurate scoring.

3. **Using schema**: Reference `references/profile-schema.md` when generating the final profile JSON to ensure all required fields are populated correctly.

4. **State management**: Always read state file at the start of each turn to restore context. Write updated state at the end of each turn to persist shadow analysis and coverage tracking.

---

## Key Design Decisions

### 1. Character Persona: "Wren"
- Warm but precise literary profiler
- References user's exact words
- Matches user energy (terse to terse, rich to rich)
- No filler phrases ("Great!", "Interesting!")

### 2. State Management via /mnt
**State file locations:**
- Claude Web: `/mnt/user-data/uploads/wren_state.json`
- Claude Code: `./readwren_state.json`

**State schema:**
```json
{
  "session_id": "ISO timestamp",
  "turn_count": 0,
  "coverage": {
    "taste_anchors": false,
    "style_preference": false,
    "narrative_desire": false,
    "consumption_habit": false
  },
  "coverage_score": 0.0,
  "shadow_analysis": {
    "cumulative_word_count": 0,
    "response_lengths": [],
    "vocabulary_tokens": [],
    "engagement_markers": {
      "examples_given": 0,
      "emotional_language": 0,
      "meta_commentary": 0
    }
  },
  "is_complete": false,
  "early_exit_eligible": false
}
```

### 3. Profile Schema (Full - keeping all dimensions)
```json
{
  "reader_archetype": "2-3 word label",
  "taste_anchors": {
    "loves": [], "hates": [], "inferred_genres": []
  },
  "style_signature": {
    "prose_density": 0-100,
    "pacing": 0-100,
    "tone": 0-100,
    "worldbuilding": 0-100,
    "character_focus": 0-100
  },
  "narrative_desires": {
    "wish": "one sentence",
    "preferred_ending": "tragic|bittersweet|hopeful|ambiguous|transcendent",
    "themes": []
  },
  "consumption": {
    "daily_time_minutes": 15-180,
    "delivery_frequency": "daily|every_few_days|weekly|binge",
    "pages_per_delivery": 5-50
  },
  "implicit": {
    "vocabulary_richness": 0-1,
    "response_brevity": 0-1,
    "engagement_index": 0-1
  },
  "explanations": {
    "prose_density": "", "pacing": "", "tone": "",
    "worldbuilding": "", "character_focus": "",
    "vocabulary_richness": "", "engagement_level": "",
    "reading_philosophy": "2-3 sentences",
    "anti_patterns": ""
  },
  "_metadata": {
    "interview_turns": 8-12,
    "completion_status": "complete|early_exit",
    "timestamp": "ISO"
  }
}
```

### 4. Shadow Analysis (Invisible to User)
Claude tracks per response:
- Word count and unique vocabulary tokens
- Engagement markers (examples, emotion words, meta-commentary)

Calculates at profile generation:
- `vocabulary_richness = unique_words / total_words`
- `response_brevity = 1 - (avg_words / 100)` (clamped 0-1)
- `engagement_index = markers / (turns * 3)`

### 5. Early Exit Logic
- Eligible at turn 8+ with coverage >= 75%
- Offer graceful transition; user can decline and continue

---

## Workflow

Sequential steps showing how Claude executes the skill during a session:

1. **Session Start**: Check for existing state file to determine if resuming or starting fresh
2. **Initialize or Resume**: If new session, read `references/prompts/initial-question.md` and create state file. If resuming, read state file to restore context.
3. **Present Question**: Deliver the appropriate question (initial or adaptive follow-up)
4. **Receive Response**: Wait for user's answer
5. **Shadow Analysis**: Silently analyze response for word count, vocabulary, engagement markers
6. **Update Coverage**: Determine which dimensions the response addressed
7. **Check Exit Conditions**: If `turn_count >= EARLY_EXIT_TURN` AND `coverage_score >= EARLY_EXIT_COVERAGE`, consider early exit offer
8. **Persist State**: Write updated state to state file
9. **Loop or Complete**: If not complete, consult `references/interview-methodology.md` and return to step 3. If complete, proceed to profile generation.
10. **Generate Profile**: Read `references/prompts/profile-generation.md` and `references/profile-rubric.md`, generate final profile JSON, save to `OUTPUT_DIR`

---

## Cookbook

Conditional patterns showing which approach to use based on user requests and interview state.

### Scenario 1: Starting a New Interview

- **IF**: User invokes ReadWren AND (no state file exists OR user explicitly requests fresh start)
- **THEN**:
  1. Initialize state file with empty schema (all coverage false, turn_count 0)
  2. Read `references/prompts/system-prompt.md` to establish Wren persona
  3. Read `references/prompts/initial-question.md`
  4. Present Wren's introduction and opening question
  5. Write initial state to state file
- **EXAMPLES**:
  - "Start a ReadWren interview"
  - "I want to discover my reader profile"
  - "Help me find books I'll love"
  - "Begin a reading preferences interview"

### Scenario 2: Resuming an Existing Interview

- **IF**: User returns AND state file exists with `is_complete` = false
- **THEN**:
  1. Read state file to restore full context
  2. Acknowledge resumption briefly as Wren
  3. Continue from where the interview left off
  4. Ask next adaptive question based on coverage gaps
- **EXAMPLES**:
  - "Continue my ReadWren interview"
  - "Where were we with my reader profile?"
  - User simply responds to previous question after break

### Scenario 3: Mid-Interview Turn (turn_count < EARLY_EXIT_TURN)

- **IF**: State exists AND `turn_count` < 8 AND `is_complete` = false AND user provides response
- **THEN**:
  1. Perform shadow analysis on user response (word count, vocabulary, engagement)
  2. Update coverage scores based on response content
  3. Increment turn_count
  4. Consult `references/interview-methodology.md` for lowest coverage dimension
  5. Ask adaptive follow-up targeting the gap
  6. Write updated state
- **EXAMPLES**:
  - User answers: "I loved The Name of the Wind but couldn't finish Malazan"
  - User answers: "I usually read before bed, maybe 30 minutes"

### Scenario 4: Early Exit Eligible

- **IF**: `turn_count` >= 8 AND `coverage_score` >= 0.75 AND `is_complete` = false
- **THEN**:
  1. Complete shadow analysis and coverage update for current response
  2. Set `early_exit_eligible` = true in state
  3. Offer graceful completion: "I have a clear picture forming. Would you like to see your profile now, or shall we explore further?"
  4. If user accepts: proceed to Scenario 6 (Profile Generation)
  5. If user declines: continue with Scenario 3 pattern
- **EXAMPLES**:
  - At turn 8+: "That gives me a rich picture. Ready to see your profile?"
  - User responds: "Yes, let's see it" → Generate profile
  - User responds: "I have more to share" → Continue interview

### Scenario 5: Maximum Turns Reached

- **IF**: `turn_count` = 12 AND user provides final response
- **THEN**:
  1. Complete final shadow analysis
  2. Update all coverage scores
  3. Set `is_complete` = true
  4. Proceed immediately to profile generation (Scenario 6)
- **EXAMPLES**:
  - Automatic transition after turn 12 response

### Scenario 6: Generate Final Profile

- **IF**: `is_complete` = true OR user accepts early exit
- **THEN**:
  1. Read `references/prompts/profile-generation.md` for generation template
  2. Read `references/profile-rubric.md` for scoring guidelines
  3. Read `references/profile-schema.md` for JSON structure
  4. Compile all shadow analysis data
  5. Generate complete profile JSON with explanations
  6. Save profile to `OUTPUT_DIR` with timestamp
  7. Present summary to user with key insights
  8. Optionally provide full JSON if requested
- **EXAMPLES**:
  - "Here's your reader profile, complete with your archetype and personalized insights..."

### Scenario 7: User Requests Profile Mid-Interview

- **IF**: User explicitly asks to see profile AND `turn_count` < 8
- **THEN**:
  1. Explain that more conversation would improve accuracy
  2. Offer to continue or generate preliminary profile
  3. If user insists: generate profile with `completion_status: "early_exit"` and note lower confidence
- **EXAMPLES**:
  - "Can I just see my profile now?"
  - "I don't have time for more questions"

---

## Implementation Tasks

### Phase 1: Create Skill Structure
1. Create directory `/common/readwren/`
2. Create `references/` subdirectory
3. Create `references/prompts/` subdirectory

### Phase 2: Create Reference Files
4. **`references/profile-rubric.md`** - Adapt from `work-in-progress/readwren/docs/PROFILE_RUBRIC.md`
   - Style metrics (0-100 scales with examples)
   - Implicit signals (0-1 scales)
   - Score consistency guidelines

5. **`references/profile-schema.md`**
   - Complete JSON schema
   - Field descriptions
   - Example profile

6. **`references/interview-methodology.md`**
   - Shadow analysis formulas
   - Coverage dimension keywords
   - Adaptive questioning decision tree
   - Early exit conversation patterns

### Phase 3: Create Prompt Files (Progressive Disclosure)
7. **`references/prompts/system-prompt.md`**
   - Core interviewer system prompt from ReadWren
   - Dynamic turn injection placeholder
   - 5 dimensions to extract
   - Response style guidelines

8. **`references/prompts/initial-question.md`**
   - Opening question ("Name 3 books...")
   - Wren's introduction

9. **`references/prompts/profile-generation.md`**
   - Profile generation prompt template
   - JSON schema for output
   - Rubric reference instructions

### Phase 4: Write SKILL.md
10. **Frontmatter** with name and comprehensive description trigger

11. **Purpose Section** (~10 lines)
    - Core functionality explanation
    - Why the skill exists (reader profiling through adaptive interviews)

12. **Variables Section** (~15 lines)
    - OUTPUT_DIR, STATE_FILE, PROMPTS_DIR, MAX_TURNS, EARLY_EXIT_TURN, EARLY_EXIT_COVERAGE
    - Platform-specific defaults in code block format

13. **Instructions Section** (~20 lines)
    - When to read prompts (system-prompt at start, profile-generation at end)
    - When to consult references (methodology for questioning, rubric for scoring)
    - State management rules (read at turn start, write at turn end)

14. **Wren Persona Section** (~20 lines)
    - Character traits and voice guidelines
    - Reference to initial-question.md

15. **Workflow Section** (~30 lines)
    - 10-step operational flow from session start to profile generation
    - References to specific files at each step

16. **Cookbook Section** (~100 lines)
    - Scenario 1: Starting a New Interview
    - Scenario 2: Resuming an Existing Interview
    - Scenario 3: Mid-Interview Turn
    - Scenario 4: Early Exit Eligible
    - Scenario 5: Maximum Turns Reached
    - Scenario 6: Generate Final Profile
    - Scenario 7: User Requests Profile Mid-Interview
    - Each with IF/THEN/EXAMPLES format

17. **Key Design Details Section** (~60 lines)
    - State schema
    - Profile schema summary (full in references)
    - Shadow analysis formulas
    - Coverage dimensions

18. **Rules Section** (~15 lines)
    - One question per turn
    - Reference user's words
    - Never mention turn count
    - Maintain persona
    - Shadow analysis is invisible

### Phase 5: Validation
19. Test full 12-turn interview on Claude Web
20. Verify state persistence between turns
21. Verify profile output to /mnt/output
22. Test early exit at turn 8
23. Test Claude Code compatibility

---

## Critical Source Files

| Purpose | Source File |
|---------|-------------|
| Rubric scales | `work-in-progress/readwren/docs/PROFILE_RUBRIC.md` |
| System prompt | `work-in-progress/readwren/src/prompts/interview_prompts.py` |
| Analysis logic | `work-in-progress/readwren/src/tools/profile_tools.py` |
| Example profile | `work-in-progress/readwren/examples/example_session/profiles/` |

---

## Output Locations

| Platform | State File | Profile Output |
|----------|------------|----------------|
| Claude Web | `/mnt/user-data/uploads/wren_state.json` | `/mnt/output/readwren_profile_{timestamp}.json` |
| Claude Code | `./readwren_state.json` | `./readwren_profile_{timestamp}.json` |

---

## Files to Create

1. `/common/readwren/SKILL.md` (~400 lines) - includes Purpose, Variables, Instructions, Workflow, Cookbook, Design Details, Rules
2. `/common/readwren/references/profile-rubric.md` (~150 lines)
3. `/common/readwren/references/profile-schema.md` (~80 lines)
4. `/common/readwren/references/interview-methodology.md` (~100 lines)
5. `/common/readwren/references/prompts/system-prompt.md` (~50 lines)
6. `/common/readwren/references/prompts/initial-question.md` (~20 lines)
7. `/common/readwren/references/prompts/profile-generation.md` (~60 lines)

**Total: ~860 lines across 7 files**
