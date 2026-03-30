/**
 * Contador de Pessoas — Dashboard JS
 *
 * - WebSocket para receber contagens em tempo real
 * - REST para estado inicial das câmeras e dados históricos
 * - MJPEG stream para vídeo ao vivo
 * - Chart.js para gráfico horário
 */

const API = '';          // mesmo origin
const WS_URL = `ws://${location.host}/ws`;

/* ------------------------------------------------------------------ */
/* Estado                                                               */
/* ------------------------------------------------------------------ */
const state = {
  cameras: [],           // lista de câmeras
  activeCameraId: null,  // câmera selecionada na sidebar
  counts: {},            // { camera_id: { count_in, count_out, inside } }
  events: [],            // lista de eventos recentes (max 50)
  wsConnected: false,
  chart: null,
};

/* ------------------------------------------------------------------ */
/* Relógio                                                              */
/* ------------------------------------------------------------------ */
function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    el.textContent = new Date().toLocaleTimeString('pt-BR');
  }
  tick();
  setInterval(tick, 1000);
}

/* ------------------------------------------------------------------ */
/* WebSocket                                                            */
/* ------------------------------------------------------------------ */
function connectWebSocket() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    state.wsConnected = true;
    setWsStatus(true);
    console.log('[WS] Conectado');
  };

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      handleCountUpdate(data);
    } catch (e) {
      console.warn('[WS] Mensagem inválida:', evt.data);
    }
  };

  ws.onclose = () => {
    state.wsConnected = false;
    setWsStatus(false);
    // Reconecta após 3s
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => ws.close();
}

function setWsStatus(connected) {
  const dot = document.getElementById('ws-dot');
  const label = document.getElementById('ws-label');
  dot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
  label.textContent = connected ? 'Conectado' : 'Reconectando…';
}

/* ------------------------------------------------------------------ */
/* Tratamento de update de contagem                                     */
/* ------------------------------------------------------------------ */
function handleCountUpdate(data) {
  const { camera_id } = data;
  const prev = state.counts[camera_id] || {};

  // Detecta novos cruzamentos
  const deltaIn  = (data.count_in  || 0) - (prev.count_in  || 0);
  const deltaOut = (data.count_out || 0) - (prev.count_out || 0);

  if (deltaIn > 0)  addEvent(camera_id, 'in',  deltaIn);
  if (deltaOut > 0) addEvent(camera_id, 'out', deltaOut);

  // Atualiza estado
  state.counts[camera_id] = {
    ...data,
    dwell_total_seconds: data.dwell_total_seconds || 0,
    dwell_count: data.dwell_count || 0
  };

  // Atualiza UI
  refreshStats();
  refreshSidebar();

  // Atualiza UI da câmera ativa
  if (state.activeCameraId === camera_id) {
    updateStreamBadge(data);
    // Atualiza o gráfico se houveram novas entradas ou saídas
    if (deltaIn > 0 || deltaOut > 0) {
      loadHourlyChart(camera_id);
    }
  }
}

/* ------------------------------------------------------------------ */
/* Feed de eventos                                                      */
/* ------------------------------------------------------------------ */
function addEvent(cameraId, direction, count = 1) {
  const cam = state.cameras.find(c => c.id === cameraId);
  const camName = cam?.name || cameraId;
  const time = new Date().toLocaleTimeString('pt-BR');

  for (let i = 0; i < count; i++) {
    state.events.unshift({ cameraId, camName, direction, time });
  }
  // Limita a 50 eventos
  state.events = state.events.slice(0, 50);

  renderEvents();
  updateEventsCount();
}

function renderEvents() {
  const feed = document.getElementById('events-feed');
  if (state.events.length === 0) {
    feed.innerHTML = '<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:20px 0;">Aguardando eventos…</div>';
    return;
  }

  feed.innerHTML = state.events.map(e => `
    <div class="event-item">
      <div class="event-arrow">${e.direction === 'in' ? '↗' : '↙'}</div>
      <div class="event-details">
        <div class="event-type ${e.direction}">${e.direction === 'in' ? 'Entrada' : 'Saída'}</div>
        <div class="event-cam">${e.camName}</div>
      </div>
      <div class="event-time">${e.time}</div>
    </div>
  `).join('');
}

function updateEventsCount() {
  document.getElementById('events-count').textContent = state.events.length;
}

