# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import requests
import plotly.express as px

st.set_page_config(layout="wide", page_title="APBD Analyzer (Robust)")

st.title("📊 APBD Analyzer — Rasio & Visualisasi")

# ----------------------------
# Helper: Template Excel
# ----------------------------
TEMPLATE_COLUMNS = ["Akun","Anggaran","Realisasi","Persentase","Tahun"]
SAMPLE_ROWS = [
    ["Pendapatan Daerah", 3557491170098, 3758774961806, 105.66, 2024],
    ["PAD", 322846709929, 561854145372, 174.03, 2024],
    ["Belanja Pegawai", 1161122041234, 1058941535362, 91.20, 2024],
    ["Belanja Modal", 1133163195359, 836917297001, 73.86, 2024],
]

def make_template_excel():
    df = pd.DataFrame(SAMPLE_ROWS, columns=TEMPLATE_COLUMNS)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="APBD")
    buffer.seek(0)
    return buffer

# ----------------------------
# Utility: parsing angka & deteksi kolom
# ----------------------------
def parse_number(x):
    """Bersihkan string angka 'Rp 1.000.000' -> 1000000, juga handle numeric types."""
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x)
    # remove common prefixes/characters
    s = s.replace("Rp", "").replace("rp", "")
    # remove whitespace
    s = s.strip()
    # handle parentheses for negatives e.g. (1.000)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    # remove dots used as thousand separator and replace commas if decimal comma
    # heuristic: if both '.' and ',' exist, assume '.' thousands, ',' decimal -> remove dots, replace ',' with '.'
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # if only dots and they look like thousands sep (more than 3 digits), remove dots
        # else replace commas with dot
        if "." in s and re.search(r"\.\d{1,2}$", s) is None:
            s = s.replace(".", "")
        s = s.replace(",", ".")
    # remove any remaining non-number characters
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s) if s not in ("", "-", ".") else 0.0
    except:
        return 0.0

def find_column_by_keywords(df, keywords):
    """Cari nama kolom yang cocok berdasarkan keywords (list). Kembalikan first match or None."""
    cols = df.columns.astype(str).tolist()
    for k in keywords:
        for c in cols:
            if k.lower() in c.lower():
                return c
    return None

# ----------------------------
# Classification (auto-categorize akun)
# ----------------------------
def classify_account(name):
    if not isinstance(name, str):
        name = str(name)
    n = name.lower()
    # PAD (pendapatan asli daerah)
    if "pad" in n or "pajak" in n or "retribusi" in n or "lain-lain pad" in n or "hasil pengelolaan" in n:
        return "PAD"
    # TRANSFER / TKDD
    if "tkdd" in n or "transfer" in n or "dau" in n or "dak" in n or "dbh" in n:
        return "TRANSFER"
    # PENDAPATAN DAERAH (umbrella)
    if "pendapatan daerah" in n or n.strip().startswith("pendapatan"):
        return "PENDAPATAN"
    # BELANJA OPERASI
    if "belanja pegawai" in n or "belanja barang" in n or "belanja jasa" in n or "belanja barang dan jasa" in n:
        return "BELANJA_OPERASI"
    # BELANJA MODAL
    if "belanja modal" in n or "modal" in n and "belanja" in n:
        return "BELANJA_MODAL"
    # BELANJA LAINNYA
    if "hibah" in n or "bantuan" in n or "subsidi" in n:
        return "BELANJA_LAINNYA"
    # BELANJA TIDAK TERDUGA
    if "tidak terduga" in n:
        return "BELANJA_TIDAK_TERDUGA"
    # PEMBIAYAAN
    if "pembiayaan" in n:
        return "PEMBIAYAAN"
    # fallback
    return "LAINNYA"

# ----------------------------
# Streamlit UI
# ----------------------------
st.sidebar.header("Kontrol")
st.sidebar.info("Gunakan template jika upload file dari portal APBD yang struktur beda.")
st.sidebar.markdown("*Tips:* jika upload gagal, download template lalu salin/format kolom sesuai.")

page = st.sidebar.selectbox("Menu", ["Home","Upload & Analyze","Download Template","Help"])

if page == "Home":
    st.header("Cara singkat pakai aplikasi")
    st.write("""
    1. Jika data mentah dari portal APBD — cukup upload file .xlsx di menu Upload & Analyze.  
    2. Aplikasi akan mencoba mendeteksi kolom Anggaran & Realisasi dan melakukan cleaning otomatis.  
    3. Jika format sangat berbeda, gunakan menu Download Template untuk membuat file contoh dan pindahkan data.  
    """)
    st.markdown("*Contoh file yang bisa diupload:* file Excel yang hanya berisi kolom: Akun dan angka Anggaran/Realisasi, format angka bebas (mengandung Rp, titik, koma).")
    st.markdown("---")

