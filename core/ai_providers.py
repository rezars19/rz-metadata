"""
RZ Automedata - AI Provider Module
Supports Groq and RZ Vision for metadata generation.
All providers use OpenAI-compatible chat completion API with vision.
"""

import requests
import json
import base64
import re
import time


# Words that should NEVER appear at the end of a title/description.
# These are articles, prepositions, conjunctions, and other "dangling" words.
_DANGLING_TAIL_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'nor', 'for', 'yet', 'so',
    'in', 'on', 'at', 'to', 'of', 'by', 'as', 'is', 'it', 'its',
    'with', 'from', 'into', 'that', 'this', 'than', 'then',
    'are', 'was', 'were', 'be', 'been', 'being',
    'has', 'have', 'had', 'do', 'does', 'did',
    'will', 'would', 'shall', 'should', 'may', 'might', 'can', 'could',
    'not', 'no', 'if', 'when', 'where', 'while', 'which', 'who',
    'their', 'our', 'your', 'his', 'her',
}


def _strip_dangling_tail(text):
    """Remove trailing articles/prepositions/conjunctions that make no sense at the end."""
    if not text:
        return text
    # Remove special characters that should NOT appear in microstock titles

    # Keep: hyphens (compound words), apostrophes (possessives)

    for ch in ['[', ']', '(', ')', '{', '}', ':', ';', '"', '“', '”', '«', '»', '„']:

        text = text.replace(ch, '')

    text = text.rstrip()
    while text:
        words = text.rsplit(None, 1)
        if len(words) < 2:
            break  # Single word left, keep it
        last_word = words[-1].rstrip('.,;:!?').lower()
        if last_word in _DANGLING_TAIL_WORDS:
            text = words[0].rstrip()
        else:
            break
    # Remove trailing punctuation (period, comma, semicolon, etc.)
    # Microstock titles/descriptions should NOT end with any punctuation
    text = text.rstrip('.,;:!? ')
    return text


def _truncate_to_complete_word(text, max_length):
    """Truncate text to max_length, ensuring it ends at a complete word boundary."""
    if not text or len(text) <= max_length:
        return _strip_dangling_tail(text)
    # Cut to max_length
    truncated = text[:max_length]
    # If the next character (beyond max_length) is a space or we're at a word boundary, we're fine
    if len(text) > max_length and text[max_length] == ' ':
        return _strip_dangling_tail(truncated.rstrip())
    # Otherwise, find the last space to avoid cutting mid-word
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return _strip_dangling_tail(truncated[:last_space].rstrip())
    return _strip_dangling_tail(truncated)  # Single long word, just cut


def _try_repair_truncated_json(text):
    """Attempt to repair a truncated JSON response from AI.
    
    When max_tokens cuts off the response mid-JSON, this tries to
    close any open strings and braces to make it parseable.
    Handles common truncation patterns like:
      {"title": "...", "keywords": "kw1, kw2, kw3, incompl
    """
    text = text.strip()
    if not text:
        return text
    
    # If it already parses, return as-is
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    
    # Try to repair: close open strings and braces
    repaired = text
    
    # Count unescaped quotes to see if a string is open
    in_string = False
    i = 0
    while i < len(repaired):
        c = repaired[i]
        if c == '\\' and in_string:
            i += 2  # skip escaped character
            continue
        if c == '"':
            in_string = not in_string
        i += 1
    
    # If we're inside an open string, close it
    if in_string:
        # Find the last opening quote (the one that started this value)
        last_quote = repaired.rfind('"')
        if last_quote >= 0:
            content_after_quote = repaired[last_quote + 1:]
            # Trim to last complete word (remove truncated fragment)
            last_comma = content_after_quote.rfind(',')
            last_space = content_after_quote.rfind(' ')
            # For keywords field: trim to last complete keyword (after comma)
            if last_comma > 0 and last_comma > last_space - 10:
                # Cut at last comma to keep complete keywords
                repaired = repaired[:last_quote + 1 + last_comma]
            elif last_space > 0:
                repaired = repaired[:last_quote + 1 + last_space]
            repaired += '"'
    
    # Close any open brackets
    open_brackets = repaired.count('[') - repaired.count(']')
    repaired += ']' * max(0, open_brackets)
    
    # Close any open braces
    open_braces = repaired.count('{') - repaired.count('}')
    repaired += '}' * max(0, open_braces)
    
    # Try to parse the repaired version
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass
    
    # Second attempt: more aggressive repair
    # Strip everything after the last properly closed key-value pair
    # Look for pattern like: "key": "value", or "key": number,
    match = re.search(r'(.*"\s*:\s*(?:"[^"]*"|\d+)\s*),?\s*"?[^}]*$', text, re.DOTALL)
    if match:
        repaired = match.group(1) + '}'
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            pass
    
    # Last resort: return original
    return text


# ─── Adobe Stock Categories ─────────────────────────────────────────────────────
ADOBE_STOCK_CATEGORIES = {
    1: "Animals",
    2: "Buildings and Architecture",
    3: "Business",
    4: "Drinks",
    5: "The Environment",
    6: "States of Mind",
    7: "Food",
    8: "Graphic Resources",
    9: "Hobbies and Leisure",
    10: "Industry",
    11: "Landscapes",
    12: "Lifestyle",
    13: "People",
    14: "Plants and Flowers",
    15: "Culture and Religion",
    16: "Science",
    17: "Social Issues",
    18: "Sports",
    19: "Technology",
    20: "Transport",
    21: "Travel"
}

CATEGORY_LIST_STR = "\n".join([f"{k}: {v}" for k, v in ADOBE_STOCK_CATEGORIES.items()])


# ─── Shutterstock Categories ─────────────────────────────────────────────────
SHUTTERSTOCK_CATEGORIES = [
    "Animals/Wildlife",
    "Backgrounds/Textures",
    "Buildings/Landmarks",
    "Business/Finance",
    "Education",
    "Food and Drink",
    "Medical",
    "Holidays",
    "Industrial",
    "Nature",
    "Objects",
    "People",
    "Religion",
    "Science",
    "Signs/Symbols",
    "Sports/Recreation",
    "Technology",
    "Transportation"
]

SHUTTERSTOCK_CATEGORY_LIST_STR = "\n".join([f"- {c}" for c in SHUTTERSTOCK_CATEGORIES])


# ─── Freepik AI Models ────────────────────────────────────────────────────────
FREEPIK_MODELS = [
    "Adobe Firefly", "Dall-e 1", "Dall-e 2", "Dall-e 3", "Flux 1.0", "Flux 1.0 Fast",
    "Flux 1.0 Realism", "Flux 1.1", "Flux Kontext [Max]", "Flux Kontext [Pro]", "Freepik Classic",
    "Freepik Classic Fast", "Freepik Flux", "Freepik Flux Fast", "Freepik Flux Realism",
    "Freepik Mystic 1.0", "Freepik Mystic 2.5", "Freepik Mystic 2.5 Flexible", "Freepik Mystic 2.5 Fluid",
    "Freepik Pikaso", "Google Imagen 3", "Google Imagen 4", "Google Imagen 4 Fast", "Google Imagen 4 Ultra",
    "Google Nano Banana", "GPT", "GPT 1 - HQ", "Ideogram 1.0", "Ideogram 3", "Leonardo", "Midjourney 1",
    "Midjourney 2", "Midjourney 3", "Midjourney 4", "Midjourney 5", "Midjourney 5.1", "Midjourney 5.2",
    "Midjourney 6", "niji", "Runway", "Seedream", "Stable Diffusion 1.4", "Stable Diffusion 1.5",
    "Stable Diffusion 2.0", "Stable Diffusion 2.1", "Stable Diffusion XL", "Wepik"
]


