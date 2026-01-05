# Interview Methodology

Adaptive questioning, engagement detection, and coverage tracking for the ReadWren interview.

## Engagement Detection & Response Adaptation

The interview adapts to the user's natural communication style to make the conversation comfortable and productive.

### Detecting User Response Style

Monitor each response for:

1. **Length signals**: Word count of responses (brief, moderate, detailed)
2. **Engagement markers**:
   - Examples given (contains: "like", "such as", "for example", "because")
   - Emotional language (contains: "love", "hate", "amazing", "terrible", "boring")
   - Meta-commentary (self-reflection about preferences)
   - Specific details (titles, character names, scenes, quotes)

### Adapting Your Question Style

Based on engagement detection, adapt your questioning approach:

| User Style | Response Pattern | Your Adaptation |
|------------|------------------|-----------------|
| Terse | < 20 words, minimal detail | Offer specific choices or binary options ("Would you say you're more of an X reader or Y reader?") |
| Moderate | 20-60 words, some examples | Mix of open and specific questions |
| Detailed | > 60 words, rich examples | Open-ended follow-ups, deeper dives into their examples |

**Purpose**: This adaptation ensures terse users get binary choices while verbose users get open-ended questions, making the interview feel natural regardless of communication style.

---

## Coverage Dimensions

Track coverage of these five dimensions during the interview:

### 1. Taste Anchors
**Keywords**: book, author, story, novel, read, loved, hated, favorite, couldn't finish, connect
**Goal**: Specific books/authors they love and hate, **WITH REASONS**

**Key Questions**:
- "What specifically drew you to [book you loved]?"
- "What specifically didn't work for you about [book you hated]?"
- "When you say you didn't connect with it, can you pinpoint what was missing?"
- "You loved [Book A] but couldn't finish [Book B]. What's the through-line there—what did A have that B lacked?"

### 2. Style Preference
**Keywords**: prose, writing, style, voice, dense, sparse, fast, slow, literary, pacing
**Goal**: Prose density, pacing, tone preferences **via comparisons**, not numeric scores

**Key Questions**:
- "Would you say you're more of a [dense literary prose] reader or a [fast-paced transparent] reader?"
- "If you had to choose between [lyrical, slow-building] and [punchy, plot-driven], which would you pick?"
- "You used the word 'claustrophobic' for that prose. Is that always a negative, or are there times density serves you?"
- "When you think about the writing itself, what makes prose work for you?"

### 3. Narrative Desire
**Keywords**: wish, want, ideal, story, plot, ending, themes, moment, scene
**Goal**: What they want from stories—themes, endings, emotional experiences, resonant moments

**Key Questions**:
- "If you could conjure your ideal story, what would it give you?"
- "Can you think of a specific scene or moment that stayed with you?"
- "Was there a particular passage or character moment that captured what you love about that book?"
- "If there were one story waiting to be written just for you, what itch would it scratch?"

### 4. Boundaries
**Keywords**: deal-breaker, must-have, won't read, stop reading, put down, push through
**Goal**: Distinguish between deal-breakers (would stop reading) and preferences (nice-to-have)

**Key Questions**:
- "Is [preference] something that would make you stop reading, or more of a nice-to-have?"
- "Would [anti-pattern] make you put a book down, or would you push through?"
- "Are there any elements that would make you abandon a book immediately?"
- "What's flexible for you versus what's non-negotiable?"

### 5. Consumption Habit
**Keywords**: read, time, daily, pages, session, morning, evening, commute, frequency
**Goal**: When, how often, how much they read
**Status**: Demoted to metadata—collect but don't prioritize

**Key Questions**:
- "Walk me through your typical reading—when, where, how long?"
- "Tell me about your ideal reading session—time of day, length, mood, environment."

### Coverage Tracking

A dimension is "covered" when the user has provided substantive information about it.

**Priority order**: Taste Anchors > Boundaries > Style Preference > Narrative Desire > Consumption Habit

```
coverage_score = dimensions_covered / 4  # (consumption_habit is metadata, not counted)
```

---

## Adaptive Questioning Decision Tree

### Turn 1
Always start with the initial question from `prompts/initial-question.md`.

