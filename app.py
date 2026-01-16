
import streamlit as st
import pandas as pd
import pdfplumber
from fpdf import FPDF
import io
import re
from datetime import datetime

# ==============================================================================
# CONFIGURAÇÃO E ESTILO VISUAL
# ==============================================================================
st.set_page_config(page_title="Cálculo de Diferença Salarial", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        border-left: 5px solid #3498db;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #2c3e50;
    }
    .metric-label {
        font-size: 14px;
        color: #7f8c8d;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .total-card {
        background-color: #d4efdf;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        border-left: 5px solid #27ae60;
    }
    .total-value {
        font-size: 32px;
        font-weight: bold;
        color: #27ae60;
    }
    div.stButton > button:first-child {
        background-color: #2980b9;
        color: white;
        font-size: 18px;
        border-radius: 8px;
        width: 100%;
        padding: 10px 0;
    }
    div.stButton > button:first-child:hover {
        background-color: #1a5276;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def limpar_valor(texto):
    if isinstance(texto, (int, float)): return float(texto)
    if not texto: return 0.0
    t = str(texto).replace('"', '').replace("'", "").replace('R$', '').strip()
    try:
        if ',' in t and '.' in t:
            if t.rfind(',') > t.rfind('.'):
                t = t.replace('.', '').replace(',', '.')
            else:
                t = t.replace(',', '')
        elif ',' in t:
            t = t.replace(',', '.')
        return float(t)
    except:
        return 0.0

def fmt_br(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==============================================================================
# INTERFACE
# ==============================================================================

st.sidebar.title("Parâmetros de Entrada")

arquivos = st.sidebar.file_uploader("Ficha Financeira (PDF - um por ano)", type=["pdf"], accept_multiple_files=True)

base_a = st.sidebar.number_input("Base Classe A (R$)", value=4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ex: João da Silva")
matricula = st.sidebar.text_input("Matrícula", "0000000")

with st.sidebar.expander("📈 Promoções (Manual)"):
    if "promocoes" not in st.session_state:
        st.session_state["promocoes"] = []

    nova_data = st.date_input("Data da Promoção")
    nova_classe = st.selectbox("Classe", ["A", "B", "C", "D", "E", "F", "G"])
    if st.button("Registrar Promoção"):
        st.session_state["promocoes"].append({
            "data": nova_data,
            "classe": nova_classe
        })

    if st.button("🗑 Limpar Promoções"):
        st.session_state["promocoes"] = []

    promocoes_registradas = st.session_state["promocoes"]

    for p in promocoes_registradas:
        st.markdown(f"- {p['data'].strftime('%d/%m/%Y')} → Classe {p['classe']}")

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Limpar Tudo"):
    st.session_state.clear()
    st.experimental_rerun()

if st.sidebar.button("🚀 Calcular"):
    st.session_state["executar"] = True

st.title("⚖️ Cálculo de Diferença de Classe (PC/AL)")

if st.session_state.get("executar", False):
    if not arquivos:
        st.warning("⚠️ Nenhum arquivo de ficha financeira foi enviado.")
    elif not promocoes_registradas:
        st.warning("⚠️ Nenhuma promoção registrada.")
    else:
        st.success("✅ Dados carregados. Pronto para executar cálculo (exemplo simulado aqui).")

else:
    st.info("👈 Envie os arquivos e registre promoções para iniciar.")

