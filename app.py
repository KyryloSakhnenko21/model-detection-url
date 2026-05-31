from flask import Flask, render_template, request, jsonify, make_response, Response, stream_with_context
import joblib
import pandas as pd
import re
import math
import json
import os
import queue
import threading
import time
import subprocess
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)

# ─────────────────────────────────────────────
# CONFIGURAÇÃO GIT
# ─────────────────────────────────────────────
GITHUB_USER       = 'KyryloSakhnenko21'
GITHUB_REPO       = 'modelo-deteção-url'
FICHEIRO_FEEDBACK = 'novos_links.json'

# ─────────────────────────────────────────────
# FILA DE ALERTAS (partilhada entre monitor e SSE)
# ─────────────────────────────────────────────
# Cada alerta é um dicionário com: url, prob_maligno, timestamp, iface
fila_alertas = queue.Queue(maxsize=500)

# Lista de subscritores SSE (um por cliente ligado ao /alertas/stream)
_subscritores_sse = []
_lock_subscritores = threading.Lock()

def publicar_alerta(alerta):
    """Coloca um alerta na fila e notifica todos os subscritores SSE."""
    # Notifica cada subscritor (cada ligação SSE aberta)
    with _lock_subscritores:
        for q in _subscritores_sse:
            try:
                q.put_nowait(alerta)
            except queue.Full:
                pass  # subscritor lento — ignora

# ─────────────────────────────────────────────
# CORS + PRIVATE NETWORK ACCESS
# ─────────────────────────────────────────────
@app.after_request
def adicionar_cabecalhos(response):
    response.headers['Access-Control-Allow-Origin']          = '*'
    response.headers['Access-Control-Allow-Methods']         = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response

@app.route('/classificar', methods=['OPTIONS'])
def classificar_preflight():
    response = make_response('', 204)
    response.headers['Access-Control-Allow-Origin']          = '*'
    response.headers['Access-Control-Allow-Methods']         = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response

@app.route('/guardar_feedback', methods=['OPTIONS'])
def feedback_preflight():
    response = make_response('', 204)
    response.headers['Access-Control-Allow-Origin']          = '*'
    response.headers['Access-Control-Allow-Methods']         = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response

@app.route('/alertas/stream', methods=['OPTIONS'])
def alertas_stream_preflight():
    response = make_response('', 204)
    response.headers['Access-Control-Allow-Origin']          = '*'
    response.headers['Access-Control-Allow-Methods']         = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    return response

# ─────────────────────────────────────────────
# CARREGAR MODELO
# ─────────────────────────────────────────────
modelo = joblib.load('modelo_rf_final.pkl')

ENCURTADORES = {
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly',
    'is.gd', 'buff.ly', 'adf.ly', 'short.link', 'rebrand.ly', 'tiny.cc'
}
TLDS_SUSPEITOS = {
    'tk', 'ml', 'ga', 'cf', 'gq', 'xyz', 'top', 'club', 'work',
    'info', 'biz', 'click', 'link', 'online', 'site', 'website'
}
PALAVRAS_SUSPEITAS = [
    'login', 'verify', 'secure', 'update', 'bank', 'paypal',
    'account', 'password', 'confirm', 'validate', 'signin',
    'wallet', 'billing', 'support', 'alert', 'security'
]

FEATURE_ORDER = [
    'lex_comp_url', 'lex_comp_dominio', 'lex_comp_path',
    'lex_n_pontos', 'lex_n_hifenes', 'lex_n_subdominios',
    'lex_n_digitos', 'lex_n_barras', 'lex_n_iguais',
    'lex_n_ampersands', 'lex_n_percent', 'lex_n_underscores',
    'lex_n_params', 'lex_ratio_digitos', 'lex_ratio_especiais',
    'lex_profundidade', 'lex_tem_https', 'lex_tem_ip',
    'lex_tem_arroba', 'lex_tem_http_no_path', 'lex_tld_suspeito',
    'lex_encurtador', 'lex_porto_suspeito', 'lex_digitos_consecutivos',
    'lex_palavras_suspeitas', 'lex_entropia_dominio', 'lex_entropia_url',
]