/* ------------------------------------------------------------------ */
/* Stats globais                                                        */
/* ------------------------------------------------------------------ */
function refreshStats() {
  let totalIn = 0, totalOut = 0, totalInside = 0;
  let globalDwellTotal = 0, globalDwellCount = 0;

  for (const c of Object.values(state.counts)) {
    totalIn     += c.count_in  || 0;
    totalOut    += c.count_out || 0;
    totalInside += Math.max(0, c.inside || 0);
    globalDwellTotal += c.dwell_total_seconds || 0;
    globalDwellCount += c.dwell_count || 0;
  }

  const globalAvg = globalDwellCount > 0 ? (globalDwellTotal / globalDwellCount) : 0;

  animateValue('stat-inside',  totalInside);
  animateValue('stat-in',      totalIn);
  animateValue('stat-out',     totalOut);
  animateValue('stat-cameras', state.cameras.length);
  
  // Atualiza dwell time (sem animação pois é string formatada)
  const dwellEl = document.getElementById('stat-dwell');
  if (dwellEl) {
    dwellEl.textContent = formatDuration(globalAvg);
  }
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  if (seconds < 60) return Math.round(seconds) + 's';
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function animateValue(elId, target) {
  const el = document.getElementById(elId);
  if (!el) return;
  const current = parseInt(el.textContent) || 0;
  if (current === target) return;

  const diff = target - current;
  const step = diff > 0 ? 1 : -1;
  const steps = Math.min(Math.abs(diff), 20);
  let i = 0;

  const timer = setInterval(() => {
    i++;
    el.textContent = current + Math.round(step * (i / steps) * Math.abs(diff));
    if (i >= steps) {
      el.textContent = target;
      clearInterval(timer);
    }
  }, 16);
}

/* ------------------------------------------------------------------ */
/* Sidebar de câmeras                                                   */
/* ------------------------------------------------------------------ */
function refreshSidebar() {
  const nav = document.getElementById('camera-nav');
  if (state.cameras.length === 0) {
    nav.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:10px;">Nenhuma câmera configurada.</div>';
    return;
  }

  nav.innerHTML = state.cameras.map(cam => {
    const counts = state.counts[cam.id] || {};
    const inside = Math.max(0, counts.inside || 0);
    const isActive = state.activeCameraId === cam.id;
    const isOnline = cam.running;

    return `
      <div class="camera-nav-item ${isActive ? 'active' : ''}"
           onclick="selectCamera('${cam.id}')"
           title="${cam.name}">
        <div class="cam-dot ${isOnline ? 'online' : 'offline'}"></div>
        <div class="cam-name">${cam.name}</div>
        <div class="cam-inside">${inside}</div>
      </div>
    `;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Seleção de câmera                                                    */
/* ------------------------------------------------------------------ */
function selectCamera(cameraId) {
  state.activeCameraId = cameraId;
  const cam = state.cameras.find(c => c.id === cameraId);
  if (!cam) return;

  // Nome no header do stream
  document.getElementById('stream-cam-name').textContent = cam.name;
  document.getElementById('chart-cam-label').textContent = cam.name;

  // Stream MJPEG
  const img = document.getElementById('video-stream');
  const overlay = document.getElementById('video-overlay');
  img.src = '';
  overlay.style.display = 'flex';

  img.onload = () => { overlay.style.display = 'none'; };
  img.onerror = () => {
    overlay.innerHTML = '<span>⚠️ Stream indisponível</span>';
  };
  img.src = `/api/cameras/${cameraId}/stream`;

  // Badge
  const counts = state.counts[cameraId] || {};
  updateStreamBadge(counts);

  // Gráfico
  loadHourlyChart(cameraId);

  // Redesenha sidebar para mostrar active
  refreshSidebar();
}

function updateStreamBadge(data) {
  const badge = document.getElementById('stream-status');
  const inside = Math.max(0, data.inside || 0);
  badge.textContent = `${inside} dentro`;
}

/* ------------------------------------------------------------------ */
/* Gráfico horário (Chart.js)                                          */
/* ------------------------------------------------------------------ */
let chartInstance = null;

async function loadHourlyChart(cameraId) {
  try {
    const res = await fetch(`/api/reports/${cameraId}/hourly`);
    if (!res.ok) return;
    const json = await res.json();
    renderChart(json.data);
  } catch (e) {
    console.warn('Erro ao carregar gráfico:', e);
  }
}

function renderChart(data) {
  const ctx = document.getElementById('hourly-chart').getContext('2d');

  if (chartInstance) chartInstance.destroy();

  const labels = data.map(d => `${String(d.hour).padStart(2,'0')}h`);
  const ins     = data.map(d => d.in);
  const outs    = data.map(d => d.out);

  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Entradas',
          data: ins,
          backgroundColor: 'rgba(72,187,120,0.5)',
          borderColor: '#48bb78',
          borderWidth: 1,
          borderRadius: 4,
        },
        {
          label: 'Saídas',
          data: outs,
          backgroundColor: 'rgba(252,129,129,0.5)',
          borderColor: '#fc8181',
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#8892a4',
            font: { family: 'Inter', size: 12 },
            boxWidth: 12,
            boxHeight: 12,
          },
        },
        tooltip: {
          backgroundColor: '#161925',
          borderColor: 'rgba(255,255,255,0.07)',
          borderWidth: 1,
          titleColor: '#e8eaf0',
          bodyColor: '#8892a4',
        },
      },
      scales: {
        x: {
          ticks: { color: '#505870', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
        y: {
          ticks: { color: '#505870', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
          beginAtZero: true,
        },
      },
    },
  });
}

/* ------------------------------------------------------------------ */
/* Bootstrap                                                            */
/* ------------------------------------------------------------------ */
async function loadCameras() {
  try {
    const res = await fetch('/api/cameras/');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cameras = await res.json();
    state.cameras = cameras;

    // Popula counts iniciais
    for (const cam of cameras) {
      state.counts[cam.id] = {
        count_in: cam.count_in,
        count_out: cam.count_out,
        inside: cam.inside,
        dwell_total_seconds: cam.dwell_total_seconds || 0,
        dwell_count: cam.dwell_count || 0
      };
    }

    refreshSidebar();
    refreshStats();

    // Seleciona a primeira câmera automaticamente
    if (cameras.length > 0 && !state.activeCameraId) {
      selectCamera(cameras[0].id);
    }
  } catch (e) {
    console.error('Erro ao carregar câmeras:', e);
    document.getElementById('camera-nav').innerHTML =
      '<div style="color:var(--red);font-size:12px;padding:10px;">Erro ao conectar na API</div>';
  }
}

// Atualiza câmeras periodicamente para detectar mudanças de status
async function pollCameras() {
  await loadCameras();
  setInterval(loadCameras, 10000);
}

// Atualiza gráfico a cada 5 minutos
function scheduleChartRefresh() {
  setInterval(() => {
    if (state.activeCameraId) {
      loadHourlyChart(state.activeCameraId);
    }
  }, 5 * 60 * 1000);
}

/* ---- INIT ---- */
document.addEventListener('DOMContentLoaded', () => {
  startClock();
  connectWebSocket();
  pollCameras();
  scheduleChartRefresh();
});
