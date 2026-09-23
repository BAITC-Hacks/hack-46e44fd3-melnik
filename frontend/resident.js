(() => {
  'use strict';

  const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : '';
  const api = (path) => `${API_BASE}${path}`;
  const $ = (selector, root = document) => root.querySelector(selector);

  let catalog = null;
  let latestResponse = null;

  function createMarkup() {
    const section = document.createElement('section');
    section.id = 'resident-voice';
    section.className = 'result-section resident-section';
    section.innerHTML = `
      <div class="resident-heading">
        <div>
          <p class="eyebrow">Голос жителя</p>
          <h2>От предложения — к проверенному плану</h2>
          <p>Опишите, что важно для района. Симулятор найдёт меру из каталога и покажет только пересчитанные кодом эффекты.</p>
        </div>
        <span class="resident-demo-badge">демо</span>
      </div>
      <form class="resident-form" id="resident-form">
        <label class="resident-field">
          <span>Район</span>
          <select id="resident-district"><option value="">Весь город</option></select>
        </label>
        <label class="resident-field resident-message-field">
          <span>Что вы хотите изменить?</span>
          <textarea id="resident-message" rows="3" required placeholder="Например: в нашем районе не хватает поликлиник"></textarea>
        </label>
        <div class="resident-chips" aria-label="Примеры предложений">
          <button type="button" data-resident-example="Поликлиника в Нуре" data-district="nura">Поликлиника в Нуре</button>
          <button type="button" data-resident-example="Темно на улицах">Темно на улицах</button>
          <button type="button" data-resident-example="Плохой воздух">Плохой воздух</button>
        </div>
        <div id="resident-district-hint" class="resident-district-hint hidden" role="status"></div>
        <button class="primary-button resident-submit" type="submit">Проверить предложение</button>
      </form>
      <p class="resident-disclaimer">Черновик. В демо обращение никуда не отправляется.</p>
      <div id="resident-status" class="resident-status" role="status" aria-live="polite"></div>
      <div id="resident-output" class="resident-output hidden"></div>`;
    return section;
  }

  async function loadCatalog() {
    if (catalog) return catalog;
    const response = await fetch(api('/api/catalog'));
    if (!response.ok) throw new Error('Не удалось загрузить список районов');
    catalog = await response.json();
    return catalog;
  }

  function districtName(district) {
    if (!district) return 'Весь город';
    if (typeof district === 'string') {
      return catalog?.districts?.find((item) => item.id === district)?.name || district;
    }
    return district.name || district.id || 'Весь город';
  }

  function measureName(measure) {
    if (!measure) return 'Мера из каталога';
    if (typeof measure === 'string') return measure;
    return measure.name || measure.title || measure.id || 'Мера из каталога';
  }

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function formatNumber(value, digits = 2) {
    const number = finite(value);
    if (number === null) return null;
    return number.toFixed(digits).replace(/\.00$/, '');
  }

  function appendText(parent, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.append(element);
    return element;
  }

  function getEffects(data) {
    const evidence = data.evidence || {};
    return evidence.effects
      || evidence.realized_effects
      || evidence.measure_contribution?.realized_effects
      || evidence.measure_contribution?.effects
      || {};
  }

  function getDistrictScores(data) {
    const evidence = data.evidence || {};
    return {
      before: evidence.district_score_before ?? evidence.district_before ?? evidence.D_before ?? evidence.district?.before ?? evidence.district?.D_before,
      after: evidence.district_score_after ?? evidence.district_after ?? evidence.D_after ?? evidence.district?.after ?? evidence.district?.D_after,
    };
  }

  function effectLabel(code) {
    return catalog?.indicator_names?.[code] || code;
  }

  function renderUnmatched(data) {
    const output = $('#resident-output');
    output.replaceChildren();
    const card = document.createElement('article');
    card.className = 'resident-unmatched';
    appendText(card, 'h3', '', 'Такой меры нет в каталоге симулятора');
    appendText(card, 'p', '', data.appeal?.body || data.message || data.reason || 'Попробуйте описать задачу иначе или выбрать один из ближайших вариантов.');
    const alternatives = Array.isArray(data.alternatives) ? data.alternatives : [];
    if (alternatives.length) {
      appendText(card, 'p', 'resident-muted', 'Ближайшие меры:');
      const list = document.createElement('ul');
      alternatives.slice(0, 3).forEach((item) => appendText(list, 'li', '', measureName(item)));
      card.append(list);
    }
    output.append(card);
    output.classList.remove('hidden');
  }

  function clearDistrictPrompt() {
    const select = $('#resident-district');
    if (!select) return;
    select.classList.remove('resident-district-required');
    select.removeAttribute('aria-invalid');
    select.removeAttribute('aria-describedby');
  }

  const DISTRICT_FORMS = {
    esil: ['есиль', 'есиля', 'есиле', 'есилю', 'есилем'],
    almaty: ['алматы'],
    saryarka: ['сарыарка', 'сарыарки', 'сарыарке', 'сарыарку', 'сарыаркой'],
    baikonur: ['байконур', 'байконура', 'байконуре', 'байконуру', 'байконуром'],
    nura: ['нура', 'нуры', 'нуре', 'нуру', 'нурой'],
  };

  function mentionedDistrict(message) {
    const tokens = (message.toLocaleLowerCase('ru').match(/[а-яё]+/gu) || []);
    const mentioned = Object.entries(DISTRICT_FORMS)
      .filter(([, forms]) => forms.some((form) => tokens.includes(form)))
      .map(([id]) => id);
    return mentioned.length === 1 ? mentioned[0] : null;
  }

  function updateDistrictHint() {
    const hint = $('#resident-district-hint');
    const selected = $('#resident-district')?.value;
    const mentioned = mentionedDistrict($('#resident-message')?.value || '');
    hint.replaceChildren();
    if (!selected || !mentioned || selected === mentioned) {
      hint.classList.add('hidden');
      return;
    }
    const name = districtName(mentioned);
    appendText(hint, 'span', '', `В тексте упомянут район ${name} — рассчитать для него?`);
    const change = appendText(hint, 'button', 'resident-hint-action', `Выбрать ${name}`);
    change.type = 'button';
    change.addEventListener('click', () => {
      $('#resident-district').value = mentioned;
      clearDistrictPrompt();
      invalidateResult();
      updateDistrictHint();
      $('#resident-district').focus();
    });
    hint.classList.remove('hidden');
  }

  function invalidateResult() {
    latestResponse = null;
    const output = $('#resident-output');
    output.replaceChildren();
    output.classList.add('hidden');
    showStatus();
  }

  function renderNeedsDistrict(data) {
    const output = $('#resident-output');
    output.replaceChildren();
    const card = document.createElement('article');
    card.className = 'resident-unmatched resident-needs-district';
    appendText(card, 'h3', '', `Нашли меру: ${measureName(data.measure)}. Выберите район`);
    appendText(card, 'p', '', 'Укажите район выше и снова нажмите «Проверить предложение», чтобы увидеть расчёт.');
    output.append(card);
    output.classList.remove('hidden');
    const select = $('#resident-district');
    if (select) {
      select.classList.add('resident-district-required');
      select.setAttribute('aria-invalid', 'true');
      select.setAttribute('aria-describedby', 'resident-status');
      select.focus();
    }
  }

  function renderEvidence(data, card) {
    const evidence = data.evidence || {};
    const effects = getEffects(data);
    const effectEntries = Object.entries(effects).filter(([, value]) => finite(value) !== null);
    const verifiedEffects = Array.isArray(evidence.measure_effects) ? evidence.measure_effects : [];
    const scores = getDistrictScores(data);
    const before = formatNumber(scores.before);
    const after = formatNumber(scores.after);

    if (!verifiedEffects.length && !effectEntries.length && (before === null || after === null)) return;
    const block = document.createElement('div');
    block.className = 'resident-evidence';
    appendText(block, 'h3', '', 'Проверенный эффект');
    if (verifiedEffects.length) {
      const list = document.createElement('ul');
      verifiedEffects.forEach((effect) => {
        const effectBefore = formatNumber(effect.before);
        const effectAfter = formatNumber(effect.after);
        const delta = formatNumber(effect.delta);
        const name = effect.name || effectLabel(effect.indicator);
        if (effectBefore !== null && effectAfter !== null) {
          appendText(list, 'li', '', `${name}: ${effectBefore} → ${effectAfter}`);
        } else if (delta !== null) {
          appendText(list, 'li', '', `${name}: ${finite(effect.delta) > 0 ? '+' : ''}${delta}`);
        }
      });
      block.append(list);
    } else if (effectEntries.length) {
      const list = document.createElement('ul');
      effectEntries.forEach(([code, value]) => {
        const formatted = formatNumber(value);
        const sign = finite(value) > 0 ? '+' : '';
        appendText(list, 'li', '', `${effectLabel(code)}: ${sign}${formatted}`);
      });
      block.append(list);
    }
    if (before !== null && after !== null) {
      appendText(block, 'p', 'resident-score-shift', `${districtName(data.district || evidence.district)}: ${before} → ${after}`);
    }
    card.append(block);
  }

  function renderPlan(data, card) {
    const planScore = formatNumber(data.plan?.score);
    const maxScore = formatNumber(data.max_score);
    if (planScore === null && maxScore === null) return;
    const block = document.createElement('div');
    block.className = 'resident-plan';
    appendText(block, 'h3', '', 'План с вашим предложением');
    const metrics = document.createElement('div');
    metrics.className = 'resident-plan-metrics';
    if (planScore !== null) {
      const item = document.createElement('div');
      appendText(item, 'span', '', 'Score плана');
      appendText(item, 'strong', '', planScore);
      metrics.append(item);
    }
    if (maxScore !== null) {
      const item = document.createElement('div');
      appendText(item, 'span', '', 'Максимум без условия');
      appendText(item, 'strong', '', maxScore);
      metrics.append(item);
    }
    block.append(metrics);
    const selections = data.plan?.selections;
    if (Array.isArray(selections) && selections.length) {
      const apply = appendText(block, 'button', 'primary-button resident-apply', 'Открыть в симуляторе');
      apply.type = 'button';
      apply.addEventListener('click', async () => {
        if (typeof window.QQApp?.applyScenario !== 'function') {
          showStatus('Симулятор ещё не готов применить сценарий.', 'error');
          return;
        }
        apply.disabled = true;
        try {
          await window.QQApp.applyScenario(selections, 'Предложение жителя');
        } catch (error) {
          showStatus(error.message || 'Не удалось открыть сценарий', 'error');
        } finally {
          apply.disabled = false;
        }
      });
    }
    card.append(block);
  }

  function appealText(appeal) {
    if (!appeal) return '';
    return [appeal.title, appeal.body].filter(Boolean).join('\n\n');
  }

  function renderAppeal(data, card) {
    const text = appealText(data.appeal);
    if (!text) return;
    const block = document.createElement('div');
    block.className = 'resident-appeal';
    appendText(block, 'h3', '', 'Черновик обращения');
    if (data.appeal.title) appendText(block, 'strong', 'resident-appeal-title', data.appeal.title);
    if (data.appeal.body) appendText(block, 'p', 'resident-appeal-body', data.appeal.body);
    const actions = document.createElement('div');
    actions.className = 'resident-appeal-actions';
    const copy = appendText(actions, 'button', 'resident-secondary-button', 'Скопировать');
    copy.type = 'button';
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(text);
        copy.textContent = 'Скопировано';
      } catch (_) {
        showStatus('Не удалось скопировать. Выделите текст вручную.', 'error');
      }
    });
    const download = appendText(actions, 'button', 'resident-secondary-button', 'Скачать .txt');
    download.type = 'button';
    download.addEventListener('click', () => {
      const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'obrashchenie.txt';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    });
    block.append(actions);
    appendText(block, 'small', 'resident-disclaimer', 'Черновик. В демо обращение никуда не отправляется.');
    card.append(block);
  }

  function renderVoteAction(data, card) {
    const measureId = typeof data.measure === 'string' ? data.measure : data.measure?.id || data.measure_id;
    if (!measureId) return;
    const button = appendText(card, 'button', 'primary-button resident-vote-submit', 'Вынести на голосование');
    button.type = 'button';
    button.addEventListener('click', async () => {
      const text = $('#resident-message')?.value.trim() || data.message || measureName(data.measure);
      const districtValue = data.district;
      const districtId = typeof districtValue === 'string'
        ? districtValue || null
        : districtValue?.id ?? data.district_id ?? null;
      button.disabled = true;
      button.textContent = 'Отправляем на доску…';
      showStatus('Публикуем предложение с проверенными сервером мерой и районом…', 'loading');
      try {
        const response = await fetch(api('/api/proposals'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ measure_id: measureId, district_id: districtId, text }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = result.detail || result.message || 'Не удалось вынести предложение на голосование';
          throw new Error(typeof detail === 'string' ? detail : 'Проверьте предложение и попробуйте ещё раз');
        }
        button.textContent = 'Предложение на доске';
        showStatus('Предложение добавлено на доску голосования.');
        window.QQVotes?.refresh?.();
      } catch (error) {
        button.disabled = false;
        button.textContent = 'Вынести на голосование';
        showStatus(error.message || 'Не удалось добавить предложение', 'error');
      }
    });
  }

  function renderMatched(data) {
    const output = $('#resident-output');
    output.replaceChildren();
    const card = document.createElement('article');
    card.className = 'resident-result-card';
    appendText(card, 'p', 'resident-result-label', 'Ваше предложение');
    appendText(card, 'h3', '', measureName(data.measure));
    const meta = document.createElement('p');
    meta.className = 'resident-result-meta';
    const pieces = [];
    const id = data.measure?.id;
    const cost = formatNumber(data.measure?.cost ?? data.evidence?.measure_cost, 0);
    if (id) pieces.push(id);
    pieces.push(districtName(data.district));
    if (cost !== null) {
      const budget = formatNumber(catalog?.budget, 0);
      pieces.push(budget === null ? `${cost} единиц бюджета` : `${cost} из ${budget} единиц бюджета`);
    }
    meta.textContent = pieces.join(' · ');
    card.append(meta);
    renderEvidence(data, card);
    renderPlan(data, card);
    renderAppeal(data, card);
    renderVoteAction(data, card);
    output.append(card);
    output.classList.remove('hidden');
  }

  function renderResponse(data) {
    latestResponse = data;
    if (data?.needs_district) renderNeedsDistrict(data);
    else if (!data?.matched) renderUnmatched(data || {});
    else renderMatched(data);
  }

  function showStatus(message = '', type = '') {
    const status = $('#resident-status');
    if (!status) return;
    status.className = `resident-status${type ? ` ${type}` : ''}`;
    status.textContent = message;
  }

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = $('.resident-submit', form);
    const districtId = $('#resident-district').value || null;
    const message = $('#resident-message').value.trim();
    if (!message) return;
    clearDistrictPrompt();
    submitButton.disabled = true;
    $('#resident-output').classList.add('hidden');
    showStatus('Сопоставляем предложение с каталогом и проверяем план…', 'loading');
    try {
      const response = await fetch(api('/api/resident/propose'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ district_id: districtId, message }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Не удалось проверить предложение');
      renderResponse(data);
      showStatus(data.matched
        ? 'Предложение проверено кодом.'
        : data.needs_district
          ? 'Мера найдена. Выберите район для расчёта.'
          : 'Совпадение в каталоге не найдено.');
    } catch (error) {
      latestResponse = null;
      showStatus(error.message || 'Сервис временно недоступен', 'error');
    } finally {
      submitButton.disabled = false;
    }
  }

  function bind(section) {
    $('#resident-form', section).addEventListener('submit', submit);
    $('#resident-district', section).addEventListener('change', () => {
      clearDistrictPrompt();
      invalidateResult();
      updateDistrictHint();
    });
    $('#resident-message', section).addEventListener('input', () => {
      clearDistrictPrompt();
      invalidateResult();
      updateDistrictHint();
    });
    section.querySelectorAll('[data-resident-example]').forEach((button) => {
      button.addEventListener('click', () => {
        $('#resident-message').value = button.dataset.residentExample;
        const district = button.dataset.district;
        $('#resident-district').value = district || '';
        clearDistrictPrompt();
        invalidateResult();
        updateDistrictHint();
        $('#resident-message').focus();
      });
    });
  }

  async function populateDistricts(section) {
    try {
      const data = await loadCatalog();
      const select = $('#resident-district', section);
      (data.districts || []).forEach((district) => {
        const option = document.createElement('option');
        option.value = district.id;
        option.textContent = district.name;
        select.append(option);
      });
    } catch (error) {
      showStatus(error.message, 'error');
    }
  }

  function mount() {
    const resultScreen = $('#result-screen');
    if (!resultScreen || $('#resident-voice')) return;
    const section = createMarkup();
    const voting = $('#resident-voting');
    if (voting) resultScreen.insertBefore(section, voting);
    else resultScreen.append(section);
    bind(section);
    populateDistricts(section);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();

  window.QQResident = Object.freeze({ mount, getLatestResponse: () => latestResponse });
})();
