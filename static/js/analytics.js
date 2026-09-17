(function () {
  'use strict';

  const root = document.querySelector('[data-analytics]');
  if (!root) return;
  const $ = (sel, scope = document) => scope.querySelector(sel);
  const $$ = (sel, scope = document) => Array.from(scope.querySelectorAll(sel));

  /* ---------- Filters: apply straight away, keep the page while it reloads ---------- */
  const filters = $('[data-analytics-filters]', root);
  const reload = () => {
    root.classList.add('is-loading');
    filters.submit();
  };
  const period = $('[data-period]', filters);
  const customRange = $('[data-custom-range]', filters);
  period.addEventListener('change', () => {
    if (period.value === 'custom') {
      customRange.hidden = false;
      $('input', customRange).focus();
    } else {
      reload();
    }
  });
  $('[data-channel]', filters).addEventListener('change', reload);
  filters.addEventListener('submit', () => root.classList.add('is-loading'));

  /* ---------- Revenue / orders switch ---------- */
  $$('[data-metric]', root).forEach((button) => {
    button.addEventListener('click', () => {
      $$('[data-metric]', root).forEach((other) => {
        const active = other === button;
        other.classList.toggle('is-active', active);
        other.setAttribute('aria-pressed', String(active));
      });
      $$('[data-chart]', root).forEach((chart) => {
        chart.hidden = chart.dataset.chart !== button.dataset.metric;
      });
    });
  });

  /* ---------- Tooltips (the same details on hover and keyboard focus) ---------- */
  const tip = document.createElement('div');
  tip.className = 'a-tip';
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  document.body.appendChild(tip);
  let current = null;

  const line = (value, label, key, extraClass) => {
    const row = document.createElement('div');
    row.className = `a-tip__row${extraClass ? ` ${extraClass}` : ''}`;
    if (key) {
      const swatch = document.createElement('span');
      swatch.className = `a-tip__key a-seg--${key}`;
      row.appendChild(swatch);
    }
    const strong = document.createElement('strong');
    strong.textContent = value;
    const span = document.createElement('span');
    span.textContent = label;
    row.append(strong, span);
    return row;
  };

  const fill = (el) => {
    let data;
    try {
      data = JSON.parse(el.dataset.tip);
    } catch (err) {
      return false;
    }
    tip.replaceChildren();
    const title = document.createElement('div');
    title.className = 'a-tip__title';
    title.textContent = data.title;
    tip.appendChild(title);
    (data.rows || []).forEach((row) => tip.appendChild(line(row.value, row.label, row.key)));
    if (data.total) tip.appendChild(line(data.total, 'Total', '', 'a-tip__total'));
    return true;
  };

  const place = (x, y) => {
    const gap = 14;
    const box = tip.getBoundingClientRect();
    let left = x + gap;
    let top = y + gap;
    if (left + box.width > window.innerWidth - 8) left = x - box.width - gap;
    if (top + box.height > window.innerHeight - 8) top = y - box.height - gap;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  };

  const show = (el, x, y) => {
    if (current !== el) {
      if (!fill(el)) return;
      current = el;
    }
    tip.hidden = false;
    place(x, y);
  };

  const hide = () => {
    tip.hidden = true;
    current = null;
  };

  root.addEventListener('pointermove', (e) => {
    const el = e.target.closest('[data-tip]');
    if (el && root.contains(el)) show(el, e.clientX, e.clientY);
    else if (current) hide();
  });
  root.addEventListener('pointerleave', hide);
  root.addEventListener('focusin', (e) => {
    const el = e.target.closest('[data-tip]');
    if (!el) return;
    const box = el.getBoundingClientRect();
    show(el, box.left + box.width / 2, box.top + box.height / 2);
  });
  root.addEventListener('focusout', hide);
  window.addEventListener('scroll', hide, { passive: true });
})();
