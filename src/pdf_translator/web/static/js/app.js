// Application JS for PDF Translator
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('active');
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

// Drag & drop file upload handler
document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('pdf-dropzone');
  const fileInput = document.getElementById('pdf-file-input');
  const fileInfo = document.getElementById('selected-file-info');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    
    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        updateFileInfo(fileInput.files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) {
        updateFileInfo(fileInput.files[0]);
      }
    });
  }

  function updateFileInfo(file) {
    if (fileInfo && file) {
      fileInfo.textContent = `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
      fileInfo.style.display = 'block';
    }
  }

  // Handle New Project Form Submission
  const newProjectForm = document.getElementById('new-project-form');
  if (newProjectForm) {
    newProjectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById('submit-project-btn');
      const errorBox = document.getElementById('project-form-error');
      
      if (!fileInput || !fileInput.files.length) {
        if (errorBox) {
          errorBox.textContent = 'Please select a PDF file.';
          errorBox.style.display = 'block';
        }
        return;
      }

      const formData = new FormData(newProjectForm);
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Processing PDF & Extracting Pages...';
      }
      if (errorBox) errorBox.style.display = 'none';

      try {
        const response = await fetch('/api/projects', {
          method: 'POST',
          body: formData
        });

        const data = await response.json();
        if (response.ok && data.success) {
          window.location.href = `/projects/${data.project_id}`;
        } else {
          throw new Error(data.detail || 'Failed to create project.');
        }
      } catch (err) {
        if (errorBox) {
          errorBox.textContent = err.message;
          errorBox.style.display = 'block';
        }
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Create Project';
        }
      }
    });
  }
});

// --- Modern Code Block Beautifier & Syntax Highlighting ---
function enhanceCodeBlocks(container) {
  if (!container) return;

  container.querySelectorAll('pre').forEach((pre) => {
    if (pre.dataset.enhanced) return;
    pre.dataset.enhanced = 'true';

    const code = pre.querySelector('code') || pre;

    // Detect language from class
    let lang = 'CODE';
    if (code.classList) {
      code.classList.forEach(cls => {
        if (cls.startsWith('language-') || cls.startsWith('lang-')) {
          lang = cls.replace(/^(language-|lang-)/, '').toUpperCase();
        }
      });
    }

    // Create wrapper card
    const wrapper = document.createElement('div');
    wrapper.className = 'code-card-wrapper';

    // Create header toolbar
    const header = document.createElement('div');
    header.className = 'code-card-header';
    header.innerHTML = `
      <div class="code-card-dots">
        <span class="dot dot-red"></span>
        <span class="dot dot-yellow"></span>
        <span class="dot dot-green"></span>
      </div>
      <span class="code-card-lang">${lang}</span>
      <button type="button" class="code-card-copy-btn" onclick="window.copyCodeFromCard ? window.copyCodeFromCard(this) : copyCodeFromCard(this)" title="کپی کردن کد">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <span>کپی</span>
      </button>
    `;

    // Wrap
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(header);
    wrapper.appendChild(pre);

    // Apply Highlight.js syntax highlighting
    if (window.hljs && code) {
      try {
        hljs.highlightElement(code);
      } catch (e) {}
    }
  });
}

function copyCodeFromCard(btn) {
  const card = btn.closest('.code-card-wrapper');
  const codeEl = card.querySelector('pre code') || card.querySelector('pre');
  if (codeEl) {
    navigator.clipboard.writeText(codeEl.textContent || '').then(() => {
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span>✓ کپی شد!</span>`;
      btn.classList.add('copied');
      setTimeout(() => {
        btn.innerHTML = origHtml;
        btn.classList.remove('copied');
      }, 2000);
    });
  }
}

window.enhanceCodeBlocks = enhanceCodeBlocks;
window.copyCodeFromCard = copyCodeFromCard;

