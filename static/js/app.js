/**
 * app.js — 오답노트 frontend
 *
 * Handles:
 *  - Image upload (drag-drop, file picker, camera)
 *  - Language selection
 *  - API call to /api/analyze
 *  - Result rendering (problem, solution, concept, practice)
 *  - Answer toggle, tab switching
 *  - Print modes (problems-only, answers-only, all)
 */

const App = (() => {
  /* ── State ──────────────────────────────────────────── */
  let selectedFile  = null;
  let previewUrl    = null;   // object URL — must be revoked when replaced
  let language      = 'korean';
  let analysisData  = null;
  let answersShown  = false;
  let cameraStream  = null;

  /* ── DOM references ─────────────────────────────────── */
  const $ = id => document.getElementById(id);

  /* ── Page-unload guard: release camera + object URL ── */
  window.addEventListener('pagehide', () => {
    _stopCamera();
    _revokePreviewUrl();
  });

  /* ══════════════════════════════════════════════════════
     LANGUAGE
     ══════════════════════════════════════════════════════ */
  function setLang(btn) {
    document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    language = btn.dataset.lang;
  }

  /* ══════════════════════════════════════════════════════
     FILE / IMAGE HANDLING
     ══════════════════════════════════════════════════════ */
  function handleFile(event) {
    const file = event.target.files[0];
    if (file) _setPreview(file);
  }

  function handleDrop(event) {
    event.preventDefault();
    $('dropzone').classList.remove('drag-over');
    const file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) _setPreview(file);
  }

  function handleDragOver(event) {
    event.preventDefault();
    $('dropzone').classList.add('drag-over');
  }

  function handleDragLeave() {
    $('dropzone').classList.remove('drag-over');
  }

  function _setPreview(file) {
    _revokePreviewUrl();                     // release previous blob URL
    selectedFile = file;
    previewUrl   = URL.createObjectURL(file);
    $('preview-img').src           = previewUrl;
    $('dz-idle').style.display    = 'none';
    $('dz-preview').style.display = 'flex';
  }

  function _revokePreviewUrl() {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
  }

  function removeImage(event) {
    event.stopPropagation();
    selectedFile = null;
    _revokePreviewUrl();
    $('preview-img').src          = '';
    $('dz-idle').style.display    = 'block';
    $('dz-preview').style.display = 'none';
    $('file-input').value         = '';
  }

  /* ══════════════════════════════════════════════════════
     CAMERA
     ══════════════════════════════════════════════════════ */
  async function openCamera(event) {
    event.stopPropagation();
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      $('cam-video').srcObject        = cameraStream;
      $('camera-modal').style.display = 'flex';
    } catch {
      _toast('카메라를 열 수 없습니다. 브라우저 권한을 확인해주세요.');
    }
  }

  function capturePhoto() {
    const video  = $('cam-video');
    const canvas = $('cam-canvas');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!blob) return;
      const file = new File([blob], 'capture.jpg', { type: 'image/jpeg' });
      _setPreview(file);
      closeCamera();
    }, 'image/jpeg', 0.92);
  }

  function closeCamera() {
    _stopCamera();
    $('camera-modal').style.display = 'none';
  }

  function _stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach(t => t.stop());
      cameraStream = null;
    }
    const video = $('cam-video');
    if (video) video.srcObject = null;
  }

  /* ══════════════════════════════════════════════════════
     ANALYSIS
     ══════════════════════════════════════════════════════ */
  async function analyze() {
    const textInput = $('problem-text').value.trim();
    if (!selectedFile && !textInput) {
      _toast('사진 또는 텍스트로 문제를 입력해주세요.');
      return;
    }

    // Show loading, hide results
    $('loading').style.display   = 'flex';
    $('results').style.display   = 'none';
    $('print-bar').style.display = 'none';
    $('analyze-btn').disabled    = true;

    try {
      const formData = new FormData();
      if (selectedFile) formData.append('image', selectedFile);
      if (textInput)    formData.append('text', textInput);
      formData.append('language', language);

      const res = await fetch('/api/analyze', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || '분석 중 오류가 발생했습니다.');
      }

      analysisData = await res.json();
      _renderResults(analysisData);

    } catch (err) {
      _toast('오류: ' + err.message, 4000);
    } finally {
      $('loading').style.display = 'none';
      $('analyze-btn').disabled  = false;
    }
  }

  /* ══════════════════════════════════════════════════════
     RENDER RESULTS
     ══════════════════════════════════════════════════════ */
  function _renderResults(data) {
    _renderProblemBar(data);
    _renderSolution(data.solution);
    _renderConcept(data.concept);
    _renderPractice(data.similar_problems || []);

    $('results').style.display   = 'block';
    $('print-bar').style.display = 'flex';

    _activateTab('solution');

    // Ask MathJax to typeset everything that was just rendered
    if (window.MathJax?.typesetPromise) {
      MathJax.typesetPromise([$('results')]).catch(console.warn);
    }

    $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* Problem bar — use innerHTML with _esc so MathJax can process LaTeX */
  function _renderProblemBar(data) {
    $('badge-type').textContent  = _typeLabel(data.problem_type);
    $('badge-level').textContent = data.difficulty || '';
    $('problem-statement').innerHTML = _esc(data.problem_text || '');
    $('final-answer').innerHTML      = _esc(data.solution?.final_answer || '');
  }

  /* Solution */
  function _renderSolution(solution) {
    const list = $('solution-steps');
    list.innerHTML = '';
    if (!solution?.steps?.length) {
      list.innerHTML = '<li>풀이를 불러올 수 없습니다.</li>';
      return;
    }
    solution.steps.forEach(step => {
      const li = document.createElement('li');
      // innerHTML + _esc preserves LaTeX delimiters as text nodes for MathJax
      li.innerHTML = _esc(step);
      list.appendChild(li);
    });
  }

  /* Concept */
  function _renderConcept(c) {
    if (!c) return;

    $('concept-title').textContent = c.title || '';
    // concept-def may contain LaTeX — use innerHTML so MathJax can typeset it
    $('concept-def').innerHTML = _esc(c.definition || '');

    // Formulas
    const formulaList = $('formula-list');
    formulaList.innerHTML = '';
    if (c.formulas?.length) {
      $('formulas-block').style.display = 'block';
      c.formulas.forEach(f => {
        const div = document.createElement('div');
        div.className = 'formula-item';
        div.innerHTML = _esc(f);
        formulaList.appendChild(div);
      });
    } else {
      $('formulas-block').style.display = 'none';
    }

    // Key points
    _renderList($('key-points'), c.key_points || []);
    // Mistakes
    _renderList($('common-mistakes'), c.common_mistakes || []);

    // Tip
    if (c.tip) {
      $('concept-tip').textContent = c.tip;
      $('tip-box').style.display   = 'flex';
    } else {
      $('tip-box').style.display   = 'none';
    }
  }

  /* Practice problems */
  function _renderPractice(problems) {
    const container = $('practice-list');
    const ansSheet  = $('answer-sheet-body');
    container.innerHTML = '';
    ansSheet.innerHTML  = '';
    answersShown = false;
    $('toggle-ans-btn').textContent = '👁 답 보기';

    problems.forEach((p, i) => {
      /* ── Practice card ── */
      const card = document.createElement('div');
      card.className = 'practice-card';

      const header = document.createElement('div');
      header.className = 'practice-card-header';
      header.innerHTML = `
        <div class="practice-num" aria-label="문제 ${p.number || i + 1}">${p.number || i + 1}</div>
        <div class="practice-q">${_esc(p.question || '')}</div>
      `;

      const body = document.createElement('div');
      body.className = 'practice-body';

      // Diagram (server-side generated PNG)
      if (p.diagram_image) {
        const dWrap = document.createElement('div');
        dWrap.className = 'practice-diagram';
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${p.diagram_image}`;
        img.alt = `문제 ${i + 1} 그림`;
        dWrap.appendChild(img);
        body.appendChild(dWrap);
      }

      // Answer section (initially hidden)
      const ansSection = document.createElement('div');
      ansSection.className = 'practice-answer-section';

      const toggleBtn = document.createElement('button');
      toggleBtn.className  = 'answer-toggle-btn';
      toggleBtn.innerHTML  = '▶ 풀이 및 정답 보기';
      toggleBtn.setAttribute('aria-expanded', 'false');
      toggleBtn.onclick = () => _toggleCard(ansSection);

      const ansContent = document.createElement('div');
      ansContent.className = 'practice-answer';
      ansContent.innerHTML = `
        <div class="answer-badge">정답: ${_esc(p.answer || '')}</div>
        <ol class="answer-steps">${
          (p.solution_steps || []).map(s => `<li>${_esc(s)}</li>`).join('')
        }</ol>
      `;

      ansSection.appendChild(toggleBtn);
      ansSection.appendChild(ansContent);
      body.appendChild(ansSection);

      card.appendChild(header);
      card.appendChild(body);
      container.appendChild(card);

      /* ── Answer sheet entry (print-only) ── */
      const asEntry = document.createElement('div');
      asEntry.style.marginBottom = '1.5rem';
      asEntry.innerHTML = `
        <p><strong>문제 ${p.number || i + 1}.</strong> ${_esc(p.question || '')}</p>
        <p><strong>정답:</strong> ${_esc(p.answer || '')}</p>
        <ol style="margin-top:.4rem;font-size:.9rem;color:#475569">
          ${(p.solution_steps || []).map(s => `<li>${_esc(s)}</li>`).join('')}
        </ol>
      `;
      ansSheet.appendChild(asEntry);
    });
  }

  /* ══════════════════════════════════════════════════════
     UI HELPERS
     ══════════════════════════════════════════════════════ */
  function switchTab(btn) {
    _activateTab(btn.dataset.tab);
    if (window.MathJax?.typesetPromise) {
      MathJax.typesetPromise([$('panel-' + btn.dataset.tab)]).catch(console.warn);
    }
  }

  function _activateTab(name) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    const panel = $('panel-' + name);
    if (panel) panel.classList.add('active');
  }

  function toggleAnswers() {
    answersShown = !answersShown;
    document.querySelectorAll('.practice-answer').forEach(el => {
      el.classList.toggle('visible', answersShown);
    });
    $('toggle-ans-btn').textContent = answersShown ? '🙈 답 숨기기' : '👁 답 보기';
  }

  function _toggleCard(ansSection) {
    const content = ansSection.querySelector('.practice-answer');
    const btn     = ansSection.querySelector('.answer-toggle-btn');
    const showing = content.classList.toggle('visible');
    btn.innerHTML = showing ? '▼ 풀이 및 정답 숨기기' : '▶ 풀이 및 정답 보기';
    btn.setAttribute('aria-expanded', showing ? 'true' : 'false');
    if (showing && window.MathJax?.typesetPromise) {
      MathJax.typesetPromise([content]).catch(console.warn);
    }
  }

  function _renderList(ul, items) {
    ul.innerHTML = '';
    items.forEach(item => {
      const li = document.createElement('li');
      li.innerHTML = _esc(item);   // innerHTML so MathJax can process LaTeX in list items
      ul.appendChild(li);
    });
  }

  /* ══════════════════════════════════════════════════════
     PRINT
     ══════════════════════════════════════════════════════ */
  function printProblems() {
    _activateTab('practice');
    document.body.classList.add('print-problems-only');
    document.body.classList.remove('print-answers-only');
    setTimeout(() => {
      window.print();
      document.body.classList.remove('print-problems-only');
    }, 300);
  }

  function printAnswers() {
    _activateTab('practice');
    document.body.classList.add('print-answers-only');
    document.body.classList.remove('print-problems-only');
    setTimeout(() => {
      window.print();
      document.body.classList.remove('print-answers-only');
    }, 300);
  }

  function printAll() {
    document.body.classList.remove('print-problems-only', 'print-answers-only');
    // Remember which answers were visible so we can restore after print
    const wasVisible = new Set(
      [...document.querySelectorAll('.practice-answer.visible')].map(
        (el, i) => i
      )
    );
    const allAnswers = [...document.querySelectorAll('.practice-answer')];
    allAnswers.forEach(el => el.classList.add('visible'));

    setTimeout(() => {
      window.print();
      // Restore previous visibility state
      allAnswers.forEach((el, i) => {
        el.classList.toggle('visible', wasVisible.has(i) || answersShown);
      });
    }, 300);
  }

  /* ══════════════════════════════════════════════════════
     UTILITIES
     ══════════════════════════════════════════════════════ */

  /**
   * Escape a string for safe insertion via innerHTML.
   * This keeps LaTeX delimiters (\( \) \[ \]) intact as text
   * while neutralising any HTML special characters.
   */
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _typeLabel(type) {
    const MAP = {
      arithmetic:      '산술',
      linear_equation: '일차방정식',
      quadratic:       '이차방정식',
      function:        '함수',
      geometry:        '도형',
      trigonometry:    '삼각함수',
      calculus:        '미적분',
      statistics:      '통계',
      other:           '기타',
    };
    return MAP[type] || type || '수학';
  }

  function _toast(msg, duration = 2500) {
    const t = $('toast');
    t.textContent   = msg;
    t.style.display = 'block';
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.style.display = 'none'; }, duration);
  }

  /* ── Public API ─────────────────────────────────────── */
  return {
    setLang, handleFile, handleDrop, handleDragOver, handleDragLeave,
    removeImage, openCamera, capturePhoto, closeCamera,
    analyze, switchTab, toggleAnswers,
    printProblems, printAnswers, printAll,
  };
})();
