// ============================================================
// URL Shield — popup.js
// ============================================================

const elEstadoAnalisar  = document.getElementById('estado-analisar');
const elEstadoSemFlask  = document.getElementById('estado-sem-flask');
const elEstadoInicial   = document.getElementById('estado-inicial');
const elResultados      = document.getElementById('resultados');
const elValTotal        = document.getElementById('val-total');
const elValBenigno      = document.getElementById('val-benigno');
const elValMaligno      = document.getElementById('val-maligno');
const elBarraFill       = document.getElementById('barra-fill');
const elPctSeguranca    = document.getElementById('pct-seguranca');
const elAlertaMaligno   = document.getElementById('alerta-maligno');
const elListaMaligno    = document.getElementById('lista-maligno');
const elTudoOk          = document.getElementById('tudo-ok');
const elBtnReanalisar   = document.getElementById('btn-reanalisar');
const elBtnRetry        = document.getElementById('btn-retry');
const elBtnAbrirApp     = document.getElementById('btn-abrir-app');
const elDotFlask        = document.getElementById('dot-flask');
const elTextoFlask      = document.getElementById('texto-flask');
const elTimestamp       = document.getElementById('timestamp');
const elToast           = document.getElementById('toast');

// Painel de alertas de rede (SSE)
const elPainelRede      = document.getElementById('painel-rede');
const elListaRede       = document.getElementById('lista-rede');
const elContadorRede    = document.getElementById('contador-rede');
const elBtnLimparRede   = document.getElementById('btn-limpar-rede');

// Contador de alertas de rede nesta sessão do popup
let alertasRede = [];

// ─────────────────────────────────────────────
// TOAST
// ─────────────────────────────────────────────
function mostrarToast(msg, cor = '#22c55e') {
  elToast.textContent = msg;
  elToast.style.borderColor = cor;
  elToast.style.color = cor;
  elToast.style.display = 'block';
  setTimeout(() => { elToast.style.display = 'none'; }, 2500);
}

// ─────────────────────────────────────────────
// VERIFICAR FLASK VIA BACKGROUND
// ─────────────────────────────────────────────
async function verificarFlask() {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ tipo: 'VERIFICAR_FLASK' }, resposta => {
      if (chrome.runtime.lastError || !resposta) resolve(false);
      else resolve(resposta.online);
    });
  });
}

function mostrarEstadoFlask(online) {
  if (online) {
    elDotFlask.className = 'dot online';
    elTextoFlask.textContent = 'online';
  } else {
    elDotFlask.className = 'dot offline';
    elTextoFlask.textContent = 'offline';
  }
}

// ─────────────────────────────────────────────
// MARCAR LINK COMO BENIGNO
// ─────────────────────────────────────────────
async function marcarComoBenigno(url, btn) {
  btn.disabled = true;
  btn.textContent = '...';

  chrome.runtime.sendMessage({ tipo: 'GUARDAR_FEEDBACK', url, label: 'BENIGNO' }, resposta => {
    if (chrome.runtime.lastError || !resposta || !resposta.ok) {
      btn.disabled = false;
      btn.textContent = '✓ Benigno';
      mostrarToast('⚠️ Erro ao guardar feedback', '#ef4444');
    } else {
      btn.textContent = '✓ Guardado';
      btn.classList.add('confirmado');
      mostrarToast('✓ Link marcado como benigno');
    }
  });
}

