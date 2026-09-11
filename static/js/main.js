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
  function showImage(thumb) {
    if (!mainImg || !thumb) return;
    $$('.gallery__thumb', gallery).forEach((t) => t.classList.toggle('is-active', t === thumb));
    if (mainImg.getAttribute('src') === thumb.dataset.src) return;
    mainImg.classList.add('is-swapping');
    const img = new Image();
    img.onload = () => { mainImg.src = thumb.dataset.src; mainImg.classList.remove('is-swapping'); };
    img.src = thumb.dataset.src;
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
    });

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
      }
    });
  }

  /* ---------- Checkout: prevent double submission ---------- */
  const checkout = $('[data-checkout]');
  if (checkout) {
    checkout.addEventListener('submit', () => {
      const btn = $('[data-submit]', checkout);
      setTimeout(() => { btn.disabled = true; btn.textContent = 'Placing your order…'; }, 0);
    });
  }
})();
