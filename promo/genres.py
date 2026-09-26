"""Genre presets: which angles, hooks, voice, pacing and look each kind of book should use.

The 5 rules apply to every genre:
  1. Hook in the first 1-2 seconds (bold claim, curiosity gap, POV, contrarian, identity).
  2. Lead with the feeling, not the book.
  3. Keep it simple (faceless, short, repeatable).
  4. End with a soft breadcrumb (cover + title + where to search), never a hard sell.
  5. Build it to be cloned: one proven format, many variations.
"""

FIVE_RULES = """1. HOOK in the first 1-2 seconds: the very first line must stop the scroll (bold claim, curiosity gap, POV, contrarian take, or identity call-out).
2. FEELING FIRST: lead with an emotion or identity the viewer recognises. Never open with "here's my book". The book is the payoff, not the pitch.
3. SIMPLE: short lines, one idea per scene, faceless-friendly, 12-35 seconds total unless the blueprint says otherwise.
4. BREADCRUMB ENDING: finish softly with the cover + title + where to find it (e.g. "Search '<title>' on Amazon"). No "BUY NOW", no hard sell.
5. CLONEABLE: keep a clear, repeatable structure so the winner can be re-made with new footage/hooks."""

GENRES = {
    "fiction": {
        "label": "Fiction / Novel",
        "angles": [
            "Trope call-out (enemies-to-lovers, found family, slow burn, morally grey, twist ending)",
            "POV: you're the reader who ... (identity)",
            "Character POV monologue - a character speaks directly to the viewer",
            "One unforgettable line from the book, highlighted on the page",
            "'If you loved <comparable book>, you'll devour this'",
            "Aesthetic / vibe montage that matches the book's world",
        ],
        "hook_examples": [
            "POV: you finally found a book that ruined you in the best way",
            "He said he'd burn the world for her. Page 212 proved it.",
            "Books with a villain you'll secretly root for",
            "Stop scrolling if you love slow burn",
        ],
        "tone": "cinematic, intriguing, emotional, a little dramatic",
        "voice": "sage",
        "voice_instructions": "Warm, intimate storyteller. Slightly hushed, dramatic pauses, as if sharing a secret.",
        "music_mood": "cinematic",
        "font": "Georgia", "caption_font": "Arial Black", "accent": "&H0000D7FF",
        "scene_seconds": (2.0, 4.0), "target_seconds": 25,
        "visual_mix": ["ai_video", "character", "page", "stock", "cover"],
        "breadcrumb": "Search '{title}' on Amazon",
        "rules": "Never spoil the ending. Sell the feeling of reading it, not the plot summary.",
    },
    "self-help": {
        "label": "Self-help / Personal growth",
        "angles": [
            "Before/after transformation - 'I used to ... now I ...'",
            "Contrarian truth - 'Discipline isn't the problem. This is.'",
            "3 lessons from page X that changed how I ...",
            "Identity call-out - 'If you're the one who always ...'",
            "One highlighted sentence that reframes a pain point",
        ],
        "hook_examples": [
            "You're not lazy. Nobody taught you this.",
            "Read this if you keep starting over every Monday",
            "The one page that fixed my mornings",
            "Stop trying harder. Try this instead.",
        ],
        "tone": "direct, empowering, honest, a little provocative",
        "voice": "onyx",
        "voice_instructions": "Confident, calm coach. Clear and grounded, with emphasis on key words. Not salesy.",
        "music_mood": "uplifting",
        "font": "Arial Black", "caption_font": "Arial Black", "accent": "&H0000D7FF",
        "scene_seconds": (1.8, 3.5), "target_seconds": 22,
        "visual_mix": ["stock", "page", "ai_video", "cover"],
        "breadcrumb": "It's all in '{title}'",
        "rules": "Promise a feeling/transformation, not guaranteed results.",
    },
    "poetry": {
        "label": "Poetry",
        "angles": [
            "Read one poem (or a few lines) over slow, moody visuals",
            "'For the ones who ...' identity dedication",
            "A poem that says what you couldn't say to someone",
            "Page-flip with a single highlighted line",
        ],
        "hook_examples": [
            "For the ones who loved someone who never stayed",
            "This poem says what I never could",
            "Send this to the person you miss",
        ],
        "tone": "soft, raw, intimate, slow",
        "voice": "shimmer",
        "voice_instructions": "Soft, slow, breathy spoken-word delivery with long pauses between lines.",
        "music_mood": "soft",
        "font": "Georgia", "caption_font": "Georgia", "accent": "&H00C0E0FF",
        "scene_seconds": (3.0, 5.0), "target_seconds": 25,
        "visual_mix": ["page", "stock", "ai_video", "cover"],
        "breadcrumb": "'{title}'",
        "rules": "Let the words breathe. Minimal text on screen; the poem is the hook.",
    },
    "gift": {
        "label": "Gift book",
        "angles": [
            "'Your dad doesn't know how much you love him' - relationship feeling",
            "Perfect gift for <person> who has everything",
            "Watch their reaction - emotional reveal moment",
            "Fill-in / keepsake pages shown page by page",
        ],
        "hook_examples": [
            "Your mom won't say it, but she needs to hear this",
            "The gift that made my dad cry",
            "Tell him before it's too late",
        ],
        "tone": "heartfelt, nostalgic, tender",
        "voice": "coral",
        "voice_instructions": "Gentle, heartfelt, warm, like talking to someone you love. Slight emotion in the voice.",
        "music_mood": "soft",
        "font": "Georgia", "caption_font": "Arial Black", "accent": "&H0000D7FF",
        "scene_seconds": (2.0, 3.5), "target_seconds": 15,
        "visual_mix": ["page", "stock", "ai_video", "cover"],
        "breadcrumb": "'{title}' - search it on Amazon",
        "rules": "Make the viewer think of one specific person. Name the relationship (dad, mom, spouse, best friend).",
    },
    "medical": {
        "label": "Medical / Health",
        "angles": [
            "Myth vs fact - a common belief the book corrects",
            "'Things your doctor wishes you knew about ...'",
            "Symptom/situation identity - 'If you've ever felt ...'",
            "One clear takeaway from page X, highlighted",
        ],
        "hook_examples": [
            "Most people get this completely wrong about sleep",
            "If you've ever felt this after eating, read this",
            "A nurse's notes on what nobody tells you",
        ],
        "tone": "trustworthy, clear, calm, evidence-based",
        "voice": "ash",
        "voice_instructions": "Calm, reassuring, credible professional. Clear pronunciation, measured pace.",
        "music_mood": "calm",
        "font": "Arial", "caption_font": "Arial Black", "accent": "&H00FFD000",
        "scene_seconds": (2.5, 4.0), "target_seconds": 28,
        "visual_mix": ["stock", "page", "ai_image", "cover"],
        "breadcrumb": "Learn more in '{title}'",
        "rules": "NO cure claims, NO diagnosis, NO fear-mongering. Educational tone only. "
                 "Final scene overlay must include 'Educational only - not medical advice.'",
    },
    "engineering": {
        "label": "Engineering / Technical",
        "angles": [
            "'The mistake every junior engineer makes'",
            "Problem -> insight -> 'it's on page X'",
            "Quick explainer of one concept in 20 seconds",
            "Career identity - 'If you want to think like a senior engineer'",
        ],
        "hook_examples": [
            "This one diagram explains why bridges don't fall",
            "Every engineer learns this the hard way",
            "The formula they never explained properly in school",
        ],
        "tone": "smart, curious, no-nonsense, satisfying",
        "voice": "echo",
        "voice_instructions": "Clear, energetic explainer. Confident and curious, like a great teacher.",
        "music_mood": "tech",
        "font": "Arial Black", "caption_font": "Arial Black", "accent": "&H0000FF9C",
        "scene_seconds": (2.0, 3.5), "target_seconds": 25,
        "visual_mix": ["stock", "page", "ai_video", "cover"],
        "breadcrumb": "Full breakdown in '{title}'",
        "rules": "Be technically accurate. Show a real page/diagram from the manuscript where possible.",
    },
    "children": {
        "label": "Children's book",
        "angles": [
            "Parent POV - 'The book my kid asks for every night'",
            "Read-aloud of a page with page-by-page flip",
            "Lesson the book teaches (sharing, bravery, feelings)",
            "Bedtime / cozy moment feeling",
        ],
        "hook_examples": [
            "My 4-year-old asks for this book every single night",
            "The bedtime story that taught my son to be brave",
            "Parents, you need this for bedtime",
        ],
        "tone": "warm, playful, cozy, wholesome",
        "voice": "fable",
        "voice_instructions": "Warm, playful bedtime-story voice. Gentle, expressive, smiling while speaking.",
        "music_mood": "playful",
        "font": "Comic Sans MS", "caption_font": "Arial Black", "accent": "&H0000D7FF",
        "scene_seconds": (2.0, 3.5), "target_seconds": 20,
        "visual_mix": ["page", "stock", "character", "cover"],
        "breadcrumb": "'{title}' - search it on Amazon",
        "rules": "Speak to parents/grandparents (the buyers). Never show real children's faces from AI; use hands, "
                 "silhouettes, or the book itself.",
    },
}