elif page == "Download Template":
    st.header("Download Template APBD (.xlsx)")
    buf = make_template_excel()
    st.download_button("Download template_apbd.xlsx", data=buf, file_name="template_apbd.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("Template berisi contoh header: " + ", ".join(TEMPLATE_COLUMNS))

elif page == "Help":
    st.header("Help & Troubleshoot")
    st.markdown("""
    - Pastikan file adalah .xlsx.  
    - Jika muncul error Missing optional dependency 'openpyxl' saat deploy, tambahkan openpyxl ke requirements.txt.  
    - Jika kolom tidak terdeteksi, gunakan nama kolom yang mengandung kata 'Anggaran' atau 'Realisasi' atau 'Realisasi' (bisa bahasa Indonesia/Inggris).  
    - Jika upload membingungkan, unggah dulu sample kecil (5-20 baris) untuk uji.
    """)
    st.markdown("---")

elif page == "Upload & Analyze":
    st.header("Upload file APBD (.xlsx) — app akan coba normalisasi otomatis")
    uploaded = st.file_uploader("Pilih file .xlsx (mentah dari portal APBD atau file lain)", type=["xlsx"])
    if uploaded is None:
        st.info("Silakan unggah file Excel untuk dianalisis. Kalau belum punya file, download template di menu Download Template.")
        st.stop()

    # baca file
    try:
        raw = pd.read_excel(uploaded, sheet_name=0, dtype=str)
    except Exception as e:
        st.error("Gagal membaca file Excel: " + str(e))
        st.stop()

    st.subheader("Preview (5 baris dari file mentah)")
    st.dataframe(raw.head(), use_container_width=True)

    # --- DETEKSI KOLom ANGGARAN/REALISASI/AKUN ---
    # cari kolom akun
    akun_col = find_column_by_keywords(raw, ["akun","nama akun","rekening","uraian","keterangan","akun "]) or raw.columns[0]
    anggaran_col = find_column_by_keywords(raw, ["anggaran","pagu","nilai anggaran","nilai","budget","anggaran (rp)"])
    realisasi_col = find_column_by_keywords(raw, ["realisasi","realisasi (rp)","realisasi (%)","realisasi anggaran","realisasi (rp)","realisasi"])
    persen_col = find_column_by_keywords(raw, ["persentase","persen","%"])

    st.markdown(f"*Deteksi kolom* → Akun: {akun_col}, Anggaran: {anggaran_col}, Realisasi: {realisasi_col}, Persen: {persen_col}")

    # jika anggaran atau realisasi tidak terdeteksi, coba heuristik: jika ada kolom bertipe numeric (string numeric) pilih salah satu
    if anggaran_col is None or realisasi_col is None:
        # cari kolom yang is_numeric
        numeric_candidates = []
        for c in raw.columns:
            sample = raw[c].dropna().astype(str).head(10).tolist()
            numeric_like = all(re.sub(r'[^\d\.\,\-\(\)]','',s).strip() != "" for s in sample) if sample else False
            if numeric_like:
                numeric_candidates.append(c)
        # assign
        if anggaran_col is None and len(numeric_candidates) >= 1:
            anggaran_col = numeric_candidates[0]
        if realisasi_col is None and len(numeric_candidates) >= 2:
            realisasi_col = numeric_candidates[1] if numeric_candidates[1] != anggaran_col else numeric_candidates[0]

    # jika tetap None -> inform user
    if anggaran_col is None or realisasi_col is None:
        st.error("Tidak dapat mendeteksi kolom Anggaran/Realisasi. Pastikan file berisi kolom angka atau gunakan template.")
        st.stop()

    # buat salinan bersih
    df = raw[[akun_col, anggaran_col, realisasi_col]].copy()
    df.columns = ["Akun","Anggaran","Realisasi"]
    # remove whitespace
    df["Akun"] = df["Akun"].astype(str).str.strip()

    # parse angka
    df["Anggaran_num"] = df["Anggaran"].apply(parse_number)
    df["Realisasi_num"] = df["Realisasi"].apply(parse_number)

    # compute percent if absent
    df["Persentase_calc"] = np.where(df["Anggaran_num"] != 0, df["Realisasi_num"] / df["Anggaran_num"] * 100, 0)

    # classify account
    df["Kategori"] = df["Akun"].apply(classify_account)

    st.subheader("Data setelah cleaning & kategorisasi (contoh 50 baris)")
    st.dataframe(df.head(50), use_container_width=True)

    # aggregate by Kategori
    agg = df.groupby("Kategori").agg({
        "Anggaran_num":"sum",
        "Realisasi_num":"sum"
    }).reset_index().rename(columns={"Anggaran_num":"Anggaran","Realisasi_num":"Realisasi"})

    st.subheader("Aggregasi per Kategori")
    st.dataframe(agg, use_container_width=True)

    # TOTALS needed for rasio
    PAD_total = agg.loc[agg["Kategori"] == "PAD", "Realisasi"].sum() if "PAD" in agg["Kategori"].values else 0.0
    TRANSFER_total = agg.loc[agg["Kategori"] == "TRANSFER", "Realisasi"].sum() if "TRANSFER" in agg["Kategori"].values else 0.0
    BELANJA_OPERASI_total = agg.loc[agg["Kategori"] == "BELANJA_OPERASI", "Realisasi"].sum() if "BELANJA_OPERASI" in agg["Kategori"].values else 0.0
    BELANJA_MODAL_total = agg.loc[agg["Kategori"] == "BELANJA_MODAL", "Realisasi"].sum() if "BELANJA_MODAL" in agg["Kategori"].values else 0.0
    TOTAL_BELANJA = agg[agg["Kategori"].str.contains("BELANJA")]["Realisasi"].sum()

    # rasio calculations (percent)
    def safe_div(a,b):
        return (a/b*100) if (b and b!=0) else 0.0

    rasio_kemandirian = safe_div(PAD_total, TRANSFER_total)
    rasio_belanja_operasi = safe_div(BELANJA_OPERASI_total, TOTAL_BELANJA)
    rasio_belanja_modal = safe_div(BELANJA_MODAL_total, TOTAL_BELANJA)

    st.subheader("Hasil Rasio (persentase)")
    st.metric("Rasio Kemandirian (PAD / Transfer) %", f"{rasio_kemandirian:.2f}")
    st.metric("Rasio Belanja Operasi %", f"{rasio_belanja_operasi:.2f}")
    st.metric("Rasio Belanja Modal %", f"{rasio_belanja_modal:.2f}")

    # visual: pie composition belanja
    comp = pd.DataFrame({
        "Kategori":["Belanja Operasi","Belanja Modal","Belanja Lainnya"],
        "Nilai":[BELANJA_OPERASI_total, BELANJA_MODAL_total, TOTAL_BELANJA - BELANJA_OPERASI_total - BELANJA_MODAL_total]
    })
    figp = px.pie(comp, names="Kategori", values="Nilai", title="Komposisi Belanja (Realisasi)")
    st.plotly_chart(figp, use_container_width=True)

    # trend if Tahun present in raw
    tahun_col = find_column_by_keywords(raw, ["tahun","periode"])
    if tahun_col:
        try:
            raw[tahun_col] = raw[tahun_col].astype(str)
            pivot = raw.groupby(tahun_col).apply(lambda g: parse_number(g[realisasi_col]).sum()).reset_index()
            pivot.columns = [tahun_col, "Total_Realisasi"]
            figt = px.line(pivot, x=tahun_col, y="Total_Realisasi", title="Tren Realisasi per Tahun")
            st.plotly_chart(figt, use_container_width=True)
        except Exception:
            pass

    # export cleaned aggregated data
    st.subheader("Download hasil cleaning & agregasi")
    download_df = agg.copy()
    csv = download_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV (aggregated)", data=csv, file_name="apbd_aggregated.csv", mime="text/csv")

    # optional: Groq explanation for top categories or items
    st.subheader("Interpretasi AI (opsional) — Groq")
    groq_key = st.text_input("Masukkan Groq API Key (opsional)", type="password")
    if groq_key:
        # prepare short prompt
        top_k = agg.sort_values("Realisasi", ascending=False).head(5)
        prompt = "Berikan analisis singkat mengenai kategori-kategori berikut berdasarkan realisasi (angka dalam rupiah):\n"
        for _, r in top_k.iterrows():
            prompt += f"- {r['Kategori']}: Realisasi = {r['Realisasi']:.0f}\n"
        prompt += "\nSebutkan potensi risiko dan rekomendasi sederhana."
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={"model":"mixtral-8x7b-32768", "messages":[{"role":"user","content":prompt}]},
                timeout=15
            )
            ai = r.json()["choices"][0]["message"]["content"]
            st.markdown("*Analisis AI:*")
            st.write(ai)
        except Exception as e:
            st.error("Gagal panggil Groq: " + str(e))

    st.info("Selesai. Jika tampilan data tidak sesuai, coba bersihkan header di Excel atau gunakan Template.")
