---
name: namegen
description: Generate fictional names. Example user requests ("give me some name options for...", "what should [chars/the] name be?", "what's a better name for him/her?"). Example thinking  ("The user wants me to generate names...", "I need to come up with a culturally appropriate name for...", "I'm being asked for name(s) appropriate for [culture]"). Supports realistic names (authentic, locale-based) and synthetic names (Markov-generated, novel-but-plausible). Use when you or the user needs character names, NPC names, or when developing story concepts that require characters to be named.
version: 1.0 (Initial release)
---

# Purpose

Generates first, middle, and last names themed by culture/nationality for fiction writing. Two modes serve different genres:

- **Realistic mode**: Draws from authentic name distributions via Faker (~70 locales). Best for contemporary, historical, or literary fiction where cultural accuracy matters.
- **Synthetic mode**: Generates novel names via Markov chains trained on cultural datasets. Best for fantasy, sci-fi, or worldbuilding where you want names that *feel* culturally consistent without being real.

Avoids "AI slop" names (Luna, Kai, Zara, Elara, etc.) through blocklist filtering.

## Variables

```
QUIET_MODE: false          # When true, suppress explanatory output—just return names
DEFAULT_MODE: "realistic"  # "realistic" or "synthetic"
DEFAULT_GENDER: "neutral"  # "male", "female", or "neutral"
DEFAULT_COMPONENTS: ["first", "last"]  # Middle name only if explicitly requested
ANTI_SLOP_ENABLED: true    # Filter out overused AI-typical names
ROMANIZE_NAMES: true       # When true, output Latin alphabet versions of non-Latin names
```

## Instructions

1. **Install dependencies** (first-time setup):
   ```bash
   uv pip install faker markovname unidecode --system --break-system-packages -q
   ```

2. **Determine invocation context**:
   - If Claude is invoking mid-conversation with sufficient context → set `QUIET_MODE: true`, infer all parameters
   - If user explicitly invokes with ambiguous request → ask ONE clarifying question, then generate

3. **Available cultures**:
   - **Realistic** (Faker locales, 105 total): ar_SA, bg_BG, cs_CZ, da_DK, de_DE, de_AT, de_CH, el_GR, en_US, en_GB, en_AU, en_CA, en_IN, en_IE, es_ES, es_MX, es_AR, et_EE, fa_IR, fi_FI, fr_FR, fr_CA, he_IL, hi_IN, hr_HR, hu_HU, id_ID, it_IT, ja_JP, ko_KR, lt_LT, lv_LV, nl_NL, no_NO, pl_PL, pt_BR, pt_PT, ro_RO, ru_RU, sk_SK, sl_SI, sv_SE, th_TH, tr_TR, uk_UA, vi_VN, zh_CN, zh_TW, and many more
   - **Synthetic** (markovname datasets): american_forenames, american_surnames, dutch_forenames, french_forenames, german_forenames, icelandic_forenames, indian_forenames, irish_forenames, italian_forenames, japanese_forenames, russian_forenames, scottish_surnames, spanish_forenames, swedish_forenames, brythonic_deities, egyptian_deities, hindu_deities, norse_deity_forenames, roman_deities, roman_emperor_forenames, tolkienesque_forenames, werewolf_forenames, mythical_humanoids, stars_proper_names

4. **Generation**: Use `scripts/generate.py` for all name generation.

## Workflow

### Step 1: Assess context and parameters

Determine these values from conversation context or user request:
- `mode`: "realistic" or "synthetic" (infer from genre: fantasy/sci-fi → synthetic; contemporary/historical → realistic)
- `culture`: Specific locale or training set
- `gender`: "male", "female", or "neutral"
- `components`: Which name parts needed (default: first,last)
- `quantity`: How many names to generate (default 1; batch for "give me options" requests)

### Step 2: If ambiguous, ask ONE clarifying question

If mode AND culture cannot be inferred, ask a compound question:

> "What's the setting—real-world (contemporary/historical) or speculative (fantasy/sci-fi)? Any cultural flavor in mind?"

Then generate immediately after response. Do not conduct extended Q&A.

### Step 3: Generate names via script

**Quiet mode (Claude-invoked, mid-conversation):**
```bash
python scripts/generate.py --mode realistic --culture ja_JP --gender male -n 1 --quiet
# Output: 太郎 山田

# With romanization:
python scripts/generate.py --mode realistic --culture ja_JP --gender male -n 1 --quiet --romanize
# Output: Taro Yamada
```

**Interactive mode (user-invoked):**
```bash
python scripts/generate.py --mode synthetic --culture tolkien --gender neutral -n 3
# Output: JSON with metadata
```

**List available cultures:**
```bash
python scripts/generate.py --list-cultures
```

