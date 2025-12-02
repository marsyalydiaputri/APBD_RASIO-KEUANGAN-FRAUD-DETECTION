import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import plotly.express as px

st.set_page_config(layout="wide", page_title="APBD Analyzer — Premium Version")

st.title("📊 APBD Analyzer — Hitung Rasio Lengkap &Interpretasi")

# ============================================
# 🔧 Template Excel
# ============================================
TEMPLATE_COLUMNS = ["Akun","Anggaran","Realisasi","Persentase","Tahun"]
SAMPLE_ROWS = [
    ["Pendapatan Daerah", 3557491170098, 3758774961806, 105.66, 2024],
    ["PAD", 322846709929, 561854145372, 174.03, 2024],
    ["Belanja Pegawai", 1161122041234, 1058941535362, 91.20, 2024],
    ["Belanja Modal", 1133163195359, 836917297001, 73.86, 2024]
]

def make_template_excel():
    df = pd.DataFrame(SAMPLE_ROWS, columns=TEMPLATE_COLUMNS)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="APBD")
    buffer.seek(0)
    return buffer

# =======================================================
# 🔧 Helper — parse angka & formatting
# =======================================================
def format_rupiah(x):
    """Format angka menjadi 1.234.567.890"""
    try:
        return f"{int(x):,}".replace(",", ".")
    except:
        return x

def parse_number(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int,float,np.integer,np.floating)):
        return float(x)

    s=str(x).lower()
    s = s.replace("rp","").replace(" ", "")

    if "(" in s and ")" in s:
        s = "-" + s.replace("(", "").replace(")", "")

    # jika ada titik & koma → asumsikan titik = ribuan
    if "." in s and "," in s:
        s = s.replace(".","").replace(",",".")
    else:
        if "." in s and re.search(r"\.\d{1,2}$",s) is None:
            s = s.replace(".", "")
        s = s.replace(",", ".")

    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s)
    except:
        return 0.0

def find_column_by_keywords(df, keywords):
    for k in keywords:
        for c in df.columns:
            if k.lower() in str(c).lower():
                return c
    return None

# =======================================================
# 🔧 Klasifikasi akun
# =======================================================
def classify_account(name):
    n = str(name).lower()
    if "pad" in n or "pajak" in n or "retribusi" in n or "hasil pengelolaan" in n:
        return "PAD"
    if "transfer" in n or "tkdd" in n or "dau" in n or "dak" in n:
        return "TRANSFER"
    if n.startswith("pendapatan"):
        return "PENDAPATAN"
    if "belanja pegawai" in n or "barang" in n or "jasa" in n:
        return "BELANJA_OPERASI"
    if "belanja modal" in n:
        return "BELANJA_MODAL"
    if "subsidi" in n or "hibah" in n or "bantuan" in n:
        return "BELANJA_LAINNYA"
    if "tidak terduga" in n:
        return "BELANJA_TIDAK_TERDUGA"
    if "pembiayaan" in n:
        return "PEMBIAYAAN"
    return "LAINNYA"

# =======================================================
# 🔧 Interpretasi AI TANPA API (rule-based)
# =======================================================
def interpret_ratio(name, value):
    """AI sederhana berbasis aturan"""
    if value > 100:
        return f"Rasio *{name}* sangat tinggi ({value:.2f}%). Menunjukkan kinerja baik atau target rendah."
    elif value > 60:
        return f"Rasio *{name}* cukup baik ({value:.2f}%). Masih dalam kategori sehat."
    elif value > 40:
        return f"Rasio *{name}* sedang ({value:.2f}%). Perlu monitoring lanjutan."
    else:
        return f"Rasio *{name}* rendah ({value:.2f}%). Mengindikasikan potensi masalah efisiensi/kemandirian fiskal."

# =======================================================
# 📂 SIDEBAR
# =======================================================
st.sidebar.header("Menu")
page = st.sidebar.radio("Navigasi", ["Home","Upload & Analisis","Download Template"])

# =======================================================
# HOME
# =======================================================
if page == "Home":
    st.write("Aplikasi ini otomatis membersihkan data APBD, menghitung banyak rasio, dan memberikan interpretasi AI tanpa API key.")
    st.info("Format angka otomatis dibersihkan (Rp, titik, koma).")

# =======================================================
# DOWNLOAD TEMPLATE
# =======================================================
elif page == "Download Template":
    st.subheader("Download Template")
    st.download_button("Download template APBD", make_template_excel(), "template_apbd.xlsx")

