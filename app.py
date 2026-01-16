
import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from fpdf import FPDF

st.set_page_config(page_title="Cálculo PC/AL", layout="wide")

# ===================== Utilitários =====================
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

def fmt_br(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ===================== Leitura da Ficha Financeira =====================
def extrair_financeiro(arquivo):
    dados = []
    adicional_ferias_map = {}
    if not arquivo.name.endswith(".pdf"):
        return pd.DataFrame()

    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if not txt:
                continue

            ano_match = re.search(r"Ano\s+Comp\D*?(\d{4})", txt)
            if not ano_match:
                continue
            ano = int(ano_match.group(1))

            linhas = txt.split("
")
            for linha in linhas:
                if "126.00" in linha and "SUBSIDIO" in linha.upper():
                    partes = linha.split()
                    for i, val in enumerate(partes):
                        valor = limpar_valor(val)
                        if valor > 0 and i < 13:
                            mes = i + 1
                            data = pd.to_datetime(f"{ano}-{mes:02d}-01")
                            dados.append({"Data": data, "Valor_Pago": valor})

                if "133.00" in linha and "FERIAS" in linha.upper():
                    partes = linha.split()
                    for i, val in enumerate(partes):
                        valor = limpar_valor(val)
                        if valor > 0 and i < 13:
                            mes = i + 1
                            data = pd.to_datetime(f"{ano}-{mes:02d}-01")
                            adicional_ferias_map[data] = valor

    df = pd.DataFrame(dados)
    if df.empty: return df

    df = df.groupby("Data")["Valor_Pago"].sum().reset_index()
    df["Adic_Pago"] = df["Data"].map(adicional_ferias_map).fillna(0.0)
    return df

# ===================== Cálculo com Classe Manual =====================
def aplicar_calculo(df, classe_dict, base_valor):
    mapa = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}

    classe_series = []
    for dt in df["Data"]:
        classe = "A"
        for item in classe_dict:
            if dt >= item["Data"]:
                classe = item["Classe"]
        classe_series.append(classe)

    df["Classe"] = classe_series
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base_valor * (1.15 ** df["Indice"])

    # Calcular adicional de férias devido (1/3 do valor devido)
    df["Adic_Devido"] = df["Valor_Devido"] / 3
    df["Dif_Subsidio"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Dif_Adicional"] = df["Adic_Devido"] - df["Adic_Pago"]

    # Final: somar diferenças positivas
    df["Diferenca_Final"] = df["Dif_Subsidio"].clip(lower=0) + df["Dif_Adicional"].clip(lower=0)
    return df

# ===================== Interface Streamlit =====================
st.title("🧮 Cálculo PC/AL com Promoções Manuais")
st.markdown("Automação do cálculo de subsídio com adicional de férias incluso.")

col1, col2 = st.columns(2)
with col1:
    base_valor = st.number_input("💰 Valor Base Classe A (R$)", value=4000.00, step=100.00, format="%.2f")
with col2:
    nome = st.text_input("👤 Nome do Servidor", value="Ex: João Silva")

mat = st.text_input("🆔 Matrícula", value="0000000")

uploaded_files = st.file_uploader("📄 Envie as Fichas Financeiras (1 por ano)", type=["pdf"], accept_multiple_files=True)

st.markdown("----")
st.subheader("📌 Informe manualmente a evolução de classe")
classe_dict = []
with st.form("form_classes"):
    col1, col2 = st.columns(2)
    datas = col1.text_area("Datas (formato: dd/mm/aaaa)", "01/01/2020\n01/01/2023")
    classes = col2.text_area("Classes Correspondentes (A-G)", "A\nC")
    submitted = st.form_submit_button("💾 Registrar Promoções")
    if submitted:
        dt_list = datas.strip().split("\n")
        cl_list = classes.strip().split("\n")
        for dt, cl in zip(dt_list, cl_list):
            try:
                data_obj = pd.to_datetime(dt, dayfirst=True)
                classe_dict.append({"Data": data_obj, "Classe": cl.strip().upper()})
            except:
                st.warning(f"Data inválida: {dt}")

st.markdown("----")
if st.button("🚀 Executar Cálculo"):
    if not uploaded_files:
        st.warning("⚠️ Envie ao menos uma ficha financeira.")
    elif not classe_dict:
        st.warning("⚠️ Informe ao menos uma promoção manual.")
    else:
        all_df = []
        for file in uploaded_files:
            df_temp = extrair_financeiro(file)
            if not df_temp.empty:
                all_df.append(df_temp)

        if not all_df:
            st.error("❌ Nenhuma ficha válida.")
        else:
            df_final = pd.concat(all_df).groupby("Data").sum().reset_index()
            resultado = aplicar_calculo(df_final, classe_dict, base_valor)

            st.success("✅ Cálculo executado com sucesso!")
            st.dataframe(resultado[["Data", "Classe", "Valor_Pago", "Valor_Devido", "Adic_Pago", "Adic_Devido", "Diferenca_Final"]])

            total = resultado["Diferenca_Final"].sum()
            st.subheader(f"💰 Total Devido: R$ {fmt_br(total)}")