TTS_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]


def default_blueprint(genre_key: str) -> dict:
    """A proven structure to use when no reference video is given."""
    g = GENRES[genre_key]
    return {
        "source": f"built-in {g['label']} blueprint",
        "summary": f"Proven faceless {g['label']} format: hook, feeling, proof from the book, soft breadcrumb.",
        "hook": {"type": "identity / curiosity", "example": g["hook_examples"][0], "seconds": 2},
        "emotion": g["tone"],
        "structure": [
            {"beat": "Hook", "purpose": "Stop the scroll with an identity or curiosity line", "seconds": 2.5},
            {"beat": "Feeling", "purpose": "Name the emotion/pain/desire the viewer has", "seconds": 4},
            {"beat": "Deepen", "purpose": "Make it specific and relatable", "seconds": 4},
            {"beat": "Proof from the book", "purpose": "Show a real page and highlight one line", "seconds": 5},
            {"beat": "Payoff", "purpose": "The feeling the book gives you", "seconds": 4},
            {"beat": "Breadcrumb", "purpose": "Cover + title + where to find it", "seconds": 3.5},
        ],
        "total_seconds": g["target_seconds"],
        "pacing": f"{g['scene_seconds'][0]}-{g['scene_seconds'][1]}s per shot",
        "voice": {"has_voiceover": True, "style": g["voice_instructions"]},
        "overlay_style": "Short bold text overlay per scene; spoken words as captions",
        "ending": {"type": "soft breadcrumb", "description": g["breadcrumb"]},
        "music": g["music_mood"],
        "why_it_works": "Emotion first, simple visuals, the book appears as the answer, easy to clone.",
    }
