(() => {
  'use strict';

  const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : '';
  const api = (path) => `${API_BASE}${path}`;
  const $ = (selector, root = document) => root.querySelector(selector);

  let latestDigest = null;
  let busy = false;

  function plural(value, one, few, many) {
    const amount = Math.abs(Number(value) || 0) % 100;
    const last = amount % 10;
    if (amount > 10 && amount < 20) return many;
    if (last === 1) return one;
    if (last >= 2 && last <= 4) return few;
    return many;
  }

  function append(parent, tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    parent.append(node);
    return node;
  }

  function formatDate(value) {
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'medium', timeStyle: 'short',
    }).format(date);
  }

  function sourceLabel(source) {
    return source === 'openai' ? 'ИИ' : 'резервный режим';
  }

  function normalizeList(value) {
    if (!Array.isArray(value)) return [];
    return value.map((item) => {
      if (typeof item === 'string' || typeof item === 'number') return String(item);
      return item?.name || item?.title || item?.id || item?.measure_id || '';
    }).filter(Boolean);
  }

  function ensurePanel() {
    const host = $('#proposal-digest');
    if (!host) return null;
    if (host.dataset.digestReady === 'true') return host;
    host.dataset.digestReady = 'true';
    host.classList.add('digest-panel');
    host.innerHTML = '';

    const heading = append(host, 'div', 'digest-heading');
    const titleGroup = append(heading, 'div', 'digest-title-group');
    append(titleGroup, 'p', 'eyebrow', 'Голос города');
    append(titleGroup, 'h3', '', 'Сводка для акимата');
    append(titleGroup, 'p', 'digest-description', 'Темы из предложений жителей. Голоса, районы и участие в народном сценарии считает только код.');

    const controls = append(heading, 'div', 'digest-controls');
    const badge = append(controls, 'span', 'digest-source hidden', '—');
    badge.id = 'digest-source';
    const download = append(controls, 'button', 'digest-download hidden', 'Скачать сводку (.txt)');
    download.id = 'digest-download';
    download.type = 'button';
    download.addEventListener('click', downloadDigest);

    const status = append(host, 'p', 'digest-status', 'Нажмите «Сводка для акимата», чтобы сгруппировать предложения по темам.');
    status.id = 'digest-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const themes = append(host, 'div', 'digest-themes hidden');
    themes.id = 'digest-themes';
    return host;
  }

  function setStatus(message, kind = '') {
    const status = $('#digest-status');
    if (!status) return;
    status.className = `digest-status${kind ? ` ${kind}` : ''}`;
    status.textContent = message;
  }

  function themeCard(theme) {
    const card = document.createElement('article');
    card.className = 'digest-theme-card';

    const top = append(card, 'div', 'digest-theme-top');
    append(top, 'h4', '', theme.title || 'Без названия');
    append(top, 'span', 'digest-votes', `${Number(theme.votes) || 0} ${plural(theme.votes, 'голос', 'голоса', 'голосов')}`);
    append(card, 'p', 'digest-summary', theme.summary || 'Предложения объединены по общей теме.');

    const proposalCount = Number(theme.proposal_count) || 0;
    const districts = normalizeList(theme.districts);
    const districtText = districts.length ? `районы: ${districts.join(', ')}` : 'районы не определены';
    append(
      card,
      'p',
      'digest-meta',
      `${proposalCount} ${plural(proposalCount, 'предложение', 'предложения', 'предложений')} · ${Number(theme.votes) || 0} ${plural(theme.votes, 'голос', 'голоса', 'голосов')} · ${districtText}`,
    );

    const measures = normalizeList(theme.measures);
    if (measures.length) {
      const list = append(card, 'div', 'digest-measures');
      measures.forEach((measure) => append(list, 'span', '', measure));
    }

    const included = Number(theme.in_people_scenario) || 0;
    append(card, 'span', 'digest-included', `Из них в народном сценарии: ${included}`);
    return card;
  }

  function render(data) {
    latestDigest = data;
    const source = $('#digest-source');
    const download = $('#digest-download');
    const themesHost = $('#digest-themes');
    const themes = Array.isArray(data?.themes)
      ? [...data.themes].sort((left, right) => (Number(right.votes) || 0) - (Number(left.votes) || 0))
      : [];

    source.textContent = sourceLabel(data?.source);
    source.className = `digest-source${data?.source === 'openai' ? ' ai' : ' fallback'}`;
    download.classList.remove('hidden');
    themesHost.innerHTML = '';

    if (!themes.length) {
      themesHost.classList.add('hidden');
      setStatus('На доске пока нет предложений — сводку можно будет собрать после первой идеи.', 'empty');
      return;
    }

    themes.forEach((theme) => themesHost.append(themeCard(theme)));
    themesHost.classList.remove('hidden');
    const generated = formatDate(data?.generated_at);
    setStatus(`Собрано тем: ${themes.length}${generated ? ` · ${generated}` : ''}.`);
  }

  async function generateDigest() {
    if (busy) return;
    const host = ensurePanel();
    if (!host) return;
    const button = $('#generate-digest');
    const themes = $('#digest-themes');
    busy = true;
    if (button) {
      button.disabled = true;
      button.dataset.originalText ||= button.textContent;
      button.textContent = 'Собираем сводку…';
    }
    $('#digest-source')?.classList.add('hidden');
    $('#digest-download')?.classList.add('hidden');
    themes?.classList.add('hidden');
    setStatus('Группируем предложения и проверяем вычисленные итоги…', 'loading');

    try {
      const response = await fetch(api('/api/proposals/digest'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = data.detail || data.message;
        throw new Error(typeof detail === 'string' ? detail : 'Не удалось собрать сводку');
      }
      render(data);
      host.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' });
    } catch (error) {
      latestDigest = null;
      setStatus(error instanceof Error ? error.message : 'Сводка временно недоступна', 'error');
    } finally {
      busy = false;
      if (button) {
        button.disabled = false;
        button.textContent = button.dataset.originalText || 'Сводка для акимата';
      }
    }
  }

  function digestText(data) {
    const themes = Array.isArray(data?.themes)
      ? [...data.themes].sort((left, right) => (Number(right.votes) || 0) - (Number(left.votes) || 0))
      : [];
    const lines = [
      'QalaQadam — сводка предложений жителей для акимата',
      `Сформировано: ${formatDate(data?.generated_at) || 'дата не указана'}`,
      `Источник группировки: ${sourceLabel(data?.source)}`,
      '',
    ];
    if (!themes.length) {
      lines.push('На доске пока нет предложений.');
      return lines.join('\n');
    }
    themes.forEach((theme, index) => {
      const districts = normalizeList(theme.districts);
      const measures = normalizeList(theme.measures);
      lines.push(`${index + 1}. ${theme.title || 'Без названия'}`);
      lines.push(theme.summary || 'Предложения объединены по общей теме.');
      lines.push(`Предложений: ${Number(theme.proposal_count) || 0}; голосов: ${Number(theme.votes) || 0}; в народном сценарии: ${Number(theme.in_people_scenario) || 0}.`);
      lines.push(`Районы: ${districts.length ? districts.join(', ') : 'не определены'}.`);
      lines.push(`Меры: ${measures.length ? measures.join(', ') : 'не определены'}.`, '');
    });
    return lines.join('\n').trimEnd();
  }

  function downloadDigest() {
    if (!latestDigest) return;
    const blob = new Blob([digestText(latestDigest)], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `qalaqadam-digest-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function bind() {
    ensurePanel();
    const button = $('#generate-digest');
    if (button && button.dataset.digestBound !== 'true') {
      button.dataset.digestBound = 'true';
      button.addEventListener('click', generateDigest);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
  else bind();

  window.QalaQadamDigest = Object.freeze({ generate: generateDigest });
})();
