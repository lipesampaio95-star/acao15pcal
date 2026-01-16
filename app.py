
import streamlit as st
import pandas as pd
import pdfplumber
import re
from fpdf import FPDF

st.set_page_config(page_title="Cálculo PC/AL - Lei 7.602/2014", layout="wide")

def limpar_valor(texto):
    if isinstance(texto, (int, float)): return float(texto)
    if not texto: return 0.0
    t = str(texto).replace('"', '').replace("'", "").replace('R$', '').strip()
    try:
        if ',' in t and '.' in t:
            if t.rfind(',') > t.rfind('.'): t = t.replace('.', '').replace(',', '.')
            else: t = t.replace(',', '')
        elif ',' in t: t = t.replace(',', '.')
        return float(t)
    except: return 0.0

def base_AI_ano(ano):
    reajustes = {
        2014: 3178.00,
        2015: 3178.00 * 1.05,
        2018: 3178.00 * 1.05 * 1.0295,
        2022: 3178.00 * 1.05 * 1.0295 * 1.10,
        2025: 3178.00 * 1.05 * 1.0295 * 1.10 * 1.0393
    }
    for a in sorted(reajustes.keys(), reverse=True):
        if ano >= a: return reajustes[a]
    return reajustes[2014]

def extrair_financeiro(arq):
    dados = []
    adic_ferias = {}
    with pdfplumber.open(arq) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if not txt: continue
            ano_match = re.search(r"Ano\s+Comp\D*?(\d{4})", txt)
            if not ano_match: continue
            ano = int(ano_match.group(1))
            linhas = txt.split("\n")
            for linha in linhas:
                if "126.00" in linha and "SUBSIDIO" in linha.upper():
                    partes = linha.split()
                    for i, val in enumerate(partes):
                        valor = limpar_valor(val)
                        if valor > 0 and i < 13:
                            data = pd.to_datetime(f"{ano}-{i+1}-01")
                            dados.append({"Data": data, "Valor_Pago": valor})
                if "133.00" in linha and "FERIAS" in linha.upper():
                    partes = linha.split()
                    for i, val in enumerate(partes):
                        valor = limpar_valor(val)
                        if valor > 0 and i < 13:
                            data = pd.to_datetime(f"{ano}-{i+1}-01")
                            adic_ferias[data] = valor
    df = pd.DataFrame(dados)
    if df.empty: return df
    df = df.groupby("Data")["Valor_Pago"].sum().reset_index()
    df["Adic_Pago"] = df["Data"].map(adic_ferias).fillna(0.0)
    return df

def aplicar_calculo(df, classe_dict):
    classe_map = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    nivel_map = {'I':0, 'II':1, 'III':2, 'IV':3}
    classe_list, nivel_list = [], []
    for dt in df["Data"]:
        cls, niv = "A", "I"
        for item in classe_dict:
            if dt >= item["Data"]:
                cls, niv = item["Classe"], item["Nivel"]
        classe_list.append(cls)
        nivel_list.append(niv)
    df["Classe"] = classe_list
    df["Nivel"] = nivel_list
    df["IndiceClasse"] = df["Classe"].map(classe_map).fillna(0)
    df["IndiceNivel"] = df["Nivel"].map(nivel_map).fillna(0)
    df["Base_A_I"] = df["Data"].dt.year.apply(base_AI_ano)
    df["Valor_Devido"] = (df["Base_A_I"] * (1.15 ** df["IndiceClasse"])) + (df["Base_A_I"] * 0.05 * df["IndiceNivel"])
    df["Adic_Devido"] = df["Valor_Devido"] / 3
    df["Dif_Subsidio"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Dif_Adicional"] = df["Adic_Devido"] - df["Adic_Pago"]
    df["Diferenca_Final"] = df["Dif_Subsidio"].clip(lower=0) + df["Dif_Adicional"].clip(lower=0)
    return df

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "LAUDO TÉCNICO PERICIAL", ln=True, align="C")
        self.ln(5)
    def add_identificacao(self, nome, matricula):
        self.set_font("Arial", "", 10)
        self.cell(0, 10, f"Autor: {nome}", ln=True)
        self.cell(0, 10, f"Matrícula: {matricula}", ln=True)
        self.ln(5)
    def add_tabela(self, df):
        self.set_font("Arial", "B", 10)
        colunas = ["Mês/Ano", "Classe", "Nível", "Pago", "Devido", "Adic. Pago", "Adic. Devido", "Diferença"]
        larguras = [25, 20, 20, 25, 25, 25, 25, 25]
        for i, col in enumerate(colunas): self.cell(larguras[i], 8, col, border=1, align="C")
        self.ln()
        self.set_font("Arial", "", 9)
        for _, row in df.iterrows():
            valores = [
                row["Data"].strftime("%m/%Y"), row["Classe"], row["Nivel"],
                f"R$ {row['Valor_Pago']:.2f}".replace(".", ","),
                f"R$ {row['Valor_Devido']:.2f}".replace(".", ","),
                f"R$ {row['Adic_Pago']:.2f}".replace(".", ","),
                f"R$ {row['Adic_Devido']:.2f}".replace(".", ","),
                f"R$ {row['Diferenca_Final']:.2f}".replace(".", ","),
            ]
            for i, v in enumerate(valores): self.cell(larguras[i], 6, v, border=1, align="C")
            self.ln()
    def add_total(self, total):
        self.ln(5)
        self.set_font("Arial", "B", 11)
        self.cell(0, 10, f"VALOR TOTAL ACUMULADO: R$ {total:.2f}".replace(".", ","), ln=True)