# ─── Provider Configurations ────────────────────────────────────────────────────
PROVIDERS = {
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "models": [
            "meta-llama/llama-4-scout-17b-16e-instruct"
        ]
    },
    "RZ Vision": {
        "base_url": "https://api.maiarouter.ai/v1/chat/completions",
        "models": [
            "maia/gemini-2.5-flash-lite",
            "maia/gemini-2.5-flash",
            "maia/gemini-2.0-flash",
            "maia/gemini-1.5-flash",
            "openai/gpt-4.1-nano",
            "openai/gpt-5-nano",
            "openai/gpt-4o-mini",
            "xai/grok-4-1-fast-reasoning-latest",
            "xai/grok-4-1-fast-non-reasoning-latest"
        ]
    }
}

# Display name mapping: model_id → clean UI name
_MODEL_DISPLAY_NAMES = {
    # Groq
    "meta-llama/llama-4-scout-17b-16e-instruct": "Llama 4 Scout 17B",
    # RZ Vision (Maia Router models)
    "maia/gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "maia/gemini-2.5-flash": "Gemini 2.5 Flash",
    "maia/gemini-2.0-flash": "Gemini 2.0 Flash",
    "maia/gemini-1.5-flash": "Gemini 1.5 Flash",
    "openai/gpt-4.1-nano": "GPT 4.1 Nano",
    "openai/gpt-5-nano": "GPT 5 Nano",
    "openai/gpt-4o-mini": "GPT 4o Mini",
    "xai/grok-4-1-fast-reasoning-latest": "Grok 4.1 Fast Reasoning",
    "xai/grok-4-1-fast-non-reasoning-latest": "Grok 4.1 Fast",
}

# Reverse mapping: display_name → model_id
_MODEL_ID_FROM_DISPLAY = {v: k for k, v in _MODEL_DISPLAY_NAMES.items()}


def get_provider_names():
    """Return list of provider names."""
    return list(PROVIDERS.keys())


def get_models_for_provider(provider_name):
    """Return list of display names for a given provider."""
    model_ids = PROVIDERS.get(provider_name, {}).get("models", [])
    return [_MODEL_DISPLAY_NAMES.get(m, m) for m in model_ids]


def get_model_id(display_name):
    """Convert a display name back to the actual model ID for API calls."""
    return _MODEL_ID_FROM_DISPLAY.get(display_name, display_name)


def _build_custom_instructions(custom_prompt, rule_num="5"):
    """Build custom prompt instructions if provided."""
    if not custom_prompt:
        return ""
    custom_keywords = [kw.strip() for kw in custom_prompt.split(",") if kw.strip()]
    if not custom_keywords:
        return ""
    kw_list_str = ", ".join(custom_keywords)
    return f"""

{rule_num}. **MANDATORY Custom Keywords** (CRITICAL - YOU MUST FOLLOW THIS):
   - The following keywords MUST appear in BOTH the description/title AND the keywords list: {kw_list_str}
   - For the DESCRIPTION/TITLE: Naturally incorporate ALL of these words/phrases. It must still read naturally and be coherent - do NOT just append them. Weave them seamlessly. Do NOT wrap them in brackets, quotes, or any special characters.
   - For the KEYWORDS: These custom keywords MUST be placed at the VERY BEGINNING of the keywords list (before any other keywords). Then fill the remaining spots with relevant keywords to reach 30-40 total.
   - This is NON-NEGOTIABLE. Every single custom keyword must appear in both description/title and keywords."""


def _build_brand_rules():
    """Build brand name restriction rules."""
    return """**ABSOLUTELY NO BRAND NAMES, TRADEMARKS, OR INTELLECTUAL PROPERTY** (CRITICAL - STRICTLY ENFORCED):
   - NEVER use ANY brand names, company names, or trademarks in the title/description or keywords. This includes but is not limited to:
     * Technology brands: Apple, iPhone, iPad, Samsung, Google, Microsoft, Windows, Android, Sony, Canon, Nikon, etc.
     * Fashion/Sports brands: Nike, Adidas, Gucci, Louis Vuitton, Puma, Reebok, Zara, H&M, etc.
     * Food/Drink brands: Coca-Cola, Pepsi, Starbucks, McDonald's, Nestle, etc.
     * Automotive brands: Tesla, BMW, Mercedes, Toyota, Ferrari, Lamborghini, etc.
     * Social media: Facebook, Instagram, TikTok, Twitter/X, YouTube, WhatsApp, Snapchat, etc.
     * ANY other recognizable brand or company name worldwide.
   - NEVER use copyrighted character names (Disney characters, Marvel/DC superheroes, anime characters, etc.).
   - NEVER use movie titles, TV show names, song titles, book titles, or game names.
   - NEVER mention logos, brand symbols, or trademarked slogans.
   - NEVER reference specific product model names (e.g., "Galaxy S24", "MacBook Pro", "Air Jordan").
   - INSTEAD, use GENERIC descriptive terms:
     * "smartphone" instead of "iPhone" or "Samsung Galaxy"
     * "athletic shoes" or "running shoes" instead of "Nike sneakers"
     * "luxury car" or "sports car" instead of "Ferrari" or "BMW"
     * "social media app" instead of "Instagram" or "TikTok"
     * "coffee shop" instead of "Starbucks"
     * "streaming service" instead of "Netflix"
     * "search engine" instead of "Google"
     * "laptop computer" instead of "MacBook"
     * "energy drink" instead of "Red Bull"
     * "fast food restaurant" instead of "McDonald's"
   - This rule applies even if the brand is clearly visible in the image. Describe the OBJECT, not the BRAND.
   - Violating this rule will cause the asset to be REJECTED. This is NON-NEGOTIABLE."""


def _build_category_rules():
    """Build category selection rules shared by both platforms."""
    return """**CATEGORY SELECTION RULES (CRITICAL - FOLLOW STRICTLY):**
   - Choose the category based on the PRIMARY/MAIN subject of the image, NOT secondary elements.
   - **Animals**: If the image features ANY animal as the main subject, ALWAYS use the Animals category. This includes:
     * Realistic animals, cartoon animals, illustrated animals, 3D rendered animals
     * Anthropomorphic animals (animals with human characteristics, wearing clothes, standing upright, talking)
     * Animal mascots, animal characters, cute animal illustrations
     * Even if the animal looks like a person or acts like a person, if it IS an animal → Animals
   - **People**: ONLY use this when the main subject is actual HUMAN beings (not animals dressed as humans)
   - **Plants/Flowers/Nature**: When flowers/plants are the PRIMARY subject (not just background decoration)
   - **Food**: When food items are the main subject
   - **Backgrounds/Textures/Graphic Resources**: For abstract patterns, textures, backgrounds, templates, icons, UI elements
   - Always ask yourself: "What is the MAIN THING in this image?" and categorize based on that answer"""


