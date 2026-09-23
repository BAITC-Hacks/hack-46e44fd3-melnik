(() => {
  'use strict';

  const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : '';
  const api = (path) => `${API_BASE}${path}`;
  const VOTE_KEY = 'qalaqadam-demo-votes-v1';
  const VOTER_KEY = 'qalaqadam-demo-voter-id-v1';
  const $ = (selector, root = document) => root.querySelector(selector);

  let proposals = [];
  let catalog = null;
  let peopleScenario = null;
  let busy = false;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);

  function votedIds() {
    try {
      const parsed = JSON.parse(localStorage.getItem(VOTE_KEY) || '[]');
      return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
    } catch (_) {
      return new Set();
    }
  }

  function markVoted(id) {
    const ids = votedIds();
    ids.add(String(id));
    try { localStorage.setItem(VOTE_KEY, JSON.stringify([...ids])); } catch (_) { /* demo protection is best effort */ }
  }

  function voterId() {
    try {
      let id = localStorage.getItem(VOTER_KEY);
      if (!id) {
        id = globalThis.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(VOTER_KEY, id);
      }
      return id;
    } catch (_) {
      return `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
  }

  function localDistrictName(id) {
    if (!id) return 'Весь город';
    const districts = catalog?.districts || [];
    return districts.find((district) => district.id === id)?.name || String(id);
  }

  function localMeasure(proposal) {
    const id = proposal?.measure_id;
    return (catalog?.measures || []).find((measure) => measure.id === id) || null;
  }

  async function request(path, options = {}) {
    const response = await fetch(api(path), {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail || data.message || 'Не удалось выполнить запрос';
      throw new Error(typeof detail === 'string' ? detail : 'Проверьте предложение и попробуйте ещё раз');
    }
    return data;
  }

  function setStatus(message, type = '') {
    const status = $('#votes-status');
    if (!status) return;
    status.className = `votes-status${type ? ` ${type}` : ''}`;
    status.textContent = message;
  }

  function format(value, digits = 2) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits).replace(/\.00$/, '') : null;
  }

  function append(parent, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    parent.append(element);
    return element;
  }

  function proposalStatus(proposal) {
    const labels = {
      submitted: 'Подано', checked: 'Проверено кодом',
      in_people_scenario: 'В народном сценарии', not_fitted: 'Не вошло',
    };
    return proposal.status_label || labels[proposal.status] || 'Статус не указан';
  }

  function voteLabel(value) {
    const amount = Math.abs(Number(value) || 0);
    const mod100 = amount % 100;
    const mod10 = amount % 10;
    if (mod100 >= 11 && mod100 <= 14) return `${amount} голосов`;
    if (mod10 === 1) return `${amount} голос`;
    if (mod10 >= 2 && mod10 <= 4) return `${amount} голоса`;
    return `${amount} голосов`;
  }

  function effectLines(effects) {
    if (!effects || typeof effects !== 'object') return [];
    if (Array.isArray(effects)) {
      return effects.map((effect) => {
        if (typeof effect === 'string') return effect;
        const name = effect.name || effect.indicator || effect.code;
        const before = format(effect.before);
        const after = format(effect.after);
        const delta = format(effect.delta ?? effect.value);
        if (name && before !== null && after !== null) return `${name}: ${before} → ${after}`;
        if (name && delta !== null) return `${name}: ${Number(delta) > 0 ? '+' : ''}${delta}`;
        return null;
      }).filter(Boolean);
    }
    return Object.entries(effects).map(([name, value]) => {
      const label = catalog?.indicator_names?.[name] || name;
      if (typeof value === 'number' || typeof value === 'string') {
        const number = format(value);
        return number === null ? null : `${label}: ${Number(number) > 0 ? '+' : ''}${number}`;
      }
      if (!value || typeof value !== 'object') return null;
      const before = format(value.before);
      const after = format(value.after);
      const delta = format(value.delta ?? value.value);
      if (before !== null && after !== null) return `${label}: ${before} → ${after}`;
      return delta === null ? null : `${label}: ${Number(delta) > 0 ? '+' : ''}${delta}`;
    }).filter(Boolean);
  }

  function proposalCard(proposal) {
    const card = document.createElement('article');
    card.className = 'vote-proposal-card';
    const top = document.createElement('div');
    top.className = 'vote-proposal-top';
    const title = proposal.measure_title || proposal.measure_name || localMeasure(proposal)?.name || proposal.measure_id || 'Предложение жителя';
    append(top, 'h3', '', title);
    const status = append(top, 'span', `vote-status-badge vote-status-${esc(proposal.status || 'unknown')}`, proposalStatus(proposal));
    status.title = proposal.status_reason || proposal.reason || '';
    card.append(top);

    const district = proposal.district_name || localDistrictName(proposal.district_id);
    const metaParts = [district];
    const cost = proposal.cost ?? localMeasure(proposal)?.cost;
    if (proposal.status !== 'submitted' && cost != null) metaParts.push(`Стоимость: ${cost}`);
    append(card, 'p', 'vote-proposal-meta', metaParts.join(' · '));
    if (proposal.text) append(card, 'p', 'vote-proposal-text', proposal.text);

    if (proposal.status !== 'submitted') {
      const effects = effectLines(proposal.effects || proposal.effect || proposal.evidence?.contribution?.realized_effects || proposal.evidence?.contribution?.effects);
      if (effects.length) {
        const effectBlock = append(card, 'div', 'vote-effects');
        append(effectBlock, 'strong', '', 'Эффект по расчёту');
        const list = document.createElement('ul');
        effects.forEach((line) => append(list, 'li', '', line));
        effectBlock.append(list);
      }
    } else {
      append(
        card,
        'p',
        'vote-unchecked-note',
        proposal.measure_id
          ? 'Мера найдена, но для проверки эффекта уточните район.'
          : 'Не нашли подходящую меру в каталоге',
      );
    }
    const reason = proposal.status_reason || proposal.reason;
    if (reason) append(card, 'p', 'vote-reason', reason);

    const actions = document.createElement('div');
    actions.className = 'vote-proposal-actions';
    const votes = Number.isFinite(Number(proposal.votes)) ? Number(proposal.votes) : 0;
    if (proposal.status !== 'submitted') append(actions, 'span', 'vote-count', voteLabel(votes));
    const didVote = votedIds().has(String(proposal.id));
    const vote = append(actions, 'button', 'primary-button vote-button', didVote ? 'Голос учтён' : 'Поддерживаю');
    vote.type = 'button';
    vote.disabled = didVote || busy;
    vote.addEventListener('click', () => castVote(proposal.id, vote));
    card.append(actions);
    return card;
  }

  function currentSelections() {
    return [...document.querySelectorAll('.measure-card.selected')].map((card) => ({
      measure_id: card.dataset.id,
      district_id: $('.district-select', card)?.value || null,
    })).filter((item) => item.measure_id);
  }

  function scoreFor(data) {
    return data?.score ?? data?.result?.score ?? data?.simulation?.score ?? null;
  }

  function renderComparison(parent, label, result) {
    const score = format(scoreFor(result));
    if (score === null) return;
    const cost = format(result?.cost ?? result?.cost_total, 0);
    const box = append(parent, 'div', 'people-comparison-card');
    append(box, 'span', '', label);
    append(box, 'strong', '', score);
    if (cost !== null) append(box, 'small', '', `Стоимость: ${cost}`);
  }

  function scenarioDistricts(scenario) {
    const districts = scenario?.districts;
    if (Array.isArray(districts)) return districts.map((item) => {
      const id = item.district_id || item.id;
      const score = format(item.score ?? item.D_d ?? item.D_after ?? item.value);
      return `${item.district_name || localDistrictName(id)}${score === null ? '' : `: ${score}`}`;
    });
    if (districts && typeof districts === 'object') return Object.entries(districts).map(([id, value]) => {
      const score = format(typeof value === 'object' ? (value.score ?? value.D_d ?? value.D_after) : value);
      return `${localDistrictName(id)}${score === null ? '' : `: ${score}`}`;
    });
    return [];
  }

  function renderPeopleScenario(data) {
    peopleScenario = data || null;
    const output = $('#people-scenario-output');
    if (!output) return;
    output.replaceChildren();
    const scenario = data?.scenario || data?.plan || {};
    const included = Array.isArray(data?.included) ? data.included : [];
    const excluded = Array.isArray(data?.excluded) ? data.excluded : [];
    const card = append(output, 'article', 'people-scenario-card');
    append(card, 'p', 'eyebrow', 'Народный сценарий');
    append(card, 'h3', '', data?.message || 'План из предложений жителей');

    const metricRow = append(card, 'div', 'people-scenario-metrics');
    const scenarioScore = format(scoreFor(scenario));
    const scenarioCost = format(scenario.cost ?? scenario.cost_total, 0);
    if (scenarioScore !== null) {
      const metric = append(metricRow, 'div', 'people-scenario-metric');
      append(metric, 'span', '', 'Score сценария');
      append(metric, 'strong', '', scenarioScore);
    }
    if (scenarioCost !== null) {
      const metric = append(metricRow, 'div', 'people-scenario-metric');
      append(metric, 'span', '', 'Стоимость');
      append(metric, 'strong', '', scenarioCost);
    }
    const districtLines = scenarioDistricts(scenario);
    if (districtLines.length) {
      const districtBlock = append(card, 'div', 'people-scenario-districts');
      append(districtBlock, 'strong', '', 'Районы');
      const list = document.createElement('ul');
      districtLines.forEach((line) => append(list, 'li', '', line));
      districtBlock.append(list);
    }

    const comparisons = append(card, 'div', 'people-comparisons');
    renderComparison(comparisons, 'Сценарий жителей', scenario);
    const max = data?.blind_max ?? data?.maximum ?? (data?.max_score != null ? { score: data.max_score } : null);
    renderComparison(comparisons, 'Максимум формулы', max);
    renderComparison(comparisons, 'Текущий сценарий', data?.current_scenario);
    if (!comparisons.children.length) comparisons.remove();

    if (included.length) {
      append(card, 'h4', '', 'Вошли в план');
      const list = document.createElement('ul');
      included.forEach((entry) => {
        const proposal = entry.proposal || proposals.find((item) => String(item.id) === String(entry.proposal_id)) || entry;
        const measure = localMeasure({ measure_id: entry.measure_id || proposal.measure_id });
        const votes = entry.votes ?? proposal.votes;
        const name = entry.measure_title || proposal.measure_title || measure?.name || proposal.measure_id || entry.measure_id || entry.proposal_id || 'Предложение';
        const district = entry.district_name || proposal.district_name || localDistrictName(entry.district_id ?? proposal.district_id);
        const bits = [name, district, votes != null ? voteLabel(votes) : null].filter(Boolean);
        append(list, 'li', '', bits.join(' · '));
      });
      card.append(list);
    }
    if (excluded.length) {
      append(card, 'h4', '', 'Не вошли');
      const list = document.createElement('ul');
      excluded.forEach((entry) => {
        const proposal = entry.proposal || proposals.find((item) => String(item.id) === String(entry.proposal_id)) || entry;
        const name = entry.measure_title || proposal.measure_title || proposal.measure_id || entry.measure_id || entry.proposal_id || 'Предложение';
        const reason = entry.reason || proposal.reason || 'Не удалось включить в допустимый план';
        append(list, 'li', 'people-excluded-item', `${name}: ${reason}`);
      });
      card.append(list);
    }

    const selections = scenario.selections || data?.selections;
    if (Array.isArray(selections) && selections.length && typeof window.QQApp?.applyScenario === 'function') {
      const open = append(card, 'button', 'primary-button people-open-button', 'Открыть в симуляторе');
      open.type = 'button';
      open.addEventListener('click', async () => {
        open.disabled = true;
        try { await window.QQApp.applyScenario(selections, 'Народный сценарий'); }
        catch (error) { setStatus(error.message || 'Не удалось открыть сценарий', 'error'); }
        finally { open.disabled = false; }
      });
    }
    output.classList.remove('hidden');
  }

  function renderBoard() {
    const board = $('#votes-board');
    if (!board) return;
    board.replaceChildren();
    const filter = $('#votes-filter')?.value || 'all';
    const sorted = [...proposals].sort((a, b) => (Number(b.votes) || 0) - (Number(a.votes) || 0));
    const filtered = filter === 'all' ? sorted : sorted.filter((proposal) => proposal.status === filter);
    if (!filtered.length) {
      append(board, 'p', 'votes-empty', proposals.length ? 'Нет предложений с выбранным статусом.' : 'Пока нет предложений. Добавьте первое из блока «Голос жителя».');
      return;
    }
    filtered.forEach((proposal) => board.append(proposalCard(proposal)));
  }

  async function loadCatalog() {
    if (catalog) return;
    try {
      const response = await fetch(api('/api/catalog'));
      if (response.ok) catalog = await response.json();
    } catch (_) { /* cards can still render with API-provided names */ }
  }

  async function refresh() {
    setStatus('Загружаем доску…', 'loading');
    try {
      const data = await request('/api/proposals');
      proposals = Array.isArray(data.proposals) ? data.proposals : Array.isArray(data) ? data : [];
      if (data.people_scenario) renderPeopleScenario(data.people_scenario);
      renderBoard();
      setStatus(proposals.length ? `Предложений на доске: ${proposals.length}. Демо без авторизации.` : 'Доска пока пустая. Демо без авторизации.');
    } catch (error) {
      setStatus(error.message || 'Не удалось загрузить доску голосования', 'error');
      $('#votes-board')?.replaceChildren();
      append($('#votes-board'), 'p', 'votes-empty', 'Доска временно недоступна. Проверьте соединение с сервером.');
    }
  }

  async function castVote(id, button) {
    if (votedIds().has(String(id))) return;
    button.disabled = true;
    try {
      const data = await request(`/api/proposals/${encodeURIComponent(id)}/vote`, {
        method: 'POST', body: JSON.stringify({ voter_id: voterId() }),
      });
      markVoted(id);
      const updated = data.proposal || data;
      if (updated && updated.id != null) proposals = proposals.map((proposal) => String(proposal.id) === String(id) ? { ...proposal, ...updated } : proposal);
      await refresh();
    } catch (error) {
      button.disabled = false;
      setStatus(error.message || 'Голос не принят', 'error');
    }
  }

  async function buildPeopleScenario() {
    const button = $('#build-people-scenario');
    button.disabled = true;
    setStatus('Ищем допустимый план по поддержанным предложениям…', 'loading');
    try {
      const data = await request('/api/proposals/people-scenario', {
        method: 'POST',
        body: JSON.stringify({ current_scenario: currentSelections() }),
      });
      renderPeopleScenario(data);
      setStatus('Народный сценарий пересчитан симулятором.');
    } catch (error) {
      setStatus(error.message || 'Не удалось собрать народный сценарий', 'error');
    } finally {
      button.disabled = false;
    }
  }

  async function clearBoard() {
    if (!window.confirm('Очистить предложения и голоса демо-доски?')) return;
    const button = $('#clear-votes-board');
    button.disabled = true;
    try {
      await request('/api/proposals', { method: 'DELETE' });
      proposals = [];
      peopleScenario = null;
      $('#people-scenario-output')?.replaceChildren();
      try { localStorage.removeItem(VOTE_KEY); } catch (_) { /* optional */ }
      await refresh();
      setStatus('Демо-доска очищена.');
    } catch (error) {
      setStatus(error.message || 'Не удалось очистить доску', 'error');
    } finally {
      button.disabled = false;
    }
  }

  function bind() {
    $('#votes-refresh')?.addEventListener('click', refresh);
    $('#votes-filter')?.addEventListener('change', renderBoard);
    $('#build-people-scenario')?.addEventListener('click', buildPeopleScenario);
    $('#clear-votes-board')?.addEventListener('click', clearBoard);
  }

  async function mount() {
    const root = $('#resident-voting');
    if (!root || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    root.classList.add('result-section', 'votes-section');
    root.innerHTML = `
      <div class="votes-heading">
        <div><p class="eyebrow">Участие жителей</p><h2>Голосование жителей</h2>
        <p>Как в «Бюджете народного участия» — только эффект каждого предложения виден до голосования.</p></div>
        <span class="votes-demo-badge">демо без авторизации</span>
      </div>
      <div class="votes-toolbar">
        <label class="votes-filter-label">Статус
          <select id="votes-filter"><option value="all">Все предложения</option>
            <option value="submitted">Подано</option><option value="checked">Проверено кодом</option>
            <option value="in_people_scenario">В народном сценарии</option><option value="not_fitted">Не вошло</option>
          </select>
        </label>
        <button type="button" class="votes-secondary-button" id="votes-refresh">Обновить</button>
        <button type="button" class="votes-secondary-button" id="clear-votes-board">Очистить демо-доску</button>
      </div>
      <p id="votes-status" class="votes-status" role="status" aria-live="polite"></p>
      <div class="digest-trigger"><button type="button" class="votes-secondary-button" id="generate-digest">Сводка для акимата</button></div>
      <div id="votes-board" class="votes-board"></div>
      <section id="proposal-digest" aria-live="polite"></section>
      <div class="people-scenario-cta"><div><h3>Собрать народный сценарий</h3><p>Код по очереди проверит самые поддержанные предложения и соберёт допустимый план.</p></div>
        <button type="button" class="primary-button" id="build-people-scenario">Собрать народный сценарий</button></div>
      <div id="people-scenario-output" class="people-scenario-output hidden"></div>`;
    bind();
    await loadCatalog();
    await refresh();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
  window.QQVotes = Object.freeze({ mount, refresh });
})();
