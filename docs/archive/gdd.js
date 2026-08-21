(function () {
  'use strict';

  // ─── Theme toggle ──────────────────────────────────────────────
  var root = document.documentElement;
  var STORAGE_KEY = 'gdd-theme';

  function applyTheme(theme) {
    if (theme === 'dark' || theme === 'light') {
      root.setAttribute('data-theme', theme);
    } else {
      root.removeAttribute('data-theme');
    }
  }

  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'light') applyTheme(saved);
  } catch (e) { /* localStorage unavailable */ }

  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var current = root.getAttribute('data-theme');
      var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var effective = current || (prefersDark ? 'dark' : 'light');
      var next = effective === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      try { localStorage.setItem(STORAGE_KEY, next); } catch (e) { /* ignore */ }
    });
  }

  // ─── Inline term reveal ────────────────────────────────────────
  document.querySelectorAll('button.term').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var targetId = btn.getAttribute('aria-controls');
      if (!targetId) return;
      var panel = document.getElementById(targetId);
      if (!panel) return;
      var open = panel.getAttribute('data-open') === 'true';
      var next = !open;
      panel.setAttribute('data-open', String(next));
      btn.setAttribute('aria-expanded', String(next));
    });
  });

  // ─── Reading progress bar ──────────────────────────────────────
  var pbar = document.getElementById('pbar');
  function updateProgress() {
    var h = document.documentElement;
    var scrolled = h.scrollTop || document.body.scrollTop;
    var max = (h.scrollHeight - h.clientHeight) || 1;
    var pct = Math.min(100, Math.max(0, (scrolled / max) * 100));
    if (pbar) pbar.style.setProperty('--p', pct.toFixed(2) + '%');
  }
  window.addEventListener('scroll', updateProgress, { passive: true });
  window.addEventListener('resize', updateProgress);
  updateProgress();

  // ─── IntersectionObserver fade-in ──────────────────────────────
  var prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!prefersReduced && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
    document.querySelectorAll('.rise').forEach(function (el) { io.observe(el); });
  } else {
    document.querySelectorAll('.rise').forEach(function (el) { el.classList.add('in'); });
  }

  // ─── Chapter list + drawer state ───────────────────────────────
  var chapters = Array.prototype.slice.call(
    document.querySelectorAll('.chapter, .cover, #intro')
  );
  var chapterIds = chapters.map(function (c) { return c.id; });
  var drawerLinks = Array.prototype.slice.call(document.querySelectorAll('.ch-link'));
  var subGroups = Array.prototype.slice.call(document.querySelectorAll('.ch-subs'));
  var subLinks = Array.prototype.slice.call(document.querySelectorAll('.ch-subs a'));
  var here = document.getElementById('here');

  function getCurrentChapter() {
    var y = window.scrollY + 100;
    var current = chapters[0];
    for (var i = 0; i < chapters.length; i++) {
      if (chapters[i].offsetTop <= y) current = chapters[i];
      else break;
    }
    return current;
  }

  function updateHighlights() {
    var current = getCurrentChapter();
    if (!current) return;
    var id = current.id;

    drawerLinks.forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('data-target') === id);
    });
    subGroups.forEach(function (g) {
      g.setAttribute('data-open', g.getAttribute('data-for') === id ? 'true' : 'false');
    });

    if (here) {
      var title = current.getAttribute('data-title');
      if (title) { here.textContent = title; here.classList.add('active'); }
      else { here.textContent = 'Field Manual'; here.classList.remove('active'); }
    }

    // active sub-link (closest h3 above current scroll)
    var y = window.scrollY + 120;
    var currentSubId = null;
    subLinks.forEach(function (a) {
      var hash = a.getAttribute('href');
      if (!hash || hash[0] !== '#') return;
      var target = document.getElementById(hash.slice(1));
      if (!target) return;
      if (target.getBoundingClientRect().top + window.scrollY <= y) currentSubId = hash;
    });
    subLinks.forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('href') === currentSubId);
    });
  }
  window.addEventListener('scroll', updateHighlights, { passive: true });
  updateHighlights();

  // ─── Drawer open/close ─────────────────────────────────────────
  var drawer = document.getElementById('drawer');
  var backdrop = document.getElementById('backdrop');
  var navTrigger = document.getElementById('nav-trigger');
  var drawerClose = document.getElementById('drawer-close');

  function openDrawer() {
    if (!drawer) return;
    drawer.setAttribute('data-open', 'true');
    drawer.setAttribute('aria-hidden', 'false');
    if (backdrop) backdrop.setAttribute('data-open', 'true');
    if (navTrigger) navTrigger.setAttribute('aria-expanded', 'true');
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.setAttribute('data-open', 'false');
    drawer.setAttribute('aria-hidden', 'true');
    if (backdrop) backdrop.setAttribute('data-open', 'false');
    if (navTrigger) navTrigger.setAttribute('aria-expanded', 'false');
  }

  if (navTrigger) navTrigger.addEventListener('click', openDrawer);
  if (drawerClose) drawerClose.addEventListener('click', closeDrawer);
  if (backdrop) backdrop.addEventListener('click', closeDrawer);

  // Close drawer when a link inside it is clicked
  document.querySelectorAll('.drawer-nav a').forEach(function (a) {
    a.addEventListener('click', function () { setTimeout(closeDrawer, 80); });
  });

  // ─── Keyboard navigation ───────────────────────────────────────
  function jumpChapter(direction) {
    var current = getCurrentChapter();
    if (!current) return;
    var idx = chapterIds.indexOf(current.id);
    var nextIdx = idx + direction;
    if (nextIdx < 0 || nextIdx >= chapters.length) return;
    chapters[nextIdx].scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  document.addEventListener('keydown', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    if (e.key === '/' || e.key === '?') {
      e.preventDefault();
      var isOpen = drawer && drawer.getAttribute('data-open') === 'true';
      if (isOpen) closeDrawer(); else openDrawer();
    } else if (e.key === 'Escape') {
      closeDrawer();
    } else if (e.key === '[') {
      jumpChapter(-1);
    } else if (e.key === ']') {
      jumpChapter(1);
    }
  });
})();
