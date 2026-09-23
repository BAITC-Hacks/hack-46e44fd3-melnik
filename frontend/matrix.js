(() => {
  'use strict';

  const INDICATORS = ['T1', 'T2', 'E1', 'E2', 'S1', 'S2', 'B1', 'B2', 'C1', 'C2'];
  let mode = 'after';

  const getState = () => (typeof state !== 'undefined' ? state : window.state || {});
  const select = (selector) => document.querySelector(selector);

  function qualityColor(value) {
    const bounded = Math.max(0, Math.min(100, Number(value)));
    if (bounded < 40) return `hsl(${4 + bounded * .25} 60% ${84 - bounded * .38}%)`;
    if (bounded < 70) return `hsl(${38 + (bounded - 40) * .55} 67% ${79 - (bounded - 40) * .2}%)`;
    return `hsl(${102 + (bounded - 70) * .45} 37% ${72 - (bounded - 70) * .25}%)`;
  }

  function deltaColor(value) {
    const strength = Math.min(1, Math.abs(value) / 10);
    return value > 0
      ? `rgba(45, 149, 108, ${.15 + strength * .65})`
      : value < 0
        ? `rgba(180, 60, 56, ${.15 + strength * .65})`
        : '#eef0eb';
  }

  function cellValue(district, code) {
    const before = Number(district.indicators_before[code]);
    const after = Number(district.indicators_after[code]);
    if (mode === 'before') return before;
    if (mode === 'delta') return after - before;
    return after;
  }

  function render() {
    const currentState = getState();
    const result = currentState.result;
    const container = select('#indicator-matrix');
    if (!container || !result?.valid || !Array.isArray(result.districts)) return;

    const names = currentState.catalog?.indicator_names || {};
    const headers = INDICATORS.map((code) =>
      `<div class="matrix-code" title="${names[code] || code}">${code}</div>`
    ).join('');
    const rows = result.districts.map((district) => {
      const cells = INDICATORS.map((code) => {
        const value = cellValue(district, code);
        const display = mode === 'delta'
          ? `${value > 0 ? '+' : ''}${value.toFixed(1)}`
          : value.toFixed(1);
        const background = mode === 'delta' ? deltaColor(value) : qualityColor(value);
        const title = `${district.name} · ${code} «${names[code] || code}»: ${display}`;
        return `<div class="matrix-cell" style="background:${background}" title="${title}" aria-label="${title}">${display}</div>`;
      }).join('');
      return `<div class="matrix-row-label">${district.name}</div>${cells}`;
    }).join('');

    container.innerHTML = `<div class="matrix-grid"><div></div>${headers}${rows}</div>`;
    select('#matrix-legend').textContent = mode === 'delta'
      ? 'Δ показывает изменение: зелёный — рост, красный — снижение.'
      : 'Единая шкала: красный < 40, жёлтый 40–69, зелёный ≥ 70.';
  }

  function mount() {
    const resultScreen = select('#result-screen');
    if (!resultScreen || !select('#indicator-matrix')) return;

    document.querySelectorAll('[data-matrix-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        mode = button.dataset.matrixMode;
        document.querySelectorAll('[data-matrix-mode]').forEach((item) => {
          const active = item === button;
          item.classList.toggle('active', active);
          item.setAttribute('aria-pressed', String(active));
        });
        render();
      });
    });

    new MutationObserver(() => {
      if (!resultScreen.classList.contains('hidden')) render();
    }).observe(resultScreen, { attributes: true, attributeFilter: ['class'] });
    if (!resultScreen.classList.contains('hidden')) render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
