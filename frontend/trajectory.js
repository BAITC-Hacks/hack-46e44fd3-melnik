(() => {
  'use strict';

  const select = (selector) => document.querySelector(selector);
  const endpoint = (path) => {
    if (typeof api === 'function') return api(path);
    const base = typeof API_BASE !== 'undefined'
      ? API_BASE
      : (window.location.protocol === 'file:' ? 'http://localhost:8000' : '');
    return `${base}${path}`;
  };
  const appState = () => (typeof state !== 'undefined' ? state : window.state || {});
  const format = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—';
  const theme = () => window.QQTheme;
  let trajectoryChart = null;
  let lastScenarioKey = '';

  function mount() {
    const resultScreen = select('#result-screen');
    if (!resultScreen || select('#strategy-dashboard')) return;

    const section = document.createElement('section');
    section.id = 'strategy-dashboard';
    section.className = 'result-section strategy-dashboard';
    section.innerHTML = `
      <div class="section-heading">
        <div>
          <p class="eyebrow">Динамика реализации</p>
          <h2 id="trajectory-title">Что изменится со временем</h2>
        </div>
        <p>Score меняется по мере реализации мер. Индекс городской справедливости — разрыв между лучшим и слабейшим районами: меньше значит справедливее.</p>
      </div>
      <div class="trajectory-chart-card">
        <div id="trajectory-loading" class="trajectory-loading">Строим поквартальную траекторию…</div>
        <canvas id="trajectory-chart" class="hidden"></canvas>
      </div>
      <div class="comparison-heading">
        <div><p class="eyebrow">Три политики</p><h2>Результат зависит от поставленной цели</h2></div>
        <p>Максимум оптимизирует только формулу. Альтернатива добавляет содержательные ограничения: без ЛРТ и с экологической мерой.</p>
      </div>
      <div id="scenario-comparison" class="scenario-comparison">
        <div class="comparison-placeholder">Сравниваем допустимые сценарии…</div>
      </div>`;

    const advisor = select('#advisor-section');
    if (advisor) advisor.before(section);
    else resultScreen.appendChild(section);

    updateHorizonCopy();
    window.addEventListener('qq:catalog-ready', updateHorizonCopy);

    const observer = new MutationObserver(() => {
      if (!resultScreen.classList.contains('hidden')) refresh();
    });
    observer.observe(resultScreen, { attributes: true, attributeFilter: ['class'] });
    if (!resultScreen.classList.contains('hidden')) refresh();
  }

  function updateHorizonCopy() {
    const catalog = appState().catalog;
    const title = select('#trajectory-title');
    if (!title || !catalog?.horizon) return;
    const years = catalog.horizon / 4;
    const display = Number.isInteger(years) ? years : years.toFixed(1);
    title.textContent = `Что изменится за ${display} года`;
  }

  async function post(path, payload) {
    const response = await fetch(endpoint(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Запрос не выполнен');
    return data;
  }

  async function refresh() {
    const current = appState().result;
    if (!current?.valid || !Array.isArray(current.selections)) return;
    const key = JSON.stringify(current.selections);
    if (key === lastScenarioKey) return;
    lastScenarioKey = key;

    select('#trajectory-loading').textContent = 'Строим поквартальную траекторию…';
    select('#trajectory-loading').className = 'trajectory-loading';
    select('#trajectory-chart').classList.add('hidden');
    select('#scenario-comparison').innerHTML = '<div class="comparison-placeholder">Ищем теоретический максимум и альтернативную политику…</div>';

    try {
      const [points, blindMaximum] = await Promise.all([
        post('/api/trajectory', { selections: current.selections }),
        post('/api/advise', {
          current_scenario: current.selections,
          message: 'Найди максимальный Score без дополнительных ограничений',
        }),
      ]);
      renderTrajectory(points);

      const balanced = await post('/api/advise', {
        current_scenario: current.selections,
        message: 'Без ЛРТ и обязательно с экологией',
      });
      renderComparison(current, blindMaximum, balanced);
    } catch (error) {
      select('#trajectory-loading').textContent = error instanceof Error ? error.message : 'Не удалось построить траекторию';
      select('#trajectory-loading').className = 'trajectory-loading error';
      select('#scenario-comparison').innerHTML = '<div class="comparison-placeholder error">Сравнение временно недоступно.</div>';
    }
  }

  function renderTrajectory(points) {
    const canvas = select('#trajectory-chart');
    const loading = select('#trajectory-loading');
    if (!Array.isArray(points) || !points.length) throw new Error('Сервер вернул пустую траекторию');
    loading.classList.add('hidden');
    canvas.classList.remove('hidden');
    if (trajectoryChart) trajectoryChart.destroy();
    if (typeof Chart === 'undefined') {
      canvas.classList.add('hidden');
      loading.textContent = 'Chart.js недоступен, но расчёт траектории выполнен.';
      loading.classList.remove('hidden');
      return;
    }
    trajectoryChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: points.map((item) => `Q${item.quarter}`),
        datasets: [
          {
            label: 'Astana Quality of Life Score',
            data: points.map((item) => item.score),
            yAxisID: 'score',
            borderColor: theme().colors.after,
            backgroundColor: theme().alpha(theme().colors.after, .12),
            borderWidth: 3,
            pointRadius: 4,
            pointBackgroundColor: theme().colors.after,
            tension: .28,
            fill: true,
          },
          {
            label: 'Индекс городской справедливости · меньше лучше',
            data: points.map((item) => item.balance),
            yAxisID: 'balance',
            borderColor: theme().colors.navy,
            borderDash: [7, 5],
            borderWidth: 2,
            pointRadius: 3,
            tension: .28,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, padding: 22 } } },
        scales: {
          score: { type: 'linear', position: 'left', suggestedMin: 48, suggestedMax: 60, title: { display: true, text: 'Score' }, grid: { color: theme().colors.line } },
          balance: { type: 'linear', position: 'right', suggestedMin: 0, title: { display: true, text: 'Разрыв между районами' }, grid: { drawOnChartArea: false } },
          x: { grid: { display: false }, title: { display: true, text: 'Квартал' } },
        },
      },
    });
  }

  function bestCandidate(advice) {
    return Array.isArray(advice?.candidates) ? advice.candidates[0] : null;
  }

  function scenarioMeasures(candidate) {
    const items = candidate?.scenario || candidate?.selections || [];
    return items.map((item) => item.measure_id).join(' · ');
  }

  function policyCard(kind, title, subtitle, score, cost, measures, note) {
    const budget = appState().catalog?.budget;
    return `<article class="policy-card ${kind}">
      <div class="policy-label">${title}</div>
      <p>${subtitle}</p>
      <div class="policy-score"><strong>${format(score)}</strong><span>Score</span></div>
      <div class="policy-cost">${format(cost, 0)} / ${format(budget, 0)} ед.</div>
      <div class="policy-measures">${measures || '—'}</div>
      <small>${note}</small>
    </article>`;
  }

  function renderComparison(current, blindAdvice, balancedAdvice) {
    const blind = bestCandidate(blindAdvice);
    const balanced = bestCandidate(balancedAdvice);
    const currentMeasures = current.selections.map((item) => item.measure_id).join(' · ');
    select('#scenario-comparison').innerHTML = [
      policyCard('current', 'Ваш сценарий', 'Решения пользователя', current.score, current.cost_total, currentMeasures, 'Точка отсчёта для сравнения.'),
      policyCard('blind', 'Теоретический максимум', 'Только максимизация формулы', blind?.score, blind?.cost, scenarioMeasures(blind), 'Может концентрировать меры в одном районе и игнорировать направления.'),
      policyCard('balanced', 'Альтернативная политика', 'Без ЛРТ + обязательная экология', balanced?.score, balanced?.cost, scenarioMeasures(balanced), 'Не «лучше вообще»: это результат при другом наборе приоритетов.'),
    ].join('');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
