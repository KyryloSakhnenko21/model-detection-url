// ============================================================
// URL Shield — content.js
// Corre em cada página automaticamente.
// NÃO faz fetch diretamente — envia mensagens ao background.js
// O SSE foi movido para o background.js (sem restrições CSP).
// Suporte a modo email: Gmail e Outlook Web.
// ============================================================

let estadoAnalise = {
  total: 0, maliciosos: 0, benignos: 0, links: [], emProgresso: false,
  modoEmail: false, plataformaEmail: null
};

// ─────────────────────────────────────────────
// DETEÇÃO DE PLATAFORMA DE EMAIL
// ─────────────────────────────────────────────
const PLATAFORMAS_EMAIL = {
  gmail: {
    nome: 'Gmail',
    dominios: ['mail.google.com'],
    // Seletores do corpo do email aberto (por ordem de preferência)
    seletoresEmail: [
      'div.a3s.aiL',      // corpo principal do email
      'div.a3s',          // alternativa
      'div[data-message-id] div.ii.gt', // email em thread
    ],
    // Seletor que indica que um email está aberto (não apenas a caixa de entrada)
    seletorAberto: 'div.adn.ads',
  },
  // Nota: o Outlook Web foi removido por limitação técnica.
  // As classes CSS do Outlook são geradas dinamicamente e mudam entre sessões,
  // tornando impossível identificar o corpo do email com seletores estáveis.
};

function detetarPlataformaEmail() {
  const hostname = window.location.hostname;
  for (const [chave, config] of Object.entries(PLATAFORMAS_EMAIL)) {
    if (config.dominios.some(d => hostname.includes(d))) {
      return { chave, ...config };
    }
  }
  return null;
}

function encontrarCorpoEmail(plataforma) {
  for (const seletor of plataforma.seletoresEmail) {
    const el = document.querySelector(seletor);
    if (el) return el;
  }
  return null;
}

function emailEstaAberto(plataforma) {
  return !!document.querySelector(plataforma.seletorAberto);
}

// ─────────────────────────────────────────────
// EXTRAÇÃO DE LINKS
// ─────────────────────────────────────────────
function extrairLinks(contexto = document) {
  const anchors = contexto.querySelectorAll('a[href]');
  const vistos = new Set();
  const links = [];
  anchors.forEach(a => {
    const href = a.href;
    if (!href || href.startsWith('javascript:') || href.startsWith('mailto:') ||
        href.startsWith('tel:') || href.startsWith('#') || vistos.has(href)) return;
    vistos.add(href);
    links.push({ url: href, element: a });
  });
  return links;
}

// ─────────────────────────────────────────────
// CLASSIFICAÇÃO E DESTAQUE
// ─────────────────────────────────────────────
function classificarURL(url) {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ tipo: 'CLASSIFICAR_URL', url }, resposta => {
      if (chrome.runtime.lastError || !resposta || !resposta.ok) resolve(null);
      else resolve(resposta.dados);
    });
  });
}

function destacarLink(elemento, probMaligno) {
  elemento.setAttribute('data-urlshield', 'maligno');
  elemento.style.setProperty('background-color', 'rgba(220, 38, 38, 0.15)', 'important');
  elemento.style.setProperty('border', '1.5px solid #dc2626', 'important');
  elemento.style.setProperty('border-radius', '3px', 'important');
  elemento.style.setProperty('padding', '1px 3px', 'important');
  elemento.style.setProperty('color', '#dc2626', 'important');
  elemento.style.setProperty('text-decoration', 'underline', 'important');
  elemento.style.setProperty('cursor', 'help', 'important');
  const percentagem = Math.round(probMaligno * 100);
  elemento.title = `⚠️ URL Shield: ${percentagem}% de probabilidade de ser malicioso`;
}

