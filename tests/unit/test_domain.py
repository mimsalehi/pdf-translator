"""Unit tests for Domain Entities and State Machine."""
import pytest
from pdf_translator.domain.entities import Page, Project, TranslationProfile
from pdf_translator.domain.enums import PageStatus, ProviderType

def test_page_state_machine_valid_transitions():
    page = Page(
        project_id="proj-1",
        page_number=1,
        status=PageStatus.READY,
        source_text="Sample text",
    )

    # READY -> APPROVED_FOR_TRANSLATION
    assert page.can_transition_to(PageStatus.APPROVED_FOR_TRANSLATION) is True
    assert page.can_transition_to(PageStatus.APPROVED) is False

    # APPROVED_FOR_TRANSLATION -> TRANSLATING
    page.status = PageStatus.APPROVED_FOR_TRANSLATION
    assert page.can_transition_to(PageStatus.TRANSLATING) is True
    assert page.can_transition_to(PageStatus.EXPORTED) is False

    # TRANSLATING -> IN_REVIEW
    page.status = PageStatus.TRANSLATING
    assert page.can_transition_to(PageStatus.IN_REVIEW) is True

    # IN_REVIEW -> APPROVED
    page.status = PageStatus.IN_REVIEW
    assert page.can_transition_to(PageStatus.APPROVED) is True

    # APPROVED -> EXPORTED
    page.status = PageStatus.APPROVED
    assert page.can_transition_to(PageStatus.EXPORTED) is True

def test_page_state_machine_failure_and_retry():
    page = Page(
        project_id="proj-1",
        page_number=1,
        status=PageStatus.TRANSLATING,
    )
    assert page.can_transition_to(PageStatus.FAILED) is True

    page.status = PageStatus.FAILED
    assert page.can_transition_to(PageStatus.APPROVED_FOR_TRANSLATION) is True
    assert page.can_transition_to(PageStatus.READY) is True
