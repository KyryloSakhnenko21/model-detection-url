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
FICHEIRO_HISTORICO = 'historico_pcap.json'

# ─────────────────────────────────────────────
# FILA DE ALERTAS SSE
# ─────────────────────────────────────────────
fila_alertas = queue.Queue(maxsize=500)
_subscritores_sse = []
_lock_subscritores = threading.Lock()

def publicar_alerta(alerta):
    with _lock_subscritores:
        for q in _subscritores_sse:
            try:
                q.put_nowait(alerta)
            except queue.Full:
                pass

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
    r = make_response('', 204)
    r.headers['Access-Control-Allow-Origin']          = '*'
    r.headers['Access-Control-Allow-Methods']         = 'POST, OPTIONS'
    r.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    r.headers['Access-Control-Allow-Private-Network'] = 'true'
    return r

@app.route('/guardar_feedback', methods=['OPTIONS'])
def feedback_preflight():
    r = make_response('', 204)
    r.headers['Access-Control-Allow-Origin']          = '*'
    r.headers['Access-Control-Allow-Methods']         = 'POST, OPTIONS'
    r.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    r.headers['Access-Control-Allow-Private-Network'] = 'true'
    return r

@app.route('/alertas/stream', methods=['OPTIONS'])
def alertas_stream_preflight():
    r = make_response('', 204)
    r.headers['Access-Control-Allow-Origin']          = '*'
    r.headers['Access-Control-Allow-Methods']         = 'GET, OPTIONS'
    r.headers['Access-Control-Allow-Headers']         = 'Content-Type, Access-Control-Request-Private-Network'
    r.headers['Access-Control-Allow-Private-Network'] = 'true'
    return r

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

    if float(probs[1]) > 0.95 or float(probs[0]) > 0.95:
        label_auto = 'MALICIOSO' if predicao == 1 else 'BENIGNO'
        guardar_feedback_local(url, label_auto, fonte='auto_alta_confianca')

    return resultado


# ─────────────────────────────────────────────
# MONITOR SCAPY EM TEMPO REAL
# ─────────────────────────────────────────────
_urls_vistos_monitor = set()
_lock_urls_vistos    = threading.Lock()

def _processar_pacote(pacote):
    try:
        from scapy.layers.http import HTTPRequest
        if not pacote.haslayer(HTTPRequest): return
        http = pacote[HTTPRequest]
        host   = http.Host.decode(errors='ignore')   if http.Host   else ''
        path   = http.Path.decode(errors='ignore')   if http.Path   else '/'
        metodo = http.Method.decode(errors='ignore') if http.Method else ''
        if metodo not in ('GET', 'POST', 'HEAD'): return
        if not host: return
        url = f'http://{host}{path}'
        with _lock_urls_vistos:
            if url in _urls_vistos_monitor: return
            _urls_vistos_monitor.add(url)
        features = extrair_features(url)
        X = pd.DataFrame([features])[FEATURE_ORDER]
        probs    = modelo.predict_proba(X)[0]
        predicao = int(modelo.predict(X)[0])
        prob_mal = round(float(probs[1]) * 100, 2)
        ts = datetime.now().strftime('%H:%M:%S')
        cor = '\033[91m' if predicao == 1 else '\033[92m'
        reset = '\033[0m'
        label = 'MALICIOSO' if predicao == 1 else 'BENIGNO  '
        print(f'[{ts}] {cor}{label}{reset}  {prob_mal:5.1f}%  {url}')
        if predicao == 1:
            publicar_alerta({
                'url': url, 'prob_maligno': prob_mal,
                'timestamp': ts, 'fonte': 'monitor_rede',
            })
    except Exception:
        pass