function limparDestaquesAnteriores() {
  document.querySelectorAll('[data-urlshield]').forEach(el => {
    el.removeAttribute('data-urlshield');
    el.style.removeProperty('background-color');
    el.style.removeProperty('border');
    el.style.removeProperty('border-radius');
    el.style.removeProperty('padding');
    el.style.removeProperty('color');
    el.style.removeProperty('text-decoration');
    el.style.removeProperty('cursor');
    if (el.title && el.title.startsWith('⚠️ URL Shield')) el.removeAttribute('title');
  });
}

// ─────────────────────────────────────────────
// ANÁLISE — MODO EMAIL
// ─────────────────────────────────────────────
async function analisarEmail(plataforma) {
  if (estadoAnalise.emProgresso) return;

  // Verificar se há email aberto
  if (!emailEstaAberto(plataforma)) {
    estadoAnalise = {
      total: 0, maliciosos: 0, benignos: 0, links: [],
      emProgresso: false, modoEmail: true,
      plataformaEmail: plataforma.nome, semEmailAberto: true
    };
    chrome.runtime.sendMessage({
      tipo: 'ANALISE_COMPLETA', dados: estadoAnalise
    }).catch(() => {});
    return;
  }

  const corpo = encontrarCorpoEmail(plataforma);
  if (!corpo) {
    // Email aberto mas corpo não encontrado — tentar modo normal como fallback
    await analisarPaginaNormal();
    return;
  }

  estadoAnalise = {
    total: 0, maliciosos: 0, benignos: 0, links: [],
    emProgresso: true, modoEmail: true,
    plataformaEmail: plataforma.nome, semEmailAberto: false
  };
  limparDestaquesAnteriores();
  chrome.runtime.sendMessage({ tipo: 'ANALISE_INICIO', modoEmail: true, plataformaEmail: plataforma.nome }).catch(() => {});

  const links = extrairLinks(corpo);
  estadoAnalise.total = links.length;

  if (links.length === 0) {
    estadoAnalise.emProgresso = false;
    chrome.runtime.sendMessage({ tipo: 'ANALISE_COMPLETA', dados: estadoAnalise }).catch(() => {});
    return;
  }

  const TAMANHO_LOTE = 5;
  for (let i = 0; i < links.length; i += TAMANHO_LOTE) {
    const lote = links.slice(i, i + TAMANHO_LOTE);
    await Promise.all(lote.map(async ({ url, element }) => {
      const resultado = await classificarURL(url);
      if (!resultado) return;
      const eMalicioso = resultado.label === 'MALICIOSO';
      const probDecimal = resultado.prob_maligno / 100;
      if (eMalicioso) { estadoAnalise.maliciosos++; destacarLink(element, probDecimal); }
      else { estadoAnalise.benignos++; }
      estadoAnalise.links.push({ url, label: resultado.label, prob_maligno: probDecimal });
      chrome.runtime.sendMessage({ tipo: 'ANALISE_PROGRESSO', dados: { ...estadoAnalise } }).catch(() => {});
    }));
  }

  estadoAnalise.emProgresso = false;
  chrome.runtime.sendMessage({ tipo: 'ANALISE_COMPLETA', dados: estadoAnalise }).catch(() => {});
  chrome.storage.local.set({ ultimaAnalise: estadoAnalise });
}