def _build_prompt(filename, file_type, custom_prompt="", title_min=70, title_max=120, kw_min=30, kw_max=40):
    """Build the system + user prompt for Adobe Stock metadata generation."""

    custom_instructions = _build_custom_instructions(custom_prompt)
    brand_rules = _build_brand_rules()
    category_rules = _build_category_rules()

    system_prompt = f"""You are a professional microstock metadata generator. Generate metadata optimized for Adobe Stock search ranking.

========================
TITLE RULES
========================

1. **Title** (CRITICAL — {title_min} to {title_max} characters):
   - The title MUST be between {title_min} and {title_max} characters. Count EVERY character including spaces.
   - **SELF-CHECK**: Before outputting, count your title's characters. If it exceeds {title_max}, REWRITE it shorter while keeping it natural and complete. NEVER submit a title longer than {title_max} characters.
   - Write the title as a natural, flowing English sentence.
   - **ENGLISH ONLY**: The title MUST be written entirely in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every single word must be a standard English word.
   - The title must read like a descriptive caption, NOT a list of keywords.
   - Describe the main subject, action, environment, and visual mood.
   - **TITLE-KEYWORD SYNERGY**: The most important keywords from your keyword list MUST appear naturally in the title. This gives a significant ranking boost on Adobe Stock.
   - Include high-value buyer search terms naturally when possible.
   - Avoid keyword stuffing or repetitive phrasing.
   - Do NOT use quotation marks, parentheses (), brackets [], braces {{}}, colons, semicolons, or any special symbols.
   - Hyphens (-) are ONLY allowed for standard compound words (e.g., close-up, high-quality, well-lit). Do NOT use hyphens as separators between phrases.
   - Apostrophes (') are ONLY allowed for grammatically correct possessives or contractions (e.g., woman's, it's, nature's). Avoid them if the sentence can be rephrased without.
   - The title must end with a complete word (never cut a word mid-way).
   - Do NOT end the title with a period (.) or any punctuation. The title is a descriptive phrase, NOT a sentence.
   - GOOD: "Futuristic cyberpunk city skyline glowing with neon lights and towering skyscrapers at night"
   - BAD: "Cyberpunk city neon future technology background"

========================
KEYWORD RULES
========================

2. Keywords (between {kw_min} and {kw_max} keywords, comma-separated)

GENERAL RULES
• Generate between {kw_min} and {kw_max} keywords. Choose the exact number based on how much relevant content the image contains.
• **ENGLISH ONLY**: ALL keywords MUST be in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every keyword must be a standard English word or phrase. This is CRITICAL — Adobe Stock will REJECT files with non-English keywords.
• Only include keywords that are TRULY RELEVANT to the image. Do NOT pad with generic filler keywords.
• Separate each keyword with a comma.
• Each keyword must contain 1–3 words.
• Every keyword must be unique and add new meaning.
• Avoid duplicate keywords or repeated phrases.
• Different phrases using the same root word are allowed if they add new meaning.
• Avoid brand names.
• Avoid camera or photography technical terms unless essential.
• Focus on terms real stock buyers would search for.

KEYWORD QUALITY OVER QUANTITY
• Only include keywords that are directly relevant to what is visible in the image.
• NEVER add irrelevant or loosely-related keywords just to increase the count.
• Let the content of the image naturally determine the keyword count within the {kw_min}-{kw_max} range.

KEYWORD ORDERING (CRITICAL FOR RANKING)
• **NEVER sort keywords alphabetically.** Adobe Stock will REJECT alphabetically ordered keywords. Keywords must be ordered strictly by RELEVANCE and IMPORTANCE, not by letter.
• Keywords are weighted by position — the FIRST keywords have the HIGHEST ranking impact.
• Place the most important, highest-search-volume keywords FIRST.
• The first 5 keywords should match what a buyer would type into the search bar.

KEYWORD STRUCTURE

First ~8 keywords: PRIMARY SUBJECT KEYWORDS (HIGHEST RANKING WEIGHT)
• These must describe the main subject and action.
• Use descriptive multi-word phrases.
• Avoid single-word generic keywords.
• These keywords should also appear in the title for maximum ranking boost.

Next ~10 keywords: DETAILED VISUAL DESCRIPTION
• Describe visible objects, colors, lighting, materials, environment, and actions.
• Prefer descriptive multi-word phrases.

Next ~8 keywords: CONTEXT, STYLE & CONCEPT
• Keywords about mood, genre, artistic style, concept, theme, and narrative context.
• Include EMOTIONAL/CONCEPTUAL keywords (e.g., "success concept", "peaceful atmosphere", "creative inspiration", "teamwork idea").
• These help buyers who search by feeling or concept rather than visual description.

Next ~5 keywords: BUYER USE-CASE KEYWORDS
• Keywords describing HOW buyers might use this image.
• Examples: "website banner", "social media post", "presentation background", "marketing material", "blog header", "commercial use", "digital wallpaper", "print design".
• Only include use-cases that genuinely fit this image.

Remaining keywords: BROADER GENERAL KEYWORDS
• More general discoverability terms.
• Single-word keywords are allowed here.

SEARCH INTENT LAYERING

Ensure the keyword list covers different buyer search intents:

• SUBJECT SEARCH — keywords describing the main subject or object.
• SCENE / ENVIRONMENT SEARCH — keywords describing the location, setting, or environment.
• STYLE / VISUAL SEARCH — keywords describing lighting, mood, visual style, or artistic look.
• CONCEPT / EMOTION SEARCH — keywords describing themes, story, emotion, or narrative meaning.
• USE-CASE SEARCH — keywords describing what the buyer would use this image for.

Distribute these intents naturally across the keywords to improve search discoverability.

STRICT REQUIREMENTS
• The first 15 keywords MUST be descriptive multi-word phrases.
• Do NOT begin the list with generic single-word keywords.
• If the first 8 keywords contain generic single words, regenerate the list.
• MINIMUM {kw_min} keywords, MAXIMUM {kw_max} keywords.
• AVOID over-generic single keywords like "background", "design", "illustration", "image" alone — instead use specific phrases like "minimalist gradient background", "flat design icon", "digital illustration style".

   **KEYWORD STRATEGY:**
   - Prioritize keywords real buyers search for on stock marketplaces.
   - Prefer concrete nouns over vague adjectives.
   - Only include keywords that someone would realistically search for to find THIS specific image.
   - Include 2-3 emotional/conceptual keywords that describe the mood or feeling.
   - Include 2-3 use-case keywords that describe potential buyer usage.
   - Maintain approximately 70%% specific descriptive keywords, 15%% conceptual/emotional, and 15%% use-case/broader keywords.

3. **Category** (choose ONE number from the list below that BEST matches the PRIMARY subject of the image):
{CATEGORY_LIST_STR}

   {category_rules}

4. {brand_rules}
{custom_instructions}

RESPOND WITH ONLY valid JSON in this exact format, no other text:
{{"title": "Your {title_min}-{title_max} character descriptive title here", "keywords": "keyword1, keyword2, keyword three, keyword4, ...({kw_min}-{kw_max} total)", "category": 13}}"""

    custom_reminder = ""
    if custom_prompt:
        custom_reminder = f" IMPORTANT: You MUST include these custom keywords in both title and at the beginning of keywords: {custom_prompt}. Do NOT use brackets or quotes around them."

    brand_reminder = " CRITICAL REMINDER: Do NOT use any brand names, trademarks, copyrighted names, or intellectual property in the title or keywords. Use only generic descriptive terms."

    if file_type == "video":
        user_text = f"Analyze these video frames from the file '{filename}'. The frames are sequential snapshots from the video. Describe the overall video content and generate metadata based on ALL frames combined. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords, and pick the most accurate category.{custom_reminder}{brand_reminder}"
    elif file_type == "vector":
        user_text = f"Analyze this vector graphic file '{filename}'. The image provided is either a rasterized version of the vector or a descriptive summary of its contents. Use the filename as a strong hint about the subject matter. Generate Adobe Stock metadata for this vector illustration. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords, and pick the most accurate category.{custom_reminder}{brand_reminder}"
    else:
        user_text = f"Analyze this image file '{filename}' and generate Adobe Stock metadata. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords, and pick the most accurate category.{custom_reminder}{brand_reminder}"

    return system_prompt, user_text