# =======================================================
# UPLOAD & ANALISIS
# =======================================================
elif page == "Upload & Analisis":
    file = st.file_uploader("Upload file APBD (.xlsx)", type=["xlsx"])
    if file is None:
        st.stop()

    try:
        raw = pd.read_excel(file, dtype=str)
    except Exception as e:
        st.error("Gagal membaca file: " + str(e))
        st.stop()

    st.subheader("Preview Data Mentah")
    st.dataframe(raw.head())

    # ---------------- detect kolom -------------------
    akun_col = find_column_by_keywords(raw, ["akun","uraian","nama","rekening"]) or raw.columns[0]
    anggaran_col = find_column_by_keywords(raw, ["anggaran","pagu","nilai"])
    realisasi_col = find_column_by_keywords(raw, ["realisasi"])

    if anggaran_col is None or realisasi_col is None:
        st.error("Kolom Anggaran/Realisasi tidak ditemukan. Ubah nama header atau pakai template.")
        st.stop()

    df = raw[[akun_col,anggaran_col,realisasi_col]].copy()
    df.columns=["Akun","Anggaran","Realisasi"]

    df["Anggaran_num"]=df["Anggaran"].apply(parse_number)
    df["Realisasi_num"]=df["Realisasi"].apply(parse_number)
    df["Persen"]=np.where(df["Anggaran_num"]>0, df["Realisasi_num"]/df["Anggaran_num"]*100, 0)

    df["Kategori"]=df["Akun"].apply(classify_account)

    st.subheader("Data Setelah Dibersihkan")
    df_show = df.copy()
    df_show["Anggaran_fmt"] = df["Anggaran_num"].apply(format_rupiah)
    df_show["Realisasi_fmt"] = df["Realisasi_num"].apply(format_rupiah)
    st.dataframe(df_show.head(40))

    # =======================
    # AGGREGATE
    # =======================
    agg = df.groupby("Kategori")[["Anggaran_num","Realisasi_num"]].sum().reset_index()

    st.subheader("Aggregasi per Kategori")
    agg_show = agg.copy()
    agg_show["Anggaran_fmt"]=agg["Anggaran_num"].apply(format_rupiah)
    agg_show["Realisasi_fmt"]=agg["Realisasi_num"].apply(format_rupiah)
    st.dataframe(agg_show)

    # =======================
    # HITUNG RASIO LENGKAP
    # =======================
    PAD = agg[agg["Kategori"]=="PAD"]["Realisasi_num"].sum()
    TRANSFER = agg[agg["Kategori"]=="TRANSFER"]["Realisasi_num"].sum()
    BO = agg[agg["Kategori"]=="BELANJA_OPERASI"]["Realisasi_num"].sum()
    BM = agg[agg["Kategori"]=="BELANJA_MODAL"]["Realisasi_num"].sum()
    TOTAL_BELANJA = agg[agg["Kategori"].str.contains("BELANJA")]["Realisasi_num"].sum()

    def safe(a,b):
        return a/b*100 if b>0 else 0

    rasio = {
        "Kemandirian (PAD/Transfer)": safe(PAD,TRANSFER),
        "Belanja Operasi / Total Belanja": safe(BO,TOTAL_BELANJA),
        "Belanja Modal / Total Belanja": safe(BM,TOTAL_BELANJA),
        "Efektivitas Pendapatan (Realisasi / Anggaran Pendapatan)": df["Realisasi_num"].sum() / df["Anggaran_num"].sum() * 100,
        "Efisiensi Belanja (Realisasi Belanja / Anggaran Belanja)": safe(TOTAL_BELANJA, df["Anggaran_num"].sum())
    }

    st.subheader("📈 Rasio Keuangan Lengkap")
    for k,v in rasio.items():
        st.metric(k, f"{v:.2f}%")

    # =======================
    # INTERPRETASI AUTO (TANPA API)
    # =======================
    st.subheader("🧠 Interpretasi AI (tanpa API key)")
    for k,v in rasio.items():
        st.markdown(f"{k}** → {interpret_ratio(k, v)}")

    # =======================
    # VISUAL
    # =======================
    st.subheader("Visualisasi Belanja")
    comp = pd.DataFrame({
        "Kategori":["Belanja Operasi","Belanja Modal","Lainnya"],
        "Nilai":[BO, BM, TOTAL_BELANJA-BO-BM]
    })
    fig = px.pie(comp, names="Kategori", values="Nilai", title="Komposisi Belanja")
    st.plotly_chart(fig)

    # =======================
    # DOWNLOAD
    # =======================
    st.subheader("Download Hasil Aggregasi")
    st.download_button("Download CSV", agg.to_csv(index=False).encode(), "apbd_aggregated.csv")
