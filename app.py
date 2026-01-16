import streamlit as st
import pandas as pd
import re
import io
from fpdf import FPDF

# Configurações da página
st.set_page_config(page_title="Cálculo PC/AL", layout="wide")

def fmt_br(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(texto):
    """Converte valores monetários para float"""
    if isinstance(texto, (int, float)): return float(texto)
    t = str(texto).replace('R$', '').replace('.', '').replace(',', '.')
    try:
        return float(t)
    except:
        return 0.0

def extrair_financeiro(pdf_file):
    """Extrai dados da ficha financeira em PDF pesquisável"""
    try:
        import pdfplumber
    except:
        st.error("⚠️ A biblioteca pdfplumber não está instalada.")
        return pd.DataFrame()

    dados = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            linhas = texto.split('\n')
            ano = None
            for linha in linhas:
                linha_upper = linha.upper()
                # Detecta ano da competência
                if "ANO COMP" in linha_upper:
                    m = re.search(r'(\d{4})', linha)
                    if m: ano = int(m.group(1))
                # Detecta subsídio e valores mensais
                if "SUBSÍDIO" in linha_upper or "SUBSIDIO" in linha_upper:
                    meses = re.findall(r'(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)', linha_upper)
                    valores = re.findall(r'R\$ ?[\d\.,]+', linha)
                    if ano and len(meses) == len(valores):
                        for i in range(len(meses)):
                            mes_num = i + 1
                            valor = limpar_valor(valores[i])
                            dados.append({
                                "Data": pd.to_datetime(f"{ano}-{mes_num:02d}-01"),
                                "Valor_Pago": valor
                            })
    df = pd.DataFrame(dados)
    return df.sort_values("Data")

def extrair_carreira(pdf_files):
    """Extrai histórico de promoções a partir das fichas cadastrais"""
    try:
        from PyPDF2 import PdfReader
    except:
        st.error("⚠️ A biblioteca PyPDF2 não está instalada.")
        return pd.DataFrame()

    historico = []
    for file in pdf_files:
        reader = PdfReader(file)
        for page in reader.pages:
            txt = page.extract_text()
            if not txt: continue
            # Extrair promoções
            matches = re.findall(r'Data Promoção\s*:\s*(\d{2}/\d{2}/\d{4}).*?(PC[EA][A-Z0-9\-]+|NV[0-9A-Z\-]+|AGP[A-Z0-9\-]+)', txt)
            for data_str, cod in matches:
                classe = None
                if "G40" in cod:
                    classe = "G"
                elif "F40" in cod:
                    classe = "F"
                elif "E40" in cod:
                    classe = "E"
                elif "D40" in cod:
                    classe = "D"
                elif "C40" in cod:
                    classe = "C"
                elif "B40" in cod:
                    classe = "B"
                elif "A40" in cod:
                    classe = "A"
                if classe:
                    historico.append({
                        "Data_Mudanca": pd.to_datetime(data_str, dayfirst=True),
                        "Classe": classe
                    })
    df = pd.DataFrame(historico).drop_duplicates().sort_values("Data_Mudanca")
    return df

def calcular_diferencas(df_fin, df_car, base_valor):
    """Cruza a ficha financeira com o histórico de carreira"""
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df = pd.merge_asof(df_fin.sort_values("Data"), df_car.sort_values("Data_Mudanca"),
                       left_on="Data", right_on="Data_Mudanca", direction='backward')
    df["Classe"] = df["Classe"].fillna("A")
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base_valor * (1.15 ** df["Indice"])

    # Adicionais (simples para Streamlit Cloud)
    df["Mes"] = df["Data"].dt.month
    df["Adicional_Ferias"] = df["Mes"].apply(lambda m: base_valor if m == 1 else 0)
    df["Terco_Ferias"] = df["Adicional_Ferias"] / 3
    df["Decimo_Terceiro"] = df["Mes"].apply(lambda m: base_valor if m == 12 else 0)

    df["Diferenca_Base"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Total"] = df["Diferenca_Base"] + df["Terco_Ferias"] + df["Decimo_Terceiro"]
    df["Diferenca_Final"] = df["Diferenca_Total"].apply(lambda x: x if x > 0 else 0)
    return df

def gerar_txt_projefweb(df):
    """Gera TXT no padrão Projefweb"""
    s = io.StringIO()
    for _, row in df.iterrows():
        if row["Diferenca_Final"] > 0:
            data_fmt = row["Data"].strftime("%m-%Y")
            valor_fmt = fmt_br(row["Diferenca_Final"])
            s.write(f"{data_fmt}\tR$ {valor_fmt}\n")
    return s.getvalue().encode('utf-8')

# ========== INTERFACE STREAMLIT ==========
st.title("⚖️ Sistema de Cálculo PC/AL - Versão Streamlit Cloud")

col1, col2 = st.columns(2)
with col1:
    fin_file = st.file_uploader("📄 Ficha Financeira (PDF)", type=["pdf"])
with col2:
    car_files = st.file_uploader("📂 Fichas Cadastrais (PDFs)", type=["pdf"], accept_multiple_files=True)

base_valor = st.number_input("💰 Valor Base Classe A (R$)", value=4000.00)
nome = st.text_input("👤 Nome do Servidor", "Ex: João Silva")
matricula = st.text_input("🆔 Matrícula", "0000000")

if st.button("🚀 Executar Cálculo"):
    if fin_file and car_files:
        df_fin = extrair_financeiro(fin_file)
        df_car = extrair_carreira(car_files)

        if df_fin.empty or df_car.empty:
            st.error("⚠️ Dados insuficientes. Verifique os PDFs.")
        else:
            resultado = calcular_diferencas(df_fin, df_car, base_valor)
            total = resultado["Diferenca_Final"].sum()

            st.success(f"Cálculo concluído com sucesso! Total devido: R$ {fmt_br(total)}")

            st.dataframe(resultado[["Data", "Classe", "Valor_Pago", "Valor_Devido", "Diferenca_Final"]])

            txt_bytes = gerar_txt_projefweb(resultado)
            st.download_button("📑 Baixar Projefweb TXT", txt_bytes, f"{nome}_projefweb.txt", "text/plain")
    else:
        st.warning("👈 Faça upload dos dois arquivos para iniciar.")