def _build_shutterstock_prompt(filename, file_type, custom_prompt="", title_min=120, title_max=200, kw_min=30, kw_max=40):
    """Build the system + user prompt for Shutterstock metadata generation."""

    custom_instructions = _build_custom_instructions(custom_prompt)
    brand_rules = _build_brand_rules()
    category_rules = _build_category_rules()

    system_prompt = f"""You are a professional microstock metadata generator. Generate metadata optimized for Shutterstock search ranking.

========================
DESCRIPTION RULES
========================

1. **Description** (CRITICAL — {title_min} to {title_max} characters):
   - The description MUST be between {title_min} and {title_max} characters. Count EVERY character including spaces.
   - **SELF-CHECK**: Before outputting, count your description's characters. If it exceeds {title_max}, REWRITE it shorter while keeping it natural and complete. NEVER submit a description longer than {title_max} characters.
   - Write as a natural, flowing English sentence.
   - **ENGLISH ONLY**: The description MUST be written entirely in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every single word must be a standard English word.
   - Describe the main subject, action, environment, and visual mood.
   - **DESCRIPTION-KEYWORD SYNERGY**: The most important keywords from your keyword list MUST appear naturally in the description. Shutterstock uses both description and keywords for search ranking.
   - Include high-value buyer search terms naturally when possible.
   - Avoid keyword stuffing or repetitive phrasing.
   - Do NOT use quotation marks, parentheses (), brackets [], braces {{}}, colons, semicolons, or any special symbols.
   - Hyphens (-) are ONLY allowed for standard compound words (e.g., close-up, high-quality, well-lit). Do NOT use hyphens as separators between phrases.
   - Apostrophes (') are ONLY allowed for grammatically correct possessives or contractions (e.g., woman's, it's, nature's). Avoid them if the sentence can be rephrased without.
   - Do NOT use line breaks. Write in a single sentence or two short sentences.
   - The description must end with a complete word (never cut mid-word).
   - Do NOT end the description with a period (.) or any punctuation. The description is a descriptive phrase, NOT a sentence.
   - GOOD: "A stunning futuristic cyberpunk city skyline glowing with vibrant neon lights at night with towering skyscrapers reflecting on rain-soaked streets"
   - BAD: "Cyberpunk city neon future technology background urban night skyline building"

========================
KEYWORD RULES
========================

2. Keywords (between {kw_min} and {kw_max} keywords, comma-separated)

GENERAL RULES
• Generate between {kw_min} and {kw_max} keywords. Choose the exact number based on how much relevant content the image contains.
• **ENGLISH ONLY**: ALL keywords MUST be in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every keyword must be a standard English word or phrase.
• Only include keywords that are TRULY RELEVANT to the image. Do NOT pad with generic filler keywords.
• Separate each keyword with a comma.
• Each keyword must contain 1–3 words.
• Every keyword must be unique and add new meaning.
• Avoid duplicate keywords or repeated phrases.
• Different phrases using the same root word are allowed if they add new meaning.
• Avoid brand names.
• Avoid camera or photography technical terms unless essential.
• Focus on terms real stock buyers would search for.

KEYWORD QUALITY OVER QUANTITY
• Only include keywords that are directly relevant to what is visible in the image.
• NEVER add irrelevant or loosely-related keywords just to increase the count.
• Let the content of the image naturally determine the keyword count within the {kw_min}-{kw_max} range.

KEYWORD ORDERING (CRITICAL FOR RANKING)
• **NEVER sort keywords alphabetically.** Keywords must be ordered strictly by RELEVANCE and IMPORTANCE, not by letter.
• Keywords are weighted by position — the FIRST keywords have the HIGHEST ranking impact.
• Place the most important, highest-search-volume keywords FIRST.
• The first 5 keywords should match what a buyer would type into the search bar.

KEYWORD STRUCTURE

First ~8 keywords: PRIMARY SUBJECT KEYWORDS (HIGHEST RANKING WEIGHT)
• These must describe the main subject and action.
• Use descriptive multi-word phrases.
• Avoid single-word generic keywords.
• These keywords should also appear in the description for maximum ranking boost.

Next ~10 keywords: DETAILED VISUAL DESCRIPTION
• Describe visible objects, colors, lighting, materials, environment, and actions.
• Prefer descriptive multi-word phrases.

Next ~8 keywords: CONTEXT, STYLE & CONCEPT
• Keywords about mood, genre, artistic style, concept, theme, and narrative context.
• Include EMOTIONAL/CONCEPTUAL keywords (e.g., "success concept", "peaceful atmosphere", "creative inspiration", "teamwork idea").
• These help buyers who search by feeling or concept rather than visual description.

Next ~5 keywords: BUYER USE-CASE KEYWORDS
• Keywords describing HOW buyers might use this image.
• Examples: "website banner", "social media post", "presentation background", "marketing material", "blog header", "commercial use", "digital wallpaper", "print design".
• Only include use-cases that genuinely fit this image.

Remaining keywords: BROADER GENERAL KEYWORDS
• More general discoverability terms.
• Single-word keywords are allowed here.

SEARCH INTENT LAYERING

Ensure the keyword list covers different buyer search intents:

• SUBJECT SEARCH — keywords describing the main subject or object.
• SCENE / ENVIRONMENT SEARCH — keywords describing the location, setting, or environment.
• STYLE / VISUAL SEARCH — keywords describing lighting, mood, visual style, or artistic look.
• CONCEPT / EMOTION SEARCH — keywords describing themes, story, emotion, or narrative meaning.
• USE-CASE SEARCH — keywords describing what the buyer would use this image for.

Distribute these intents naturally across the keywords to improve search discoverability.

STRICT REQUIREMENTS
• The first 15 keywords MUST be descriptive multi-word phrases.
• Do NOT begin the list with generic single-word keywords.
• If the first 8 keywords contain generic single words, regenerate the list.
• MINIMUM {kw_min} keywords, MAXIMUM {kw_max} keywords.
• AVOID over-generic single keywords like "background", "design", "illustration", "image" alone — instead use specific phrases like "minimalist gradient background", "flat design icon", "digital illustration style".

   **KEYWORD STRATEGY:**
   - Prioritize keywords real buyers search for on stock marketplaces.
   - Prefer concrete nouns over vague adjectives.
   - Only include keywords that someone would realistically search for to find THIS specific image.
   - Include 2-3 emotional/conceptual keywords that describe the mood or feeling.
   - Include 2-3 use-case keywords that describe potential buyer usage.
   - Maintain approximately 70%% specific descriptive keywords, 15%% conceptual/emotional, and 15%% use-case/broader keywords.

3. **Categories** (choose TWO categories from the list below):
   - category1: The PRIMARY/MAIN category that BEST matches the image content
   - category2: A SECONDARY category that also relates to the image content
   Available categories:
{SHUTTERSTOCK_CATEGORY_LIST_STR}

   {category_rules}

4. {brand_rules}
{custom_instructions}

RESPOND WITH ONLY valid JSON in this exact format, no other text:
{{"description": "Your {title_min}-{title_max} character descriptive description here", "keywords": "keyword1, keyword2, keyword three, keyword4, ...({kw_min}-{kw_max} total)", "category1": "Animals/Wildlife", "category2": "Nature"}}"""

    custom_reminder = ""
    if custom_prompt:
        custom_reminder = f" IMPORTANT: You MUST include these custom keywords in both description and at the beginning of keywords: {custom_prompt}. Do NOT use brackets or quotes around them."

    brand_reminder = " CRITICAL REMINDER: Do NOT use any brand names, trademarks, copyrighted names, or intellectual property in the description or keywords. Use only generic descriptive terms."

    if file_type == "video":
        user_text = f"Analyze these video frames from the file '{filename}'. The frames are sequential snapshots from the video. Describe the overall video content and generate metadata based on ALL frames combined. Remember: description MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance, and pick the 2 most accurate categories.{custom_reminder}{brand_reminder}"
    elif file_type == "vector":
        user_text = f"Analyze this vector graphic file '{filename}'. The image provided is either a rasterized version of the vector or a descriptive summary of its contents. Use the filename as a strong hint about the subject matter. Generate Shutterstock metadata for this vector illustration. Remember: description MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance, and pick the 2 most accurate categories.{custom_reminder}{brand_reminder}"
    else:
        user_text = f"Analyze this image file '{filename}' and generate Shutterstock metadata. Remember: description MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance, and pick the 2 most accurate categories.{custom_reminder}{brand_reminder}"

    return system_prompt, user_text


