(() => {
  'use strict';

  const INDICATORS = ['T1', 'T2', 'E1', 'E2', 'S1', 'S2', 'B1', 'B2', 'C1', 'C2'];
  const SHORT_LABELS = {
    T1: 'Дороги', T2: 'Транспорт', E1: 'Зелень', E2: 'Воздух', S1: 'Школы',
    S2: 'Поликлиники', B1: 'Улицы', B2: 'ДТП', C1: 'ЖКХ', C2: 'Обращения',
  };
  let mode = 'after';
  let selectedQuarter = 8;
  let animationKey = '';
  let animationTimers = [];

  const getState = () => (typeof state !== 'undefined' ? state : window.state || {});
  const select = (selector) => document.querySelector(selector);
  const theme = () => window.QQTheme;

  function deltaColor(value) {
    const colors = theme();
    const strength = Math.min(1, Math.abs(Number(value)) / 10);
    if (value > 0) return colors.alpha(colors.colors.high, .16 + strength * .64);
    if (value < 0) return colors.alpha(colors.colors.low, .16 + strength * .64);
    return colors.colors.line;
  }

  function clearAnimation() {
    animationTimers.forEach((timer) => window.clearTimeout(timer));
    animationTimers = [];
  }

  function matrixMarkup(districts, names, selectedMode, animate) {
    const headers = INDICATORS.map((code) =>
      `<div class="matrix-code" title="${code} · ${names[code] || code}">${SHORT_LABELS[code]}</div>`
    ).join('');
    let cellIndex = 0;
    const rows = districts.map((district) => {
      const cells = INDICATORS.map((code) => {
        const before = Number(district.indicators_before[code]);
        const after = Number(district.indicators_after[code]);
        const value = selectedMode === 'before' ? before : selectedMode === 'delta' ? after - before : after;
        const display = selectedMode === 'delta'
          ? `${value > 0 ? '+' : ''}${value.toFixed(1)}`
          : value.toFixed(1);
        const target = selectedMode === 'delta' ? deltaColor(value) : theme().scale(value);
        const background = animate ? theme().scale(before) : target;
        const title = `${district.name} · ${code} «${names[code] || code}»: ${display}`;
        const critical = selectedMode !== 'delta' && value < 40 ? ' matrix-cell-critical' : '';
        const animation = animate ? ` data-matrix-target="${target}" data-matrix-order="${cellIndex++}"` : '';
        return `<div class="matrix-cell${critical}" style="background:${background}"${animation} title="${title}" aria-label="${title}">${display}</div>`;
      }).join('');
      return `<div class="matrix-row-label">${district.name}</div>${cells}`;
    }).join('');
    return `<div class="matrix-grid"><div></div>${headers}${rows}</div>`;
  }

  function resultDistricts(result) {
    const point = window.QQTrajectory?.getPoint?.();
    const quarterById = new Map((point?.districts || []).map((district) => [district.id, district]));
    return result.districts.map((district) => ({
      id: district.id,
      name: district.name,
      indicators_before: district.indicators_before,
      indicators_after: quarterById.get(district.id)?.indicators || district.indicators_after,
    }));
  }

  function baselineDistricts(catalog) {
    return (catalog.districts || []).map((district) => ({
      name: district.name,
      indicators_before: district.indicators,
      indicators_after: district.indicators,
    }));
  }

  function renderBaseline() {
    const catalog = getState().catalog;
    const container = select('#baseline-matrix');
    if (!container || !catalog?.districts) return;
    container.innerHTML = matrixMarkup(
      baselineDistricts(catalog),
      catalog.indicator_names || {},
      'after',
      false,
    );
  }

  function renderResult() {
    const currentState = getState();
    const result = currentState.result;
    const container = select('#indicator-matrix');
    if (!container || !result?.valid || !Array.isArray(result.districts)) return;
    const key = JSON.stringify(result.selections || []);
    const animate = mode === 'after' && key !== animationKey && !theme().reducedMotion();
    if (animate) animationKey = key;
    clearAnimation();
    container.innerHTML = matrixMarkup(
      resultDistricts(result),
      currentState.catalog?.indicator_names || {},
      mode,
      animate,
    );
    const legend = select('#matrix-legend');
    if (legend) {
      legend.textContent = mode === 'delta'
        ? 'Δ показывает изменение: зелёный — рост, красный — снижение.'
        : 'Визуальная шкала: красный < 45, янтарный 45–65, зелёный > 65. Критический порог расчёта — ниже 40.';
    }
    if (animate) {
      container.querySelectorAll('[data-matrix-target]').forEach((cell) => {
        const timer = window.setTimeout(() => {
          cell.style.background = cell.dataset.matrixTarget;
        }, Number(cell.dataset.matrixOrder) * 40);
        animationTimers.push(timer);
      });
    }
  }

  function mountQuarterControl() {
    const matrix = select('#indicator-matrix');
    const section = matrix?.closest('.indicator-views');
    if (!section || select('#trajectory-quarter-control')) return;
    const control = document.createElement('div');
    control.id = 'trajectory-quarter-control';
    control.setAttribute('role', 'group');
    control.setAttribute('aria-label', 'Горизонт прогноза');
    control.className = 'trajectory-quarter-control';
    const horizons = { 1: '3 месяца', 2: 'полгода', 4: 'год', 8: '2 года' };
    control.innerHTML = `<span class="trajectory-quarter-label">Прогноз:</span>${[1, 2, 4, 8].map((quarter) => `<button type="button" data-trajectory-quarter="${quarter}" aria-pressed="${quarter === selectedQuarter}" class="trajectory-quarter-button${quarter === selectedQuarter ? ' active' : ''}">${horizons[quarter]}</button>`).join('')}`;
    const note = document.createElement('p');
    note.className = 'trajectory-delay-note';
    note.textContent = 'Эффект мер наступает с задержкой: школы и ЖКХ дают результат позже, освещение и сервисы — быстрее.';
    const toolbar = section.querySelector('.matrix-toolbar');
    if (toolbar) toolbar.before(control);
    else matrix.before(control);
    control.after(note);
    control.addEventListener('click', (event) => {
      const button = event.target.closest('[data-trajectory-quarter]');
      if (!button) return;
      selectedQuarter = Number(button.dataset.trajectoryQuarter);
      control.querySelectorAll('[data-trajectory-quarter]').forEach((item) => {
        const active = item === button;
        item.classList.toggle('active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      window.QQTrajectory?.selectQuarter?.(selectedQuarter);
      renderResult();
    });
  }

  function mount() {
    const resultScreen = select('#result-screen');
    mountQuarterControl();
    document.querySelectorAll('[data-matrix-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        mode = button.dataset.matrixMode;
        document.querySelectorAll('[data-matrix-mode]').forEach((item) => {
          const active = item === button;
          item.classList.toggle('active', active);
          item.setAttribute('aria-pressed', String(active));
        });
        renderResult();
      });
    });
    if (resultScreen) {
      new MutationObserver(() => {
        if (!resultScreen.classList.contains('hidden')) renderResult();
      }).observe(resultScreen, { attributes: true, attributeFilter: ['class'] });
      if (!resultScreen.classList.contains('hidden')) renderResult();
    }
    renderBaseline();
    window.addEventListener('qq:catalog-ready', renderBaseline);
    window.addEventListener('qq:trajectory-quarter', (event) => {
      selectedQuarter = Number(event.detail?.quarter || 8);
      document.querySelectorAll('[data-trajectory-quarter]').forEach((item) => {
        const active = Number(item.dataset.trajectoryQuarter) === selectedQuarter;
        item.classList.toggle('active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      renderResult();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
