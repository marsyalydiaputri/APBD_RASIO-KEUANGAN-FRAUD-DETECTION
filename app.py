# app.py
import streamlit as st
import pandas as pd
import numpy as np
import requests
from sklearn.ensemble import IsolationForest
import plotly.express as px
import io

st.set_page_config(layout="wide", page_title="APBD Super — Rasio & Fraud Detection")

# -----------------------
# Helper: TEMPLATE EXCEL
# -----------------------
TEMPLATE_COLUMNS = [
    "Tahun","SKPD","Kode_Rekening","Uraian","Jenis_Transaksi",
    "PAD","Dana_Transfer","Pendapatan_Daerah","Target_PAD","Realisasi_PAD",
    "Belanja_Operasi","Belanja_Modal","Total_Belanja","Anggaran_Belanja",
    "Nilai_Transaksi"
]

SAMPLE_ROWS = [
    [2024,"Dinas A","5.1.01","Belanja honor kegiatan X","Belanja",0,0,1000000,500000,480000,200000,300000,500000,550000,200000],
    [2024,"Dinas B","5.2.02","Pembelian alat tulis","Belanja",0,0,1000000,0,0,50000,0,50000,50000,50000],
    [2024,"Dinas A","4.1.01","Pendapatan PAD sektor X","Pendapatan",150000,0,150000,160000,155000,0,0,0,0,0],
]

def make_template_excel():
    df = pd.DataFrame(SAMPLE_ROWS, columns=TEMPLATE_COLUMNS)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="APBD")
    buffer.seek(0)
    return buffer

# -----------------------
# Sidebar navigation
# -----------------------
st.sidebar.title("APBD Super (Menu)")
page = st.sidebar.radio("Navigate", ["Home", "APBD Analyzer", "Fraud Detection", "Download Template"])

# -----------------------
# Home
# -----------------------
if page == "Home":
    st.title("📊 APBD Super — Rasio Keuangan & Macro Fraud Detection")
    st.markdown("""
    Aplikasi ini membantu:
    - Menghitung rasio keuangan (kemandirian, efektivitas, efisiensi, dll.)
    - Mendeteksi anomali anggaran (macro-level) menggunakan IsolationForest
    - Memberi penjelasan otomatis (opsional) via Groq API
    ---
    *Cara pakai singkat:*
    1. Download template Excel (menu Download Template) lalu isi data sesuai kolom.  
    2. Upload file .xlsx di menu APBD Analyzer / Fraud Detection.  
    3. Cek validasi kolom — aplikasi akan memberi pesan jelas jika ada kolom hilang.
    """)