FEATURE_IMPORTANCE = {
    'lex_palavras_suspeitas' : 0.2654,
    'lex_comp_path'          : 0.0715,
    'lex_n_subdominios'      : 0.0714,
    'lex_entropia_url'       : 0.0679,
    'lex_n_params'           : 0.0662,
    'lex_entropia_dominio'   : 0.0608,
    'lex_n_pontos'           : 0.0605,
    'lex_comp_dominio'       : 0.0598,
    'lex_comp_url'           : 0.0497,
    'lex_ratio_especiais'    : 0.0369,
}

DESCRICOES = {
    'lex_palavras_suspeitas'  : 'Palavras suspeitas no URL',
    'lex_comp_url'            : 'Comprimento total do URL',
    'lex_comp_dominio'        : 'Comprimento do domínio',
    'lex_comp_path'           : 'Comprimento do path',
    'lex_n_pontos'            : 'Nº de pontos (.)',
    'lex_n_hifenes'           : 'Nº de hífenes (-)',
    'lex_n_subdominios'       : 'Nº de subdomínios',
    'lex_n_digitos'           : 'Nº de dígitos',
    'lex_n_barras'            : 'Nº de barras (/)',
    'lex_n_iguais'            : 'Nº de iguais (=)',
    'lex_n_ampersands'        : 'Nº de & (parâmetros)',
    'lex_n_percent'           : 'Nº de % (hex encoding)',
    'lex_n_underscores'       : 'Nº de underscores (_)',
    'lex_n_params'            : 'Nº de parâmetros query',
    'lex_ratio_digitos'       : 'Rácio dígitos/comprimento',
    'lex_ratio_especiais'     : 'Rácio caracteres especiais',
    'lex_profundidade'        : 'Profundidade do path',
    'lex_tem_https'           : 'Usa HTTPS',
    'lex_tem_ip'              : 'IP no URL',
    'lex_tem_arroba'          : 'Contém @',
    'lex_tem_http_no_path'    : 'HTTP no path',
    'lex_tld_suspeito'        : 'TLD suspeito',
    'lex_encurtador'          : 'Serviço encurtador',
    'lex_porto_suspeito'      : 'Porto não standard',
    'lex_digitos_consecutivos': 'Dígitos consecutivos no domínio',
    'lex_entropia_dominio'    : 'Entropia do domínio',
    'lex_entropia_url'        : 'Entropia do URL',
}


def calcular_entropia(texto):
    if not texto: return 0.0
    f = {}
    for c in texto:
        f[c] = f.get(c, 0) + 1
    e = 0.0
    for v in f.values():
        p = v / len(texto)
        e -= p * math.log2(p)
    return round(e, 4)


