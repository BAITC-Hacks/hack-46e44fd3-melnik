const state = { catalog: null, selected: new Map(), result: null, chart: null };
const $ = (selector) => document.querySelector(selector);
const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : '';
const api = (path) => `${API_BASE}${path}`;

async function init() {
  const response = await fetch(api('/api/catalog'));
  if (!response.ok) throw new Error('Не удалось загрузить каталог');
  state.catalog = await response.json();
  $('#baseline-score').textContent = state.catalog.baseline.score.toFixed(2);
  renderCatalog();
  bindControls();
  updateValidation();
}

function bindControls() {
  $('#calculate-button').addEventListener('click', calculate);
  $('#back-button').addEventListener('click', () => showScreen('selection'));
  $('#reset-selection').addEventListener('click', () => { state.selected.clear(); renderCatalog(); updateValidation(); });
  $('#load-example').addEventListener('click', loadExample);
}

function groupBy(items, key) {
  return items.reduce((groups, item) => ((groups[item[key]] ??= []).push(item), groups), {});
}

function effectText(measure) {
  const fraction = (state.catalog.horizon - measure.lag) / state.catalog.horizon;
  return Object.entries(measure.effects).map(([key, value]) => {
    const realized = value * fraction;
    return `${key} ${realized >= 0 ? '+' : ''}${Number.isInteger(realized) ? realized : realized.toFixed(2)}`;
  }).join(' · ');
}

function renderCatalog() {
  const groups = groupBy(state.catalog.measures, 'direction');
  $('#catalog').innerHTML = Object.entries(groups).map(([direction, measures]) => `
    <section class="direction-group">
      <h2>${direction} <span>${measures.length} мероприятия</span></h2>
      <div class="measure-grid">
        ${measures.map(measureCard).join('')}
      </div>
    </section>`).join('');

  document.querySelectorAll('.measure-card').forEach(card => {
    const id = card.dataset.id;
    card.addEventListener('click', event => {
      if (event.target.matches('select')) return;
      state.selected.has(id) ? state.selected.delete(id) : state.selected.set(id, null);
      renderCatalog();
      updateValidation();
    });
  });
  document.querySelectorAll('.district-select').forEach(select => {
    select.addEventListener('change', event => {
      state.selected.set(event.target.dataset.id, event.target.value || null);
      updateValidation();
    });
  });
}

function measureCard(measure) {
  const selected = state.selected.has(measure.id);
  const district = state.selected.get(measure.id);
  const options = state.catalog.districts.map(item => `<option value="${item.id}" ${district === item.id ? 'selected' : ''}>${item.name}</option>`).join('');
  return `<article class="measure-card ${selected ? 'selected' : ''}" data-id="${measure.id}">
    <input type="checkbox" ${selected ? 'checked' : ''} tabindex="-1">
    <div class="measure-top"><span class="measure-id">${measure.id}</span><span class="measure-cost">${measure.cost} ед.</span></div>
    <h3>${measure.name}</h3>
    <div class="measure-meta">
      <span class="pill">${measure.type === 'city' ? 'Весь город' : 'Один район'}</span>
      <span class="pill">лаг ${measure.lag} кв.</span>
      <span class="pill">${effectText(measure)}</span>
    </div>
    ${measure.type === 'district' ? `<select class="district-select" data-id="${measure.id}" ${selected ? '' : 'disabled'} aria-label="Район для ${measure.name}">
      <option value="">Выберите район</option>${options}</select>` : ''}
  </article>`;
}

function selections() {
  return [...state.selected.entries()].map(([measure_id, district_id]) => ({ measure_id, district_id }));
}