// --- Modern Toast Notification Helper ---
function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('global-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'global-toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ'
  };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || 'ℹ'}</div>
    <div class="toast-msg">${message}</div>
    <button type="button" class="toast-close" onclick="this.closest('.toast').remove()">✕</button>
  `;

  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('toast-show');
  });

  const timer = setTimeout(() => {
    toast.classList.remove('toast-show');
    toast.classList.add('toast-hide');
    setTimeout(() => toast.remove(), 300);
  }, duration);

  toast.addEventListener('mouseenter', () => clearTimeout(timer));
}

window.showToast = showToast;

// Automatically enhance code blocks on page load
document.addEventListener('DOMContentLoaded', () => {
  enhanceCodeBlocks(document.body);
});

// --- Modern Project Deletion with Custom Non-Blocking Modal ---
let pendingDeleteProjectId = null;

function promptDeleteProject(projectId, projectTitle = '') {
  pendingDeleteProjectId = projectId;
  let modal = document.getElementById('delete-project-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'delete-project-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-content" style="max-width: 480px; border: 1px solid rgba(239, 68, 68, 0.4);">
        <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; color: #ef4444;">
          <span style="font-size: 1.5rem;">⚠️</span>
          <h3 style="margin: 0; color: #f8fafc;">حذف کامل پروژه ترجمه</h3>
        </div>
        <p style="color: #cbd5e1; font-size: 0.92rem; line-height: 1.7; margin-bottom: 1.5rem;">
          آیا از حذف کامل این پروژه <strong id="delete-modal-project-title" style="color: #f1f5f9;"></strong> اطمینان دارید؟
          <br>
          <span style="font-size: 0.82rem; color: #94a3b8;">تمام صفحات استخراج‌شده، تصاویر و ترجمه‌ها برای همیشه پاک خواهند شد. این عملیات غیرقابل بازگشت است.</span>
        </p>
        <div style="display: flex; justify-content: flex-end; gap: 0.75rem;">
          <button class="btn btn-secondary" onclick="closeModal('delete-project-modal')">انصراف</button>
          <button class="btn btn-danger" id="confirm-delete-project-btn" onclick="executeDeleteProject()">بله، حذف کن</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  const titleEl = document.getElementById('delete-modal-project-title');
  if (titleEl) titleEl.textContent = projectTitle ? `«${projectTitle}»` : '';
  openModal('delete-project-modal');
}

async function executeDeleteProject() {
  if (!pendingDeleteProjectId) return;
  const btn = document.getElementById('confirm-delete-project-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'در حال حذف...';
  }
  try {
    const res = await fetch(`/api/projects/${pendingDeleteProjectId}`, { method: 'DELETE' });
    if (res.ok) {
      if (window.showToast) showToast('پروژه با موفقیت حذف شد.', 'success');
      setTimeout(() => {
        window.location.href = '/';
      }, 400);
    } else {
      if (window.showToast) showToast('خطا در حذف پروژه.', 'error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'بله، حذف کن';
      }
    }
  } catch (err) {
    if (window.showToast) showToast('خطا در حذف پروژه: ' + err.message, 'error');
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'بله، حذف کن';
    }
  }
}

function deleteProject(projectId, projectTitle = '') {
  promptDeleteProject(projectId, projectTitle);
}

window.promptDeleteProject = promptDeleteProject;
window.executeDeleteProject = executeDeleteProject;
window.deleteProject = deleteProject;

// --- Reading Mode Themes & Appearance Manager ---
const READER_THEMES = ['dark', 'paper', 'sepia', 'sage'];
const DEFAULT_READER_THEME = 'dark';

function getSavedReaderTheme() {
  try {
    const saved = localStorage.getItem('pdf_translator_reader_theme');
    if (saved && READER_THEMES.includes(saved)) return saved;
  } catch (e) {}
  return DEFAULT_READER_THEME;
}

function setReaderTheme(theme) {
  if (!READER_THEMES.includes(theme)) theme = DEFAULT_READER_THEME;
  try {
    localStorage.setItem('pdf_translator_reader_theme', theme);
  } catch (e) {}
  applyReaderTheme(theme);
}

function cycleReaderTheme() {
  const current = getSavedReaderTheme();
  const nextIdx = (READER_THEMES.indexOf(current) + 1) % READER_THEMES.length;
  setReaderTheme(READER_THEMES[nextIdx]);
}

function applyReaderTheme(theme) {
  if (!READER_THEMES.includes(theme)) theme = DEFAULT_READER_THEME;
  const themeClass = `reader-theme-${theme}`;

  // 1. Apply to reader modal dialog & overlay if present
  const modal = document.getElementById('reader-modal');
  if (modal) {
    const dialog = modal.querySelector('.reader-modal-dialog') || modal;
    READER_THEMES.forEach(t => {
      modal.classList.remove(`reader-theme-${t}`);
      dialog.classList.remove(`reader-theme-${t}`);
    });
    modal.classList.add(themeClass);
    dialog.classList.add(themeClass);
  }

  // 2. Apply to chapter modals if present
  const chapterDialog = document.getElementById('view-chapter-dialog');
  if (chapterDialog) {
    READER_THEMES.forEach(t => {
      chapterDialog.classList.remove(`reader-theme-${t}`);
      if (chapterDialog.parentElement) chapterDialog.parentElement.classList.remove(`reader-theme-${t}`);
    });
    chapterDialog.classList.add(themeClass);
    if (chapterDialog.parentElement) chapterDialog.parentElement.classList.add(themeClass);
  }
  // 3. Apply to workspace inline reading paper
  const inlineReader = document.getElementById('reading-mode-container');
  if (inlineReader) {
    READER_THEMES.forEach(t => inlineReader.classList.remove(`reader-theme-${t}`));
    inlineReader.classList.add(themeClass);
  }

  // 4. Apply to book_reader wrapper
  const bookReaderWrapper = document.getElementById('book-reader-wrapper');
  if (bookReaderWrapper) {
    READER_THEMES.forEach(t => bookReaderWrapper.classList.remove(`reader-theme-${t}`));
    bookReaderWrapper.classList.add(themeClass);
    
    // Also update body background on full book reader view
    READER_THEMES.forEach(t => document.body.classList.remove(`reader-page-theme-${t}`));
    document.body.classList.add(`reader-page-theme-${theme}`);
  }

  // 5. Apply to all .reading-book-paper cards
  document.querySelectorAll('.reading-book-paper').forEach(el => {
    READER_THEMES.forEach(t => el.classList.remove(`reader-theme-${t}`));
    el.classList.add(themeClass);
  });

  // 6. Update active states on any theme chip buttons in UI
  document.querySelectorAll('.theme-chip').forEach(chip => {
    if (chip.getAttribute('data-theme') === theme) {
      chip.classList.add('active');
    } else {
      chip.classList.remove('active');
    }
  });
}

// Auto-initialize reading theme on page load
document.addEventListener('DOMContentLoaded', () => {
  const currentTheme = getSavedReaderTheme();
  applyReaderTheme(currentTheme);
});

window.READER_THEMES = READER_THEMES;
window.getSavedReaderTheme = getSavedReaderTheme;
window.setReaderTheme = setReaderTheme;
window.cycleReaderTheme = cycleReaderTheme;
window.applyReaderTheme = applyReaderTheme;
