"""
AI Service using spaCy for intelligent message processing.
Features:
  - Entity extraction (people, organizations, dates, etc.)
  - Message intent classification (question, task, announcement, etc.)
  - Sentiment analysis (basic rule-based + spaCy)
  - Smart search with semantic similarity
  - Auto-tagging and keyword extraction
  - @mention suggestions based on context
"""

import re
import logging
import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

def parse_fuzzy_date(text: str) -> datetime.datetime:
    """Very rudimentary date parser for AI mockup purposes."""
    text = text.lower()
    now = datetime.datetime.now()
    if 'tomorrow' in text:
        return now + datetime.timedelta(days=1)
    if 'monday' in text:
        days_ahead = 0 - now.weekday()
        if days_ahead <= 0: days_ahead += 7
        return now + datetime.timedelta(days=days_ahead)
    if 'friday' in text:
        days_ahead = 4 - now.weekday()
        if days_ahead <= 0: days_ahead += 7
        return now + datetime.timedelta(days=days_ahead)
    # Default fallback to tomorrow if it detects a date but doesn't know it
    return now + datetime.timedelta(days=1)

# Lazy-load spaCy to avoid slowing down Django startup
_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("✅ spaCy model 'en_core_web_sm' loaded successfully.")
        except OSError:
            logger.warning("⚠️  spaCy model not found. Run: python -m spacy download en_core_web_sm")
            _nlp = None
        except ImportError:
            logger.warning("⚠️  spaCy not installed. Run: pip install spacy")
            _nlp = None
        except Exception as e:
            # spaCy can crash on Python 3.14+ due to pydantic v1 incompatibility.
            # Fall back to regex-only mode so the app still runs.
            logger.warning(f"⚠️  spaCy failed to load (Python version incompatibility?): {e}")
            _nlp = None
    return _nlp


# ─── Intent Classification ──────────────────────────────────────────────────

INTENT_PATTERNS = {
    "question": [
        r"\?$", r"^(what|who|where|when|why|how|is|are|can|could|would|should|do|does|did)\b"
    ],
    "task": [
        r"\b(todo|to-do|task|action item|need to|must|should|please|can you|could you)\b",
        r"\b(deadline|by (monday|tuesday|wednesday|thursday|friday|tomorrow|eod|eow))\b"
    ],
    "announcement": [
        r"\b(announcing|announcement|update|fyi|heads up|reminder|notice|important)\b",
        r"^(hey everyone|hi all|hi team|good morning|good afternoon|dear team)\b"
    ],
    "meeting": [
        r"\b(meeting|call|standup|stand-up|sync|review|demo|sprint|scrum)\b",
        r"\b(at \d{1,2}(:\d{2})?\s*(am|pm)|tomorrow|today at)\b"
    ],
    "help": [
        r"\b(help|stuck|issue|problem|bug|error|not working|broken|failing)\b"
    ],
    "praise": [
        r"\b(great job|well done|amazing|awesome|fantastic|kudos|congrats|congratulations|thanks|thank you)\b"
    ],
}

def classify_intent(text: str) -> str:
    """Classify the intent of a message."""
    text_lower = text.lower().strip()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "general"


# ─── Sentiment Analysis ──────────────────────────────────────────────────────

POSITIVE_WORDS = {
    "great", "good", "excellent", "amazing", "fantastic", "awesome", "love",
    "perfect", "wonderful", "brilliant", "happy", "excited", "thanks", "thank",
    "congrats", "congratulations", "nice", "well", "best", "impressive", "helpful"
}
NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "hate", "wrong", "broken", "error", "bug",
    "fail", "failed", "issue", "problem", "stuck", "confused", "frustrated",
    "annoying", "slow", "crash", "worst", "ugly", "difficult", "impossible"
}

def analyze_sentiment(text: str) -> str:
    """Basic sentiment analysis."""
    words = set(re.findall(r'\b\w+\b', text.lower()))
    pos_score = len(words & POSITIVE_WORDS)
    neg_score = len(words & NEGATIVE_WORDS)
    if pos_score > neg_score:
        return "positive"
    elif neg_score > pos_score:
        return "negative"
    return "neutral"


# ─── Entity & Keyword Extraction ─────────────────────────────────────────────