def extrair_features(url):
    url = str(url).strip()
    dominio = ''; path = ''; query = ''; esquema = ''; porto = None
    try:
        if not url.startswith(('http://', 'https://')):
            parsed = urlparse('http://' + url)
        else:
            parsed = urlparse(url)
        dominio = parsed.netloc or parsed.path.split('/')[0]
        path    = parsed.path
        query   = parsed.query
        esquema = parsed.scheme
        try:
            porto = parsed.port
        except ValueError:
            porto = None
    except ValueError:
        pass

    dominio_limpo = dominio.replace('www.', '')
    partes_dom    = dominio_limpo.split('.')
    tld           = partes_dom[-1].lower() if len(partes_dom) > 1 else ''
    url_lower     = url.lower()
    comp_url      = len(url)
    n_digitos     = sum(c.isdigit() for c in url)
    n_hifenes     = url.count('-')
    n_underscore  = url.count('_')
    n_percent     = url.count('%')
    n_iguais      = url.count('=')

    return {
        'lex_comp_url'            : comp_url,
        'lex_comp_dominio'        : len(dominio_limpo),
        'lex_comp_path'           : len(path),
        'lex_n_pontos'            : url.count('.'),
        'lex_n_hifenes'           : n_hifenes,
        'lex_n_subdominios'       : max(0, len(dominio_limpo.split('.')) - 2),
        'lex_n_digitos'           : n_digitos,
        'lex_n_barras'            : url.count('/'),
        'lex_n_iguais'            : n_iguais,
        'lex_n_ampersands'        : url.count('&'),
        'lex_n_percent'           : n_percent,
        'lex_n_underscores'       : n_underscore,
        'lex_n_params'            : len([p for p in query.split('&') if p]),
        'lex_ratio_digitos'       : round(n_digitos / comp_url, 4) if comp_url > 0 else 0,
        'lex_ratio_especiais'     : round((n_hifenes + n_underscore + n_percent + n_iguais) / comp_url, 4) if comp_url > 0 else 0,
        'lex_profundidade'        : len([p for p in path.split('/') if p]),
        'lex_tem_https'           : 1 if esquema == 'https' else 0,
        'lex_tem_ip'              : 1 if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', dominio) else 0,
        'lex_tem_arroba'          : 1 if '@' in url else 0,
        'lex_tem_http_no_path'    : 1 if 'http' in path.lower() else 0,
        'lex_tld_suspeito'        : 1 if tld in TLDS_SUSPEITOS else 0,
        'lex_encurtador'          : 1 if any(e in url_lower for e in ENCURTADORES) else 0,
        'lex_porto_suspeito'      : 1 if (porto and porto not in {80, 443, 8080}) else 0,
        'lex_digitos_consecutivos': 1 if re.search(r'\d{3,}', dominio_limpo) else 0,
        'lex_palavras_suspeitas'  : sum(1 for p in PALAVRAS_SUSPEITAS if p in url_lower),
        'lex_entropia_dominio'    : calcular_entropia(dominio_limpo),
        'lex_entropia_url'        : calcular_entropia(url),
    }


def classificar_url(url):
    features = extrair_features(url)
    X = pd.DataFrame([features])[FEATURE_ORDER]
    probs    = modelo.predict_proba(X)[0]
    predicao = int(modelo.predict(X)[0])

    top5 = []
    for feat, imp in list(FEATURE_IMPORTANCE.items())[:5]:
        top5.append({
            'feature'    : feat,
            'descricao'  : DESCRICOES.get(feat, feat),
            'importancia': round(imp * 100, 2),
            'valor'      : features.get(feat, 0),
        })

    features_display = {
        k: v for k, v in features.items()
        if k in ['lex_comp_url', 'lex_comp_dominio', 'lex_comp_path',
                 'lex_n_subdominios', 'lex_n_digitos', 'lex_profundidade',
                 'lex_palavras_suspeitas', 'lex_entropia_url',
                 'lex_entropia_dominio', 'lex_tem_https',
                 'lex_tem_ip', 'lex_tem_arroba', 'lex_tld_suspeito',
                 'lex_encurtador']
    }

    resultado = {
        'url'         : url,
        'predicao'    : predicao,
        'label'       : 'MALICIOSO' if predicao == 1 else 'BENIGNO',
        'prob_maligno': round(float(probs[1]) * 100, 2),
        'prob_benigno': round(float(probs[0]) * 100, 2),
        'features'    : features_display,
        'top5'        : top5,
    }

    # Guardar automaticamente links com alta confiança (>95%)
    if float(probs[1]) > 0.95 or float(probs[0]) > 0.95:
        label_auto = 'MALICIOSO' if predicao == 1 else 'BENIGNO'
        guardar_feedback_local(url, label_auto, fonte='auto_alta_confianca')

    return resultado


# ─────────────────────────────────────────────
# MONITOR EM TEMPO REAL (scapy — thread background)
# ─────────────────────────────────────────────
_urls_vistos_monitor = set()
_lock_urls_vistos    = threading.Lock()

