# Profile Generation Prompt

Template for generating the final reader profile from interview conversation.

---

## Prompt Template

Based on this interview conversation, generate a Markdown reader profile following the structure in `references/profile-template.md`.

**CRITICAL**: This is a qualitative synthesis, not data extraction. The value is in the prose, the insights, and the prescience of your interpretation. Write in second person ("You prefer..." not "The reader prefers...").

### Output Format

Follow the Markdown template structure in `references/profile-template.md`:

1. **Reader archetype** (heading)
2. **Your Ideal Story** - synthesized wish
3. **What You Love** - books with reasons
4. **What Doesn't Work** - books with reasons
5. **Your Boundaries** - deal-breakers, preferences, flexible items
6. **Your Reading Identity** - prose synthesis
7. **Themes You're Drawn To**
8. **What to Avoid** - anti-patterns for recommenders

### Critical Requirements

#### 1. Reasons for Every Book

**Every book mentioned must have a reason explaining WHY it worked or didn't work.**

- Ground reasons in the reader's actual words from the interview
- Quote or paraphrase their language
- Don't invent reasons they didn't give

Example:
```
### The Remains of the Day by Kazuo Ishiguro
You said you're "drawn to narratives where characters can't say what they mean" - Stevens' suppressed emotions and the tragedy of unexpressed love exemplify this perfectly. The restraint in Ishiguro's prose mirrors the emotional containment you find so compelling.
```

#### 2. Comparative Statements

Include 1-2 comparative statements in the "In shorthand" section.

Format: "More [Author/Style X] than [Author/Style Y]"

Examples:
- "More Sally Rooney than Thomas Pynchon"
- "More domestic psychological drama than epic fantasy"
- "More Toni Morrison than Stephen King"

These comparisons help calibrate recommendations quickly.

#### 3. Clear Boundary Separation

Distinguish between three levels of preferences:

**Deal-breakers** (will cause DNF):
- Hard stops that make them abandon a book
- Use their language: "I can't stand...", "I'll DNF if..."

**Strong preferences** (important but flexible):
- Significant but not absolute
- "I really prefer... but I've made exceptions"

**Flexible** (can go either way):
- They don't care or are open to either
- "Doesn't matter to me", "I'm fine with both"

#### 4. Ground Everything in Their Words

Throughout the profile:
- Reference specific phrases they used
- Echo their language back to them
- Use quotes when particularly distinctive
- Don't ascribe preferences they didn't express

Bad: "You enjoy complex narrative structures"
Good: "You mentioned being drawn to 'stories that fracture and reassemble' - non-linear structures that mirror the fragmentation you're interested in"

#### 5. Create a Memorable Reader Archetype

The archetype should:
- Be 2-3 words
- Capture their reading identity
- Feel prescient and insightful (the "wow" moment)
- Not be generic ("Book Lover") or pretentious
- Evoke their core relationship with literature

Examples:
- "Inner Dragon Slayer" - someone who reads to confront their demons
- "Quiet Storm Chaser" - drawn to subtle emotional intensity
- "Wound Excavator" - fascinated by trauma narratives
- "Fracture Dweller" - lives in narrative/psychological ruptures
- "Precision Seeker" - needs exactness in language and craft

### Generating the Profile

1. **Review the complete conversation transcript**
   - Read through all turns
   - Note their exact language
   - Identify patterns in what excites them

2. **Extract explicit preferences**
   - Books they loved/hated
   - Specific scenes or moments they mentioned
   - Themes they named
   - Deal-breakers they stated

3. **Synthesize their reading identity**
   - What hooks them?
   - What keeps them reading?
   - What makes them abandon a book?
   - How do they describe their ideal story?

4. **Craft the archetype**
   - Find the 2-3 words that capture their essence
   - Test: Would this feel insightful to them?
   - Avoid generic labels

5. **Write each section in their language**
   - Use their vocabulary
   - Reference their examples
   - Quote their distinctive phrases
   - Stay grounded in what they actually said

6. **Add comparative statements**
   - Who are they "more like" than others?
   - What calibrates their taste?

7. **Separate boundaries clearly**
   - What will make them DNF? (deal-breakers)
   - What do they prefer? (strong preferences)
   - What are they flexible on? (flexible)

8. **Write anti-patterns for recommenders**
   - What should NOT be recommended?
   - Why would it fail for this reader?
   - Be specific and actionable

9. **Output Markdown following the template**

### reader_archetype Guidelines

The archetype should be:
- Memorable and evocative (2-3 words)
- Capture their core reading identity
- Feel prescient - something they didn't know about themselves
- Not generic ("Book Lover") or pretentious
- Rooted in their actual preferences

Examples:
- "Fracture Dweller" - for someone drawn to psychological/narrative ruptures
- "Comfort Architect" - builds safe emotional spaces through reading
- "Precision Seeker" - needs exactness in craft and language
- "Mood Chaser" - led by emotional atmosphere
- "Wound Excavator" - fascinated by trauma narratives

### Conversation Transcript

{conversation}

---

**Output the profile in Markdown format following the template structure. Write in second person. Ground everything in their actual words.**
