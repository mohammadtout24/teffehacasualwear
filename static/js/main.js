(function () {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- Panels: menu, search, bag drawer, mobile filters ---------- */
  const panels = {
    menu: $('[data-panel="menu"]'),
    search: $('[data-panel="search"]'),
    bag: $('[data-panel="bag"]'),
    filters: $('[data-panel="filters"]'),
  };

  function openPanel(name) {
    const panel = panels[name];
    if (!panel) return;
    Object.keys(panels).forEach((other) => other !== name && closePanel(other));
    if (name === 'filters') {
      panel.classList.add('is-open');
    } else {
      panel.hidden = false;
    }
    if (name !== 'search') document.body.classList.add('no-scroll');
    if (name === 'search') {
      const input = $('input', panel);
      input && input.focus();
    }
  }

  function closePanel(name) {
    const panel = panels[name];
    if (!panel) return;
    if (name === 'filters') panel.classList.remove('is-open');
    else panel.hidden = true;
    document.body.classList.remove('no-scroll');
  }

  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open]');
    if (opener) {
      const name = opener.dataset.open;
      const panel = panels[name];
      const isOpen = panel && (name === 'filters' ? panel.classList.contains('is-open') : !panel.hidden);
      isOpen ? closePanel(name) : openPanel(name);
      return;
    }
    const closer = e.target.closest('[data-close]');
    if (closer) {
      const panel = closer.closest('[data-panel]');
      if (panel) closePanel(panel.dataset.panel);
      return;
    }
    // Bag icon opens the drawer (except on the bag and checkout pages).
    const bagLink = e.target.closest('[data-open-drawer]');
    if (bagLink && panels.bag && !/\/(bag|checkout)\//.test(location.pathname)) {
      e.preventDefault();
      openPanel('bag');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') Object.keys(panels).forEach(closePanel);
  });

  /* ---------- Confirm before destructive forms ---------- */
  document.addEventListener('submit', (e) => {
    const message = e.target.dataset && e.target.dataset.confirm;
    if (message && !window.confirm(message)) e.preventDefault();
  });

  /* ---------- Toasts ---------- */
  $$('.toast').forEach((toast, i) => {
    setTimeout(() => {
      toast.classList.add('is-leaving');
      setTimeout(() => toast.remove(), 450);
    }, 4200 + i * 400);
  });

  /* ---------- Auto-submitting controls ---------- */
  $$('select[data-autosubmit]').forEach((select) => {
    select.addEventListener('change', () => select.form.submit());
  });

  /* ---------- Quantity steppers ---------- */
  $$('[data-qty]').forEach((qty) => {
    const input = $('input[type="number"]', qty);
    const autosubmit = qty.hasAttribute('data-autosubmit-qty');
    let timer;
    const commit = () => {
      if (!autosubmit) return;
      clearTimeout(timer);
      timer = setTimeout(() => qty.submit(), 450);
    };
    $$('[data-step]', qty).forEach((btn) => {
      btn.addEventListener('click', () => {
        const min = parseInt(input.min || '0', 10);
        const max = parseInt(input.max || '20', 10);
        const next = Math.min(max, Math.max(min, (parseInt(input.value, 10) || 0) + parseInt(btn.dataset.step, 10)));
        if (String(next) !== input.value) {
          input.value = next;
          commit();
        }
      });
    });
    input.addEventListener('change', commit);
  });

  /* ---------- Product gallery ---------- */
  const gallery = $('[data-gallery]');
  const mainImg = gallery && $('[data-gallery-main]', gallery);
  // The photo most recently asked for; an older photo that finishes loading later is ignored.
  let wantedSrc = mainImg ? mainImg.getAttribute('src') : '';
  function showImage(thumb) {
    if (!mainImg || !thumb) return;
    $$('.gallery__thumb', gallery).forEach((t) => t.classList.toggle('is-active', t === thumb));
    const src = thumb.dataset.src;
    if (src === wantedSrc) return;
    wantedSrc = src;
    mainImg.classList.add('is-swapping');
    const img = new Image();
    img.onload = () => {
      if (wantedSrc !== src) return;
      mainImg.src = src;
      mainImg.classList.remove('is-swapping');
    };
    img.src = src;
  }
  if (gallery) {
    gallery.addEventListener('click', (e) => {
      const thumb = e.target.closest('.gallery__thumb');
      if (thumb) showImage(thumb);
    });
  }

  /* ---------- Add to bag ---------- */
  const form = $('[data-add-to-cart]');
  if (form) {
    const colorLabel = $('[data-color-label]', form);
    const sizeLabel = $('[data-size-label]', form);
    const errorBox = $('[data-form-error]', form);

    // Stock per "size|color", capped by the server: 0 sold out, 1-2 left, 3 plenty.
    const stockData = document.getElementById('variant-stock');
    const stock = stockData ? JSON.parse(stockData.textContent) : null;
    const stockMsg = $('[data-stock-msg]', form);
    const addButton = $('button[type="submit"]', form);
    const sizeInputs = () => $$('input[name="size"]', form);
    const colorInputs = () => $$('input[name="color"]', form);
    const picked = (inputs) => (inputs.find((input) => input.checked) || {}).value || '';
    const left = (size, color) => (stock && stock[`${size}|${color}`]) || 0;
    const sizeNames = () => (sizeInputs().length ? sizeInputs().map((input) => input.value) : ['']);

    function updateStock() {
      if (!stock || !addButton || !stockMsg) return;
      const color = picked(colorInputs());
      colorInputs().forEach((input) => {
        input.closest('.swatch').classList.toggle('is-sold-out', sizeNames().every((size) => !left(size, input.value)));
      });
      const sizes = sizeInputs();
      sizes.forEach((input) => {
        const soldOut = !left(input.value, color);
        input.disabled = soldOut;
        input.closest('.size-box').classList.toggle('is-sold-out', soldOut);
        if (soldOut && input.checked) {
          input.checked = false;
          if (sizeLabel) sizeLabel.textContent = 'Select a size';
        }
      });

      const size = picked(sizes);
      const allSizesOut = sizes.length > 0 && sizes.every((input) => input.disabled);
      const count = !sizes.length || size ? left(size, color) : null;
      let text = '';
      if (allSizesOut || count === 0) text = colorInputs().length ? 'Sold out in this color' : 'Sold out';
      else if (count && count <= 2) text = `Only ${count} left`;
      stockMsg.textContent = text;
      stockMsg.hidden = !text;
      stockMsg.classList.toggle('is-out', allSizesOut || count === 0);
      addButton.disabled = allSizesOut || count === 0;

      const qty = $('input[name="quantity"]', form);
      if (qty) {
        qty.max = count && count <= 2 ? count : 20;
        if (parseInt(qty.value, 10) > parseInt(qty.max, 10)) qty.value = qty.max;
      }
    }

    form.addEventListener('change', (e) => {
      if (e.target.name === 'color') {
        colorLabel && (colorLabel.textContent = e.target.value);
        const thumb = gallery && $$('.gallery__thumb', gallery).find((t) => t.dataset.color === e.target.value);
        showImage(thumb);
      }
      if (e.target.name === 'size') {
        sizeLabel && (sizeLabel.textContent = e.target.value);
        e.target.closest('.option').classList.remove('is-invalid');
        errorBox.hidden = true;
      }
      updateStock();
    });

    // If the pre-selected color is completely sold out, start on one that isn't.
    if (stock) {
      const current = colorInputs().find((input) => input.checked);
      const hasStock = (input) => sizeNames().some((size) => left(size, input.value));
      const better = current && !hasStock(current) && colorInputs().find(hasStock);
      if (better) {
        better.checked = true;
        better.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    updateStock();

    form.addEventListener('submit', async (e) => {
      const sizeInputs = $$('input[name="size"]', form);
      if (sizeInputs.length && !sizeInputs.some((i) => i.checked)) {
        e.preventDefault();
        sizeInputs[0].closest('.option').classList.add('is-invalid');
        errorBox.textContent = 'Please choose your size.';
        errorBox.hidden = false;
        return;
      }
      if (!window.fetch) return;
      e.preventDefault();
      const button = $('button[type="submit"]', form);
      button.disabled = true;
      const label = button.textContent;
      button.textContent = 'Adding…';
      try {
        const res = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          headers: { 'x-requested-with': 'fetch' },
          credentials: 'same-origin',
        });
        const data = await res.json();
        if (!data.ok) {
          errorBox.textContent = data.error || 'Something went wrong. Please try again.';
          errorBox.hidden = false;
          return;
        }
        $$('[data-cart-count]').forEach((el) => {
          el.textContent = data.count;
          el.hidden = false;
          el.classList.remove('bump');
          void el.offsetWidth;
          el.classList.add('bump');
        });
        const body = $('[data-drawer-body]');
        if (body) body.innerHTML = data.drawer;
        openPanel('bag');
      } catch (err) {
        form.submit();
      } finally {
        button.disabled = false;
        button.textContent = label;
        updateStock();
      }
    });
  }

  /* ---------- Checkout: promo code + prevent double submission ---------- */
  const checkout = $('[data-checkout]');
  if (checkout) {
    checkout.addEventListener('submit', (e) => {
      const promoBtn = e.submitter && e.submitter.name === 'action' ? e.submitter : null;
      const btn = promoBtn || $('[data-submit]', checkout);
      const busy = !promoBtn ? 'Placing your order…' : promoBtn.value === 'apply_promo' ? 'Applying…' : 'Removing…';
      setTimeout(() => { btn.disabled = true; btn.textContent = busy; }, 0);
    });

    // Choosing a saved address fills in the delivery fields.
    const savedAddresses = $('[data-saved-addresses]', checkout);
    if (savedAddresses) {
      const setField = (name, value) => {
        const input = checkout.querySelector(`[name="${name}"]`);
        if (input) input.value = value;
      };
      savedAddresses.addEventListener('change', (e) => {
        const radio = e.target;
        if (radio.name !== 'saved_address') return;
        if (radio.hasAttribute('data-new')) {
          setField('city', '');
          setField('address', '');
          const city = checkout.querySelector('[name="city"]');
          city && city.focus();
        } else {
          ['full_name', 'phone', 'city', 'address'].forEach((name) => setField(name, radio.dataset[name]));
        }
      });
    }

    // Enter in the promo field applies the code instead of placing the order.
    const promoInput = $('[data-promo-input]', checkout);
    if (promoInput) {
      promoInput.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        $('[data-promo-apply]', checkout).click();
      });
    }
  }
})();
