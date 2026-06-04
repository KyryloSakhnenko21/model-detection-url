// ============================================================
// URL Shield — background.js
// Service worker: faz pedidos ao Flask sem restrições CSP.
// Gere também a ligação SSE para alertas de rede em tempo real.
// ============================================================

const FLASK_URL          = 'http://localhost:5000/classificar';
const FLASK_FEEDBACK_URL = 'http://localhost:5000/guardar_feedback';
const FLASK_SSE_URL      = 'http://localhost:5000/alertas/stream';

// ─────────────────────────────────────────────
// MENSAGENS DO CONTENT.JS / POPUP.JS
// ─────────────────────────────────────────────
chrome.runtime.onMessage.addListener((mensagem, sender, sendResponse) => {

  // Classificar URL via Flask
  if (mensagem.tipo === 'CLASSIFICAR_URL') {
    fetch(FLASK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: mensagem.url })
    })
    .then(r => r.json())
    .then(dados => sendResponse({ ok: true, dados }))
    .catch(erro => sendResponse({ ok: false, erro: erro.message }));
    return true;
  }

  // Verificar se Flask está online
  if (mensagem.tipo === 'VERIFICAR_FLASK') {
    fetch(FLASK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: 'http://test.com' }),
      signal: AbortSignal.timeout(3000)
    })
    .then(() => sendResponse({ online: true }))
    .catch(() => sendResponse({ online: false }));
    return true;
  }

  // Guardar feedback (marcar link como benigno)
  if (mensagem.tipo === 'GUARDAR_FEEDBACK') {
    fetch(FLASK_FEEDBACK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: mensagem.url, label: mensagem.label })
    })
    .then(r => r.json())
    .then(dados => sendResponse({ ok: true, dados }))
    .catch(erro => sendResponse({ ok: false, erro: erro.message }));
    return true;
  }
});

// ─────────────────────────────────────────────
// SSE — MONITOR DE REDE EM TEMPO REAL
// O EventSource corre aqui no background (sem restrições CSP).
// Quando chega um alerta, retransmite para todos os tabs ativos.
// ─────────────────────────────────────────────
let _sseAtivo = false;

function iniciarSSE() {
  if (_sseAtivo) return;
  _sseAtivo = true;

  const source = new EventSource(FLASK_SSE_URL);

  source.onmessage = (evento) => {
    try {
      const dados = JSON.parse(evento.data);
      if (dados.tipo !== 'alerta') return;

      // Retransmitir para todos os content scripts ativos
      chrome.tabs.query({}, (tabs) => {
        tabs.forEach(tab => {
          if (!tab.id || !tab.url || tab.url.startsWith('chrome://')) return;
          chrome.tabs.sendMessage(tab.id, {
            tipo  : 'ALERTA_REDE',
            alerta: {
              url         : dados.url,
              prob_maligno: dados.prob_maligno,
              timestamp   : dados.timestamp,
            }
          }).catch(() => {
            // Tab sem content script injetado — ignorar silenciosamente
          });
        });
      });

    } catch { /* JSON inválido — ignorar */ }
  };

  source.onerror = () => {
    // Flask offline ou ligação perdida — tentar reconectar em 10 s
    _sseAtivo = false;
    source.close();
    setTimeout(() => { iniciarSSE(); }, 10000);
  };
}

// Arrancar SSE quando o service worker inicializa
iniciarSSE();

// Rearrancar SSE se o service worker adormecer e acordar
chrome.runtime.onStartup.addListener(() => { iniciarSSE(); });