// ─────────────────────────────────────────────
// PAINEL DE ALERTAS DE REDE (SSE)
// ─────────────────────────────────────────────
function renderizarAlertasRede() {
  if (!elPainelRede || !elListaRede) return;

  if (alertasRede.length === 0) {
    elPainelRede.style.display = 'none';
    return;
  }

  elPainelRede.style.display = 'block';
  if (elContadorRede) elContadorRede.textContent = alertasRede.length;

  elListaRede.innerHTML = '';
  // Mostrar os 5 mais recentes (ordem inversa)
  const recentes = [...alertasRede].reverse().slice(0, 5);
  recentes.forEach(alerta => {
    const li = document.createElement('li');
    li.className = 'alerta-rede-item';

    const badge = document.createElement('span');
    badge.className = 'prob-badge';
    badge.textContent = Math.round(alerta.prob_maligno) + '%';

    const info = document.createElement('div');
    info.className = 'alerta-rede-info';

    const urlCurto = alerta.url.length > 40 ? alerta.url.slice(0, 37) + '...' : alerta.url;
    const textoUrl = document.createElement('span');
    textoUrl.className = 'link-texto';
    textoUrl.textContent = urlCurto;
    textoUrl.title = alerta.url;

    const textoHora = document.createElement('span');
    textoHora.className = 'alerta-rede-hora';
    textoHora.textContent = alerta.timestamp;

    const btn = document.createElement('button');
    btn.className = 'btn-benigno';
    btn.textContent = '✓ Benigno';
    btn.title = 'Marcar como benigno';
    btn.addEventListener('click', () => marcarComoBenigno(alerta.url, btn));

    info.appendChild(textoUrl);
    info.appendChild(textoHora);

    const row = document.createElement('div');
    row.className = 'link-row';
    row.appendChild(badge);
    row.appendChild(info);
    row.appendChild(btn);

    li.appendChild(row);
    elListaRede.appendChild(li);
  });
}

function adicionarAlertaRede(alerta) {
  // Evitar duplicados (mesmo URL na última 1 min)
  const jaExiste = alertasRede.some(a => a.url === alerta.url);
  if (jaExiste) return;

  alertasRede.push(alerta);
  renderizarAlertasRede();

  // Piscar o painel para chamar a atenção
  if (elPainelRede) {
    elPainelRede.classList.add('novo-alerta');
    setTimeout(() => elPainelRede.classList.remove('novo-alerta'), 1000);
  }
}

if (elBtnLimparRede) {
  elBtnLimparRede.addEventListener('click', () => {
    alertasRede = [];
    renderizarAlertasRede();
  });
}

// ─────────────────────────────────────────────
// ATUALIZAR INTERFACE — ANÁLISE DE PÁGINA
// ─────────────────────────────────────────────
function mostrarResultados(dados) {
  elEstadoAnalisar.style.display = 'none';
  elEstadoSemFlask.style.display = 'none';
  elEstadoInicial.style.display  = 'none';

  if (dados.total === 0) {
    elEstadoInicial.style.display = 'block';
    elResultados.style.display = 'none';
    return;
  }

  elResultados.style.display = 'block';
  elValTotal.textContent   = dados.total;
  elValBenigno.textContent = dados.benignos;
  elValMaligno.textContent = dados.maliciosos;

  const pctSeguro = dados.total > 0 ? Math.round((dados.benignos / dados.total) * 100) : 100;
  elBarraFill.style.width = pctSeguro + '%';
  elPctSeguranca.textContent = pctSeguro + '%';
  if (dados.maliciosos > 0) elBarraFill.classList.add('com-maligno');
  else elBarraFill.classList.remove('com-maligno');

  if (dados.maliciosos > 0) {
    elAlertaMaligno.style.display = 'block';
    elTudoOk.style.display = 'none';
    elListaMaligno.innerHTML = '';

    const linksMaliciosos = dados.links
      .filter(l => l.label === 'MALICIOSO')
      .sort((a, b) => b.prob_maligno - a.prob_maligno);

    linksMaliciosos.forEach(link => {
      const li = document.createElement('li');
      const prob = Math.round(link.prob_maligno * 100);
      const urlCurto = link.url.length > 45 ? link.url.slice(0, 42) + '...' : link.url;

      const row = document.createElement('div');
      row.className = 'link-row';

      const badge = document.createElement('span');
      badge.className = 'prob-badge';
      badge.textContent = prob + '%';

      const texto = document.createElement('span');
      texto.className = 'link-texto';
      texto.textContent = urlCurto;
      texto.title = link.url;

      const btn = document.createElement('button');
      btn.className = 'btn-benigno';
      btn.textContent = '✓ Benigno';
      btn.title = 'Marcar como benigno para melhorar o modelo';
      btn.addEventListener('click', () => marcarComoBenigno(link.url, btn));

      row.appendChild(badge);
      row.appendChild(texto);
      row.appendChild(btn);
      li.appendChild(row);
      elListaMaligno.appendChild(li);
    });
  } else {
    elAlertaMaligno.style.display = 'none';
    elTudoOk.style.display = 'block';
  }

  const agora = new Date();
  elTimestamp.textContent = agora.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function mostrarAnalisar() {
  elEstadoAnalisar.style.display = 'block';
  elEstadoSemFlask.style.display = 'none';
  elEstadoInicial.style.display  = 'none';
  elResultados.style.display     = 'none';
  elBtnReanalisar.disabled = true;
}

function mostrarSemFlask() {
  elEstadoAnalisar.style.display = 'none';
  elEstadoSemFlask.style.display = 'block';
  elEstadoInicial.style.display  = 'none';
  elResultados.style.display     = 'none';
  elBtnReanalisar.disabled = false;
}

// ─────────────────────────────────────────────
// COMUNICAR COM CONTENT.JS
// ─────────────────────────────────────────────
async function pedirEstadoAoContentScript() {
  return new Promise(resolve => {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (!tabs[0]) return resolve(null);
      chrome.tabs.sendMessage(tabs[0].id, { tipo: 'PEDIR_ESTADO' }, resposta => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resposta);
      });
    });
  });
}

