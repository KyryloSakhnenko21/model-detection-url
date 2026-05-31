// ============================================================
// URL Shield — content.js
// Corre em cada página automaticamente.
// NÃO faz fetch diretamente — envia mensagens ao background.js
// O SSE foi movido para o background.js (sem restrições CSP).
// ============================================================

let estadoAnalise = {
  total: 0, maliciosos: 0, benignos: 0, links: [], emProgresso: false
};

// ─────────────────────────────────────────────
// EXTRAÇÃO E ANÁLISE DE LINKS DA PÁGINA
// ─────────────────────────────────────────────
function extrairLinks() {
  const anchors = document.querySelectorAll('a[href]');
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

async function analisarPagina() {
  if (estadoAnalise.emProgresso) return;
  estadoAnalise.emProgresso = true;
  limparDestaquesAnteriores();
  estadoAnalise = { total: 0, maliciosos: 0, benignos: 0, links: [], emProgresso: true };
  chrome.runtime.sendMessage({ tipo: 'ANALISE_INICIO' }).catch(() => {});

  const links = extrairLinks();
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
    // Veio do background.js — destacar links na página e notificar popup
    destacarLinkPorUrl(mensagem.alerta.url);
    chrome.runtime.sendMessage({
      tipo  : 'ALERTA_REDE_POPUP',
      alerta: mensagem.alerta
    }).catch(() => {});
  }
  return true;
});

// ─────────────────────────────────────────────
// ARRANQUE
// ─────────────────────────────────────────────
setTimeout(() => { analisarPagina(); }, 1500);