def _build_freepik_prompt(filename, file_type, custom_prompt="", ai_generated=False, title_min=70, title_max=100, kw_min=30, kw_max=40):
    """Build the system + user prompt for Freepik metadata generation."""

    custom_instructions = _build_custom_instructions(custom_prompt)
    brand_rules = _build_brand_rules()

    prompt_section = ""
    prompt_json_field = ""
    if ai_generated:
        prompt_section = """3. **Prompt** (the AI generation prompt that would recreate this image):
   - Write a detailed, descriptive prompt that an AI image generator would use to create this exact image.
   - Include style, composition, colors, mood, lighting, and specific details.
   - Write in English, natural language.
   - Be specific enough that an AI model could recreate a very similar image.
   - NEVER start the prompt with "Create", "Generate", "Design", "Make", "Produce", "Draw", or "Render".
   - Start DIRECTLY with the subject description. Example: "A sleek modern brown glass bottle on a beige surface" NOT "Create an image of a brown glass bottle".

4. """
        prompt_json_field = ', "prompt": "A sleek modern brown glass bottle on a beige surface with soft lighting"'
    else:
        prompt_section = "3. "
        prompt_json_field = ""

    system_prompt = f"""You are a professional microstock metadata generator. Generate metadata optimized for Freepik search ranking.

========================
TITLE RULES
========================

1. **Title** (CRITICAL — {title_min} to {title_max} characters):
   - The title MUST be between {title_min} and {title_max} characters. Count EVERY character including spaces.
   - **SELF-CHECK**: Before outputting, count your title's characters. If it exceeds {title_max}, REWRITE it shorter while keeping it natural and complete. NEVER submit a title longer than {title_max} characters.
   - Write the title as a natural, flowing English sentence.
   - **ENGLISH ONLY**: The title MUST be written entirely in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every single word must be a standard English word.
   - The title must read like a descriptive caption, NOT a list of keywords.
   - Describe the main subject, action, environment, and visual mood.
   - **TITLE-KEYWORD SYNERGY**: The most important keywords from your keyword list MUST appear naturally in the title. Freepik uses the title heavily for search ranking.
   - Include high-value buyer search terms naturally when possible.
   - Avoid keyword stuffing or repetitive phrasing.
   - Do NOT use quotation marks, parentheses (), brackets [], braces {{}}, colons, semicolons, or any special symbols.
   - Hyphens (-) are ONLY allowed for standard compound words (e.g., close-up, high-quality, well-lit). Do NOT use hyphens as separators between phrases.
   - Apostrophes (') are ONLY allowed for grammatically correct possessives or contractions (e.g., woman's, it's, nature's). Avoid them if the sentence can be rephrased without.
   - The title must end with a complete word (never cut a word mid-way).
   - Do NOT end the title with a period (.) or any punctuation. The title is a descriptive phrase, NOT a sentence.
   - GOOD: "Futuristic cyberpunk city skyline glowing with neon lights and towering skyscrapers at night"
   - BAD: "Cyberpunk city neon future technology background"

========================
KEYWORD RULES
========================

2.  Keywords (between {kw_min} and {kw_max} keywords, comma-separated)

GENERAL RULES
• Generate between {kw_min} and {kw_max} keywords. Choose the exact number based on how much relevant content the image contains.
• **ENGLISH ONLY**: ALL keywords MUST be in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every keyword must be a standard English word or phrase.
• Only include keywords that are TRULY RELEVANT to the image. Do NOT pad with generic filler keywords.
• Separate each keyword with a comma.
• Each keyword must contain 1–3 words.
• Every keyword must be unique and add new meaning.
• Avoid duplicate keywords or repeated phrases.
• Different phrases using the same root word are allowed if they add new meaning.
• Avoid brand names.
• Avoid camera or photography technical terms unless essential.
• Focus on terms real stock buyers would search for.

KEYWORD QUALITY OVER QUANTITY
• Only include keywords that are directly relevant to what is visible in the image.
• NEVER add irrelevant or loosely-related keywords just to increase the count.
• Let the content of the image naturally determine the keyword count within the {kw_min}-{kw_max} range.

KEYWORD ORDERING (CRITICAL FOR RANKING)
• **NEVER sort keywords alphabetically.** Keywords must be ordered strictly by RELEVANCE and IMPORTANCE, not by letter.
• Keywords are weighted by position — the FIRST keywords have the HIGHEST ranking impact.
• Place the most important, highest-search-volume keywords FIRST.
• The first 5 keywords should match what a buyer would type into the search bar.

KEYWORD STRUCTURE

First ~8 keywords: PRIMARY SUBJECT KEYWORDS (HIGHEST RANKING WEIGHT)
• These must describe the main subject and action.
• Use descriptive multi-word phrases.
• Avoid single-word generic keywords.
• These keywords should also appear in the title for maximum ranking boost.

Next ~10 keywords: DETAILED VISUAL DESCRIPTION
• Describe visible objects, colors, lighting, materials, environment, and actions.
• Prefer descriptive multi-word phrases.

Next ~8 keywords: CONTEXT, STYLE & CONCEPT
• Keywords about mood, genre, artistic style, concept, theme, and narrative context.
• Include EMOTIONAL/CONCEPTUAL keywords (e.g., "success concept", "peaceful atmosphere", "creative inspiration", "teamwork idea").
• These help buyers who search by feeling or concept rather than visual description.

Next ~5 keywords: BUYER USE-CASE KEYWORDS
• Keywords describing HOW buyers might use this image.
• Examples: "website banner", "social media post", "presentation background", "marketing material", "blog header", "commercial use", "digital wallpaper", "print design".
• Only include use-cases that genuinely fit this image.

Remaining keywords: BROADER GENERAL KEYWORDS
• More general discoverability terms.
• Single-word keywords are allowed here.

SEARCH INTENT LAYERING

Ensure the keyword list covers different buyer search intents:

• SUBJECT SEARCH — keywords describing the main subject or object.
• SCENE / ENVIRONMENT SEARCH — keywords describing the location, setting, or environment.
• STYLE / VISUAL SEARCH — keywords describing lighting, mood, visual style, or artistic look.
• CONCEPT / EMOTION SEARCH — keywords describing themes, story, emotion, or narrative meaning.
• USE-CASE SEARCH — keywords describing what the buyer would use this image for.

Distribute these intents naturally across the keywords to improve search discoverability.

STRICT REQUIREMENTS
• The first 15 keywords MUST be descriptive multi-word phrases.
• Do NOT begin the list with generic single-word keywords.
• If the first 8 keywords contain generic single words, regenerate the list.
• MINIMUM {kw_min} keywords, MAXIMUM {kw_max} keywords.
• AVOID over-generic single keywords like "background", "design", "illustration", "image" alone — instead use specific phrases like "minimalist gradient background", "flat design icon", "digital illustration style".

   **KEYWORD STRATEGY:**
   - Prioritize keywords real buyers search for on stock marketplaces.
   - Prefer concrete nouns over vague adjectives.
   - Only include keywords that someone would realistically search for to find THIS specific image.
   - Include 2-3 emotional/conceptual keywords that describe the mood or feeling.
   - Include 2-3 use-case keywords that describe potential buyer usage.
   - Maintain approximately 70%% specific descriptive keywords, 15%% conceptual/emotional, and 15%% use-case/broader keywords.

{prompt_section}{brand_rules}
{custom_instructions}

RESPOND WITH ONLY valid JSON in this exact format, no other text:
{{"title": "Your {title_min}-{title_max} character descriptive title here", "keywords": "keyword1, keyword2, keyword three, ...({kw_min}-{kw_max} total)"{prompt_json_field}}}"""

    custom_reminder = ""
    if custom_prompt:
        custom_reminder = f" IMPORTANT: You MUST include these custom keywords in both title and at the beginning of keywords: {custom_prompt}. Do NOT use brackets or quotes around them."

    brand_reminder = " CRITICAL REMINDER: Do NOT use any brand names, trademarks, copyrighted names, or intellectual property in the title or keywords. Use only generic descriptive terms."

    if file_type == "video":
        user_text = f"Analyze these video frames from the file '{filename}'. Generate Freepik metadata. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"
    elif file_type == "vector":
        user_text = f"Analyze this vector graphic file '{filename}'. Generate Freepik metadata for this vector. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"
    else:
        user_text = f"Analyze this image file '{filename}' and generate Freepik metadata. Remember: title MUST be {title_min}-{title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"

    return system_prompt, user_text


