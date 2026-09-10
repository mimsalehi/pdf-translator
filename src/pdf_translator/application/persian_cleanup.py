"""Persian Text Normalization and Editorial Cleanup Module.

Provides zero-dependency, Paknevis/Davat-grade Persian text cleanup and
Markdown-safe editorial normalization based on standard Persian orthography
and typography (Academy of Persian Language and Literature rules and Vazirmatn guidelines).
"""

from __future__ import annotations

import re
import unicodedata


# Zero-Width Non-Joiner (نیم‌فاصله)
ZWNJ = "\u200c"

# Persian and Arabic digits
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
EN_DIGITS = "0123456789"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"

_EN_TO_FA = {ord(e): f for e, f in zip(EN_DIGITS, FA_DIGITS)}
_AR_TO_FA = {ord(a): f for a, f in zip(AR_DIGITS, FA_DIGITS)}
_FA_TO_EN = {ord(f): e for f, e in zip(FA_DIGITS, EN_DIGITS)}

# Arabic to Persian character mapping
_ARABIC_TO_PERSIAN = {
    ord("ي"): "ی",  # Arabic Yeh -> Persian Yeh
    ord("ى"): "ی",  # Alef Maksura -> Persian Yeh
    ord("ك"): "ک",  # Arabic Kaf -> Persian Kaf
    ord("ؤ"): "و",  # Waw with Hamza
    ord("إ"): "ا",  # Alef with Hamza below
    ord("أ"): "ا",  # Alef with Hamza above
    ord("ة"): "ه",  # Teh Marbuta -> Heh
    ord("ۀ"): "هٔ", # Heh with Yeh above
}

# Diacritics (harakat)
_DIACRITICS = (
    "\u064b",  # fathatan
    "\u064c",  # dammatan
    "\u064d",  # kasratan
    "\u064e",  # fatha
    "\u064f",  # damma
    "\u0650",  # kasra
    "\u0651",  # shadda
    "\u0652",  # sukun
    "\u0670",  # superscript alef
)

# Common prefixes and prepositions that take ZWNJ
_PREFIXES_ZWNJ = (
    "به",
    "بی",
)

_PREFIX_NOUNS_PATTERN = (
    r"عنوان|گونه‌ای|طوری|اصطلاح|طور|ویژه|راحتی|سادگی|خودی|مراتب|شدت|ندرت|تنهایی"
)

# Suffixes that attach to nouns/adjectives with ZWNJ
_SUFFIXES_PATTERN = r"تر|ترین|ها|های|هایی|هایم|هایت|هایش|هایمان|هایتان|هایشان"

# Possessive enclitics that attach to heh-ending words with ZWNJ
_POSSESSIVES_PATTERN = r"ام|ات|اش|مان|تان|شان"


def to_persian_digits(text: str) -> str:
    """Converts English and Arabic digits to Persian digits."""
    if not isinstance(text, str):
        return text
    return text.translate(_EN_TO_FA).translate(_AR_TO_FA)


def to_english_digits(text: str) -> str:
    """Converts Persian and Arabic digits to English digits."""
    if not isinstance(text, str):
        return text
    return text.translate(_FA_TO_EN).translate(
        {ord(a): e for a, e in zip(AR_DIGITS, EN_DIGITS)}
    )


def fix_arabic_chars(text: str) -> str:
    """Maps Arabic characters (ي، ك، ة، ؤ، ...) to standard Persian equivalents."""
    if not text:
        return ""
    return text.translate(_ARABIC_TO_PERSIAN)


def remove_tatweel(text: str) -> str:
    """Removes tatweel/keshide (ـ) characters."""
    if not text:
        return ""
    return text.replace("\u0640", "")


def remove_diacritics(text: str) -> str:
    """Removes Arabic/Persian diacritics (harakat)."""
    if not text:
        return ""
    for d in _DIACRITICS:
        text = text.replace(d, "")
    return text


def fix_zwnj_verbs(text: str) -> str:
    """Inserts ZWNJ between verb prefixes ('می' / 'نمی') and verb stems.
    
    Examples:
        'می شود' -> 'می‌شود'
        'نمی دانم' -> 'نمی‌دانم'
    """
    if not text:
        return ""
    # Matches 'می' or 'نمی' followed by space and a Persian word of at least 2 letters
    return re.sub(r"\b(ن?می)\s+([ء-ی]{2,})", r"\1" + ZWNJ + r"\2", text)