def extract_tags(text: str) -> List[str]:
    """
    Extract meaningful tags from a message using spaCy NER + fallback regex.
    Returns a list of tag strings like ['@Alice', '#project-alpha', 'deadline:friday']
    """
    tags = []

    # Extract @mentions
    mentions = re.findall(r'@(\w+)', text)
    tags.extend([f"@{m}" for m in mentions])

    # Extract #channels
    channels = re.findall(r'#(\w[\w-]*)', text)
    tags.extend([f"#{c}" for c in channels])

    # Extract URLs
    urls = re.findall(r'https?://[^\s]+', text)
    if urls:
        tags.append("has-link")

    # Use spaCy for NER if available
    nlp = get_nlp()
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            label = ent.label_
            ent_text = ent.text.strip()
            if label == "PERSON":
                tags.append(f"person:{ent_text}")
            elif label == "ORG":
                tags.append(f"org:{ent_text}")
            elif label == "DATE":
                tags.append(f"date:{ent_text}")
            elif label == "TIME":
                tags.append(f"time:{ent_text}")
            elif label in ("GPE", "LOC"):
                tags.append(f"place:{ent_text}")
            elif label == "PRODUCT":
                tags.append(f"product:{ent_text}")

        # Extract noun chunks as keywords (top 3)
        noun_chunks = [chunk.text.lower() for chunk in doc.noun_chunks
                       if len(chunk.text) > 3 and chunk.text.lower() not in {'i', 'we', 'you', 'they', 'it'}]
        tags.extend(noun_chunks[:3])
    else:
        # Fallback: simple keyword extraction
        words = re.findall(r'\b[A-Za-z]{4,}\b', text)
        stopwords = {'this', 'that', 'with', 'have', 'from', 'they', 'will', 'been',
                     'just', 'also', 'into', 'some', 'your', 'their', 'what', 'when'}
        temporals = {'tomorrow', 'today', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'}
        
        for w in words:
            wl = w.lower()
            if wl in temporals:
                tags.append(f"date:{wl}")
        
        keywords = [w.lower() for w in words if w.lower() not in stopwords and w.lower() not in temporals]
        tags.extend(list(set(keywords))[:3])

    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags[:10]  # Max 10 tags


# ─── Smart Search ─────────────────────────────────────────────────────────────

def smart_search(query: str, messages: List[Dict]) -> List[Dict]:
    """
    Enhanced search using spaCy token similarity + keyword matching.
    Returns messages sorted by relevance score.
    """
    nlp = get_nlp()
    query_lower = query.lower()
    results = []

    if nlp:
        try:
            query_doc = nlp(query)
        except Exception:
            query_doc = None
    else:
        query_doc = None

    for msg in messages:
        text = msg.get('text', '')
        text_lower = text.lower()
        score = 0

        # Exact keyword match (highest weight)
        if query_lower in text_lower:
            score += 10

        # Word-level match
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        common_words = query_words & text_words
        score += len(common_words) * 3

        # Tag match
        for tag in msg.get('ai_tags', []):
            if query_lower in tag.lower():
                score += 5

        # spaCy semantic similarity
        if query_doc and nlp:
            try:
                text_doc = nlp(text[:500])  # limit length
                if query_doc.has_vector and text_doc.has_vector:
                    similarity = query_doc.similarity(text_doc)
                    score += int(similarity * 8)
            except Exception:
                pass

        if score > 0:
            results.append({**msg, '_relevance': score})

    results.sort(key=lambda x: x['_relevance'], reverse=True)
    return results


# ─── Mention Suggestions ─────────────────────────────────────────────────────

def suggest_mentions(partial: str, channel_members: List[Dict]) -> List[Dict]:
    """
    Suggest @mentions based on partial text input.
    Uses fuzzy matching on username and display_name.
    """
    partial_lower = partial.lower()
    suggestions = []
    for member in channel_members:
        username = member.get('username', '').lower()
        display = member.get('display_name', '').lower()
        if partial_lower in username or partial_lower in display:
            suggestions.append(member)
    return suggestions[:5]


# ─── Message Summary (spaCy-based) ───────────────────────────────────────────

def summarize_channel_activity(messages: List[str]) -> Dict:
    """
    Analyze a list of message texts and return activity insights.
    Used for the channel info panel / activity summary.
    """
    if not messages:
        return {"topics": [], "active_intents": {}, "message_count": 0}

    intents = {}
    all_tags = []

    for text in messages:
        intent = classify_intent(text)
        intents[intent] = intents.get(intent, 0) + 1
        tags = extract_tags(text)
        all_tags.extend(tags)

    # Most common tags (topics)
    tag_counts = {}
    for tag in all_tags:
        if not tag.startswith(('@', '#', 'has-')):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    top_topics = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "topics": [t[0] for t in top_topics],
        "active_intents": intents,
        "message_count": len(messages),
        "most_common_intent": max(intents, key=intents.get) if intents else "general"
    }


# ─── Full Message Analysis ────────────────────────────────────────────────────

def analyze_message(text: str) -> Dict:
    """
    Main entry point: run all AI analysis on a message.
    Returns dict with intent, sentiment, tags.
    """
    return {
        "intent": classify_intent(text),
        "sentiment": analyze_sentiment(text),
        "tags": extract_tags(text),
    }