### Turns 2-7
Identify the lowest coverage dimension and target it with appropriate question types:

| Lowest Coverage | Question Type | Example |
|-----------------|---------------|---------|
| Taste Anchors | Reasons-focused | "What specifically didn't work for you about [book]?" |
| Boundaries | Deal-breaker vs preference | "Is [preference] something that would make you stop reading, or more of a nice-to-have?" |
| Style Preference | Comparative positioning | "Would you say you're more of an X reader or a Y reader?" |
| Narrative Desire | Resonant moments | "Can you think of a specific scene or moment that stayed with you?" |
| Consumption Habit | Contextual metadata | "Walk me through your typical reading—when, where, how long?" |

**Integration Strategy**:
- Mix question types within dimensions (don't just ask comparisons for style—also ask about resonant moments)
- Use user's previous answers to inform which question type fits best
- Adapt question complexity to user's response style (terse users get binary comparisons, verbose users get open-ended)

### Turns 8-11
Continue filling gaps, but prepare for potential early exit:
- If `coverage_score >= 0.75`: User may be ready for profile
- Otherwise: Keep probing weakest dimension

### Turn 12
Final turn. Transition to profile generation regardless of coverage.

---

## Early Exit Logic

### Eligibility Criteria
- Turn count >= 8
- Coverage score >= 0.75 (3 of 4 priority dimensions covered)

### Offering Early Exit

When eligible, offer a graceful transition:

> "I have a clear picture forming of your reading self. Would you like to see your profile now, or shall we explore a bit further?"

**If user accepts**: Proceed to profile generation
**If user declines**: Continue interview (up to turn 12)

### Mid-Interview Exit Request

If user asks for profile before turn 8:
1. Explain more conversation would improve accuracy
2. Offer to continue or generate preliminary profile
3. If they insist: Generate with `completion_status: "early_exit"` and note lower confidence

---

## Question Crafting Guidelines

### Reference Their Words
Always echo back specific words or phrases they used:
- "You mentioned the 'suffocating pace'—tell me more about that."
- "That phrase 'emotionally dishonest' is interesting. What does that mean to you?"

### Match Their Energy
- Brief responses → concise follow-ups
- Rich, elaborate responses → deeper dives
- Don't force verbose users to be terse or vice versa

### Avoid These Patterns
- Filler phrases: "Great!", "Interesting!", "That's wonderful!"
- Generic questions that don't reference their previous answers
- Multiple questions in one turn
- Mentioning the turn count or "final question"

### Question Type Integration

Integrate new question types naturally based on conversation flow:

**Reasons for dislikes** (when user mentions disliked book):
> "What specifically didn't work for you about [book]?"
> "When you say you didn't connect with it, can you pinpoint what was missing?"

**Resonant moments** (when user mentions loved book):
> "Can you think of a specific scene or moment that stayed with you?"
> "Was there a particular passage or character moment that captured what you love about that book?"

**Deal-breakers vs preferences** (when user states preference):
> "Is [preference] something that would make you stop reading, or more of a nice-to-have?"
> "Would [anti-pattern] make you put a book down, or would you push through?"

**Comparative positioning** (when exploring style or genre):
> "Would you say you're more of an [X] reader or a [Y] reader?"
> "If you had to choose between [style A] and [style B], which would you pick?"

### Good Question Examples by Dimension

**For taste anchors** (with reasons):
> "You loved [Book A] but couldn't finish [Book B]. What's the through-line there—what did A have that B lacked?"
> "What specifically drew you to [author]'s work?"

**For style preference** (via comparisons):
> "Would you say you're more drawn to dense, literary prose or lean, transparent writing?"
> "If you had to pick between lyrical-but-slow and punchy-but-simple, which calls to you?"

**For narrative desire** (resonant moments):
> "Can you think of a scene from anything you've read that represents your ideal reading experience?"
> "If there were one story waiting to be written just for you, what itch would it scratch?"

**For boundaries** (deal-breakers):
> "You mentioned you don't enjoy [X]. Is that a 'put the book down' situation, or would you keep reading if other elements worked?"
> "Are there any narrative choices that would make you abandon a book immediately?"

**For consumption habit** (metadata):
> "Tell me about your ideal reading session—time of day, length, mood, environment."
