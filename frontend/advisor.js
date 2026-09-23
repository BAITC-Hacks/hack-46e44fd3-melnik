(() => {
  'use strict';

  const select = (selector) => document.querySelector(selector);
  const safeHtml = (value) => {
    if (typeof escapeHtml === 'function') return escapeHtml(value);
    return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
    })[char]);
  };
  const endpoint = (path) => {
    if (typeof api === 'function') return api(path);
    const base = typeof API_BASE !== 'undefined'
      ? API_BASE
      : (window.location.protocol === 'file:' ? 'http://localhost:8000' : '');
    return `${base}${path}`;
  };
  const appState = () => (typeof state !== 'undefined' ? state : window.state || {});
  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
  const formatNumber = (value, digits = 2) => {
    const parsed = number(value);
    return parsed === null ? '—' : parsed.toFixed(digits);
  };
  let renderedCandidates = [];
  let renderedCondition = '';

  function mount() {
    const resultScreen = select('#result-screen');
    if (!resultScreen || select('#advisor-section')) return;

    const section = document.createElement('section');
    section.id = 'advisor-section';
    section.className = 'result-section advisor-section';
    section.innerHTML = `
      <div class="advisor-heading">
        <div>
          <p class="eyebrow">Советник акима</p>
          <h2>Задайте приоритеты словами</h2>
          <p>Опишите словами, что важно, — советник найдёт допустимые варианты, код их пересчитает.</p>
        </div>
        <span id="advisor-source" class="advisor-source hidden"></span>
      </div>
      <form id="advisor-form" class="advisor-form">
        <label class="advisor-label" for="advisor-message">Как изменить текущий сценарий?</label>
        <div class="advisor-input-row">
          <input id="advisor-message" type="text" autocomplete="off"
            placeholder="Например: без ЛРТ и обязательно с экологией" required>
          <button id="advisor-submit" class="primary-button" type="submit">Спросить ИИ</button>
        </div>
        <div class="advisor-examples" aria-label="Примеры запросов">
          <button type="button" data-advisor-example="Без ЛРТ и обязательно с экологией">Без ЛРТ + экология</button>
          <button type="button" data-advisor-example="Найди максимальный Score без ЛРТ">Максимум без ЛРТ</button>
        </div>
      </form>
      <div id="advisor-status" class="advisor-status" role="status" aria-live="polite"></div>
      <div id="advisor-output" class="advisor-output hidden"></div>`;

    resultScreen.appendChild(section);
    select('#advisor-form').addEventListener('submit', requestAdvice);
    select('#advisor-output').addEventListener('click', applyCandidate);
    section.querySelectorAll('[data-advisor-example]').forEach((button) => {
      button.addEventListener('click', () => {
        select('#advisor-message').value = button.dataset.advisorExample;
        select('#advisor-message').focus();
      });
    });
  }

  async function requestAdvice(event) {
    event.preventDefault();
    const messageInput = select('#advisor-message');
    const button = select('#advisor-submit');
    const status = select('#advisor-status');
    const output = select('#advisor-output');
    const message = messageInput.value.trim();
    if (!message) return;

    button.disabled = true;
    button.textContent = 'Ищем сценарии…';
    status.className = 'advisor-status loading';
    status.textContent = 'ИИ разбирает ограничения, затем код проверяет все допустимые варианты.';
    output.classList.add('hidden');

    try {
      const currentState = appState();
      const response = await fetch(endpoint('/api/advise'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_scenario: currentState.result?.selections ?? [],
          message,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : data.detail?.message;
        throw new Error(detail || 'Не удалось получить рекомендацию');
      }
      renderAdvice(data, message);
      status.textContent = '';
      status.className = 'advisor-status';
    } catch (error) {
      status.className = 'advisor-status error';
      status.textContent = error instanceof Error ? error.message : 'AI-советник временно недоступен';
    } finally {
      button.disabled = false;
      button.textContent = 'Спросить ИИ';
    }
  }

  function scenarioSelections(candidate) {
    const scenario = candidate?.scenario ?? candidate?.selections ?? [];
    if (Array.isArray(scenario)) return scenario;
    return Array.isArray(scenario?.selections) ? scenario.selections : [];
  }

  function measureId(selection) {
    return selection?.measure_id ?? selection?.id ?? '';
  }

  function measureLabel(selection) {
    const currentState = appState();
    const id = measureId(selection);
    const measure = currentState.catalog?.measures?.find((item) => item.id === id);
    const districtId = selection?.district_id;
    const district = currentState.catalog?.districts?.find((item) => item.id === districtId);
    const placement = district ? ` · ${district.name}` : '';
    return `${id}${measure ? ` · ${measure.name}` : ''}${placement}`;
  }

  function selectionKey(selection) {
    return `${measureId(selection)}:${selection?.district_id ?? 'city'}`;
  }

  function scenarioDiff(candidate) {
    if (candidate?.diff_vs_current && typeof candidate.diff_vs_current === 'object') {
      return candidate.diff_vs_current;
    }
    const currentSelections = appState().result?.selections ?? [];
    const proposed = scenarioSelections(candidate);
    const currentKeys = new Set(currentSelections.map(selectionKey));
    const proposedKeys = new Set(proposed.map(selectionKey));
    return {
      added: proposed.filter((item) => !currentKeys.has(selectionKey(item))),
      removed: currentSelections.filter((item) => !proposedKeys.has(selectionKey(item))),
    };
  }

  function diffMarkup(candidate) {
    const diff = scenarioDiff(candidate);
    if (typeof diff === 'string') return `<p class="candidate-diff">${safeHtml(diff)}</p>`;
    if (typeof diff === 'number') return '';
    const added = diff?.added ?? diff?.add ?? [];
    const removed = diff?.removed ?? diff?.remove ?? [];
    if (!added.length && !removed.length) return '<p class="candidate-diff muted">Набор мер не изменился</p>';
    return `<div class="candidate-diff">
      ${removed.length ? `<span class="diff-remove">− ${removed.map(measureLabel).map(safeHtml).join(', ')}</span>` : ''}
      ${added.length ? `<span class="diff-add">+ ${added.map(measureLabel).map(safeHtml).join(', ')}</span>` : ''}
    </div>`;
  }

  function candidateCard(candidate, index) {
    const selectionsList = scenarioSelections(candidate);
    const currentScore = number(appState().result?.score);
    const candidateScore = number(candidate?.score ?? candidate?.result?.score);
    const delta = number(candidate?.diff_vs_current?.score ?? candidate?.score_delta)
      ?? (currentScore !== null && candidateScore !== null ? candidateScore - currentScore : null);
    const cost = candidate?.cost ?? candidate?.cost_total ?? candidate?.result?.cost_total;
    return `<article class="advisor-candidate ${index === 0 ? 'recommended' : ''}">
      <div class="candidate-rank"><span>${index === 0 ? 'Рекомендация' : `Вариант ${index + 1}`}</span><b>#${index + 1}</b></div>
      <div class="candidate-metrics">
        <div><span>Score</span><strong>${formatNumber(candidateScore)}</strong></div>
        <div><span>К текущему</span><strong class="${delta !== null && delta < 0 ? 'negative' : ''}">${delta === null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`}</strong></div>
        <div><span>Бюджет</span><strong>${formatNumber(cost, 0)}</strong></div>
      </div>
      <div class="candidate-measures">${selectionsList.map((item) => `<span>${safeHtml(measureLabel(item))}</span>`).join('')}</div>
      ${diffMarkup(candidate)}
      <button type="button" class="candidate-apply" data-candidate-index="${index}">Применить сценарий</button>
    </article>`;
  }

  async function applyCandidate(event) {
    const button = event.target.closest('[data-candidate-index]');
    if (!button) return;
    const index = Number(button.dataset.candidateIndex);
    const candidate = renderedCandidates[index];
    const scenario = scenarioSelections(candidate);
    if (!scenario.length || typeof window.QQApp?.applyScenario !== 'function') return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Проверяем кодом…';
    try {
      await window.QQApp.applyScenario(scenario, renderedCondition);
    } catch (error) {
      const status = select('#advisor-status');
      status.className = 'advisor-status error';
      status.textContent = error instanceof Error ? error.message : 'Не удалось применить сценарий';
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function constraintsMarkup(constraints) {
    if (!constraints || typeof constraints !== 'object') return '';
    const labels = [];
    const mappings = [
      ['exclude', 'Исключить'],
      ['require_measures', 'Обязательно'],
      ['require_directions', 'Направление'],
    ];
    mappings.forEach(([key, title]) => {
      const values = Array.isArray(constraints[key]) ? constraints[key] : [];
      values.forEach((value) => labels.push(`<span><b>${safeHtml(title)}:</b> ${safeHtml(value)}</span>`));
    });
    if (constraints.objective) labels.push(`<span><b>Цель:</b> ${safeHtml(constraints.objective)}</span>`);
    return labels.length ? `<div class="advisor-constraints">${labels.join('')}</div>` : '';
  }

  function renderAdvice(data, condition) {
    const output = select('#advisor-output');
    const candidates = Array.isArray(data.candidates) ? data.candidates.slice(0, 3) : [];
    renderedCandidates = candidates;
    renderedCondition = String(condition || '').trim().slice(0, 120);
    const source = String(data.source ?? data.mode ?? (data.fallback ? 'fallback' : 'openai'));
    const isFallback = source.toLowerCase().includes('fallback') || source.toLowerCase().includes('резерв');
    const sourceBadge = select('#advisor-source');
    sourceBadge.textContent = isFallback ? 'поиск без LLM' : 'OpenAI + инструменты';
    sourceBadge.className = `advisor-source ${isFallback ? 'fallback' : ''}`;

    const current = appState().result ?? {};
    const recommendation = data.recommendation_text || (isFallback
      ? 'OpenAI API недоступен. Показаны лучшие варианты, найденные детерминированным поиском по формальным ограничениям.'
      : 'Допустимые сценарии найдены и проверены симулятором.');
    output.innerHTML = `
      ${constraintsMarkup(data.parsed_constraints)}
      <div class="advisor-comparison">
        <article class="advisor-current">
          <span>Текущий сценарий</span>
          <strong>${formatNumber(current.score)}</strong>
          <small>${formatNumber(current.cost_total, 0)} из 100 ед.</small>
        </article>
        <div class="comparison-arrow" aria-hidden="true">→</div>
        <article class="advisor-best">
          <span>Рекомендованный</span>
          <strong>${formatNumber(candidates[0]?.score ?? candidates[0]?.result?.score)}</strong>
          <small>${formatNumber(candidates[0]?.cost ?? candidates[0]?.cost_total ?? candidates[0]?.result?.cost_total, 0)} из 100 ед.</small>
        </article>
      </div>
      <p class="advisor-recommendation">${safeHtml(recommendation)}</p>
      ${candidates.length
        ? `<div class="advisor-candidates">${candidates.map(candidateCard).join('')}</div>`
        : '<p class="advisor-empty">Под эти ограничения не найдено допустимых сценариев.</p>'}`;
    output.classList.remove('hidden');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