function validateClient() {
  const chosen = selections();
  if (chosen.length !== 5) return `Нужно выбрать ровно 5 решений: сейчас ${chosen.length}`;
  const lookup = Object.fromEntries(state.catalog.measures.map(item => [item.id, item]));
  const cost = chosen.reduce((sum, item) => sum + lookup[item.measure_id].cost, 0);
  if (cost > 100) return `Превышен бюджет: ${cost} > 100`;
  const missing = chosen.find(item => lookup[item.measure_id].type === 'district' && !item.district_id);
  if (missing) return `Выберите район для ${missing.measure_id}`;
  const counts = {};
  chosen.forEach(item => counts[lookup[item.measure_id].direction] = (counts[lookup[item.measure_id].direction] || 0) + 1);
  const overloaded = Object.entries(counts).find(([, count]) => count > 2);
  if (overloaded) return `В направлении «${overloaded[0]}» выбрано больше 2 мер`;
  const byId = Object.fromEntries(chosen.map(item => [item.measure_id, item]));
  if (byId.M1 && byId.M3) return 'M1 и M3 несовместимы в любых районах';
  for (const [a, b] of [['M4','M7'], ['M5','M13']]) {
    if (byId[a] && byId[b] && byId[a].district_id === byId[b].district_id) return `${a} и ${b} несовместимы в одном районе`;
  }
  return null;
}

function updateValidation() {
  const chosen = selections();
  const lookup = Object.fromEntries(state.catalog.measures.map(item => [item.id, item]));
  const cost = chosen.reduce((sum, item) => sum + lookup[item.measure_id].cost, 0);
  const directions = new Set(chosen.map(item => lookup[item.measure_id].direction));
  $('#budget-used').textContent = cost;
  $('#decision-count').textContent = chosen.length;
  $('#direction-count').textContent = directions.size;
  $('#budget-bar').style.width = `${Math.min(cost, 100)}%`;
  $('#budget-bar').style.background = cost > 100 ? 'var(--red)' : 'var(--green-2)';
  const error = validateClient();
  const message = $('#validation-message');
  message.textContent = error || 'Сценарий готов к расчёту';
  message.className = `validation-message ${error ? 'error' : 'ok'}`;
  $('#calculate-button').disabled = Boolean(error);
}