def fix_zwnj_prefixes(text: str) -> str:
    """Inserts ZWNJ between frequent compound prefixes and their base words.
    
    Examples:
        'به عنوان' -> 'به‌عنوان'
        'بی نظیر' -> 'بی‌نظیر'
        'به راحتی' -> 'به‌راحتی'
    """
    if not text:
        return ""
    # 'به' + specific common adverbs/nouns
    text = re.sub(
        r"\b(به)\s+(" + _PREFIX_NOUNS_PATTERN + r")\b",
        r"\1" + ZWNJ + r"\2",
        text,
    )
    # 'بی' + any Persian noun (at least 2 letters)
    text = re.sub(
        r"\b(بی)\s+([ء-ی]{2,})\b",
        r"\1" + ZWNJ + r"\2",
        text,
    )
    return text


def fix_zwnj_suffixes(text: str) -> str:
    """Inserts ZWNJ before comparative, superlative, and plural suffixes.
    
    Examples:
        'کتاب ها' -> 'کتاب‌ها'
        'بزرگ تر' -> 'بزرگ‌تر'
        'بهترین ها' -> 'بهترین‌ها'
    """
    if not text:
        return ""
    pattern = re.compile(r"([ء-ی]+)\s+(" + _SUFFIXES_PATTERN + r")\b")
    return pattern.sub(r"\1" + ZWNJ + r"\2", text)


def fix_zwnj_possessives(text: str) -> str:
    """Inserts ZWNJ between words ending in 'ه' / 'ة' and possessive pronouns.
    
    Examples:
        'خانه ام' -> 'خانه‌ام'
        'نکته اش' -> 'نکته‌اش'
    """
    if not text:
        return ""
    pattern = re.compile(r"([ء-ی]+[هة])\s+(" + _POSSESSIVES_PATTERN + r")\b")
    return pattern.sub(r"\1" + ZWNJ + r"\2", text)


def fix_persian_punctuation(text: str) -> str:
    """Converts English punctuation to standard Persian typography:
    - '?' -> '؟'
    - ';' -> '؛'
    - ',' between or beside Persian words -> '،'
    - Paired double quotes '"..."' -> '«...»'
    - Unnecessary em dashes ('—') replaced with '، ' or comma
    """
    if not text:
        return ""

    # Question mark & semicolon
    text = text.replace("?", "؟").replace(";", "؛")

    # Comma: convert to Persian comma when touching or adjacent to Persian characters
    # Avoid breaking decimal points or code: 3.14 or foo,bar in ASCII
    text = re.sub(r"([ء-ی])\s*,\s*", r"\1، ", text)
    text = re.sub(r",\s*([ء-ی])", r"، \1", text)

    # Em dash replacement: AI frequently injects English em-dashes
    text = re.sub(r"\s*—\s*", "، ", text)

    # Convert paired double quotes into Persian guillemets «...»
    # Only replace if quotes are paired properly
    if text.count('"') >= 2:
        out = []
        in_quote = False
        for ch in text:
            if ch == '"':
                out.append("»" if in_quote else "«")
                in_quote = not in_quote
            else:
                out.append(ch)
        text = "".join(out)

    return text


def fix_punctuation_spacing(text: str) -> str:
    """Enforces standard Persian typography spacing around punctuation:
    - Removes whitespace before: ، ؛ ؟ ! . :
    - Ensures a single space after: ، ؛ ؟ ! : (unless at line break)
    """
    if not text:
        return ""

    # Remove space before punctuation
    text = re.sub(r"[ \t]+([،؛؟!.:])", r"\1", text)

    # Ensure single space after punctuation when followed by Persian/alphanumeric (exclude markdown delimiters *, _, `, ~)
    text = re.sub(r"([،؛؟!:])(?=[^\s\d،؛؟!:.\)\]\}»\"'\/*_`~])", r"\1 ", text)
    # Collapse multiple spaces (preserve newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def normalize_persian_prose(text: str) -> str:
    """Applies all editorial rules on pure Persian prose text."""
    if not text:
        return ""

    # 1. Unicode NFC
    text = unicodedata.normalize("NFC", text)

    # 2. Arabic to Persian characters
    text = fix_arabic_chars(text)

    # 3. Remove tatweel/keshide
    text = remove_tatweel(text)

    # 4. ZWNJ placement
    text = fix_zwnj_verbs(text)
    text = fix_zwnj_prefixes(text)
    text = fix_zwnj_suffixes(text)
    text = fix_zwnj_possessives(text)

    # 5. Punctuation and quotes
    text = fix_persian_punctuation(text)

    # 6. Spacing around punctuation
    text = fix_punctuation_spacing(text)

    return text