def _iniciar_monitor():
    try:
        from scapy.all import sniff
        print('[Monitor] ✓ Scapy carregado — a monitorizar tráfego HTTP (porta 80)...')
        print('[Monitor]   (requer Npcap instalado e privilégios de administrador)')
        sniff(filter='tcp port 80', prn=_processar_pacote, store=False)
    except ImportError:
        print('[Monitor] ✗ Scapy não instalado. Execute: pip install scapy')
    except PermissionError:
        print('[Monitor] ✗ Sem permissões. Execute como Administrador.')
    except OSError as e:
        if 'npcap' in str(e).lower() or 'no suitable' in str(e).lower() or 'winpcap' in str(e).lower():
            print('[Monitor] ✗ Npcap não encontrado. Instale em: https://npcap.com/')
        else:
            print(f'[Monitor] ✗ Erro: {e}')
    except Exception as e:
        print(f'[Monitor] ✗ Erro inesperado: {e}')

def arrancar_monitor():
    t = threading.Thread(target=_iniciar_monitor, daemon=True, name='MonitorScapy')
    t.start()


# ─────────────────────────────────────────────
# FEEDBACK E GIT
# ─────────────────────────────────────────────
def carregar_feedback():
    if os.path.exists(FICHEIRO_FEEDBACK):
        with open(FICHEIRO_FEEDBACK, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def guardar_feedback_local(url, label, fonte='utilizador'):
    dados = carregar_feedback()
    if url in {e['url'] for e in dados}: return False
    dados.append({'url': url, 'label': label, 'fonte': fonte,
                  'timestamp': datetime.now().isoformat()})
    with open(FICHEIRO_FEEDBACK, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return True

def fazer_git_push(url, label):
    try:
        subprocess.run(['git', 'add', FICHEIRO_FEEDBACK], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'feedback: {label} — {url[:60]}'],
                       check=True, capture_output=True)
        subprocess.run(['git', 'push'], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


# ─────────────────────────────────────────────
# HISTÓRICO DE ANÁLISES PCAP
# ─────────────────────────────────────────────
def carregar_historico():
    if os.path.exists(FICHEIRO_HISTORICO):
        with open(FICHEIRO_HISTORICO, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def guardar_historico(entrada):
    dados = carregar_historico()
    dados.insert(0, entrada)
    dados = dados[:20]  # guardar apenas as últimas 20 análises
    with open(FICHEIRO_HISTORICO, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# ROTAS — PÁGINAS
# ─────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

@app.route('/wireshark')
def wireshark():
    historico = carregar_historico()
    return render_template('wireshark.html', historico=historico)


# ─────────────────────────────────────────────
# ROTAS — API
# ─────────────────────────────────────────────
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
        return jsonify({'erro': 'Label inválido.'}), 400
    novo = guardar_feedback_local(url, label, fonte='utilizador')
    if not novo:
        return jsonify({'ok': True, 'mensagem': 'URL já existia.', 'push': False})
    push_ok = fazer_git_push(url, label)
    return jsonify({'ok': True,
                    'mensagem': 'Guardado e enviado para GitHub.' if push_ok else 'Guardado localmente (push falhou).',
                    'push': push_ok})

@app.route('/alertas/stream')
def alertas_stream():
    q_cliente = queue.Queue(maxsize=100)
    with _lock_subscritores:
        _subscritores_sse.append(q_cliente)

    def gerar():
        yield 'data: {"tipo":"ligado"}\n\n'
        try:
            while True:
                try:
                    alerta = q_cliente.get(timeout=25)
                    payload = json.dumps({
                        'tipo': 'alerta', 'url': alerta['url'],
                        'prob_maligno': alerta['prob_maligno'],
                        'timestamp': alerta['timestamp'],
                        'fonte': alerta.get('fonte', 'monitor_rede'),
                    }, ensure_ascii=False)
                    yield f'data: {payload}\n\n'
                except queue.Empty:
                    yield 'data: {"tipo":"heartbeat"}\n\n'
        except GeneratorExit:
            pass
        finally:
            with _lock_subscritores:
                try:
                    _subscritores_sse.remove(q_cliente)
                except ValueError:
                    pass

    return Response(stream_with_context(gerar()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
                             'Access-Control-Allow-Origin': '*'})

@app.route('/alertas/injetar', methods=['POST'])
def alertas_injetar():
    data = request.get_json()
    url  = data.get('url', '').strip()
    prob = float(data.get('prob_maligno', 0.0))
    if not url:
        return jsonify({'erro': 'URL obrigatório'}), 400
    publicar_alerta({'url': url, 'prob_maligno': prob,
                     'timestamp': datetime.now().strftime('%H:%M:%S'), 'fonte': 'manual'})
    return jsonify({'ok': True})

@app.route('/analisar_pcap', methods=['POST'])
def analisar_pcap():
    if 'ficheiro' not in request.files:
        return jsonify({'erro': 'Nenhum ficheiro enviado.'}), 400
    f = request.files['ficheiro']
    if not f.filename.endswith('.pcap'):
        return jsonify({'erro': 'O ficheiro tem de ser .pcap'}), 400

    # Guardar temporariamente
    caminho_tmp = os.path.join('uploads_tmp', f.filename)
    os.makedirs('uploads_tmp', exist_ok=True)
    f.save(caminho_tmp)

    try:
        from scapy.all import rdpcap, TCP, Raw
        pacotes = rdpcap(caminho_tmp)
    except ImportError:
        os.remove(caminho_tmp)
        return jsonify({'erro': 'Scapy não instalado. Execute: pip install scapy'}), 500
    except Exception as e:
        os.remove(caminho_tmp)
        return jsonify({'erro': f'Erro ao ler o ficheiro: {str(e)}'}), 500

    urls_vistos = set()
    resultados  = []

    for pkt in pacotes:
        try:
            if not (pkt.haslayer(TCP) and pkt.haslayer(Raw)): continue
            payload = pkt[Raw].load.decode(errors='ignore')
            linhas  = payload.split('\r\n')
            if not linhas: continue
            primeira = linhas[0].split()
            if len(primeira) < 2 or primeira[0] not in ('GET', 'POST', 'HEAD'): continue
            metodo = primeira[0]
            uri    = primeira[1]
            host   = ''
            for linha in linhas[1:]:
                if linha.lower().startswith('host:'):
                    host = linha.split(':', 1)[1].strip()
                    break
            if not host: continue
            url = f'http://{host}{uri}'
            if url in urls_vistos: continue
            urls_vistos.add(url)

            features = extrair_features(url)
            X = pd.DataFrame([features])[FEATURE_ORDER]
            probs    = modelo.predict_proba(X)[0]
            predicao = int(modelo.predict(X)[0])

            resultados.append({
                'url'         : url,
                'metodo'      : metodo,
                'dominio'     : host,
                'label'       : 'MALICIOSO' if predicao == 1 else 'BENIGNO',
                'prob_maligno': round(float(probs[1]) * 100, 1),
                'prob_benigno': round(float(probs[0]) * 100, 1),
            })
        except Exception:
            continue

    os.remove(caminho_tmp)

    total      = len(resultados)
    maliciosos = sum(1 for r in resultados if r['label'] == 'MALICIOSO')
    benignos   = total - maliciosos

    # Guardar no histórico
    guardar_historico({
        'ficheiro'  : f.filename,
        'data'      : datetime.now().strftime('%d/%m/%Y %H:%M'),
        'total'     : total,
        'maliciosos': maliciosos,
        'benignos'  : benignos,
    })

    return jsonify({
        'ok'        : True,
        'total'     : total,
        'maliciosos': maliciosos,
        'benignos'  : benignos,
        'resultados': resultados,
    })

@app.route('/historico_pcap')
def historico_pcap():
    return jsonify(carregar_historico())


# ─────────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────────
if __name__ == '__main__':
    print('=' * 60)
    print('  URL Shield — Flask + Monitor em Tempo Real')
    print('=' * 60)
    arrancar_monitor()
    app.run(debug=False, port=5000, threaded=True)
