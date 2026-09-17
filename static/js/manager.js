(function () {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- Sidebar on small screens ---------- */
  const shell = $('[data-shell]');
  document.addEventListener('click', (e) => {
    if (!shell) return;
    if (e.target.closest('[data-side-open]')) shell.classList.add('is-open');
    else if (e.target.closest('[data-side-close]')) shell.classList.remove('is-open');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && shell) shell.classList.remove('is-open');
  });

  /* ---------- Messages ---------- */
  $$('.m-toast').forEach((toast, i) => {
    setTimeout(() => {
      toast.classList.add('is-leaving');
      setTimeout(() => toast.remove(), 400);
    }, 4200 + i * 400);
  });

  /* ---------- Confirm before deleting ---------- */
  document.addEventListener('submit', (e) => {
    const message = e.target.dataset && e.target.dataset.confirm;
    if (message && !window.confirm(message)) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  }, true);

  /* ---------- Filters that apply as soon as they change ---------- */
  $$('select[data-autosubmit]').forEach((select) => {
    select.addEventListener('change', () => select.form.submit());
  });

  /* ---------- Whole table rows are clickable ---------- */
  document.addEventListener('click', (e) => {
    const row = e.target.closest('[data-href]');
    if (!row || e.target.closest('a, button, input, select, textarea, label, form')) return;
    if (e.ctrlKey || e.metaKey) window.open(row.dataset.href, '_blank');
    else window.location.href = row.dataset.href;
  });

  /* ---------- On/off switches save instantly ---------- */
  document.addEventListener('submit', async (e) => {
    const form = e.target.closest('[data-toggle-form]');
    if (!form || !window.fetch) return;
    e.preventDefault();
    const button = $('button', form);
    button.disabled = true;
    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'x-requested-with': 'fetch' },
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      button.setAttribute('aria-checked', String(data.value));
    } catch (err) {
      form.submit();
    } finally {
      button.disabled = false;
    }
  });

  /* ---------- Product photos ---------- */
  document.addEventListener('change', (e) => {
    if (e.target.matches('[data-main]')) {
      $$('[data-photo]').forEach((photo) => photo.classList.toggle('is-main', photo.contains(e.target)));
    }
    if (e.target.matches('[data-remove]')) {
      e.target.closest('[data-photo]').classList.toggle('is-removed', e.target.checked);
    }
  });

  $$('[data-dropzone]').forEach((zone) => {
    const input = $('input[type="file"]', zone);
    const label = $('[data-dropzone-label]', zone);
    const list = zone.parentElement.querySelector('[data-preview-list]');
    const render = () => {
      const files = Array.from(input.files);
      if (list) {
        list.innerHTML = '';
        files.forEach((file) => {
          const img = document.createElement('img');
          img.alt = '';
          img.src = URL.createObjectURL(file);
          list.appendChild(img);
        });
      }
      if (label) {
        label.textContent = files.length
          ? `${files.length} photo${files.length > 1 ? 's' : ''} ready — they upload when you save`
          : 'Click to add photos';
      }
    };
    input.addEventListener('change', render);
    ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (e) => {
      e.preventDefault();
      zone.classList.add('is-over');
    }));
    ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, () => zone.classList.remove('is-over')));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        render();
      }
    });
  });

  /* ---------- Promo code type ---------- */
  const kinds = $$('input[name="kind"]');
  if (kinds.length) {
    const valueField = $('[data-kind-value]');
    const suffix = $('[data-kind-suffix]');
    const update = () => {
      const kind = (kinds.find((k) => k.checked) || {}).value;
      if (valueField) valueField.hidden = kind === 'free_delivery';
      if (suffix) suffix.textContent = kind === 'fixed' ? suffix.dataset.currency : '%';
    };
    kinds.forEach((k) => k.addEventListener('change', update));
    update();
  }

  /* ---------- In-store sale form ---------- */
  const saleForm = $('[data-sale-form]');
  if (saleForm) {
    const rowsBox = $('[data-sale-rows]', saleForm);
    const template = $('#sale-row');
    const totalEl = $('[data-sale-total]', saleForm);
    const currency = saleForm.dataset.currency || '';
    const knownIds = new Set($$('#sale-products option').map((o) => o.value.toLowerCase()));
    const EMPTY_TEXT = 'Enter an ID or pick a product';

    const promoInput = $('[data-promo-input]', saleForm);
    const promoMsg = $('[data-promo-msg]', saleForm);
    let promo = null; // rules of the applied promo code

    const money = (amount) => {
      const value = Math.round(amount * 100) / 100;
      const text = Number.isInteger(value)
        ? value.toLocaleString('en-US')
        : value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return currency + text;
    };

    const showPromoMessage = (text, type) => {
      promoMsg.textContent = text;
      promoMsg.className = `m-sale-promo__msg${type ? ` is-${type}` : ''}`;
    };

    const updateTotals = () => {
      let subtotal = 0;
      $$('[data-row]', rowsBox).forEach((row, i) => {
        const qty = parseInt($('[name="item_qty"]', row).value, 10) || 0;
        const price = parseFloat($('[name="item_price"]', row).value) || 0;
        subtotal += qty * price;
        $('[data-line-total]', row).textContent = money(qty * price);
        $('[data-row-num]', row).textContent = i + 1;
      });

      let discount = 0;
      if (promo) {
        if (promo.min_subtotal && subtotal < promo.min_subtotal) {
          showPromoMessage(
            `Add ${money(promo.min_subtotal - subtotal)} more to use ${promo.code} (minimum order ${money(promo.min_subtotal)}).`,
            'error',
          );
        } else {
          discount = promo.kind === 'percent' ? Math.round(subtotal * promo.value) / 100 : promo.value;
          discount = Math.min(discount, subtotal);
          showPromoMessage(`${promo.code} applied — ${promo.label}`, 'ok');
        }
      }

      $('[data-sale-subtotal]', saleForm).textContent = money(subtotal);
      $('[data-sale-discount]', saleForm).textContent = `−${money(discount)}`;
      $('[data-discount-code]', saleForm).textContent = promo ? `(${promo.code})` : '';
      $('[data-subtotal-row]', saleForm).hidden = !discount;
      $('[data-discount-row]', saleForm).hidden = !discount;
      totalEl.textContent = money(subtotal - discount);
    };

    const applyPromo = async () => {
      const code = promoInput.value.trim();
      promo = null;
      if (!code) {
        showPromoMessage('', '');
        updateTotals();
        return;
      }
      showPromoMessage('Checking the code…', '');
      try {
        const res = await fetch(`${saleForm.dataset.promoUrl}?code=${encodeURIComponent(code)}`, {
          headers: { 'x-requested-with': 'fetch' },
          credentials: 'same-origin',
        });
        const data = await res.json();
        if (promoInput.value.trim() !== code) return; // the code changed while we were checking
        if (data.ok) {
          promo = data;
          promoInput.value = data.code;
        } else {
          showPromoMessage(data.error, 'error');
        }
      } catch (err) {
        showPromoMessage('Couldn’t check the code — try again.', 'error');
      }
      updateTotals();
    };

    const fillSelect = (select, options, selected) => {
      select.replaceChildren();
      if (!options.length) {
        select.appendChild(new Option('—', ''));
        return;
      }
      if (options.length > 1) select.appendChild(new Option('Choose…', ''));
      options.forEach((name) => select.appendChild(new Option(name, name, false, name === selected)));
      if (options.length === 1) select.value = options[0];
    };

    const setPhoto = (row, url) => {
      const img = $('[data-product-img]', row);
      const icon = $('[data-photo-icon]', row);
      if (url) {
        if (img.getAttribute('src') !== url) img.src = url;
        img.hidden = false;
        icon.setAttribute('hidden', '');
      } else {
        img.hidden = true;
        img.removeAttribute('src');
        icon.removeAttribute('hidden');
      }
    };

    // The photo of the chosen color, or the product's main photo.
    const photoForColor = (row) => {
      const data = row.productData;
      if (!data) return '';
      const color = $('[name="item_color"]', row).value;
      return (color && data.photos[color]) || data.image;
    };

    const setText = (row, name, meta) => {
      const box = $('[data-product-text]', row);
      box.replaceChildren();
      if (name) {
        const strong = document.createElement('strong');
        strong.textContent = name;
        box.appendChild(strong);
      }
      if (meta) {
        const span = document.createElement('span');
        span.className = name ? 'm-muted m-small' : 'm-small';
        span.textContent = meta;
        box.appendChild(span);
      }
    };

    // "ID TF-1000 · 4 in stock" once the size and color are chosen.
    const showStock = (row) => {
      const data = row.productData;
      if (!data) return;
      const size = $('[name="item_size"]', row).value;
      const color = $('[name="item_color"]', row).value;
      let meta = `ID ${data.id}`;
      if ((!data.sizes.length || size) && (!data.colors.length || color)) {
        const count = data.stock[`${size}|${color}`] || 0;
        meta += count ? ` · ${count} in stock` : ' · out of stock';
      } else {
        meta += ` · choose ${data.sizes.length && !size ? 'a size' : 'a color'}`;
      }
      if (!data.in_stock) meta += ' · marked not for sale';
      setText(row, data.name, meta);
    };

    const resetRow = (row, message) => {
      row.productData = null;
      row.dataset.lookedUp = '';
      row.classList.remove('is-found', 'is-missing');
      setPhoto(row, '');
      setText(row, '', message);
      fillSelect($('[name="item_size"]', row), [], '');
      fillSelect($('[name="item_color"]', row), [], '');
    };

    const lookup = async (row, keep = {}) => {
      const input = $('[name="item_product"]', row);
      const raw = input.value.trim();
      if (!raw) {
        resetRow(row, EMPTY_TEXT);
        return;
      }
      if (row.dataset.lookedUp === raw.toLowerCase()) return; // already showing this product
      setText(row, '', 'Looking it up…');
      try {
        const res = await fetch(`${saleForm.dataset.lookupUrl}?id=${encodeURIComponent(raw)}`, {
          headers: { 'x-requested-with': 'fetch' },
          credentials: 'same-origin',
        });
        const data = await res.json();
        if (input.value.trim() !== raw) return; // the ID changed while we were looking
        if (!data.ok) {
          resetRow(row, `No product has the ID “${raw}”.`);
          row.classList.add('is-missing');
          return;
        }
        row.productData = data;
        row.dataset.lookedUp = raw.toLowerCase();
        row.classList.remove('is-missing');
        row.classList.add('is-found');
        fillSelect($('[name="item_size"]', row), data.sizes, keep.size || '');
        fillSelect($('[name="item_color"]', row), data.colors, keep.color || '');
        showStock(row);
        setPhoto(row, photoForColor(row));
        $('[name="item_price"]', row).value = keep.price || data.price;
        updateTotals();
      } catch (err) {
        setText(row, '', 'Couldn’t look this up — check the connection and try again.');
      }
    };

    const addRow = (data = {}) => {
      const row = template.content.firstElementChild.cloneNode(true);
      rowsBox.appendChild(row);
      const input = $('[name="item_product"]', row);
      input.value = data.product || '';
      $('[name="item_qty"]', row).value = data.qty || 1;
      if (data.price) $('[name="item_price"]', row).value = data.price;

      // Picking from the suggestion list doesn't fire "change" until the field
      // loses focus, so look the product up as soon as the value is a known ID.
      input.addEventListener('input', () => {
        const value = input.value.trim().toLowerCase();
        if (knownIds.has(value)) lookup(row);
        else if (!value) resetRow(row, EMPTY_TEXT);
      });
      input.addEventListener('change', () => lookup(row));
      input.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        lookup(row).then(() => $('[name="item_qty"]', row).focus());
      });
      row.addEventListener('input', (e) => {
        if (e.target.matches('[name="item_qty"], [name="item_price"]')) updateTotals();
      });
      row.addEventListener('change', (e) => {
        if (e.target.name === 'item_color') setPhoto(row, photoForColor(row));
        if (e.target.name === 'item_color' || e.target.name === 'item_size') showStock(row);
      });
      $('[data-remove-row]', row).addEventListener('click', () => {
        if ($$('[data-row]', rowsBox).length > 1) {
          row.remove();
        } else {
          input.value = '';
          $('[name="item_price"]', row).value = '';
          $('[name="item_qty"]', row).value = 1;
          resetRow(row, EMPTY_TEXT);
        }
        updateTotals();
      });

      if (data.product) lookup(row, data);
      updateTotals();
      return row;
    };

    $('[data-add-row]', saleForm).addEventListener('click', () => {
      $('[name="item_product"]', addRow()).focus();
    });

    // Promo code: Apply button, Enter key, and forget the code once it's edited.
    $('[data-promo-apply]', saleForm).addEventListener('click', applyPromo);
    promoInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      applyPromo();
    });
    promoInput.addEventListener('input', () => {
      if (promo && promoInput.value.trim().toUpperCase() !== promo.code) {
        promo = null;
        showPromoMessage('', '');
        updateTotals();
      }
    });

    const saved = JSON.parse($('#sale-rows-data').textContent || '[]');
    (saved.length ? saved : [{}]).forEach((data) => addRow(data));
    if (!saved.length) $('[name="item_product"]', rowsBox).focus();
    // Re-apply a code kept after a failed save (unless the server said it's invalid).
    if (promoInput.value.trim() && !promoMsg.textContent.trim()) applyPromo();
  }

  /* ---------- Print ---------- */
  $$('[data-print]').forEach((button) => button.addEventListener('click', () => window.print()));
})();