# -----------------------
# Download Template
# -----------------------
elif page == "Download Template":
    st.header("Download Template Excel APBD (untuk upload)")
    st.write("Klik tombol di bawah untuk mendownload template .xlsx. Isi data sesuai kolom header yang tersedia.")
    buf = make_template_excel()
    st.download_button("Download template_apbd.xlsx", data=buf, file_name="template_apbd.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("*Kolom wajib (header persis):*")
    st.write(TEMPLATE_COLUMNS)

# -----------------------
# APBD Analyzer (rasio & visual)
# -----------------------
elif page == "APBD Analyzer":
    st.header("APBD Analyzer — Hitung Rasio & Visualisasi")
    uploaded = st.file_uploader("Upload file APBD (.xlsx) - gunakan template", type=["xlsx"], key="analyzer")
    if uploaded is None:
        st.info("Upload file .xlsx terlebih dahulu, atau download template di menu 'Download Template'.")
        st.stop()

    # read excel with error handling
    try:
        df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Gagal membaca file Excel: {e}")
        st.stop()

    st.subheader("Preview (5 baris)")
    st.dataframe(df.head(), use_container_width=True)

    # validate columns
    required_cols = TEMPLATE_COLUMNS
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error("Kolom tidak lengkap. Kolom yang hilang: " + ", ".join(missing))
        st.info("Pastikan header persis sesuai template (case-sensitive).")
        st.stop()

    # compute totals and rasio (persen)
    totals = {
        "PAD": df["PAD"].sum(),
        "Transfer": df["Dana_Transfer"].sum(),
        "Realisasi_PAD": df["Realisasi_PAD"].sum(),
        "Target_PAD": df["Target_PAD"].sum(),
        "Belanja_Realisasi": df["Belanja_Operasi"].sum() + df["Belanja_Modal"].sum(),
        "Anggaran_Belanja": df["Anggaran_Belanja"].sum(),
        "Total_Belanja": df["Total_Belanja"].sum(),
        "Pendapatan_Daerah": df["Pendapatan_Daerah"].sum()
    }

    def rasio_kemandirian(pad, transfer): return (pad / transfer * 100) if transfer != 0 else 0
    def rasio_efektivitas(realisasi, target): return (realisasi / target * 100) if target != 0 else 0
    def rasio_efisiensi(realisasi_belanja, anggaran_belanja): return (realisasi_belanja / anggaran_belanja * 100) if anggaran_belanja != 0 else 0
    def rasio_bo(b_op, total_b): return (b_op / total_b * 100) if total_b != 0 else 0
    def rasio_bm(b_mod, total_b): return (b_mod / total_b * 100) if total_b != 0 else 0

    rasios = {
        "Rasio Kemandirian (%)": round(rasio_kemandirian(totals["PAD"], totals["Transfer"]), 2),
        "Rasio Efektivitas PAD (%)": round(rasio_efektivitas(totals["Realisasi_PAD"], totals["Target_PAD"]), 2),
        "Rasio Efisiensi (%)": round(rasio_efisiensi(totals["Belanja_Realisasi"], totals["Anggaran_Belanja"]), 2),
        "Rasio Belanja Operasi (%)": round(rasio_bo(df["Belanja_Operasi"].sum(), totals["Total_Belanja"]), 2),
        "Rasio Belanja Modal (%)": round(rasio_bm(df["Belanja_Modal"].sum(), totals["Total_Belanja"]), 2)
    }

    st.subheader("Ringkasan Rasio")
    st.json(rasios)

    # visual: trend PAD vs Total Belanja by Tahun (jika ada lebih dari 1 tahun)
    if "Tahun" in df.columns:
        pivot = df.groupby("Tahun").agg({"PAD":"sum","Total_Belanja":"sum"}).reset_index()
        fig = px.line(pivot, x="Tahun", y=["PAD","Total_Belanja"], title="Tren PAD vs Total Belanja")
        st.plotly_chart(fig, use_container_width=True)

    # composition pie
    st.subheader("Komposisi Belanja")
    comp = pd.DataFrame({
        "Kategori":["Belanja Operasi","Belanja Modal"],
        "Nilai":[df["Belanja_Operasi"].sum(), df["Belanja_Modal"].sum()]
    })
    figp = px.pie(comp, names="Kategori", values="Nilai", title="Komposisi Belanja")
    st.plotly_chart(figp, use_container_width=True)

    # allow download report CSV
    st.subheader("Ekspor Ringkasan")
    if st.button("Download ringkasan rasio (CSV)"):
        out = pd.DataFrame([rasios])
        csv = out.to_csv(index=False).encode("utf-8")
        st.download_button("Klik untuk download CSV", data=csv, file_name="ringkasan_rasio.csv", mime="text/csv")

# -----------------------
# Fraud Detection
# -----------------------
elif page == "Fraud Detection":
    st.header("Fraud Detection (Macro-level) — Outlier & Risk Scoring")
    uploaded = st.file_uploader("Upload file APBD (.xlsx) - gunakan template", type=["xlsx"], key="fraud")
    if uploaded is None:
        st.info("Upload file .xlsx terlebih dahulu, atau download template di menu 'Download Template'.")
        st.stop()

    # read excel
    try:
        df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Gagal membaca file Excel: {e}")
        st.stop()

    # validate
    required_cols = TEMPLATE_COLUMNS
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error("Kolom tidak lengkap. Kolom yang hilang: " + ", ".join(missing))
        st.stop()

    st.subheader("Preview data")
    st.dataframe(df.head(), use_container_width=True)

    # Feature engineering minimal
    df["prop_total"] = df["Nilai_Transaksi"] / (df["Total_Belanja"].sum() + 1e-9)
    df["log_val"] = np.log1p(df["Nilai_Transaksi"].fillna(0))

    X = df[["log_val","prop_total"]].fillna(0).values

    n_estimators = st.sidebar.slider("Jumlah trees (IsolationForest)", 50, 300, 100)
    contamination = st.sidebar.slider("Perkiraan proporsi anomali (contamination)", 0.001, 0.2, 0.02, step=0.001)

    model = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=42)
    with st.spinner("Melatih model..."):
        model.fit(X)

    df["anomaly_score"] = model.decision_function(X)  # higher = normal, lower = anomaly
    df["is_anomaly_flag"] = model.predict(X) == -1  # True for anomaly

    st.success(f"Deteksi selesai. Baris ter-flag anomali: {df['is_anomaly_flag'].sum()} dari {len(df)}")

    st.subheader("Daftar Anomali (terurut)")
    anomali_df = df[df["is_anomaly_flag"]].sort_values("anomaly_score")
    display_cols = ["Tahun","SKPD","Kode_Rekening","Uraian","Nilai_Transaksi","anomaly_score"]
    st.dataframe(anomali_df[display_cols].head(200), use_container_width=True)

    # allow user to inspect full table with highlighting (uses st.dataframe; style not perfectly supported in cloud)
    st.subheader("Tabel lengkap (anomaly flag shown)")
    st.dataframe(df[[*TEMPLATE_COLUMNS,"prop_total","log_val","anomaly_score","is_anomaly_flag"]].head(500), use_container_width=True)

    # Groq interpretation
    st.subheader("Interpretasi otomatis (Groq) — opsional")
    groq_key = st.text_input("Masukkan Groq API Key (opsional)", type="password")
    if groq_key:
        top_n = st.number_input("Berapa anomali teratas yang mau dijelaskan?", min_value=1, max_value=10, value=3)
        top = anomali_df.head(top_n)
        for i, row in top.iterrows():
            prompt = f"""
            Baris data APBD yang dicurigai anomali:
            Tahun: {row.get('Tahun')}, SKPD: {row.get('SKPD')}, Kode: {row.get('Kode_Rekening')},
            Uraian: {row.get('Uraian')}, Nilai: {row.get('Nilai_Transaksi')}, anomaly_score: {row.get('anomaly_score')}.
            Jelaskan mengapa baris ini bisa dicurigai (singkat), dan rekomendasi pemeriksaan.
            """
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "mixtral-8x7b-32768",
                        "messages": [{"role":"user","content":prompt}]
                    },
                    timeout=15
                )
                txt = r.json()["choices"][0]["message"]["content"]
                st.markdown(f"*Analisis (Kode {row.get('Kode_Rekening')} / SKPD {row.get('SKPD')}):*")
                st.write(txt)
            except Exception as e:
                st.error(f"Gagal panggil Groq: {e}")
                break

    # download flagged results
    st.subheader("Ekspor hasil deteksi")
    if st.button("Download hasil dengan flag (CSV)"):
        out = df.copy()
        csv = out.to_csv(index=False).encode("utf-8")
        st.download_button("Klik untuk download", data=csv, file_name="apbd_with_flags.csv", mime="text/csv")

# End of file
