# 🛡️ URL Shield — Deteção de URLs Maliciosos com Machine Learning

> **Projeto Académico** · Inteligência Artificial aplicada à Cibersegurança · ESTCB · IPCB · 2025/2026  
> **Autores:** Kyrylo Sakhnenko & Rodrigo Figueiredo · **Orientador:** Prof. Alexandre Fonte

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-RandomForest-orange)](https://scikit-learn.org)
[![Flask](https://img.shields.io/badge/Flask-Web%20App-lightgrey?logo=flask)](https://flask.palletsprojects.com)
[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension%20MV3-yellow?logo=googlechrome)](https://developer.chrome.com/docs/extensions)

---

## 📋 Descrição

O URL Shield é um pipeline completo de Machine Learning para deteção de URLs maliciosos (phishing, malware). O sistema extrai **27 features lexicais** diretamente da string do URL — sem consultas externas — e classifica URLs em tempo real usando um modelo **Random Forest** treinado em ~153.000 URLs.

O projeto foi construído em múltiplas camadas seguindo uma estratégia de **Defesa em Profundidade** (Defense in Depth):

```
Camada 1 — Aplicação Web         → Análise manual de URLs com explicação de features
Camada 2 — Extensão de Browser   → Análise automática de todos os links de qualquer página
Camada 3 — Monitor de Rede       → Captura e classificação de tráfego HTTP em tempo real
Camada 4 — Dashboard Wireshark   → Análise offline de ficheiros .pcap
Camada 5 — Análise de Email      → Análise focada nos links de emails abertos no Gmail
```

---

## 📊 Desempenho do Modelo

| Métrica | Valor |
|---------|-------|
| Accuracy | 94,65% |
| Precision | 93,68% |
| Recall | 88,71% |
| F1-Score | 91,13% |
| **AUC-ROC** | **98,40%** |

Dataset de treino: ~153.000 URLs · Algoritmo: Random Forest (500 árvores, 27 features)

---

## 🚀 Instalação Rápida

### Pré-requisitos
```bash
pip install flask joblib pandas scikit-learn scapy
```
> **Windows:** O [Npcap](https://npcap.com/) é necessário para o monitor de rede (instalado automaticamente com o Wireshark).

### Correr a aplicação
```bash
# Executar como Administrador (necessário para captura de pacotes de rede)
cd app/
python app.py
```
Abre o browser em **http://localhost:5000**

### Instalar a extensão de browser
1. Abre o Chrome → `chrome://extensions`
2. Ativa o **Modo de programador** (canto superior direito)
3. Clica em **Carregar sem compactação** → seleciona a pasta `extension/`
4. O ícone do URL Shield aparece na barra do Chrome

---

## 📁 Estrutura do Repositório

```
url-shield/
│
├── app/                          # Aplicação Flask
│   ├── app.py                    # App principal: rotas, monitor scapy, alertas SSE
│   ├── treino_semanal.py         # Script de re-treino semanal do modelo
│   ├── modelo_rf_final.pkl       # Modelo Random Forest treinado (Git LFS)
│   ├── novos_links.json          # Dados de feedback para aprendizagem contínua
│   ├── templates/
│   │   ├── index.html            # Página de análise de URL
│   │   ├── monitor.html          # Página do monitor de rede em tempo real
│   │   └── wireshark.html        # Página do dashboard Wireshark
│   └── .github/
│       └── workflows/
│           └── treino_semanal.yml  # Re-treino automático semanal (GitHub Actions)
│
├── extension/                    # Extensão Chrome (Manifest V3)
│   ├── manifest.json
│   ├── background.js             # Service worker: SSE + pedidos ao Flask
│   ├── content.js                # Script de página: extração de links + modo Gmail
│   ├── popup.html                # Interface do popup da extensão
│   ├── popup.js                  # Lógica do popup
│   └── icons/
│
├── data-pipeline/                # Notebooks de processamento e treino
│   ├── 01_data_cleaning.ipynb
│   ├── 02_normalization.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_training.ipynb
│   ├── 04b_model_training_lexical.ipynb
│   ├── 05_model_optimization.ipynb
│   ├── 06_final_model.ipynb
│   ├── 07_wireshark_analysis.ipynb
│   └── figures/                  # Gráficos e figuras geradas
│
├── models/                       # Modelos treinados (Git LFS)
│   ├── modelo_rf_lexical.pkl     # Modelo intermédio (10 features)
│   └── modelo_rf_final.pkl       # Modelo final (27 features, ~153k URLs)
│
├── reports/                      # Relatórios do projeto (PDF)
│   ├── Cap05_Limpeza_Dados.pdf
│   ├── Cap06_Treino_Modelos.pdf
│   ├── Cap07_Otimizacao.pdf
│   ├── Cap08_Modelo_Final.pdf
│   ├── Cap09_Aplicacao_Web.pdf
│   ├── Cap10_Extensao_Browser.pdf
│   ├── Cap11_Wireshark.pdf
│   ├── Cap12_Monitor_Tempo_Real.pdf
│   └── Cap13_Dashboard.pdf
│
├── README.md                     # Versão em inglês
├── README.pt.md                  # Este ficheiro (Português)
├── .gitignore
└── .gitattributes                # Configuração Git LFS para ficheiros .pkl
```

---

## ✨ Funcionalidades

### 🌐 Aplicação Web (3 páginas separadas)
- **Analisar URL** — Classificar qualquer URL com barras de probabilidade e explicação das 5 features mais influentes
- **Monitor em Tempo Real** — Captura de tráfego HTTP ao vivo com scapy; URLs maliciosos geram alertas SSE instantâneos na app e na extensão
- **Dashboard Wireshark** — Upload de ficheiros `.pcap`, classificação de todos os URLs HTTP, tabela filtrável e ordenável, gráficos donut e barras, exportação CSV, histórico persistente de análises

### 🧩 Extensão Chrome
- Análise automática de links em qualquer página (1,5s após carregamento)
- Destaque a vermelho dos links maliciosos com tooltip de probabilidade
- **Modo Gmail** — analisa apenas os links dentro do email aberto, ignorando os elementos de navegação do Gmail
- Painel de alertas de rede em tempo real no popup (SSE do Flask)
- Alertas persistentes ao navegar entre páginas (sessionStorage)
- Botão "✓ Benigno" integrado com o pipeline de aprendizagem contínua

### 🤖 Pipeline de Aprendizagem Contínua
- Correções do utilizador recolhidas via botão "✓ Benigno"
- Auto-rotulagem de predições com alta confiança (>95% de probabilidade)
- Workflow **GitHub Actions** corre todos os domingos à meia-noite UTC
- `warm_start=True` adiciona 50 novas árvores ao modelo existente sem re-treino completo
- Modelo atualizado guardado automaticamente no repositório via commit automático

---

## 🔬 27 Features Lexicais

Todas as features são extraídas apenas da string do URL — sem DNS, sem WHOIS, sem APIs externas:

| Categoria | Features |
|-----------|----------|
| Comprimento | `comp_url`, `comp_dominio`, `comp_path` |
| Contagens | `n_pontos`, `n_hifenes`, `n_subdominios`, `n_digitos`, `n_barras`, `n_iguais`, `n_ampersands`, `n_percent`, `n_underscores`, `n_params` |
| Rácios | `ratio_digitos`, `ratio_especiais` |
| Estrutura | `profundidade`, `tem_https`, `tem_ip`, `tem_arroba`, `http_no_path` |
| Flags | `tld_suspeito`, `encurtador`, `porto_suspeito`, `digitos_consecutivos` |
| Texto | `palavras_suspeitas` (login, verify, paypal, bank, password…) |
| Entropia | `entropia_dominio`, `entropia_url` |

---

## 🛠️ Tecnologias Utilizadas

| Componente | Tecnologia |
|-----------|-----------|
| Modelo ML | scikit-learn RandomForestClassifier |
| Framework Web | Flask (Python 3.13) |
| Captura de Rede | scapy + Npcap |
| Alertas em Tempo Real | Server-Sent Events (SSE) |
| Extensão de Browser | Chrome Manifest V3 |
| Re-treino Automático | GitHub Actions |
| Ficheiros Grandes | Git LFS (modelos .pkl) |
| Processamento de Dados | pandas, numpy |
| Gráficos | matplotlib, seaborn, Chart.js |

---

## 📄 Contexto Académico

Este projeto foi desenvolvido como **Projeto II** da Licenciatura em Engenharia Informática na ESTCB · IPCB (Instituto Politécnico de Castelo Branco).

---

*🇬🇧 [English version available here](README.md)*
