// Registration form logic
(function () {
  const form = document.getElementById('reg-form');
  if (!form) return;

  const toggleBtns = document.querySelectorAll('.toggle-btn');
  const fieldsIndividual = form.querySelector('.fields-individual');
  const fieldsLegal = form.querySelector('.fields-legal');
  const entityTypeInput = form.querySelector('#entity_type');
  const errorBox = document.getElementById('form-error');
  const successBox = document.getElementById('form-success');
  const submitBtn = document.getElementById('submit-btn');
  const legalInfoBlock = document.getElementById('legal-info');

  toggleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      toggleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const type = btn.dataset.type;
      entityTypeInput.value = type;
      if (type === 'individual') {
        // Показать форму, скрыть блок юрлица
        form.style.display = '';
        if (legalInfoBlock) legalInfoBlock.style.display = 'none';
        fieldsIndividual.style.display = '';
        fieldsLegal.style.display = 'none';
      } else {
        // Скрыть форму, показать блок юрлица
        form.style.display = 'none';
        if (legalInfoBlock) legalInfoBlock.style.display = '';
      }
    });
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorBox.style.display = 'none';
    successBox.style.display = 'none';

    const type = entityTypeInput.value;
    const data = {
      entity_type: type,
      email: form.email.value.trim(),
      phone: form.phone.value.trim(),
      report_type: form.querySelector('input[name="report_type"]:checked')?.value || '',
      participation_type: form.querySelector('input[name="participation_type"]:checked')?.value || '',
      hotel: form.hotel.checked,
      oferta: form.oferta.checked,
    };

    if (type === 'individual') {
      data.full_name = form.full_name.value.trim();
      data.organization = form.organization.value.trim();
    } else {
      data.company_name = form.company_name.value.trim();
      data.inn = form.inn.value.trim();
      data.representative_name = form.representative_name.value.trim();
      data.representative_position = form.representative_position.value.trim();
    }

    // Client-side validation
    const fieldLabels = {
      full_name: 'ФИО',
      organization: 'Организация',
      company_name: 'Наименование организации',
      inn: 'ИНН',
      representative_name: 'ФИО представителя',
      representative_position: 'Должность',
      email: 'Электронная почта',
      phone: 'Номер телефона',
      report_type: 'Вид доклада',
      participation_type: 'Тип участия',
    };
    const clientErrors = [];
    const typeFields = type === 'individual'
      ? ['full_name', 'organization']
      : ['company_name', 'inn', 'representative_name', 'representative_position'];
    for (const f of [...typeFields, 'email', 'phone', 'report_type', 'participation_type']) {
      if (!data[f]) clientErrors.push(fieldLabels[f]);
    }
    if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) clientErrors.push('Электронная почта');
    if (data.phone && !/^\+\d{10,15}$/.test(data.phone)) clientErrors.push('Номер телефона');
    if (type === 'individual' && data.full_name && data.full_name.split(/\s+/).filter(Boolean).length < 2) clientErrors.push('ФИО');
    if (type === 'legal' && data.representative_name && data.representative_name.split(/\s+/).filter(Boolean).length < 2) clientErrors.push('ФИО представителя');
    if (clientErrors.length) {
      errorBox.textContent = 'Заполните обязательные поля: ' + clientErrors.join(', ');
      errorBox.style.display = '';
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Переход к оплате…';

    try {
      const resp = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const json = await resp.json();
      if (resp.ok && json.paymentUrl) {
        window.location.href = json.paymentUrl;
      } else {
        errorBox.textContent = json.error || 'Произошла ошибка. Попробуйте ещё раз.';
        errorBox.style.display = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Перейти к оплате';
      }
    } catch {
      errorBox.textContent = 'Не удалось отправить данные. Проверьте соединение.';
      errorBox.style.display = '';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Перейти к оплате';
    }
  });
})();

// Legal entity inquiry form
(function () {
  const legalForm = document.getElementById('legal-form');
  if (!legalForm) return;

  const errorBox  = document.getElementById('legal-form-error');
  const successBox = document.getElementById('legal-form-success');
  const submitBtn  = document.getElementById('legal-submit-btn');

  legalForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorBox.style.display = 'none';
    successBox.style.display = 'none';

    const companyName  = legalForm.legal_company_name.value.trim();
    const contactName  = legalForm.legal_contact_name.value.trim();
    const email        = legalForm.legal_email.value.trim();
    const phone        = legalForm.legal_phone.value.trim();

    const errors = [];
    if (!companyName) errors.push('Наименование организации');
    if (!contactName || contactName.split(/\s+/).filter(Boolean).length < 2) errors.push('Контактное лицо (ФИО)');
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.push('Электронная почта');
    if (!phone || !/^\+\d{10,15}$/.test(phone)) errors.push('Номер телефона');

    if (errors.length) {
      errorBox.textContent = 'Заполните обязательные поля: ' + errors.join(', ');
      errorBox.style.display = '';
      return;
    }

    const data = {
      company_name:   companyName,
      contact_name:   contactName,
      email,
      phone,
      cnt_in_person:   parseInt(legalForm.cnt_in_person.value)   || 0,
      cnt_student:     parseInt(legalForm.cnt_student.value)     || 0,
      cnt_accompanying: parseInt(legalForm.cnt_accompanying.value) || 0,
      cnt_remote:      parseInt(legalForm.cnt_remote.value)      || 0,
    };

    submitBtn.disabled = true;
    submitBtn.textContent = 'Отправляем…';

    try {
      const resp = await fetch('/api/legal_inquiry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const json = await resp.json();
      if (resp.ok) {
        successBox.style.display = '';
        legalForm.reset();
      } else {
        errorBox.textContent = json.error || 'Произошла ошибка. Попробуйте ещё раз.';
        errorBox.style.display = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Отправить заявку';
      }
    } catch {
      errorBox.textContent = 'Не удалось отправить данные. Проверьте соединение.';
      errorBox.style.display = '';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Отправить заявку';
    }
  });
})();

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
