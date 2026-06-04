"""
treino_semanal.py
─────────────────
Corre toda sábado às 22:00 via GitHub Actions.
Lê os novos links do novos_links.json, extrai features,
re-treina o modelo Random Forest, guarda o novo modelo
e limpa o ficheiro de feedback para o próximo ciclo.
"""

import json
import os
import math
import re
import joblib
import pandas as pd
from datetime import datetime
from urllib.parse import urlparse
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, accuracy_score

# ─────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────
FICHEIRO_FEEDBACK  = 'novos_links.json'
MODELO_ATUAL       = 'modelo_rf_final.pkl'
MODELO_NOVO        = 'modelo_rf_final.pkl'  # Substitui o atual
MIN_NOVOS_LINKS    = 5   # Mínimo de links novos para re-treinar

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


# ─────────────────────────────────────────────
# FUNÇÕES
# ─────────────────────────────────────────────
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
    if url.startswith(('http://www.', 'https://www.')):
        url = url.replace('://www.', '://', 1)
    elif url.startswith('www.'):
        url = url[4:]

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

    dominio_limpo = dominio
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


# ─────────────────────────────────────────────
# TREINO
# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  URL Shield — Treino Semanal")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 1. Carregar feedback
    if not os.path.exists(FICHEIRO_FEEDBACK):
        print("❌ Ficheiro novos_links.json não encontrado. A terminar.")
        return

    with open(FICHEIRO_FEEDBACK, 'r', encoding='utf-8') as f:
        feedback = json.load(f)

    print(f"📂 Links no ficheiro de feedback: {len(feedback)}")

    if len(feedback) < MIN_NOVOS_LINKS:
        print(f"⚠️  Menos de {MIN_NOVOS_LINKS} links novos. Re-treino não realizado.")
        return

    # 2. Extrair features dos novos links
    print("🔄 A extrair features dos novos links...")
    registos = []
    for entrada in feedback:
        try:
            features = extrair_features(entrada['url'])
            features['label'] = 1 if entrada['label'] == 'MALICIOSO' else 0
            registos.append(features)
        except Exception as e:
            print(f"   ⚠️  Erro em {entrada['url']}: {e}")

    df_novos = pd.DataFrame(registos)
    print(f"   ✓ {len(df_novos)} registos extraídos")
    print(f"   Distribuição: {df_novos['label'].value_counts().to_dict()}")

    # 3. Carregar modelo atual
    print("\n📦 A carregar modelo atual...")
    modelo_atual = joblib.load(MODELO_ATUAL)

    # 4. Preparar dados
    X_novos = df_novos[FEATURE_ORDER]
    y_novos = df_novos['label']

    # 5. Re-treinar com warm_start
    print("\n🌲 A re-treinar o modelo com novos dados...")
    modelo_atual.set_params(warm_start=True, n_estimators=modelo_atual.n_estimators + 50)
    modelo_atual.fit(X_novos, y_novos)
    print(f"   ✓ Modelo re-treinado com {modelo_atual.n_estimators} árvores no total")

    # 6. Avaliar (apenas nos novos dados, se suficientes)
    if len(df_novos) >= 10:
        X_tr, X_te, y_tr, y_te = train_test_split(X_novos, y_novos, test_size=0.2, random_state=42)
        modelo_atual.fit(X_tr, y_tr)
        y_pred = modelo_atual.predict(X_te)
        f1  = f1_score(y_te, y_pred, zero_division=0)
        acc = accuracy_score(y_te, y_pred)
        print(f"\n📊 Avaliação nos novos dados:")
        print(f"   Accuracy : {acc*100:.2f}%")
        print(f"   F1-Score : {f1*100:.2f}%")

    # 7. Guardar novo modelo
    joblib.dump(modelo_atual, MODELO_NOVO)
    print(f"\n✅ Novo modelo guardado: {MODELO_NOVO}")
    print(f"   Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 8. Limpar novos_links.json após treino bem sucedido
    with open(FICHEIRO_FEEDBACK, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=2)
    print(f"\n🧹 {FICHEIRO_FEEDBACK} limpo — pronto para novos dados.")
    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    main()
