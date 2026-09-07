# ADR — PDF Book Translator

## 1. هدف

ساخت یک Web Application به‌صورت Local-first برای ترجمه تخصصی کتاب‌های PDF، به‌صورت **صفحه‌به‌صفحه و Human-in-the-Loop**، بدون نیاز به Copy/Paste دستی بین PDF و ابزارهای AI.

Workflow اصلی:

```text
PDF
 ↓
Extract Page
 ↓
Operator Approval
 ↓
AI Translation
 ↓
Human Review
 ↓
Save Page
 ↓
Next Page
 ↓
Assemble Book
 ↓
PDF
```

---

## 2. اصل ترجمه

Translation باید **ترجمه انسانی، روان، طبیعی و قابل فهم** باشد؛ نه ترجمه کلمه‌به‌کلمه و نه ترجمه رباتی.

مدل باید:

* مفهوم را منتقل کند، نه ساختار کلمات را.
* جمله‌بندی طبیعی زبان مقصد داشته باشد.
* از ترجمه تحت‌اللفظی غیرطبیعی پرهیز کند.
* متن را خلاصه نکند.
* چیزی به متن اضافه نکند.
* هیچ بخش معناداری را حذف نکند.
* مفهوم تخصصی نویسنده را تغییر ندهد.
* لحن و منظور متن اصلی را حفظ کند.

### اصطلاحات تخصصی

در مواردی که معادل فارسی ممکن است برای خواننده تخصصی مبهم باشد، **معادل انگلیسی اصطلاح داخل پرانتز** قرار گیرد.

مثال:

```text
شیء مقدار (Value Object)
```

اما این کار نباید افراطی باشد.

```text
❌ موجودیت (Entity)، تجمیع (Aggregate)، ریشه تجمیع (Aggregate Root)
```

در صورتی که همه اصطلاحات کاملاً واضح و شناخته‌شده باشند.

هدف:

```text
ترجمه فارسی روان
+
English terminology فقط در موارد واقعاً ضروری
```

---

## 3. انتخاب زبان مقصد

کاربر باید هنگام ایجاد یا تنظیم Project بتواند زبان مقصد را انتخاب کند.

مثلاً:

```text
Source Language: English
Target Language: Persian
```

یا:

```text
Source Language: English
Target Language: German
```

یا:

```text
Target Language: French
```

Translation Engine باید بر اساس Target Language انتخاب‌شده Translation را انجام دهد.

زبان مقصد نباید در Core Translation Logic Hard-code شود.

---

## 4. PDF & Project

هر کتاب یک Project است.

Project شامل:

```text
Project
├── Source PDF
├── Pages
├── Translation Configuration
├── Translation Results
└── Exports
```

سیستم باید:

* PDF را از Local Path دریافت کند.
* تعداد صفحات را تشخیص دهد.
* صفحات را Index کند.
* وضعیت هر Page را نگهداری کند.
* امکان Resume داشته باشد.
* امکان Start From Page X داشته باشد.

---

## 5. Page Workflow

هر Page دارای State است:

```text
PENDING
 ↓
READY
 ↓
APPROVED
 ↓
TRANSLATING
 ↓
TRANSLATED
 ↓
REVIEW
 ↓
APPROVED
 ↓
EXPORTED
```

قانون اصلی:

```text
No Operator Approval
        =
No Translation Request
```

در MVP ترجمه صفحات Sequential است و همزمان چند صفحه ترجمه نمی‌شود.

---

## 6. Translation Engine

Translation Provider باید از Core جدا باشد.

```text
Translation Engine
        │
        ▼
TranslationProvider
        │
   ┌────┴────┐
   │         │
 API      Browser
   │         │
OpenAI   Chromium
Gemini   ChatGPT
Claude   Gemini
         Claude
```

### API Strategy

پشتیبانی از:

* OpenAI
* Gemini
* Claude

API Key باید امن نگهداری شود و هرگز در Log نمایش داده نشود.

### Browser Strategy

با استفاده از Chromium:

```text
Open Browser
 ↓
User Login
 ↓
Open AI Provider
 ↓
Paste Source
 ↓
Submit
 ↓
Read Response
 ↓
Save Translation
```

Browser Automation باید Adapter مستقل برای هر Provider داشته باشد.

---

## 7. Translation Profile

Translation باید قابل Configuration باشد.

هر Profile حداقل شامل:

```text
Source Language
Target Language
Translation Prompt
AI Provider
Model
Glossary
Context Settings
```

نمونه:

```text
Technical English → Persian
```

قواعد Translation Profile باید شامل:

```text
Natural human translation
Faithful to original meaning
No summarization
No omission
No unnecessary additions
Preserve technical meaning
Preserve headings/lists/code/tables where possible
Use English terminology in parentheses only when genuinely useful
Avoid robotic/literal translation
```

---

## 8. Context & Terminology

برای حفظ Consistency بین صفحات، Translation Engine باید در آینده بتواند Context صفحات قبلی و Glossary را در اختیار مدل قرار دهد.

