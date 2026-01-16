import streamlit as st
import pandas as pd
import pdfplumber
import datetime
import io
from fpdf import FPDF

st.set_page_config(page_title="Calculadora PC/AL", layout="wide")

# -------------------------------
# Funções auxiliares
# -------------------------------
def converter_nome_mes(mes_str):
    meses = {
        "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
        "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
        "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12",
    }
    return meses.get(mes_str, "00")

def extrair_financeiro(file):
    with pdfplumber.open(file) as pdf:
        tabela = []
        ano = None
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            if "Ano Comp" in text:
                try:
                    ano = int(text.split("Ano Comp:")[1].split()[0])
                except:
                    pass

            lines = text.split("\n")
            for line in lines:
                if "126.00 SUBSIDIO" in line:
                    colunas = line.split()
                    valores = colunas[-13:]
                    meses = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
                    for i, val in enumerate(valores[:12]):
                        val_float = float(val.replace(".", "").replace(",", "."))
                        data = f"{ano}-{meses[i]}"
                        tabela.append({"Data": data, "Valor_Pago": val_float})
        return pd.DataFrame(tabela)

def calcular_base_ano(base_inicial):
    reajustes = {
        2015: 1.05,
        2018: 1.0295,
        2022: 1.10,
        2025: 1.0393
    }
    base_por_ano = {}
    atual = base_inicial
    for ano in range(2014, datetime.datetime.now().year + 1):
        if ano in reajustes:
            atual *= reajustes[ano]
        base_por_ano[ano] = atual
    return base_por_ano

def calcular_valor_devido(base_A_I, classe_idx, nivel_idx):
    return (base_A_I * (1.15 ** classe_idx)) + (base_A_I * 0.05 * nivel_idx)

