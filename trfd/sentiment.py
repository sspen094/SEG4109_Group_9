"""Sentiment engine: lexicon baseline with negation and sarcasm handling.

Returns a label (negative, neutral, positive) and a confidence score.
This baseline must reach 80% agreement with the team-labelled validation
set; if it does not, it is replaced by a trained model behind the same
score() interface.
"""
import re

POSITIVE = {
    "good", "great", "clean", "friendly", "helpful", "fast", "quick", "love",
    "nice", "smooth", "easy", "reliable", "comfortable", "thanks", "thank",
    "safe", "polite", "improved", "awesome", "excellent", "punctual", "accessible",
}
NEGATIVE = {
    "late", "delayed", "delay", "dirty", "filthy", "rude", "unsafe", "broken",
    "cancelled", "canceled", "slow", "crowded", "packed", "terrible", "awful",
    "worst", "stuck", "smells", "missed", "unreliable", "crashes", "crash",
    "expensive", "scary", "useless", "garbage", "ghost", "freezing", "bad",
}
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "aren't"}
# Positive words that cancel out against a service failure usually signal
# sarcasm: "Thanks LRT for being late again" is a complaint, not praise.
FAILURE_CUES = {"late", "delayed", "cancelled", "canceled", "stuck", "broken", "ghost"}

TOKEN = re.compile(r"[a-z][a-z'-]*")


def score(text):
    tokens = TOKEN.findall(text.lower())
    total = 0
    pos_hits = 0
    for i, tok in enumerate(tokens):
        polarity = 1 if tok in POSITIVE else -1 if tok in NEGATIVE else 0
        if polarity == 0:
            continue
        if any(t in NEGATORS for t in tokens[max(0, i - 2):i]):
            polarity = -polarity
        if polarity > 0:
            pos_hits += 1
        total += polarity

    sarcastic = total == 0 and pos_hits > 0 and bool(FAILURE_CUES & set(tokens))
    if sarcastic:
        total = -1

    if total > 0:
        label = "positive"
    elif total < 0:
        label = "negative"
    else:
        label = "neutral"
    confidence = 0.5 if total == 0 else min(0.95, 0.55 + 0.15 * abs(total))
    return label, round(confidence, 2)