**Script arguments:**
- `--mode`, `-m`: "realistic" or "synthetic" (required)
- `--culture`, `-c`: Locale code, friendly name, or dataset (required)
- `--gender`, `-g`: "male", "female", or "neutral" (default: neutral)
- `--components`: Comma-separated "first,middle,last" (default: first,last)
- `--quantity`, `-n`: Number of names (default: 1)
- `--quiet`, `-q`: Output names only, no JSON metadata
- `--no-filter`: Disable anti-slop filtering
- `--romanize`, `-r`: Convert non-Latin names to romanized (Latin alphabet) form
- `--list-cultures`: Show all available options

### Step 4: Return output

**Quiet mode** (`QUIET_MODE: true`):
```
Kenji Yamamoto
```

**Interactive mode** (`QUIET_MODE: false`):
```
Kenji Yamamoto — realistic Japanese male
```

## Cookbook

### Scenario 1: Claude-Invoked (Mid-Conversation)

- **IF**: Claude is generating a name as part of ongoing story/worldbuilding discussion AND context provides sufficient information about setting, culture, genre
- **THEN**: 
  1. Set `QUIET_MODE: true`
  2. Infer all parameters from conversation context
  3. Generate immediately
  4. Present name inline without ceremony
- **EXAMPLES**:
  - User (in ongoing convo): "What should I name the captain?" → Generate based on established story context
  - User developing Korean sci-fi setting asks "I need a name for the antagonist" → Synthetic Korean-adjacent, present inline

### Scenario 2: User-Invoked, Fully Specified

- **IF**: User explicitly requests names with mode + culture provided (or strongly implied by genre keywords)
- **THEN**:
  1. Set `QUIET_MODE: false`
  2. Generate immediately with specified parameters
  3. Include brief metadata in output
- **EXAMPLES**:
  - "German female name, realistic" → Generate, no clarification needed
  - "Celtic synthetic name for a druid" → Synthetic Celtic, neutral gender
  - "Japanese businessman name" → Realistic Japanese male

### Scenario 3: User-Invoked, Genre-Implied Mode

- **IF**: User mentions genre keywords that imply mode
- **THEN**: Infer mode, may still need culture clarification
- **GENRE → MODE MAPPING**:
  - "fantasy", "sci-fi", "worldbuilding", "elven", "alien", "far-future" → synthetic
  - "contemporary", "modern", "historical", "noir", "Victorian", "1920s" → realistic
- **EXAMPLES**:
  - "Name for my fantasy ranger" → Synthetic (ask: "Any cultural inspiration—Celtic, Norse, Germanic, or something else?")
  - "1940s detective name" → Realistic American, generate immediately

### Scenario 4: User-Invoked, Ambiguous

- **IF**: User request lacks mode AND culture hints
- **THEN**:
  1. Ask ONE compound clarifying question
  2. Generate immediately after response
- **CLARIFYING QUESTION**: "What's the setting—real-world (contemporary/historical) or speculative (fantasy/sci-fi)? Any cultural flavor in mind?"
- **EXAMPLES**:
  - "I need a character name" → Ask clarifying question
  - "Help me name some characters for a story" → Ask clarifying question

### Scenario 5: Batch Generation

- **IF**: User requests multiple names ("give me options", "10 NPC names", "a few names to choose from")
- **THEN**:
  1. Generate 3-5 names for "options" requests, or specified quantity
  2. Introduce variety (mix genders if neutral, slight cultural variation if regional)
- **EXAMPLES**:
  - "Give me some options for a Celtic warrior" → 4-5 synthetic Celtic names, mixed genders
  - "10 names for a medieval European village" → Mix of English, French, German realistic names

### Scenario 6: Culture Mismatch (Synthetic Unavailable)

- **IF**: User requests synthetic mode for a culture without markovname training data
- **THEN**: Offer alternatives:
  1. Realistic version of that culture (Faker has 105 locales), OR
  2. Related synthetic dataset that captures similar phonetics
- **AVAILABLE SYNTHETIC**: american, dutch, french, german, icelandic, indian, irish, italian, japanese, russian, scottish (surnames), spanish, swedish, plus fantasy sets (norse, roman, tolkienesque, etc.)
- **EXAMPLES**:
  - "Korean synthetic name" → "Synthetic Korean isn't available. I can do realistic Korean, or synthetic Japanese for similar phonetic feel?"
  - "Arabic synthetic" → "Synthetic Arabic isn't available. Realistic Arabic covers many regions (ar_SA, ar_EG, ar_AE, etc.), or I could try egyptian_deities for ancient flavor?"

### Scenario 7: Blended Mode (Diaspora/Multicultural)

- **IF**: User implies mixed heritage or far-future setting where cultural blending makes sense
- **THEN**: Combine modes—synthetic first name + realistic surname (or vice versa)
- **EXAMPLES**:
  - "Far-future character with Japanese heritage" → Synthetic first + realistic Japanese surname
  - "Fantasy character with Roman roots" → Synthetic Latin first + realistic Italian surname

### Scenario 8: Anti-Slop Rejection

- **IF**: Generated name matches blocklist AND `ANTI_SLOP_ENABLED: true`
- **THEN**: Silently regenerate until non-slop name produced (max 10 attempts)
- **NOTE**: This is automatic, no user interaction needed