def gerar_pdf(df, nome, matricula, total):
    pdf = PDF()
    pdf.add_page()
    pdf.add_identificacao(nome, matricula)
    pdf.add_tabela(df)
    pdf.add_total(total)
    output = "/mnt/data/laudo.pdf"
    pdf.output(output)
    return output

def gerar_projefweb_txt(df):
    linhas_txt = []
    for _, row in df.iterrows():
        data_fmt = row["Data"].strftime("%m-%Y")
        valor = max(0, row["Diferenca_Final"])
        valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        linhas_txt.append(f"{data_fmt}	{valor_fmt}")
    caminho = "/mnt/data/projefweb.txt"
    with open(caminho, "w", encoding="utf-8") as f: f.write("\n".join(linhas_txt))
    return caminho

# ==== INTERFACE STREAMLIT ====
st.title("⚖️ Cálculo PC/AL – Lei 7.602/2014")
nome = st.text_input("👤 Nome do servidor", "João Silva")
matricula = st.text_input("🆔 Matrícula", "0000001")
uploaded_files = st.file_uploader("📂 Fichas Financeiras (PDF - 1 por ano)", type=["pdf"], accept_multiple_files=True)

classe_dict = []
st.subheader("📌 Promoções Manuais")
with st.form("promocoes"):
    col1, col2, col3 = st.columns(3)
    datas = col1.text_area("Datas (dd/mm/aaaa)", "01/01/2020\n01/01/2023")
    classes = col2.text_area("Classes (A-G)", "A\nC")
    niveis = col3.text_area("Níveis (I-IV)", "I\nII")
    if st.form_submit_button("💾 Registrar Promoções"):
        for d, c, n in zip(datas.strip().split("\n"), classes.strip().split("\n"), niveis.strip().split("\n")):
            try:
                classe_dict.append({"Data": pd.to_datetime(d, dayfirst=True), "Classe": c.strip().upper(), "Nivel": n.strip().upper()})
            except: st.warning(f"Data inválida: {d}")

if st.button("🚀 Calcular"):
    if not uploaded_files or not classe_dict:
        st.warning("Envie os arquivos e registre promoções.")
    else:
        all_df = []
        for file in uploaded_files:
            df = extrair_financeiro(file)
            if not df.empty: all_df.append(df)
        if not all_df:
            st.error("Nenhum dado encontrado.")
        else:
            df_merged = pd.concat(all_df).groupby("Data").sum().reset_index()
            resultado = aplicar_calculo(df_merged, classe_dict)
            total = resultado["Diferenca_Final"].sum()
            st.success("✅ Cálculo realizado.")
            st.dataframe(resultado)
            st.markdown(f"### 💰 Total Devido: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

            path_pdf = gerar_pdf(resultado, nome, matricula, total)
            path_txt = gerar_projefweb_txt(resultado)
            with open(path_pdf, "rb") as f: st.download_button("📄 Baixar PDF", f, file_name="laudo.pdf")
            with open(path_txt, "rb") as f: st.download_button("📑 Baixar TXT Projefweb", f, file_name="projefweb.txt")
