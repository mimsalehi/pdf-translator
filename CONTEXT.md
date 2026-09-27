# PDF Book Translator

A local-first web application for translating PDF books page-by-page with Human-in-the-Loop (HITL) workflows, ensuring natural, fluent, and domain-accurate translations without manual copy-pasting.

## Language

**Project**:
A translation workspace dedicated to a single source document — a PDF book or a web article — containing its configuration, pages, translation history, and export artifacts.
_Avoid_: Book (when referring to the workspace entity), Workspace, Task

**SourceType**:
The origin of a Project's content: `PDF` (an uploaded PDF file, one Page per sheet) or `ARTICLE` (a web article fetched from a URL, stored as exactly one Page containing the full text and all images).
_Avoid_: Kind, Mode, Format

**Article**:
A web page whose main content (text, code, tables, and images) is fetched from a URL and translated as a single Page.
_Avoid_: Post, Webpage, Link

**Page**:
A single indexed leaf/sheet from the source PDF containing its zero-based index, extracted source text, rendered visual representation, and current workflow lifecycle state.
_Avoid_: Sheet, Leaf, Slice

**PageStatus**:
The discrete lifecycle state of a Page (`PENDING`, `READY`, `APPROVED_FOR_TRANSLATION`, `TRANSLATING`, `TRANSLATED`, `IN_REVIEW`, `APPROVED`, `EXPORTED`, `FAILED`).
_Avoid_: State, Stage

**TranslationProfile**:
A set of configuration parameters governing how translation is executed, including source and target languages, prompt instructions, provider adapter settings, model choices, and glossary rules.
_Avoid_: Config, Settings, Preset

**TranslationAttempt**:
An immutable record of a single execution of translation (or human manual edit) on a specific Page, storing AI raw response, refined text, model metadata, operator notes, and timestamp.
_Avoid_: Version, Revision, HistoryItem

**Glossary**:
A curated dictionary of domain-specific terminology mapping source phrases to preferred target language equivalents and rules for parenthetical English annotations.
_Avoid_: Dictionary, Vocab, TermBase

**TranslationProvider**:
An abstraction adapter responsible for taking a translation request and producing a translated result via either an API client or a browser automation session.
_Avoid_: AIClient, Engine, ModelConnector

**Operator**:
The human user reviewing extracted text, providing approvals, editing translations, and controlling the translation pipeline.
_Avoid_: User, Reviewer, Admin
