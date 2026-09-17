(function () {
  'use strict';

  // The stock table on the product form: one box per ticked size × color.
  const grid = document.querySelector('[data-stock-grid]');
  const source = document.getElementById('stock-data');
  if (!grid || !source) return;

  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const data = JSON.parse(source.textContent);
  const values = Object.assign({}, data.values); // "sizeId-colorId" -> quantity typed so far
  const totalEl = document.querySelector('[data-stock-total]');
  const checkedIds = (name) => $$(`input[name="${name}"]:checked`).map((input) => input.value);

  const remember = () => {
    $$('input[data-key]', grid).forEach((input) => { values[input.dataset.key] = input.value; });
  };

  const markCell = (input) => {
    const quantity = parseInt(input.value, 10) || 0;
    input.classList.toggle('is-zero', quantity === 0);
    input.classList.toggle('is-low', quantity > 0 && quantity <= data.low);
  };

  const updateTotal = () => {
    const total = $$('input[data-key]', grid).reduce((sum, input) => sum + (parseInt(input.value, 10) || 0), 0);
    if (totalEl) totalEl.textContent = `${total.toLocaleString('en-US')} in stock`;
  };

  const cell = (tag, text) => {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    return el;
  };

  const render = () => {
    remember();
    const sizeIds = checkedIds('sizes');
    const colorIds = checkedIds('colors');
    const sizes = sizeIds.length ? data.sizes.filter((s) => sizeIds.includes(String(s.id))) : [{ id: 0, name: 'One size' }];
    const colors = colorIds.length ? data.colors.filter((c) => colorIds.includes(String(c.id))) : [{ id: 0, name: 'Any color' }];

    const headRow = document.createElement('tr');
    headRow.appendChild(cell('th', colorIds.length ? 'Color' : ''));
    sizes.forEach((size) => {
      const th = cell('th', size.name);
      th.scope = 'col';
      headRow.appendChild(th);
    });
    const head = document.createElement('thead');
    head.appendChild(headRow);

    const body = document.createElement('tbody');
    colors.forEach((color) => {
      const row = document.createElement('tr');
      const rowHead = cell('th');
      rowHead.scope = 'row';
      const label = cell('span');
      label.className = 'm-stock-color';
      if (color.hex) {
        const dot = document.createElement('i');
        dot.className = 'm-swatch';
        dot.style.background = color.hex;
        label.appendChild(dot);
      }
      label.appendChild(document.createTextNode(color.name));
      rowHead.appendChild(label);
      row.appendChild(rowHead);

      sizes.forEach((size) => {
        const key = `${size.id}-${color.id}`;
        const input = document.createElement('input');
        input.type = 'number';
        input.min = '0';
        input.max = '99999';
        input.inputMode = 'numeric';
        input.name = `stock-${key}`;
        input.placeholder = '0';
        input.value = values[key] ?? '';
        input.dataset.key = key;
        input.setAttribute('aria-label', `Stock of ${color.name}, ${size.name}`);
        markCell(input);
        const td = cell('td');
        td.appendChild(input);
        row.appendChild(td);
      });
      body.appendChild(row);
    });

    grid.replaceChildren(head, body);
    updateTotal();
  };

  document.addEventListener('change', (e) => {
    if (e.target.name === 'sizes' || e.target.name === 'colors') render();
  });
  grid.addEventListener('input', (e) => {
    if (!e.target.dataset.key) return;
    markCell(e.target);
    updateTotal();
  });

  const fillInput = document.getElementById('stock-fill');
  const fillButton = document.querySelector('[data-stock-fill]');
  const fill = () => {
    if (fillInput.value === '') return;
    $$('input[data-key]', grid).forEach((input) => {
      input.value = fillInput.value;
      markCell(input);
    });
    updateTotal();
  };
  if (fillInput && fillButton) {
    fillButton.addEventListener('click', fill);
    fillInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault(); // don't save the whole product form
      fill();
    });
  }

  render();
})();