async function pedirReanalisarAoContentScript() {
  return new Promise(resolve => {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (!tabs[0]) return resolve(false);
      chrome.tabs.sendMessage(tabs[0].id, { tipo: 'RE_ANALISAR' }, () => {
        if (chrome.runtime.lastError) return resolve(false);
        resolve(true);
      });
    });
  });
}

// ─────────────────────────────────────────────
// OUVIR MENSAGENS EM TEMPO REAL
// ─────────────────────────────────────────────
chrome.runtime.onMessage.addListener((mensagem) => {
  if (mensagem.tipo === 'ANALISE_INICIO') {
    mostrarAnalisar();
  } else if (mensagem.tipo === 'ANALISE_PROGRESSO') {
    mostrarResultados(mensagem.dados);
    elBtnReanalisar.disabled = true;
  } else if (mensagem.tipo === 'ANALISE_COMPLETA') {
    mostrarResultados(mensagem.dados);
    elBtnReanalisar.disabled = false;
  } else if (mensagem.tipo === 'ALERTA_REDE_POPUP') {
    // Alerta vindo do monitor de rede (via content.js → SSE)
    adicionarAlertaRede(mensagem.alerta);
  }
});

// ─────────────────────────────────────────────
// BOTÕES
// ─────────────────────────────────────────────
elBtnReanalisar.addEventListener('click', async () => {
  const flaskOk = await verificarFlask();
  if (!flaskOk) { mostrarEstadoFlask(false); mostrarSemFlask(); return; }
  mostrarAnalisar();
  await pedirReanalisarAoContentScript();
});

elBtnRetry.addEventListener('click', async (e) => {
  e.preventDefault();
  elDotFlask.className = 'dot loading';
  elTextoFlask.textContent = 'a verificar...';
  const flaskOk = await verificarFlask();
  mostrarEstadoFlask(flaskOk);
  if (flaskOk) { mostrarAnalisar(); await pedirReanalisarAoContentScript(); }
});

elBtnAbrirApp.addEventListener('click', () => {
  chrome.tabs.create({ url: 'http://localhost:5000' });
});

// ─────────────────────────────────────────────
// INICIALIZAÇÃO
// ─────────────────────────────────────────────
async function inicializar() {
  const flaskOk = await verificarFlask();
  mostrarEstadoFlask(flaskOk);
  if (!flaskOk) { mostrarSemFlask(); return; }

  const estado = await pedirEstadoAoContentScript();
  if (!estado) { mostrarAnalisar(); return; }
  if (estado.emProgresso) mostrarAnalisar();
  else mostrarResultados(estado);

  // Esconder painel de rede inicialmente (só aparece quando chegar alerta)
  if (elPainelRede) elPainelRede.style.display = 'none';
}

inicializar();
