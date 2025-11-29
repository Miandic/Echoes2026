// Mobile nav toggle and reveal-on-scroll
(function() {
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('site-nav');
  const backdrop = document.querySelector('.backdrop');

  function openMenu() {
    if (!nav) return;
    nav.classList.add('open');
    document.body.classList.add('no-scroll');
    if (backdrop) backdrop.classList.add('show');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    if (nav) nav.setAttribute('aria-hidden', 'false');
  }

  function closeMenu() {
    if (!nav) return;
    nav.classList.remove('open');
    document.body.classList.remove('no-scroll');
    if (backdrop) backdrop.classList.remove('show');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (nav) nav.setAttribute('aria-hidden', 'true');
  }

  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      if (expanded) closeMenu(); else openMenu();
    });
  }

  // Close on link click (mobile)
  if (nav) {
    nav.addEventListener('click', (e) => {
      const t = e.target;
      if (t && t.tagName === 'A' && nav.classList.contains('open')) {
        closeMenu();
      }
    });
  }

  // Close on backdrop click
  if (backdrop) {
    backdrop.addEventListener('click', closeMenu);
  }

  // ESC to close
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && nav && nav.classList.contains('open')) {
      closeMenu();
    }
  });

  // Reveal on scroll
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

  // Particle background (nodes and beams)
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas ? canvas.getContext('2d') : null;
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let particles = [];
  let rafId = null;
  let lastTs = 0;

  function resizeCanvas() {
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Recompute particle count based on area
    const density = 0.00008; // particles per px^2
    const target = Math.max(20, Math.min(160, Math.floor(w * h * density)));
    particles = createParticles(target, w, h);
  }

  function createParticles(count, w, h) {
    const arr = new Array(count);
    for (let i = 0; i < count; i++) {
      arr[i] = {
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3 * 0.25,
        vy: (Math.random() - 0.5) * 0.3 * 0.25,
        r: 1.2 + Math.random() * 1.6,
      };
    }
    return arr;
  }

  function step(ts) {
    if (!ctx || !canvas) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
  const dt = Math.min(32, ts - lastTs || 16) * 0.25; // slow down to ~0.25x
    lastTs = ts;

    ctx.clearRect(0, 0, w, h);

    // Update
    for (let p of particles) {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (p.x < -10) p.x = w + 10;
      if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10;
      if (p.y > h + 10) p.y = -10;
    }

    // Draw links
    const linkDist = Math.max(60, Math.min(180, Math.hypot(w, h) * 0.07));
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i];
        const b = particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx*dx + dy*dy;
        if (d2 < linkDist * linkDist) {
          const d = Math.sqrt(d2);
          const alpha = 0.35 * (1 - d / linkDist);
          ctx.strokeStyle = `rgba(203, 213, 225, ${alpha.toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // Draw particles (glow)
    for (let p of particles) {
      ctx.fillStyle = 'rgba(147, 197, 253, 0.9)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }

    rafId = requestAnimationFrame(step);
  }

  function startParticles() {
    if (!canvas || !ctx || prefersReduced) return;
    resizeCanvas();
    if (!rafId) rafId = requestAnimationFrame(step);
  }

  function stopParticles() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  // Initialize
  if (canvas && !prefersReduced) {
    startParticles();
    window.addEventListener('resize', resizeCanvas);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopParticles(); else if (!rafId) startParticles();
    });
  }
})();