def gerar_pdf(df, nome, matricula, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(200, 10, "LAUDO TÉCNICO PERICIAL", ln=True, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, f"Autor: {nome}", ln=True)
    pdf.cell(200, 10, f"Matrícula: {matricula}", ln=True)
    pdf.ln(5)

    pdf.set_fill_color(242, 243, 244)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(40, 10, "Mês/Ano", 1, 0, "C", True)
    pdf.cell(30, 10, "Classe", 1, 0, "C", True)
    pdf.cell(30, 10, "Nível", 1, 0, "C", True)
    pdf.cell(40, 10, "Pago", 1, 0, "C", True)
    pdf.cell(40, 10, "Devido", 1, 0, "C", True)
    pdf.cell(30, 10, "Diferença", 1, 1, "C", True)

    pdf.set_font("Arial", size=10)
    for _, row in df.iterrows():
        pdf.cell(40, 10, row["Data"], 1)
        pdf.cell(30, 10, row["Classe"], 1)
        pdf.cell(30, 10, row["Nível"], 1)
        pdf.cell(40, 10, f'R$ {row["Valor_Pago"]:,.2f}'.replace('.', '#').replace(',', '.').replace('#', ','), 1, 0, 'R')
        pdf.cell(40, 10, f'R$ {row["Valor_Devido"]:,.2f}'.replace('.', '#').replace(',', '.').replace('#', ','), 1, 0, 'R')
        pdf.cell(30, 10, f'R$ {row["Diferenca"]:,.2f}'.replace('.', '#').replace(',', '.').replace('#', ','), 1, 1, 'R')

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.set_fill_color(212, 239, 223)
    pdf.cell(200, 10, f"VALOR TOTAL ACUMULADO: R$ {total:,.2f}".replace('.', '#').replace(',', '.').replace('#', ','), 1, 1, 'C', True)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

def gerar_projefweb_txt(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        valor = f"R$ {row['Diferenca']:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
        output.write(f"{row['Data'][5:]}	{valor}\n")
    return output.getvalue().encode()

# -------------------------------
# Interface do Streamlit
# -------------------------------
st.title("⚖️ Cálculo de Diferença de Classe (PC/AL)")

with st.sidebar:
    st.header("Parâmetros de Entrada")

    arquivos = st.file_uploader("Ficha Financeira (PDF - um por ano)", type=["pdf"], accept_multiple_files=True)

    base_classe_A = st.number_input("Base Classe A (R$)", value=3178.00, step=100.0)

    nome = st.text_input("Nome do Servidor", "Ex: João da Silva")
    matricula = st.text_input("Matrícula", "0000000")

    st.markdown("### 📌 Promoções (Manual)")
    datas = []
    classes = []
    niveis = []

    promo_col1, promo_col2 = st.columns([2, 2])
    with promo_col1:
        data_promo = st.text_input("Data da Promoção", "2016/03/01")
    with promo_col2:
        classe_promo = st.selectbox("Classe", ["A", "B", "C", "D", "E", "F", "G"])
    nivel_promo = st.selectbox("Nível", ["I", "II", "III", "IV"])

    if "historico" not in st.session_state:
        st.session_state.historico = []

    if st.button("Registrar Promoção"):
        st.session_state.historico.append((data_promo, classe_promo, nivel_promo))

    if st.button("🧹 Limpar Promoções"):
        st.session_state.historico = []

    for item in sorted(st.session_state.historico):
        st.write(f"{item[0]} → Classe {item[1]} / Nível {item[2]}")

    if st.button("🧹 Limpar Tudo"):
        st.session_state.clear()
        st.rerun()

# -------------------------------
# Execução do Cálculo
# -------------------------------
if st.button("🚀 Calcular") and arquivos and st.session_state.historico:
    dfs = []
    for file in arquivos:
        df = extrair_financeiro(file)
        dfs.append(df)

    df_fin = pd.concat(dfs).sort_values(by="Data")
    df_fin.reset_index(drop=True, inplace=True)

    base_ano = calcular_base_ano(base_classe_A)

    promo_df = pd.DataFrame(st.session_state.historico, columns=["Data", "Classe", "Nivel"])
    promo_df["Data"] = pd.to_datetime(promo_df["Data"])
    promo_df = promo_df.sort_values("Data")

    historico_completo = []
    for i in range(len(promo_df)):
        inicio = promo_df.iloc[i]["Data"]
        fim = promo_df.iloc[i + 1]["Data"] if i + 1 < len(promo_df) else datetime.datetime.now()
        datas = pd.date_range(inicio, fim, freq="MS").strftime("%Y-%m").tolist()
        for d in datas:
            historico_completo.append((d, promo_df.iloc[i]["Classe"], promo_df.iloc[i]["Nivel"]))

    df_hist = pd.DataFrame(historico_completo, columns=["Data", "Classe", "Nivel"])
    df_merge = pd.merge(df_fin, df_hist, on="Data", how="inner")

    df_merge["Ano"] = df_merge["Data"].str[:4].astype(int)
    df_merge["Base_A"] = df_merge["Ano"].map(base_ano)

    df_merge["Classe_Index"] = df_merge["Classe"].map(lambda x: ord(x.upper()) - ord("A"))
    df_merge["Nivel_Index"] = df_merge["Nivel"].map({"I": 0, "II": 1, "III": 2, "IV": 3})

    df_merge["Valor_Devido"] = df_merge.apply(lambda row: calcular_valor_devido(row["Base_A"], row["Classe_Index"], row["Nivel_Index"]), axis=1)
    df_merge["Diferenca"] = df_merge["Valor_Devido"] - df_merge["Valor_Pago"]
    df_merge["Diferenca"] = df_merge["Diferenca"].apply(lambda x: x if x > 0 else 0)

    df_merge["Valor_Pago"] = df_merge["Valor_Pago"].round(2)
    df_merge["Valor_Devido"] = df_merge["Valor_Devido"].round(2)
    df_merge["Diferenca"] = df_merge["Diferenca"].round(2)

    total = df_merge["Diferenca"].sum()

    st.success("✅ Cálculo finalizado com sucesso!")

    st.dataframe(df_merge[["Data", "Classe", "Nivel", "Valor_Pago", "Valor_Devido", "Diferenca"]])

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📑 Baixar PDF", gerar_pdf(df_merge, nome, matricula, total), "laudo.pdf", "application/pdf")
    with col2:
        st.download_button("📂 Baixar Projefweb TXT", gerar_projefweb_txt(df_merge), "projefweb.txt", "text/plain")