هدف Context:

```text
Terminology Consistency
+
Meaning Consistency
+
Natural Translation
```

اما Context نباید باعث تولید محتوای جدید شود.

---

## 9. Review

پس از Translation:

```text
AI Translation
      ↓
Human Review
      ↓
Edit / Retry / Approve
```

Translation نهایی باید نسخه تأییدشده توسط Operator باشد.

Translation باید Versionable باشد تا Retry باعث از بین رفتن نسخه قبلی نشود.

---

## 10. Output

هر صفحه به‌صورت مستقل ذخیره شود:

```text
pages/
├── page-001.md
├── page-001.docx
├── page-002.md
├── page-002.docx
└── ...
```

سپس:

```text
Pages
 ↓
Book.md / Book.docx
 ↓
Translated Book.pdf
```

ترتیب صفحات بر اساس `page_number` است.

---

## 11. Resume & Failure

در صورت بسته شدن Application:

```text
Restart
 ↓
Open Project
 ↓
Resume From Last Valid State
```

در صورت Failure:

```text
Page → FAILED
       ↓
     Retry
```

Failure یک صفحه نباید روی Translationهای موفق قبلی اثر بگذارد.

---

## 12. MVP

### Core

* [ ] Local Web Application
* [ ] Project Management
* [ ] PDF Processing
* [ ] Page State Management
* [ ] Start From Page X
* [ ] Resume

### Translation

* [ ] Configurable Target Language
* [ ] Natural Human-like Translation
* [ ] Faithful Translation
* [ ] Technical Terminology Handling
* [ ] Translation Profile
* [ ] Human Approval
* [ ] Retry
* [ ] Versioning

### Providers

* [ ] Provider Abstraction
* [ ] OpenAI API
* [ ] Browser/Chromium Strategy
* [ ] ChatGPT Adapter
* [ ] Gemini/Claude Adapter

### Export

* [ ] Markdown per Page
* [ ] DOCX per Page
* [ ] Book Assembly
* [ ] Final PDF

---

## 13. Architecture Principle

مهم‌ترین تصمیم معماری:

> **Core سیستم نباید به هیچ AI Provider وابسته باشد.**

Core فقط باید بداند:

```text
Source Text
    ↓
Translation Request
    ↓
Translation Result
```

اینکه Translation توسط:

```text
OpenAI API
Gemini API
Claude API
ChatGPT Browser
Gemini Browser
Claude Browser
```

انجام می‌شود، باید در Infrastructure/Adapter Layer قرار گیرد.

---

## 14. Definition of Done

MVP زمانی کامل است که کاربر بتواند:

```text
PDF
 ↓
Select Target Language
 ↓
Select Start Page
 ↓
Review Page
 ↓
Approve
 ↓
AI Translation
 ↓
Human Review/Edit
 ↓
Approve
 ↓
Save MD/DOCX
 ↓
Continue
 ↓
...
 ↓
Assemble Book
 ↓
Generate Final PDF
```

را بدون Copy/Paste دستی و با امکان Resume از آخرین وضعیت معتبر انجام دهد.

## 15. Technology Stack

### Primary Programming Language

**Python** زبان معیار و اصلی پروژه است.

تمامی Backend، Core Domain، Translation Engine، PDF Processing، Provider Adapters، Browser Automation و Export Logic باید تا حد امکان با Python پیاده‌سازی شوند.

```text id="py7x2k"
Primary Language:
Python
```

### Technology Decision

Agentها باید Python را به‌عنوان **Default Technology Choice** در نظر بگیرند و برای پیاده‌سازی قابلیت‌های جدید به سراغ زبان دیگری نروند، مگر اینکه:

1. یک قابلیت به‌صورت عملی با Python قابل پیاده‌سازی نباشد؛ یا
2. استفاده از یک ابزار خارجی/Native برای آن قابلیت ضروری باشد؛ یا
3. دلیل فنی مشخص و مستند برای استفاده از تکنولوژی دیگر وجود داشته باشد.

در چنین شرایطی باید ابتدا دلیل انتخاب ثبت شود.

### Architectural Preference

ترجیح کلی:

```text id="1qzq8v"
Python
 │
 ├── Web Application
 ├── Domain / Business Logic
 ├── PDF Processing
 ├── Translation Engine
 ├── AI Provider Adapters
 ├── Browser Automation
 ├── Export Pipeline
 └── CLI / Background Processing
```

هدف این است که پروژه تا حد ممکن **یکپارچه، ساده و Python-based** باقی بماند و از ایجاد Polyglot Architecture غیرضروری جلوگیری شود.

### Agent Rule

Agent هنگام شروع هر Task باید ابتدا بررسی کند:

> آیا این قابلیت با Python و اکوسیستم Python به‌صورت مناسب قابل پیاده‌سازی است؟

اگر پاسخ مثبت است، **Python باید انتخاب شود.**

استفاده از JavaScript/TypeScript، Go، Rust یا زبان‌های دیگر نباید انتخاب پیش‌فرض باشد.