def _processar_pacote(pacote):
    """Callback do scapy: chamado para cada pacote capturado."""
    try:
        from scapy.layers.http import HTTPRequest
        if not pacote.haslayer(HTTPRequest): return

        http = pacote[HTTPRequest]
        host  = http.Host.decode(errors='ignore')  if http.Host  else ''
        path  = http.Path.decode(errors='ignore')  if http.Path  else '/'
        metodo = http.Method.decode(errors='ignore') if http.Method else ''

        if metodo not in ('GET', 'POST', 'HEAD'): return
        if not host: return

        url = f'http://{host}{path}'

        # Evitar duplicados
        with _lock_urls_vistos:
            if url in _urls_vistos_monitor: return
            _urls_vistos_monitor.add(url)

        # Classificar
        features = extrair_features(url)
        X = pd.DataFrame([features])[FEATURE_ORDER]
        probs    = modelo.predict_proba(X)[0]
        predicao = int(modelo.predict(X)[0])

        prob_mal = round(float(probs[1]) * 100, 2)
        ts = datetime.now().strftime('%H:%M:%S')

        # Imprimir no terminal sempre
        cor = '\033[91m' if predicao == 1 else '\033[92m'
        reset = '\033[0m'
        label = 'MALICIOSO' if predicao == 1 else 'BENIGNO  '
        print(f'[{ts}] {cor}{label}{reset}  {prob_mal:5.1f}%  {url}')

        # Só publica alerta SSE se for malicioso
        if predicao == 1:
            alerta = {
                'url'         : url,
                'prob_maligno': prob_mal,
                'timestamp'   : ts,
                'fonte'       : 'monitor_rede',
            }
            publicar_alerta(alerta)

    except Exception:
        pass  # pacotes malformados — ignorar silenciosamente


def _iniciar_monitor():
    """Tenta importar scapy e iniciar o sniff. Corre em thread separada."""
    try:
        from scapy.all import sniff
        print('[Monitor] ✓ Scapy carregado — a monitorizar tráfego HTTP (porta 80)...')
        print('[Monitor]   (requer Npcap instalado e privilégios de administrador)')
        sniff(
            filter='tcp port 80',
            prn=_processar_pacote,
            store=False,
        )
    except ImportError:
        print('[Monitor] ✗ Scapy não instalado. Execute: pip install scapy')
        print('[Monitor]   O Flask continua a funcionar normalmente sem o monitor.')
    except PermissionError:
        print('[Monitor] ✗ Sem permissões para capturar tráfego.')
        print('[Monitor]   Execute o app.py como Administrador (Windows) ou com sudo (Linux).')
    except OSError as e:
        if 'Npcap' in str(e) or 'winpcap' in str(e).lower() or 'no suitable' in str(e).lower():
            print('[Monitor] ✗ Npcap não encontrado. Instale em: https://npcap.com/')
        else:
            print(f'[Monitor] ✗ Erro ao iniciar monitor: {e}')
    except Exception as e:
        print(f'[Monitor] ✗ Erro inesperado: {e}')


def arrancar_monitor():
    """Arranca o monitor scapy numa thread daemon (termina com o Flask)."""
    t = threading.Thread(target=_iniciar_monitor, daemon=True, name='MonitorScapy')
    t.start()