def normalize_markdown_emphasis(text: str) -> str:
    """Normalizes Markdown bold (**...**) and italic (__...__) delimiters with misplaced whitespace.
    Moves leading/trailing whitespace inside bold/italic tags outside, collapses multiple spaces
    around delimiters, and ensures separator hyphens/dashes have appropriate spacing so CommonMark
    parsers recognize bold formatting.
    """
    if not text:
        return ""

    def fix_bold(m):
        inner = m.group(1)
        if not inner.strip():
            return m.group(0)
        leading = " " if inner.startswith(" ") else ""
        trailing = " " if inner.endswith(" ") else ""
        return f"{leading}**{inner.strip()}**{trailing}"

    text = re.sub(r"\*\*([^\*\n]+?)\*\*", fix_bold, text)

    def fix_under_bold(m):
        inner = m.group(1)
        if not inner.strip():
            return m.group(0)
        leading = " " if inner.startswith(" ") else ""
        trailing = " " if inner.endswith(" ") else ""
        return f"{leading}__{inner.strip()}__{trailing}"

    text = re.sub(r"(?<!\w)__([^_\n]+?)__(?!\w)", fix_under_bold, text)

    # Collapse double spaces around delimiters
    text = re.sub(r"\*\*[ \t]+", "** ", text)
    text = re.sub(r"[ \t]+\*\*", " **", text)

    # Ensure space before separator hyphens/dashes attached to bold
    text = re.sub(r"\*\*([^\*\n]+?)\*\*([–—-])(?=\s|[\u0600-\u06FF])", r"**\1** \2", text)
    text = re.sub(r"\*\*([^\*\n]+?)\*\*\s+([–—-])(?=[\u0600-\u06FF])", r"**\1** \2 ", text)

    return text


def clean_markdown_persian(text: str) -> str:
    """Markdown-safe Persian text normalization.
    
    Protects all non-prose segments (code blocks, inline code, math formulas,
    image/code placeholders, links, and URLs) from corruption while applying
    full Persian editorial rules to the surrounding prose, headings, and lists.
    """
    if not text or not isinstance(text, str):
        return text

    # 0. Normalize Markdown emphasis delimiters with spaces inside (e.g. "**foo: **" -> "**foo:** ")
    text = normalize_markdown_emphasis(text)
    protected_tokens: dict[str, str] = {}
    counter = 0

    def protect(match_text: str) -> str:
        nonlocal counter
        token = f"__PROTECTED_SEGMENT_{counter}__"
        counter += 1
        protected_tokens[token] = match_text
        return token

    # 1. Protect Fenced Code Blocks (```...```)
    def mask_code_block(m):
        return protect(m.group(0))
    text = re.sub(r"```[\s\S]*?```", mask_code_block, text)

    # 2. Protect Block Math ($$...$$)
    text = re.sub(r"\$\$[\s\S]*?\$\$", mask_code_block, text)

    # 3. Protect Inline Math ($...$)
    text = re.sub(r"\$[^$\n]+?\$", mask_code_block, text)

    # 4. Protect Inline Code (`...`)
    text = re.sub(r"`[^`\n]+?`", mask_code_block, text)

    # 5. Protect System Placeholders [[CODE_BLOCK_X]] and [[IMAGE_BLOCK_X]]
    text = re.sub(r"\[\[(?:CODE|IMAGE)_BLOCK_\d+\]\]", mask_code_block, text)
    # 5.5 Protect Full Markdown Image Tags: ![caption](url)
    text = re.sub(r"!\[[\s\S]*?\]\([^)]+\)", mask_code_block, text)

    # 6. Protect Markdown Link URLs: [title](URL) -> protect URL
    def mask_markdown_links(m):
        prefix = m.group(1)  # e.g. [title]
        url = m.group(2)     # destination url
        url_token = protect(url)
        return f"{prefix}({url_token})"
    text = re.sub(r"(\[[^\]]*?\])\(([^)]+)\)", mask_markdown_links, text)
    # 7. Protect standalone HTTP(S) URLs
    text = re.sub(r"https?://[^\s\)]+", mask_code_block, text)

    # 8. Protect HTML Tags (<tag>...</tag>)
    text = re.sub(r"<[^>]+>", mask_code_block, text)

    # 9. Apply Persian normalization on prose
    text = normalize_persian_prose(text)

    # 10. Convert numbered list digits to Persian in Markdown lists:
    # e.g. "^1. " -> "۱. "
    def fa_list_number(m):
        indent = m.group(1)
        num = m.group(2)
        return f"{indent}{to_persian_digits(num)}. "
    text = re.sub(r"(?m)^(\s*)(\d+)\.\s+", fa_list_number, text)

    # 11. Restore all protected tokens
    for token, original in protected_tokens.items():
        text = text.replace(token, original)

    return text
