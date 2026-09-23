(() => {
  'use strict';

  const appState = () => (typeof state !== 'undefined' ? state : window.state || {});
  let renderedKey = '';

  function mount() {
    const screen = document.querySelector('#result-screen');
    if (!screen || document.querySelector('#implementation-roadmap')) return;

    const section = document.createElement('section');
    section.id = 'implementation-roadmap';
    section.className = 'result-section implementation-roadmap';
    section.setAttribute('aria-labelledby', 'roadmap-title');
    section.innerHTML = `
      <div class="section-heading">
        <div><p class="eyebrow">План по кварталам</p><h2 id="roadmap-title">Дорожная карта внедрения</h2></div>
        <p>Все меры стартуют в Q1. Цветная часть шкалы показывает кварталы после задержки эффекта.</p>
      </div>
      <div id="roadmap-content" class="roadmap-content" aria-live="polite"></div>`;

    const contributions = document.querySelector('#contributions')?.closest('.result-section');
    if (contributions) contributions.after(section);
    else screen.appendChild(section);

    const observer = new MutationObserver(() => {
      if (!screen.classList.contains('hidden')) render();
    });
    observer.observe(screen, { attributes: true, attributeFilter: ['class'] });
    window.addEventListener('qq:catalog-ready', render);
    if (!screen.classList.contains('hidden')) render();
  }

  function render() {
    const current = appState();
    const result = current.result;
    const catalog = current.catalog;
    const target = document.querySelector('#roadmap-content');
    if (!target || !result?.valid || !Array.isArray(result.selections) || !Array.isArray(catalog?.measures)) return;

    const key = JSON.stringify({ selections: result.selections, measures: catalog.measures });
    if (key === renderedKey) return;
    renderedKey = key;

    const horizon = Number(catalog.horizon);
    const budget = Number(catalog.budget);
    const byId = new Map(catalog.measures.map((measure) => [measure.id, measure]));
    const districts = new Map((catalog.districts || []).map((district) => [district.id, district.name]));
    target.replaceChildren();

    if (!Number.isInteger(horizon) || horizon < 1 || !Number.isFinite(budget)) {
      target.textContent = 'Данные о горизонте или бюджете недоступны.';
      return;
    }

    const legend = document.createElement('div');
    legend.className = 'roadmap-quarter-labels';
    legend.setAttribute('aria-hidden', 'true');
    for (let quarter = 1; quarter <= horizon; quarter += 1) {
      const label = document.createElement('span');
      label.textContent = `Q${quarter}`;
      legend.appendChild(label);
    }
    target.appendChild(legend);

    for (const selection of result.selections) {
      const measure = byId.get(selection.measure_id);
      if (!measure) continue;
      const lag = Number(measure.lag);
      const realized = ((horizon - lag) / horizon) * 100;
      const realizedLabel = Number.isInteger(realized) ? String(realized) : realized.toFixed(1);
      const district = selection.district_id ? districts.get(selection.district_id) || selection.district_id : 'Весь город';
      const row = document.createElement('article');
      row.className = 'roadmap-measure';

      const heading = document.createElement('div');
      heading.className = 'roadmap-measure-heading';
      const title = document.createElement('h3');
      title.textContent = `${measure.id} · ${measure.name}`;
      const metadata = document.createElement('p');
      metadata.textContent = `${district} · ${measure.cost} из ${budget} единиц`;
      heading.append(title, metadata);

      const track = document.createElement('div');
      track.className = 'roadmap-track';
      track.style.setProperty('--roadmap-direction', window.QQTheme?.direction?.(measure.direction) || 'var(--sky)');
      track.setAttribute('role', 'img');
      track.setAttribute('aria-label', `${measure.name}: старт Q1, эффект с Q${lag + 1}, к 2 годам реализовано ${realizedLabel}%`);
      for (let quarter = 1; quarter <= horizon; quarter += 1) {
        const cell = document.createElement('span');
        cell.className = quarter > lag ? 'roadmap-quarter roadmap-quarter-effective' : 'roadmap-quarter roadmap-quarter-waiting';
        if (quarter === 1) cell.classList.add('roadmap-quarter-start');
        cell.title = quarter > lag ? `Q${quarter}: эффект начался` : `Q${quarter}: эффект ещё не наступил`;
        cell.setAttribute('aria-hidden', 'true');
        track.appendChild(cell);
      }

      const note = document.createElement('p');
      note.className = 'roadmap-measure-note';
      note.textContent = `Старт Q1 · эффект с Q${lag + 1} · к 2 годам реализовано ${realizedLabel}%`;
      row.append(heading, track, note);
      target.appendChild(row);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