def _build_vecteezy_prompt(filename, file_type, custom_prompt="", title_min=150, title_max=200, kw_min=30, kw_max=40):
    """Build the system + user prompt for Vecteezy metadata generation."""

    custom_instructions = _build_custom_instructions(custom_prompt)
    brand_rules = _build_brand_rules()

    system_prompt = f"""You are a professional microstock metadata generator. Generate metadata optimized for Vecteezy search ranking.

========================
TITLE RULES
========================

1. **Title** (CRITICAL — maximum {title_max} characters, aim for {title_min}+):
   - Count EVERY character including spaces. NEVER exceed {title_max} characters.
   - **SELF-CHECK**: Before outputting, count your title's characters. If it exceeds {title_max}, REWRITE it shorter while keeping it natural and complete.
   - Write the title as a natural, flowing English sentence.
   - **ENGLISH ONLY**: The title MUST be written entirely in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every single word must be a standard English word.
   - The title must read like a descriptive caption, NOT a list of keywords.
   - Describe the main subject, action, environment, and visual mood.
   - **TITLE-KEYWORD SYNERGY**: The most important keywords from your keyword list MUST appear naturally in the title. Vecteezy uses the title for search ranking.
   - Include high-value buyer search terms naturally when possible.
   - Avoid keyword stuffing or repetitive phrasing.
   - Do NOT use quotation marks, parentheses (), brackets [], braces {{}}, colons, semicolons, hyphens (-), apostrophes ('), or any special symbols.
   - **NO HYPHENS**: Use spaces instead. Write "close up" not "close-up", "high quality" not "high-quality".
   - **NO APOSTROPHES**: Rephrase without them. Write "womans hand" not "woman's hand", "natures beauty" not "nature's beauty".
   - **ABSOLUTELY NO COMMAS in the title.** Use spaces and conjunctions instead. This is critical for CSV formatting.
   - The title must end with a complete word (never cut a word mid-way).
   - Do NOT end the title with a period (.) or any punctuation. The title is a descriptive phrase, NOT a sentence.
   - GOOD: "Futuristic cyberpunk city skyline glowing with neon lights at night reflecting on wet urban streets"
   - BAD: "Cyberpunk city neon future technology background urban night"

========================
KEYWORD RULES
========================

2.  Keywords (between {kw_min} and {kw_max} keywords, comma-separated)

GENERAL RULES
• Generate between {kw_min} and {kw_max} keywords. Choose the exact number based on how much relevant content the image contains.
• **ENGLISH ONLY**: ALL keywords MUST be in English. Do NOT use any foreign language words, Latin phrases, romanized Japanese/Chinese/Korean words, or any non-English terms. Every keyword must be a standard English word or phrase.
• Only include keywords that are TRULY RELEVANT to the image. Do NOT pad with generic filler keywords.
• Separate each keyword with a comma.
• Each keyword must contain 1–3 words.
• Every keyword must be unique and add new meaning.
• Avoid duplicate keywords or repeated phrases.
• Different phrases using the same root word are allowed if they add new meaning.
• Avoid brand names.
• Avoid camera or photography technical terms unless essential.
• Focus on terms real stock buyers would search for.

KEYWORD QUALITY OVER QUANTITY
• Only include keywords that are directly relevant to what is visible in the image.
• NEVER add irrelevant or loosely-related keywords just to increase the count.
• Let the content of the image naturally determine the keyword count within the {kw_min}-{kw_max} range.

KEYWORD ORDERING (CRITICAL FOR RANKING)
• **NEVER sort keywords alphabetically.** Keywords must be ordered strictly by RELEVANCE and IMPORTANCE, not by letter.
• Keywords are weighted by position — the FIRST keywords have the HIGHEST ranking impact.
• Place the most important, highest-search-volume keywords FIRST.
• The first 5 keywords should match what a buyer would type into the search bar.

KEYWORD STRUCTURE

First ~8 keywords: PRIMARY SUBJECT KEYWORDS (HIGHEST RANKING WEIGHT)
• These must describe the main subject and action.
• Use descriptive multi-word phrases.
• Avoid single-word generic keywords.
• These keywords should also appear in the title for maximum ranking boost.

Next ~10 keywords: DETAILED VISUAL DESCRIPTION
• Describe visible objects, colors, lighting, materials, environment, and actions.
• Prefer descriptive multi-word phrases.

Next ~8 keywords: CONTEXT, STYLE & CONCEPT
• Keywords about mood, genre, artistic style, concept, theme, and narrative context.
• Include EMOTIONAL/CONCEPTUAL keywords (e.g., "success concept", "peaceful atmosphere", "creative inspiration", "teamwork idea").
• These help buyers who search by feeling or concept rather than visual description.

Next ~5 keywords: BUYER USE-CASE KEYWORDS
• Keywords describing HOW buyers might use this image.
• Examples: "website banner", "social media post", "presentation background", "marketing material", "blog header", "commercial use", "digital wallpaper", "print design".
• Only include use-cases that genuinely fit this image.

Remaining keywords: BROADER GENERAL KEYWORDS
• More general discoverability terms.
• Single-word keywords are allowed here.

SEARCH INTENT LAYERING

Ensure the keyword list covers different buyer search intents:

• SUBJECT SEARCH — keywords describing the main subject or object.
• SCENE / ENVIRONMENT SEARCH — keywords describing the location, setting, or environment.
• STYLE / VISUAL SEARCH — keywords describing lighting, mood, visual style, or artistic look.
• CONCEPT / EMOTION SEARCH — keywords describing themes, story, emotion, or narrative meaning.
• USE-CASE SEARCH — keywords describing what the buyer would use this image for.

Distribute these intents naturally across the keywords to improve search discoverability.

STRICT REQUIREMENTS
• The first 15 keywords MUST be descriptive multi-word phrases.
• Do NOT begin the list with generic single-word keywords.
• If the first 8 keywords contain generic single words, regenerate the list.
• MINIMUM {kw_min} keywords, MAXIMUM {kw_max} keywords.
• **NO SPECIAL CHARACTERS IN KEYWORDS**: Keywords must contain ONLY letters and spaces. Do NOT use hyphens (-), apostrophes ('), quotation marks, parentheses, brackets, or any other punctuation/symbols inside keywords. Use "close up" instead of "close-up", "womans hand" instead of "woman's hand".
• AVOID over-generic single keywords like "background", "design", "illustration", "image" alone — instead use specific phrases like "minimalist gradient background", "flat design icon", "digital illustration style".

   **KEYWORD STRATEGY:**
   - Prioritize keywords real buyers search for on stock marketplaces.
   - Prefer concrete nouns over vague adjectives.
   - Only include keywords that someone would realistically search for to find THIS specific image.
   - Include 2-3 emotional/conceptual keywords that describe the mood or feeling.
   - Include 2-3 use-case keywords that describe potential buyer usage.
   - Maintain approximately 70%% specific descriptive keywords, 15%% conceptual/emotional, and 15%% use-case/broader keywords.

3. {brand_rules}
{custom_instructions}

RESPOND WITH ONLY valid JSON in this exact format, no other text:
{{"title": "Your descriptive title here (max {title_max} chars)", "keywords": "keyword1, keyword2, keyword three, ...({kw_min}-{kw_max} total)"}}"""

    custom_reminder = ""
    if custom_prompt:
        custom_reminder = f" IMPORTANT: You MUST include these custom keywords in both title and at the beginning of keywords: {custom_prompt}. Do NOT use brackets or quotes around them."

    brand_reminder = " CRITICAL REMINDER: Do NOT use any brand names, trademarks, copyrighted names, or intellectual property in the title or keywords. Use only generic descriptive terms."

    if file_type == "video":
        user_text = f"Analyze these video frames from the file '{filename}'. Generate Vecteezy metadata. Remember: title max {title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"
    elif file_type == "vector":
        user_text = f"Analyze this vector graphic file '{filename}'. Generate Vecteezy metadata for this vector. Remember: title max {title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"
    else:
        user_text = f"Analyze this image file '{filename}' and generate Vecteezy metadata. Remember: title max {title_max} characters, {kw_min}-{kw_max} relevant keywords ranked by importance.{custom_reminder}{brand_reminder}"

    return system_prompt, user_text