function loadExample() {
  state.selected = new Map([['M7','nura'], ['M8','nura'], ['M10','nura'], ['M12',null], ['M5','saryarka']]);
  renderCatalog();
  updateValidation();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function calculate() {
  const button = $('#calculate-button');
  button.disabled = true;
  button.textContent = 'Считаем…';
  try {
    const response = await fetch(api('/api/simulate'), { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({selections: selections()}) });
    const result = await response.json();
    if (!result.valid) throw new Error(result.reason);
    state.result = result;
    renderResult();
    showScreen('result');
    loadExplanation(result);
  } catch (error) {
    const message = $('#validation-message');
    message.textContent = error.message;
    message.className = 'validation-message error';
  } finally {
    button.textContent = 'Рассчитать сценарий';
    updateValidation();
  }
}

function showScreen(name) {
  $('#selection-screen').classList.toggle('hidden', name !== 'selection');
  $('#result-screen').classList.toggle('hidden', name !== 'result');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderResult() {
  const r = state.result;
  $('#result-score').textContent = r.score.toFixed(2);
  $('#result-delta').textContent = `${r.delta >= 0 ? '+' : ''}${r.delta.toFixed(2)}`;
  $('#score-caption').textContent = `Базовый уровень ${r.score_base.toFixed(2)}. Использовано ${r.cost_total} из 100 единиц бюджета.`;
  const districtName = id => state.catalog.districts.find(item => item.id === id).name;
  $('#summary-metrics').innerHTML = `
    <div class="metric"><span>Средний городской балл</span><strong>${r.city_avg_before.toFixed(2)} → ${r.city_avg_after.toFixed(2)}</strong></div>
    <div class="metric"><span>Минимальный район после</span><strong>${districtName(r.min_district_after)}</strong></div>
    <div class="metric"><span>Критические показатели</span><strong>${r.n_crit_before} → ${r.n_crit_after}</strong></div>
    <div class="metric"><span>Синергий применено</span><strong>${r.synergies_applied.length}</strong></div>`;
  renderChart(r);
  $('#district-results').innerHTML = r.districts.map(districtCard).join('');
  renderContributions(r);
}

function renderChart(result) {
  if (state.chart) state.chart.destroy();
  const context = $('#district-chart');
  if (typeof Chart === 'undefined') {
    context.parentElement.innerHTML = '<p class="validation-message">График недоступен без CDN, числовые карточки районов ниже продолжают работать.</p>';
    return;
  }
  state.chart = new Chart(context, {
    type: 'bar',
    data: {
      labels: result.districts.map(item => item.name),
      datasets: [
        { label: 'До', data: result.districts.map(item => item.D_before), backgroundColor: '#bfc7bf', borderRadius: 7 },
        { label: 'После', data: result.districts.map(item => item.D_after), backgroundColor: '#2d956c', borderRadius: 7 },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100, grid: { color: '#e7e8e2' } } }, plugins: { legend: { position: 'bottom' } } }
  });
}

function districtCard(item) {
  const rows = Object.keys(item.indicators_before).map(code => {
    const before = item.indicators_before[code], after = item.indicators_after[code], critical = after < 40;
    return `<div class="indicator-row ${critical ? 'critical' : ''}" title="${state.catalog.indicator_names[code]}">
      <span class="indicator-code">${code}</span>
      <span class="mini-track"><i class="mini-before" style="width:${before}%"></i><i class="mini-after" style="width:${after}%"></i></span>
      <span class="indicator-values">${before.toFixed(1)} → ${after.toFixed(1)}</span>
    </div>`;
  }).join('');
  return `<article class="district-card">
    <div class="district-header"><h3>${item.name}</h3><span class="district-score">${item.D_before.toFixed(2)} → <b>${item.D_after.toFixed(2)}</b></span></div>
    ${rows}
    ${item.critical_after.length ? `<p class="critical-note">Критические: ${item.critical_after.join(', ')}</p>` : ''}
  </article>`;
}

async function loadExplanation(result) {
  $('#analysis-loading').classList.remove('hidden');
  $('#analysis-content').classList.add('hidden');
  $('#explanation-source').textContent = 'загрузка';
  try {
    const response = await fetch(api('/api/explain'), { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(result) });
    if (!response.ok) throw new Error('AI-анализ временно недоступен');
    const data = await response.json();
    $('#explanation-source').textContent = data.source === 'openai' ? 'OpenAI' : 'резервный анализ';
    $('#analysis-content').innerHTML = `<p class="analysis-summary">${escapeHtml(data.summary)}</p><div class="analysis-columns">
      ${analysisColumn('Сильные стороны', data.strengths)}${analysisColumn('Риски', data.risks)}${analysisColumn('Компромиссы', data.tradeoffs)}
    </div>`;
  } catch (error) {
    $('#analysis-content').innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    $('#explanation-source').textContent = 'ошибка';
  } finally {
    $('#analysis-loading').classList.add('hidden');
    $('#analysis-content').classList.remove('hidden');
  }
}

function analysisColumn(title, items) {
  return `<div class="analysis-column"><h3>${title}</h3><ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>`;
}

function renderContributions(result) {
  const measures = Object.fromEntries(state.catalog.measures.map(item => [item.id, item]));
  const districts = Object.fromEntries(state.catalog.districts.map(item => [item.id, item.name]));
  const normal = result.measure_contributions.map(item => {
    const effects = Object.entries(item.realized_effects).map(([code, value]) => `${code} ${value >= 0 ? '+' : ''}${value.toFixed(2)}`).join(' · ');
    return `<div class="contribution"><div><strong>${item.measure_id} · ${measures[item.measure_id].name}</strong><small>${item.district_id ? districts[item.district_id] : 'Весь город'} · реализовано ${(item.realized_fraction * 100).toFixed(0)}%</small></div><b>${effects}</b></div>`;
  });
  const synergies = result.synergies_applied.map(item => `<div class="contribution synergy"><div><strong>Синергия ${item.pair.join(' + ')}</strong><small>${districts[item.district_id]} · без масштабирования лагом</small></div><b>${Object.entries(item.bonus).map(([k,v]) => `${k} +${v}`).join(' · ')}</b></div>`);
  $('#contributions').innerHTML = [...normal, ...synergies].join('');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

init().catch(error => {
  document.body.innerHTML = `<main class="screen"><h1>Не удалось запустить интерфейс</h1><p>${escapeHtml(error.message)}</p></main>`;
});
