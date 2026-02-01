// Mobile nav toggle and reveal-on-scroll
(function() {
  const backdrop = document.querySelector('.backdrop');
  const dropdownItems = document.querySelectorAll('.has-dropdown');

  // Close on backdrop click
  if (backdrop) {
    backdrop.addEventListener('click', () => {
      document.body.classList.remove('no-scroll');
      backdrop.classList.remove('show');
    });
  }

  // Email copy to clipboard
  const emailButton = document.querySelector('.email-copy');
  if (emailButton) {
    emailButton.addEventListener('click', async function(e) {
      e.preventDefault();
      const email = this.getAttribute('data-email');
      
      try {
        await navigator.clipboard.writeText(email);
        this.classList.add('copied');
        setTimeout(() => {
          this.classList.remove('copied');
        }, 2000);
      } catch (err) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = email;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
          document.execCommand('copy');
          this.classList.add('copied');
          setTimeout(() => {
            this.classList.remove('copied');
          }, 2000);
        } catch (err2) {
          console.error('Failed to copy email:', err2);
        }
        document.body.removeChild(textArea);
      }
    });
  }

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href === '#') return;
      
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
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

    const density = 0.00008;
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

  function updateParticles(dt, w, h) {
    for (let p of particles) {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      p.x = Math.max(0, Math.min(w, p.x));
      p.y = Math.max(0, Math.min(h, p.y));
    }
  }

  function drawParticles() {
    if (!ctx || !canvas) return;
    const w = canvas.width / (Math.min(window.devicePixelRatio || 1, 2));
    const h = canvas.height / (Math.min(window.devicePixelRatio || 1, 2));

    ctx.clearRect(0, 0, w, h);

    const maxDist = 140;
    const maxDist2 = maxDist * maxDist;
    for (let i = 0; i < particles.length; i++) {
      const a = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < maxDist2) {
          const alpha = (1 - Math.sqrt(d2) / maxDist) * 0.12;
          ctx.strokeStyle = `rgba(96,165,250,${alpha})`;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    ctx.fillStyle = 'rgba(147,197,253,0.6)';
    for (let p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function animate(ts) {
    if (!lastTs) lastTs = ts;
    const dt = Math.min((ts - lastTs) / 16, 3);
    lastTs = ts;

    const w = canvas ? canvas.width / (Math.min(window.devicePixelRatio || 1, 2)) : 0;
    const h = canvas ? canvas.height / (Math.min(window.devicePixelRatio || 1, 2)) : 0;
    updateParticles(dt, w, h);
    drawParticles();

    rafId = requestAnimationFrame(animate);
  }

  if (canvas && ctx && !prefersReduced) {
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    animate(0);
  }
})();
