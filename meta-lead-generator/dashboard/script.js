let allLeads = [];
let currentLead = null;

const PRODUCT_LABELS = {
  internet:  '🌐 Internet',
  tv:        '📺 TV',
  mobilfunk: '📱 Mobilfunk',
  strom:     '⚡ Strom'
};

const STATUS_LABELS = {
  neu:            'Neu',
  kontaktiert:    'Kontaktiert',
  termin:         'Termin vereinbart',
  abgeschlossen:  'Abgeschlossen',
  kein_interesse: 'Kein Interesse'
};

async function loadLeads() {
  try {
    const res = await fetch('/api/leads');
    const data = await res.json();
    allLeads = data.leads || [];
    renderStats();
    filterLeads();
  } catch (err) {
    console.error('Fehler beim Laden:', err);
    // Demo-Daten für Vorschau ohne Backend
    allLeads = getDemoLeads();
    renderStats();
    filterLeads();
  }
}

function getDemoLeads() {
  return [
    {
      id: 1, first_name: 'Max', last_name: 'Mustermann',
      phone: '+49 151 12345678', email: 'max@beispiel.de',
      street: 'Musterstraße', house_number: '12', zip: '44135', city: 'Dortmund',
      products: ['internet', 'tv'], best_time: 'nachmittag',
      note: 'Aktuell bei Telekom', status: 'neu',
      created_at: new Date().toISOString(), source: 'landing_page'
    },
    {
      id: 2, first_name: 'Anna', last_name: 'Schmidt',
      phone: '+49 171 87654321', email: '',
      street: 'Hauptstraße', house_number: '5', zip: '44137', city: 'Dortmund',
      products: ['mobilfunk', 'strom'], best_time: 'abend',
      note: '', status: 'kontaktiert',
      created_at: new Date(Date.now() - 86400000).toISOString(), source: 'meta_ads'
    },
    {
      id: 3, first_name: 'Klaus', last_name: 'Müller',
      phone: '+49 160 11223344', email: 'k.mueller@web.de',
      street: 'Gartenweg', house_number: '3a', zip: '44141', city: 'Dortmund',
      products: ['internet', 'mobilfunk', 'tv'], best_time: 'vormittag',
      note: '', status: 'termin',
      created_at: new Date(Date.now() - 172800000).toISOString(), source: 'meta_ads'
    }
  ];
}

function renderStats() {
  const total = allLeads.length;
  const today = allLeads.filter(l => {
    const d = new Date(l.created_at);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  }).length;
  const neu = allLeads.filter(l => l.status === 'neu').length;
  const done = allLeads.filter(l => l.status === 'abgeschlossen').length;

  document.getElementById('statTotal').textContent = total;
  document.getElementById('statToday').textContent = today;
  document.getElementById('statNew').textContent = neu;
  document.getElementById('statDone').textContent = done;
}

function filterLeads() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const product = document.getElementById('filterProduct').value;
  const status = document.getElementById('filterStatus').value;

  const filtered = allLeads.filter(l => {
    const matchSearch = !search ||
      `${l.first_name} ${l.last_name} ${l.city} ${l.phone} ${l.zip}`.toLowerCase().includes(search);
    const matchProduct = !product || (l.products && l.products.includes(product));
    const matchStatus = !status || l.status === status;
    return matchSearch && matchProduct && matchStatus;
  });

  renderTable(filtered);
}

function renderTable(leads) {
  const tbody = document.getElementById('leadsTableBody');

  if (leads.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state">Keine Leads gefunden</td></tr>`;
    return;
  }

  tbody.innerHTML = leads.map((l, i) => {
    const products = (l.products || []).map(p =>
      `<span class="product-tag">${PRODUCT_LABELS[p] || p}</span>`
    ).join('');

    const date = new Date(l.created_at).toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit'
    });

    const statusClass = `status-${l.status || 'neu'}`;
    const statusLabel = STATUS_LABELS[l.status] || 'Neu';

    return `<tr>
      <td style="color:#999;font-size:12px">${l.id}</td>
      <td><strong>${l.first_name} ${l.last_name}</strong></td>
      <td><a href="tel:${l.phone}" style="color:inherit;text-decoration:none">${l.phone}</a></td>
      <td>${l.street} ${l.house_number}, ${l.zip} ${l.city}</td>
      <td><div class="product-tags">${products}</div></td>
      <td style="font-size:13px;color:#667">${formatBestTime(l.best_time)}</td>
      <td style="font-size:13px;color:#667">${date}</td>
      <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
      <td><button class="btn-detail" onclick="openModal(${l.id})">Details</button></td>
    </tr>`;
  }).join('');
}

