"""SQLite Repository implementation using SQLModel."""
from typing import List, Optional
from sqlmodel import Session, select
from pdf_translator.domain.entities import (
    Project, Page, TranslationProfile, TranslationAttempt, GlossaryItem,
    PromptTemplate, PageConversation, ChapterSummary, ChapterPromptTemplate,
    ChapterConversation
)
from pdf_translator.domain.ports import (
    ProjectRepositoryPort, PageRepositoryPort, ProfileRepositoryPort,
    PromptTemplateRepositoryPort, PageConversationRepositoryPort,
    ChapterSummaryRepositoryPort, ChapterPromptTemplateRepositoryPort,
    ChapterConversationRepositoryPort
)

class SQLiteProjectRepository(ProjectRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, project: Project) -> Project:
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def get_by_id(self, project_id: str) -> Optional[Project]:
        return self.session.get(Project, project_id)

    def list_all(self) -> List[Project]:
        statement = select(Project).order_by(Project.created_at.desc())
        return list(self.session.exec(statement).all())

    def delete(self, project_id: str) -> bool:
        project = self.get_by_id(project_id)
        if project:
            # 1. Delete associated conversations
            convos = self.session.exec(select(PageConversation).where(PageConversation.project_id == project_id)).all()
            for c in convos:
                self.session.delete(c)

            # 2. Delete pages and their translation attempts
            pages = self.session.exec(select(Page).where(Page.project_id == project_id)).all()
            for p in pages:
                attempts = self.session.exec(select(TranslationAttempt).where(TranslationAttempt.page_id == p.id)).all()
                for a in attempts:
                    self.session.delete(a)
                self.session.delete(p)

            # 3. Delete project record
            self.session.delete(project)
            self.session.commit()
            return True
        return False


class SQLitePageRepository(PageRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, page: Page) -> Page:
        self.session.add(page)
        self.session.commit()
        self.session.refresh(page)
        return page

    def get_by_id(self, page_id: str) -> Optional[Page]:
        return self.session.get(Page, page_id)

    def get_by_project_and_number(self, project_id: str, page_number: int) -> Optional[Page]:
        statement = select(Page).where(
            Page.project_id == project_id,
            Page.page_number == page_number
        )
        return self.session.exec(statement).first()

    def list_by_project(self, project_id: str) -> List[Page]:
        statement = select(Page).where(Page.project_id == project_id).order_by(Page.page_number.asc())
        return list(self.session.exec(statement).all())

    def save_attempt(self, attempt: TranslationAttempt) -> TranslationAttempt:
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def list_attempts(self, page_id: str) -> List[TranslationAttempt]:
        statement = select(TranslationAttempt).where(
            TranslationAttempt.page_id == page_id
        ).order_by(TranslationAttempt.version_number.desc())
        return list(self.session.exec(statement).all())


class SQLiteProfileRepository(ProfileRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, profile: TranslationProfile) -> TranslationProfile:
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_by_id(self, profile_id: str) -> Optional[TranslationProfile]:
        return self.session.get(TranslationProfile, profile_id)

    def get_default(self) -> TranslationProfile:
        statement = select(TranslationProfile).order_by(TranslationProfile.created_at.asc())
        profile = self.session.exec(statement).first()
        if not profile:
            profile = TranslationProfile()
            self.session.add(profile)
            self.session.commit()
            self.session.refresh(profile)
        return profile

    def list_all(self) -> List[TranslationProfile]:
        statement = select(TranslationProfile).order_by(TranslationProfile.created_at.desc())
        return list(self.session.exec(statement).all())