# ─────────────────────────────────────────────
# SISTEMA DE FEEDBACK E GIT
# ─────────────────────────────────────────────
def carregar_feedback():
    if os.path.exists(FICHEIRO_FEEDBACK):
        with open(FICHEIRO_FEEDBACK, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def guardar_feedback_local(url, label, fonte='utilizador'):
    dados = carregar_feedback()
    urls_existentes = {entry['url'] for entry in dados}
    if url in urls_existentes:
        return False
    entrada = {
        'url'      : url,
        'label'    : label,
        'fonte'    : fonte,
        'timestamp': datetime.now().isoformat()
    }
    dados.append(entrada)
    with open(FICHEIRO_FEEDBACK, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return True


def fazer_git_push(url, label):
    try:
        subprocess.run(['git', 'add', FICHEIRO_FEEDBACK], check=True, capture_output=True)
        msg_commit = f'feedback: {label} — {url[:60]}'
        subprocess.run(['git', 'commit', '-m', msg_commit], check=True, capture_output=True)
        subprocess.run(['git', 'push'], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


# ─────────────────────────────────────────────
# ROTAS
# ─────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/classificar', methods=['POST'])
def classificar():
    data = request.get_json()
    url  = data.get('url', '').strip()
    if not url:
        return jsonify({'erro': 'URL não pode estar vazio.'}), 400
    try:
        return jsonify(classificar_url(url))
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar o URL: {str(e)}'}), 500


@app.route('/guardar_feedback', methods=['POST'])
def guardar_feedback():
    data  = request.get_json()
    url   = data.get('url', '').strip()
    label = data.get('label', '').strip().upper()

    if not url:
        return jsonify({'erro': 'URL não pode estar vazio.'}), 400
    if label not in ('BENIGNO', 'MALICIOSO'):
        return jsonify({'erro': 'Label inválido. Use BENIGNO ou MALICIOSO.'}), 400

    novo = guardar_feedback_local(url, label, fonte='utilizador')
    if not novo:
        return jsonify({'ok': True, 'mensagem': 'URL já existia no feedback.', 'push': False})

    push_ok = fazer_git_push(url, label)
    return jsonify({
        'ok'      : True,
        'mensagem': 'Feedback guardado e enviado para GitHub.' if push_ok else 'Feedback guardado localmente (push falhou).',
        'push'    : push_ok
    })


# ─────────────────────────────────────────────
# SSE — STREAM DE ALERTAS EM TEMPO REAL
# ─────────────────────────────────────────────
@app.route('/alertas/stream')
def alertas_stream():
    """
    Endpoint SSE. Cada cliente que se liga recebe a sua fila individual.
    O monitor publica alertas → publicar_alerta() → cada fila individual é notificada.
    """
    # Criar uma fila individual para este cliente
    q_cliente = queue.Queue(maxsize=100)
    with _lock_subscritores:
        _subscritores_sse.append(q_cliente)

    def gerar():
        # Heartbeat inicial para confirmar ligação
        yield 'data: {"tipo":"ligado"}\n\n'
        try:
            while True:
                try:
                    # Bloqueia até 25 segundos; se não houver alerta, envia heartbeat
                    alerta = q_cliente.get(timeout=25)
                    payload = json.dumps({
                        'tipo'        : 'alerta',
                        'url'         : alerta['url'],
                        'prob_maligno': alerta['prob_maligno'],
                        'timestamp'   : alerta['timestamp'],
                        'fonte'       : alerta.get('fonte', 'monitor_rede'),
                    }, ensure_ascii=False)
                    yield f'data: {payload}\n\n'
                except queue.Empty:
                    # Heartbeat a cada 25 s para manter a ligação viva
                    yield 'data: {"tipo":"heartbeat"}\n\n'
        except GeneratorExit:
            pass
        finally:
            # Remover cliente da lista quando fechar a ligação
            with _lock_subscritores:
                try:
                    _subscritores_sse.remove(q_cliente)
                except ValueError:
                    pass

    return Response(
        stream_with_context(gerar()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control'              : 'no-cache',
            'X-Accel-Buffering'          : 'no',
            'Access-Control-Allow-Origin': '*',
        }
    )


@app.route('/alertas/injetar', methods=['POST'])
def alertas_injetar():
    """
    Endpoint auxiliar: permite injetar um alerta manualmente (útil para testes).
    Corpo JSON: { "url": "...", "prob_maligno": 87.5 }
    """
    data = request.get_json()
    url  = data.get('url', '').strip()
    prob = float(data.get('prob_maligno', 0.0))
    if not url:
        return jsonify({'erro': 'URL obrigatório'}), 400
    alerta = {
        'url'         : url,
        'prob_maligno': prob,
        'timestamp'   : datetime.now().strftime('%H:%M:%S'),
        'fonte'       : 'manual',
    }
    publicar_alerta(alerta)
    return jsonify({'ok': True, 'mensagem': f'Alerta injetado: {url}'})


# ─────────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────────
if __name__ == '__main__':
    print('=' * 60)
    print('  URL Shield — Flask + Monitor em Tempo Real')
    print('=' * 60)
    arrancar_monitor()
    app.run(debug=False, port=5000, threaded=True)
