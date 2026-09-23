(() => {
  'use strict';

  const INDICATORS = ['T1', 'T2', 'E1', 'E2', 'S1', 'S2', 'B1', 'B2', 'C1', 'C2'];
  const SHORT_LABELS = {
    T1: 'Дороги', T2: 'Транспорт', E1: 'Зелень', E2: 'Воздух', S1: 'Школы',
    S2: 'Поликлиники', B1: 'Улицы', B2: 'ДТП', C1: 'ЖКХ', C2: 'Обращения',
  };
  let mode = 'after';
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
    return result.districts.map((district) => ({
      name: district.name,
      indicators_before: district.indicators_before,
      indicators_after: district.indicators_after,
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

  function mount() {
    const resultScreen = select('#result-screen');
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
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