// ─────────────────────────────────────────────
// ANÁLISE — MODO NORMAL (páginas comuns)
// ─────────────────────────────────────────────
async function analisarPaginaNormal() {
  if (estadoAnalise.emProgresso) return;
  estadoAnalise = {
    total: 0, maliciosos: 0, benignos: 0, links: [],
    emProgresso: true, modoEmail: false, plataformaEmail: null
  };
  limparDestaquesAnteriores();
  chrome.runtime.sendMessage({ tipo: 'ANALISE_INICIO', modoEmail: false }).catch(() => {});

  const links = extrairLinks(document);
  estadoAnalise.total = links.length;

  if (links.length === 0) {
    estadoAnalise.emProgresso = false;
    chrome.runtime.sendMessage({ tipo: 'ANALISE_COMPLETA', dados: estadoAnalise }).catch(() => {});
    return;
  }

  const TAMANHO_LOTE = 5;
  for (let i = 0; i < links.length; i += TAMANHO_LOTE) {
    const lote = links.slice(i, i + TAMANHO_LOTE);
    await Promise.all(lote.map(async ({ url, element }) => {
      const resultado = await classificarURL(url);
      if (!resultado) return;
      const eMalicioso = resultado.label === 'MALICIOSO';
      const probDecimal = resultado.prob_maligno / 100;
      if (eMalicioso) { estadoAnalise.maliciosos++; destacarLink(element, probDecimal); }
      else { estadoAnalise.benignos++; }
      estadoAnalise.links.push({ url, label: resultado.label, prob_maligno: probDecimal });
      chrome.runtime.sendMessage({ tipo: 'ANALISE_PROGRESSO', dados: { ...estadoAnalise } }).catch(() => {});
    }));
  }

  estadoAnalise.emProgresso = false;
  chrome.runtime.sendMessage({ tipo: 'ANALISE_COMPLETA', dados: estadoAnalise }).catch(() => {});
  chrome.storage.local.set({ ultimaAnalise: estadoAnalise });
}

// ─────────────────────────────────────────────
// PONTO DE ENTRADA — decide o modo
// ─────────────────────────────────────────────
const _plataforma = detetarPlataformaEmail();

async function analisarPagina() {
  if (_plataforma) {
    await analisarEmail(_plataforma);
  } else {
    await analisarPaginaNormal();
  }
}

// ─────────────────────────────────────────────
// OBSERVER — reanalisar ao abrir email diferente
// Deteta mudanças no DOM que indicam que o utilizador
// navegou para outro email dentro do Gmail / Outlook.
// ─────────────────────────────────────────────
let _observerTimeout = null;

function iniciarObserverEmail() {
  if (!_plataforma) return;

  const observer = new MutationObserver(() => {
    // Debounce — aguarda 800 ms de estabilidade antes de reanalisar
    clearTimeout(_observerTimeout);
    _observerTimeout = setTimeout(() => {
      if (!estadoAnalise.emProgresso) {
        analisarEmail(_plataforma);
      }
    }, 800);
  });

  // Observar mudanças na área principal da página
  const alvo = document.body;
  observer.observe(alvo, { childList: true, subtree: true });
}

// ─────────────────────────────────────────────
// ALERTAS DE REDE — recebidos do background.js
// ─────────────────────────────────────────────
function destacarLinkPorUrl(urlAlerta) {
  try {
    const alertaHost = new URL(
      urlAlerta.startsWith('http') ? urlAlerta : 'http://' + urlAlerta
    ).hostname.replace('www.', '');

    document.querySelectorAll('a[href]').forEach(a => {
      try {
        const hrefHost = new URL(a.href).hostname.replace('www.', '');
        if (hrefHost === alertaHost && !a.hasAttribute('data-urlshield')) {
          destacarLink(a, 0.95);
        }
      } catch { /* URL inválido — ignorar */ }
    });
  } catch { /* URL do alerta inválido — ignorar */ }
}

// ─────────────────────────────────────────────
// MENSAGENS DO POPUP / BACKGROUND
// ─────────────────────────────────────────────
chrome.runtime.onMessage.addListener((mensagem, sender, sendResponse) => {
  if (mensagem.tipo === 'PEDIR_ESTADO') {
    sendResponse(estadoAnalise);
  } else if (mensagem.tipo === 'RE_ANALISAR') {
    analisarPagina();
    sendResponse({ ok: true });
  } else if (mensagem.tipo === 'ALERTA_REDE') {
    destacarLinkPorUrl(mensagem.alerta.url);
    chrome.runtime.sendMessage({
      tipo: 'ALERTA_REDE_POPUP', alerta: mensagem.alerta
    }).catch(() => {});
  }
  return true;
});

// ─────────────────────────────────────────────
// ARRANQUE
// ─────────────────────────────────────────────
setTimeout(() => {
  analisarPagina();
  if (_plataforma) iniciarObserverEmail();
}, 1500);