def _encode_image_to_base64(image_pil):
    """Convert a PIL Image to base64 string."""
    import io
    buffer = io.BytesIO()
    image_pil.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def _build_messages(images_base64, filename, file_type, custom_prompt="", platform="adobestock", ai_generated=False, title_min=70, title_max=120, kw_min=30, kw_max=40):
    """Build the messages array for the API call."""
    if platform == "freepik":
        system_prompt, user_text = _build_freepik_prompt(filename, file_type, custom_prompt, ai_generated=ai_generated, title_min=title_min, title_max=title_max, kw_min=kw_min, kw_max=kw_max)
    elif platform == "vecteezy":
        system_prompt, user_text = _build_vecteezy_prompt(filename, file_type, custom_prompt, title_min=title_min, title_max=title_max, kw_min=kw_min, kw_max=kw_max)
    elif platform == "shutterstock":
        system_prompt, user_text = _build_shutterstock_prompt(filename, file_type, custom_prompt, title_min=title_min, title_max=title_max, kw_min=kw_min, kw_max=kw_max)
    else:
        system_prompt, user_text = _build_prompt(filename, file_type, custom_prompt, title_min=title_min, title_max=title_max, kw_min=kw_min, kw_max=kw_max)

    content = [{"type": "text", "text": user_text}]
    for img_b64 in images_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{img_b64}"
            }
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content}
    ]
    return messages


def _parse_response(response_text, custom_prompt="", platform="adobestock", title_max=120, kw_max=40):
    """Parse JSON from the AI response, handling markdown code blocks."""
    text = response_text.strip()

    # Try to extract JSON from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    # Try to find JSON object - use greedy match to get the full object
    # First try to find a complete JSON object with balanced braces
    json_obj_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_obj_match:
        text = json_obj_match.group(0)
    else:
        # If no closing brace found, the response might be truncated
        # Try to find at least an opening brace
        json_start = text.find('{')
        if json_start >= 0:
            text = text[json_start:]

    # Attempt to repair truncated JSON before parsing
    text = _try_repair_truncated_json(text)

    try:
        data = json.loads(text)

        # ── Parse keywords (shared by all platforms) ────────────────────
        keywords_raw = str(data.get("keywords", "")).strip()
        # Split carefully: keywords may contain commas inside phrases
        kw_list = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]

        # Enforce custom keywords at the beginning of keywords list
        if custom_prompt:
            custom_keywords = [kw.strip() for kw in custom_prompt.split(",") if kw.strip()]
            custom_lower = [ck.lower() for ck in custom_keywords]
            kw_list = [kw for kw in kw_list if kw.lower() not in custom_lower]
            kw_list = custom_keywords + kw_list

        # Remove empty / whitespace-only entries that may inflate the count
        kw_list = [kw for kw in kw_list if kw.strip()]

        # ── Remove duplicate keywords (case-insensitive) ────────────────
        seen = set()
        unique_kw_list = []
        for kw in kw_list:
            kw_lower = kw.strip().lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_kw_list.append(kw)
        kw_list = unique_kw_list

        # Ensure maximum keywords (trim excess)
        if len(kw_list) > kw_max:
            kw_list = kw_list[:kw_max]

        # Reconstruct keywords as a clean comma-separated string
        keywords = ", ".join(kw_list)

        if platform == "freepik":
            title = str(data.get("title", "")).strip()
            # Clean up title (remove trailing punctuation and dangling words)
            title = _strip_dangling_tail(title)
            # Safety net: Freepik hard limit is 100 chars
            if len(title) > 100:
                title = _truncate_to_complete_word(title, 100)
                title = _strip_dangling_tail(title)
            prompt = str(data.get("prompt", "")).strip()

            # Strip "Create/Generate/Design..." prefixes from prompt
            prompt = re.sub(
                r'^(Create|Generate|Design|Make|Produce|Draw|Render)\s+(an?\s+)?(image|picture|photo|illustration|graphic|artwork|scene|visual|vector|design)?\s*(of|showing|depicting|featuring|with)?\s*',
                '', prompt, count=1, flags=re.IGNORECASE
            ).strip()
            # Capitalize the first letter after stripping
            if prompt:
                prompt = prompt[0].upper() + prompt[1:]

            return {
                "title": title,
                "keywords": keywords,
                "category": "",
                "prompt": prompt
            }
        elif platform == "vecteezy":
            title = str(data.get("title", "")).strip()
            # Clean up title (remove trailing punctuation and dangling words)
            title = _strip_dangling_tail(title)
            # Vecteezy-specific: NO hyphens or apostrophes in title
            title = title.replace('-', ' ').replace("'", '').replace("\u2019", '')
            # Clean up double spaces from hyphen replacement
            while '  ' in title:
                title = title.replace('  ', ' ')
            title = title.strip()
            # Safety net: Vecteezy hard limit is 200 chars
            if len(title) > 200:
                title = _truncate_to_complete_word(title, 200)
                title = _strip_dangling_tail(title)

            # Vecteezy-specific: NO hyphens or apostrophes in keywords
            kw_list_clean = []
            for kw in keywords.split(", "):
                kw = kw.replace('-', ' ').replace("'", '').replace("\u2019", '')
                while '  ' in kw:
                    kw = kw.replace('  ', ' ')
                kw_list_clean.append(kw.strip())
            keywords = ", ".join([kw for kw in kw_list_clean if kw])

            return {
                "title": title,
                "keywords": keywords,
                "category": ""
            }
        elif platform == "shutterstock":
            description = str(data.get("description", "")).strip()
            # Clean up description (remove trailing punctuation and dangling words)
            description = _strip_dangling_tail(description)
            # Safety net: Shutterstock hard limit is 200 chars
            if len(description) > 200:
                description = _truncate_to_complete_word(description, 200)
                description = _strip_dangling_tail(description)

            category1 = str(data.get("category1", "")).strip()
            category2 = str(data.get("category2", "")).strip()

            # Validate categories against Shutterstock list
            if category1 not in SHUTTERSTOCK_CATEGORIES:
                category1 = SHUTTERSTOCK_CATEGORIES[0]
            if category2 not in SHUTTERSTOCK_CATEGORIES:
                category2 = SHUTTERSTOCK_CATEGORIES[1] if category1 != SHUTTERSTOCK_CATEGORIES[1] else SHUTTERSTOCK_CATEGORIES[0]

            return {
                "title": description,
                "keywords": keywords,
                "category": f"{category1},{category2}"
            }
        else:
            title = str(data.get("title", "")).strip()
            category = str(data.get("category", "")).strip()

            # Clean up title (remove trailing punctuation and dangling words)
            title = _strip_dangling_tail(title)
            # Safety net: Adobe Stock hard limit is 200 chars
            if len(title) > 200:
                title = _truncate_to_complete_word(title, 200)
                title = _strip_dangling_tail(title)

            # Validate category is a number 1-21
            try:
                cat_num = int(category)
                if cat_num < 1 or cat_num > 21:
                    category = "1"
                else:
                    category = str(cat_num)
            except ValueError:
                category = "1"

            return {
                "title": title,
                "keywords": keywords,
                "category": category
            }
    except json.JSONDecodeError:
        raise ValueError(f"Failed to parse AI response as JSON: {response_text[:300]}")


