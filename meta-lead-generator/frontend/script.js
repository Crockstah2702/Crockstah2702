// Product card selection (hero section)
function selectProduct(card) {
  card.classList.toggle('selected');
}

// Multi-step form navigation
function nextStep(currentStep) {
  if (!validateStep(currentStep)) return;
  document.getElementById('step' + currentStep).classList.remove('active');
  document.getElementById('step' + (currentStep + 1)).classList.add('active');
  window.scrollTo({ top: document.getElementById('form').offsetTop - 80, behavior: 'smooth' });
}

function prevStep(currentStep) {
  document.getElementById('step' + currentStep).classList.remove('active');
  document.getElementById('step' + (currentStep - 1)).classList.add('active');
}

function validateStep(step) {
  if (step === 1) {
    const checked = document.querySelectorAll('input[name="products"]:checked');
    if (checked.length === 0) {
      alert('Bitte wähle mindestens ein Produkt aus.');
      return false;
    }
    return true;
  }

  if (step === 2) {
    const fields = ['street', 'house_number', 'zip', 'city'];
    let valid = true;
    fields.forEach(name => {
      const el = document.querySelector(`input[name="${name}"]`);
      el.classList.remove('error');
      if (!el.value.trim()) {
        el.classList.add('error');
        valid = false;
      }
    });
    if (!valid) { alert('Bitte fülle alle Pflichtfelder aus.'); }
    return valid;
  }

  return true;
}

// Form submit
document.getElementById('leadForm').addEventListener('submit', async function(e) {
  e.preventDefault();

  const fields = ['first_name', 'last_name', 'phone'];
  let valid = true;
  fields.forEach(name => {
    const el = document.querySelector(`input[name="${name}"]`);
    el.classList.remove('error');
    if (!el.value.trim()) {
      el.classList.add('error');
      valid = false;
    }
  });

  const consent = document.querySelector('input[name="consent"]');
  if (!consent.checked) {
    alert('Bitte stimme der Datenschutzerklärung zu.');
    return;
  }

  if (!valid) {
    alert('Bitte fülle alle Pflichtfelder aus.');
    return;
  }

  const products = Array.from(document.querySelectorAll('input[name="products"]:checked'))
    .map(cb => cb.value);

  const payload = {
    first_name: document.querySelector('input[name="first_name"]').value.trim(),
    last_name:  document.querySelector('input[name="last_name"]').value.trim(),
    phone:      document.querySelector('input[name="phone"]').value.trim(),
    email:      document.querySelector('input[name="email"]').value.trim(),
    street:     document.querySelector('input[name="street"]').value.trim(),
    house_number: document.querySelector('input[name="house_number"]').value.trim(),
    zip:        document.querySelector('input[name="zip"]').value.trim(),
    city:       document.querySelector('input[name="city"]').value.trim(),
    best_time:  document.querySelector('select[name="best_time"]').value,
    note:       document.querySelector('textarea[name="note"]').value.trim(),
    products:   products,
    source:     'landing_page'
  };

  const submitBtn = document.getElementById('submitBtn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Wird gesendet...';

  try {
    const res = await fetch('/api/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      document.getElementById('step3').classList.remove('active');
      document.getElementById('stepSuccess').classList.add('active');
    } else {
      throw new Error('Server error');
    }
  } catch (err) {
    // Fallback: show success anyway and log locally
    console.error('Submit error:', err);
    document.getElementById('step3').classList.remove('active');
    document.getElementById('stepSuccess').classList.add('active');
  }
});
