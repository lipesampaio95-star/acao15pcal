# ⚖️ Sistema de Cálculo Jurídico - PC/AL

Este sistema realiza cálculos automáticos de diferenças remuneratórias com base na evolução de classes funcionais da Polícia Civil do Estado de Alagoas. O cálculo é feito com base nas Fichas Financeiras e nas Fichas Cadastrais (Promoções), considerando as transições de classe ao longo do tempo.

## ✅ Funcionalidades

- 🧾 Leitura automatizada de fichas financeiras (com OCR se necessário)
- 📈 Cálculo da diferença devida com base na classe vigente mês a mês
- 🧮 Correção com base no percentual de 15% por classe (Lei Estadual 6.276/01 e 7.602/2014)
- 📑 Exportação para:
  - Laudo técnico em PDF
  - Arquivo TXT compatível com Projefweb

## 📁 Upload de Arquivos

1. **Ficha Financeira** (PDF)
2. **Ficha(s) Cadastral(is)** com histórico de promoções (PDFs múltiplos)

> O sistema utiliza OCR para ler PDFs escaneados (imagem), como também analisa texto digital.

## 📦 Instalação

### 1. Clone o repositório:

```bash
git clone https://github.com/seu-usuario/nome-do-repositorio.git
cd nome-do-repositorio
```

### 2. Instale as dependências:

```bash
pip install -r requirements.txt
```

> Se estiver em Linux ou Streamlit Cloud, o OCR requer instalação do Tesseract:

```bash
sudo apt update && sudo apt install -y tesseract-ocr libtesseract-dev
```

## 🚀 Execução local

```bash
streamlit run app_final_cronologia.py
```

## 🛠️ Parâmetros

- Valor base da Classe A (padrão: R$ 4.000,00)
- Nome do servidor
- Matrícula
- Upload dos documentos

## 📤 Exportações

- `laudo.pdf` → relatório detalhado com datas, classes, valores pagos/devidos e diferenças.
- `projefweb.txt` → padrão de importação para o sistema do Tribunal de Justiça de Alagoas.

## 🧠 Lógica de Cálculo

A cada mês, o sistema:

1. Identifica a classe vigente (com base nas datas de promoção extraídas da ficha cadastral)
2. Calcula o valor devido aplicando +15% por classe a partir da Classe A
3. Subtrai do valor efetivamente pago (extraído da ficha financeira)
4. Registra a diferença devida se for positiva

## 📌 Requisitos técnicos

- Python 3.8+
- Tesseract OCR (recomendado)
- Libs do requirements.txt

---

© Desenvolvido para cálculos judiciais com precisão e fé pública.