def generate_metadata(provider_name, model, api_key, images_pil, filename, file_type="image", custom_prompt="", platform="adobestock", ai_generated=False, title_min=70, title_max=120, kw_min=30, kw_max=40):
    """
    Generate metadata using the specified AI provider.
    
    Args:
        provider_name: "Groq" or "RZ Vision"
        model: Model identifier string
        api_key: API key for the provider
        images_pil: List of PIL Image objects to analyze
        filename: Original filename of the asset
        file_type: "image", "vector", or "video"
        custom_prompt: Custom keywords to include in title and keywords
        platform: "adobestock", "shutterstock", "freepik", or "vecteezy"
        ai_generated: For Freepik, whether AI Generated checkbox is on
        title_min: Minimum title character count
        title_max: Maximum title character count
        kw_min: Minimum keyword count
        kw_max: Maximum keyword count
    
    Returns:
        dict with keys: title, keywords, category (and prompt for freepik)
    
    Raises:
        Exception on API or parsing errors
    """
    provider = PROVIDERS.get(provider_name)
    if not provider:
        raise ValueError(f"Unknown provider: {provider_name}")

    # Convert PIL images to base64
    images_base64 = [_encode_image_to_base64(img) for img in images_pil]

    # Build request
    messages = _build_messages(images_base64, filename, file_type, custom_prompt, platform=platform, ai_generated=ai_generated, title_min=title_min, title_max=title_max, kw_min=kw_min, kw_max=kw_max)
    url = provider["base_url"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }


    # max_tokens intentionally omitted — let the model finish naturally
    # to avoid truncation. Output is small (~300 tokens) so cost is minimal.

    # Convert display name to actual model ID for API
    actual_model = get_model_id(model)

    payload = {
        "model": actual_model,
        "messages": messages,
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    # Debug: log key info for troubleshooting
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    print(f"[DEBUG] Provider: {provider_name}, Model: {model}")
    print(f"[DEBUG] API Key: {masked_key} (len={len(api_key)})")

    # ── API call with retry for transient server errors ────────────────
    MAX_RETRIES = 3
    RETRY_STATUSES = {500, 502, 503, 429}   # server errors + rate limit
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.exceptions.Timeout:
            last_error = "Request timed out (60s). The server may be overloaded."
            if attempt < MAX_RETRIES:
                wait = 3 * (2 ** (attempt - 1))  # 3s, 6s, 12s
                print(f"[RETRY] Attempt {attempt}/{MAX_RETRIES} timed out, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise Exception(last_error)
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
            if attempt < MAX_RETRIES:
                wait = 3 * (2 ** (attempt - 1))
                print(f"[RETRY] Attempt {attempt}/{MAX_RETRIES} connection error, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise Exception(last_error)

        if response.status_code == 200:
            break  # Success — exit retry loop

        error_text = response.text[:500]
        print(f"[DEBUG] Response status: {response.status_code}")
        print(f"[DEBUG] Response body: {error_text}")

        if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
            wait = 3 * (2 ** (attempt - 1))  # 3s, 6s, 12s
            print(f"[RETRY] Attempt {attempt}/{MAX_RETRIES} got {response.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue

        # Non-retryable error or final attempt
        raise Exception(f"API Error ({response.status_code}): {error_text}")

    resp_json = response.json()

    # ── Extract content and check finish_reason ───────────────────────
    finish_reason = resp_json.get("choices", [{}])[0].get("finish_reason", "")

    try:
        content = resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print(f"[DEBUG] Full response: {json.dumps(resp_json)[:800]}")
        raise Exception(f"Unexpected API response structure: {json.dumps(resp_json)[:500]}")

    if not content or not content.strip():
        print(f"[DEBUG] Empty response from model. Full response: {json.dumps(resp_json)[:800]}")
        raise Exception(
            f"Model '{model}' returned an empty response. "
            f"This model may not support vision/image inputs. "
            f"Try a different model (e.g. gemini-2.5-flash-lite or gpt-4.1-nano)."
        )

    # ── Layer 3: If truncated (finish_reason=length), retry with explicit max_tokens ──
    if finish_reason == "length":
        print(f"[WARNING] Response truncated (finish_reason=length). Retrying with max_tokens=8192...")
        retry_payload = {**payload, "max_tokens": 8192}
        try:
            retry_response = requests.post(url, headers=headers, json=retry_payload, timeout=90)
            if retry_response.status_code == 200:
                retry_json = retry_response.json()
                retry_finish = retry_json.get("choices", [{}])[0].get("finish_reason", "")
                try:
                    retry_content = retry_json["choices"][0]["message"]["content"]
                    if retry_content and retry_content.strip():
                        content = retry_content
                        print(f"[INFO] Truncation retry successful (finish_reason={retry_finish})")
                except (KeyError, IndexError):
                    print(f"[WARNING] Retry response had unexpected structure, using original")
        except Exception as e:
            print(f"[WARNING] Truncation retry failed: {e}, using original response")

    # ── Layer 4: Parse JSON with retry on failure ─────────────────────
    PARSE_RETRIES = 2
    last_parse_error = None

    for parse_attempt in range(1, PARSE_RETRIES + 1):
        try:
            return _parse_response(content, custom_prompt, platform=platform, title_max=title_max, kw_max=kw_max)
        except (ValueError, json.JSONDecodeError) as e:
            last_parse_error = e
            print(f"[PARSE ERROR] Attempt {parse_attempt}/{PARSE_RETRIES}: {e}")

            if parse_attempt < PARSE_RETRIES:
                print(f"[PARSE RETRY] Re-requesting from API...")
                try:
                    time.sleep(2)
                    retry_resp = requests.post(url, headers=headers, json=payload, timeout=90)
                    if retry_resp.status_code == 200:
                        retry_json = retry_resp.json()
                        try:
                            new_content = retry_json["choices"][0]["message"]["content"]
                            if new_content and new_content.strip():
                                content = new_content
                                print(f"[PARSE RETRY] Got new response, retrying parse...")
                                continue
                        except (KeyError, IndexError):
                            pass
                except Exception as retry_err:
                    print(f"[PARSE RETRY] Re-request failed: {retry_err}")

    raise Exception(f"Failed to parse AI response after {PARSE_RETRIES} attempts. Last error: {last_parse_error}")