class SQLitePromptTemplateRepository(PromptTemplateRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, template: PromptTemplate) -> PromptTemplate:
        self.session.add(template)
        self.session.commit()
        self.session.refresh(template)
        return template

    def get_by_id(self, template_id: str) -> Optional[PromptTemplate]:
        return self.session.get(PromptTemplate, template_id)

    def get_default(self) -> Optional[PromptTemplate]:
        statement = select(PromptTemplate).where(PromptTemplate.is_default == True)
        tpl = self.session.exec(statement).first()
        if not tpl:
            statement_first = select(PromptTemplate).order_by(PromptTemplate.created_at.asc())
            tpl = self.session.exec(statement_first).first()
        return tpl

    def list_all(self) -> List[PromptTemplate]:
        statement = select(PromptTemplate).order_by(PromptTemplate.created_at.asc())
        return list(self.session.exec(statement).all())

    def delete(self, template_id: str) -> bool:
        template = self.get_by_id(template_id)
        if template:
            self.session.delete(template)
            self.session.commit()
            return True
        return False


class SQLitePageConversationRepository(PageConversationRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, conversation: PageConversation) -> PageConversation:
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def list_by_page(self, project_id: str, page_number: int) -> List[PageConversation]:
        statement = select(PageConversation).where(
            PageConversation.project_id == project_id,
            PageConversation.page_number == page_number
        ).order_by(PageConversation.created_at.asc())
        return list(self.session.exec(statement).all())

    def delete(self, conversation_id: str) -> bool:
        convo = self.session.get(PageConversation, conversation_id)
        if convo:
            self.session.delete(convo)
            self.session.commit()
            return True
        return False


class SQLiteChapterSummaryRepository(ChapterSummaryRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, summary: ChapterSummary) -> ChapterSummary:
        self.session.add(summary)
        self.session.commit()
        self.session.refresh(summary)
        return summary

    def get_by_id(self, summary_id: str) -> Optional[ChapterSummary]:
        return self.session.get(ChapterSummary, summary_id)

    def list_by_project(self, project_id: str) -> List[ChapterSummary]:
        statement = select(ChapterSummary).where(
            ChapterSummary.project_id == project_id
        ).order_by(ChapterSummary.start_page.asc(), ChapterSummary.created_at.asc())
        return list(self.session.exec(statement).all())

    def delete(self, summary_id: str) -> bool:
        summary = self.session.get(ChapterSummary, summary_id)
        if summary:
            self.session.delete(summary)
            self.session.commit()
            return True
        return False


class SQLiteChapterPromptTemplateRepository(ChapterPromptTemplateRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, template: ChapterPromptTemplate) -> ChapterPromptTemplate:
        self.session.add(template)
        self.session.commit()
        self.session.refresh(template)
        return template

    def get_by_id(self, template_id: str) -> Optional[ChapterPromptTemplate]:
        return self.session.get(ChapterPromptTemplate, template_id)

    def get_default(self) -> Optional[ChapterPromptTemplate]:
        statement = select(ChapterPromptTemplate).where(ChapterPromptTemplate.is_default == True)
        tpl = self.session.exec(statement).first()
        if not tpl:
            statement_first = select(ChapterPromptTemplate).order_by(ChapterPromptTemplate.created_at.asc())
            tpl = self.session.exec(statement_first).first()
        return tpl

    def list_all(self) -> List[ChapterPromptTemplate]:
        statement = select(ChapterPromptTemplate).order_by(ChapterPromptTemplate.created_at.asc())
        return list(self.session.exec(statement).all())

    def delete(self, template_id: str) -> bool:
        tpl = self.session.get(ChapterPromptTemplate, template_id)
        if tpl:
            self.session.delete(tpl)
            self.session.commit()
            return True
        return False


class SQLiteChapterConversationRepository(ChapterConversationRepositoryPort):
    def __init__(self, session: Session):
        self.session = session

    def save(self, conversation: ChapterConversation) -> ChapterConversation:
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def list_by_chapter(self, chapter_summary_id: str, section_index: Optional[int] = None) -> List[ChapterConversation]:
        statement = select(ChapterConversation).where(ChapterConversation.chapter_summary_id == chapter_summary_id)
        if section_index is not None:
            statement = statement.where(ChapterConversation.section_index == section_index)
        statement = statement.order_by(ChapterConversation.created_at.asc())
        return list(self.session.exec(statement).all())

    def delete(self, conversation_id: str) -> bool:
        convo = self.session.get(ChapterConversation, conversation_id)
        if convo:
            self.session.delete(convo)
            self.session.commit()
            return True
        return False