function formatBestTime(val) {
  const map = {
    vormittag: 'Vormittags', mittag: 'Mittags',
    nachmittag: 'Nachmittags', abend: 'Abends', '': 'Beliebig'
  };
  return map[val] || val || 'Beliebig';
}

function openModal(id) {
  currentLead = allLeads.find(l => l.id === id);
  if (!currentLead) return;

  const l = currentLead;
  const products = (l.products || []).map(p => PRODUCT_LABELS[p] || p).join(', ');
  const date = new Date(l.created_at).toLocaleString('de-DE');

  document.getElementById('modalContent').innerHTML = `
    <h2 class="modal-title">${l.first_name} ${l.last_name}</h2>

    <div class="modal-section">
      <h4>Kontakt</h4>
      <div class="modal-row"><span>Telefon</span><span>${l.phone}</span></div>
      <div class="modal-row"><span>E-Mail</span><span>${l.email || '–'}</span></div>
      <div class="modal-row"><span>Erreichbarkeit</span><span>${formatBestTime(l.best_time)}</span></div>
    </div>

    <div class="modal-section">
      <h4>Adresse</h4>
      <div class="modal-row"><span>Straße</span><span>${l.street} ${l.house_number}</span></div>
      <div class="modal-row"><span>PLZ / Ort</span><span>${l.zip} ${l.city}</span></div>
    </div>

    <div class="modal-section">
      <h4>Produkte</h4>
      <div class="modal-row"><span>Interesse</span><span>${products}</span></div>
      <div class="modal-row"><span>Quelle</span><span>${l.source === 'meta_ads' ? 'Meta Ads' : 'Landing Page'}</span></div>
    </div>

    ${l.note ? `<div class="modal-section">
      <h4>Notiz</h4>
      <p style="font-size:14px;color:#555">${l.note}</p>
    </div>` : ''}

    <div class="modal-section">
      <h4>Eingegangen</h4>
      <div class="modal-row"><span>Datum</span><span>${date}</span></div>
    </div>

    <div class="modal-section">
      <h4>Status ändern</h4>
      <select class="modal-status-select" id="modalStatus">
        <option value="neu" ${l.status === 'neu' ? 'selected' : ''}>Neu</option>
        <option value="kontaktiert" ${l.status === 'kontaktiert' ? 'selected' : ''}>Kontaktiert</option>
        <option value="termin" ${l.status === 'termin' ? 'selected' : ''}>Termin vereinbart</option>
        <option value="abgeschlossen" ${l.status === 'abgeschlossen' ? 'selected' : ''}>Abgeschlossen</option>
        <option value="kein_interesse" ${l.status === 'kein_interesse' ? 'selected' : ''}>Kein Interesse</option>
      </select>
    </div>

    <button class="btn-save" onclick="saveStatus(${l.id})">Status speichern</button>
  `;

  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  currentLead = null;
}

async function saveStatus(id) {
  const newStatus = document.getElementById('modalStatus').value;
  try {
    await fetch(`/api/leads/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
  } catch (e) { /* offline demo */ }

  // Update local data
  const lead = allLeads.find(l => l.id === id);
  if (lead) lead.status = newStatus;
  renderStats();
  filterLeads();
  closeModal();
}

function exportCSV() {
  const headers = ['ID', 'Vorname', 'Nachname', 'Telefon', 'E-Mail', 'Straße', 'Hausnr.', 'PLZ', 'Ort', 'Produkte', 'Erreichbarkeit', 'Status', 'Quelle', 'Datum'];
  const rows = allLeads.map(l => [
    l.id, l.first_name, l.last_name, l.phone, l.email,
    l.street, l.house_number, l.zip, l.city,
    (l.products || []).join('+'), l.best_time, l.status, l.source,
    new Date(l.created_at).toLocaleString('de-DE')
  ]);

  const csv = [headers, ...rows].map(r => r.map(c => `"${String(c || '').replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `leads_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

// Init
loadLeads();
