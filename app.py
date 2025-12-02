# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import plotly.express as px

st.set_page_config(layout="wide", page_title="APBD Analyzer — Robust & Interpretasi Offline")
st.title("📊 APBD Analyzer — Hitung Rasio & Interpretasi (Offline Rule-Based)")

# -----------------------------
# Helper: parsing angka robust
# -----------------------------
def parse_number(x):
    """Convert various string representations of numbers into float.
       Handles 'Rp', '.', ',', parentheses for negatives, spaces.
       Examples:
         '3.102.745.428.958' -> 3102745428958.0
         'Rp 1.234.567,89' -> 1234567.89
         '(1.000.000)' -> -1000000.0
    """
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip()
    if s == "":
        return 0.0
    # parentheses -> negative
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    # remove currency markers and letters
    s = re.sub(r"[^\d\.,\-]", "", s)
    # Heuristic:
    # if both '.' and ',' present -> assume '.' thousands, ',' decimal -> remove dots, replace comma with dot
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # if only dots and dots are used as thousand sep (no decimal part)
        # detect if trailing dot-digit pattern (like .12)
        if "." in s and not re.search(r"\.\d{1,3}$", s):
            # treat dots as thousand separators -> remove all dots
            s = s.replace(".", "")
        # replace comma with dot if any (handle decimal comma)
        s = s.replace(",", ".")
    # final cleanup: remove any non-digit except dot and minus
    s = re.sub(r"[^\d\.\-]", "", s)
    if s in ("", "-", "."):
        return 0.0
    try:
        return float(s)
    except:
        return 0.0

# -----------------------------
# Helper: find column by keywords
# -----------------------------
def find_column_by_keywords(df, keywords):
    cols = df.columns.astype(str).tolist()
    for k in keywords:
        for c in cols:
            if k.lower() in c.lower():
                return c
    return None

# -----------------------------
# Helper: auto-category classification
# -----------------------------
def classify_account(name):
    if not isinstance(name, str):
        name = str(name)
    n = name.lower()
    # PAD-related
    if "pad" in n or "pajak" in n or "retribusi" in n or "hasil pengelolaan" in n or "lain-lain pad" in n:
        return "PAD"
    # TRANSFER
    if "tkdd" in n or "transfer" in n or "dau" in n or "dak" in n or "dbh" in n:
        return "TRANSFER"
    # PENDAPATAN umbrella
    if n.strip().startswith("pendapatan") or "pendapatan daerah" in n:
        return "PENDAPATAN"
    # BELANJA OPERASI
    if "belanja pegawai" in n or "belanja barang" in n or "belanja jasa" in n or "belanja barang dan jasa" in n:
        return "BELANJA_OPERASI"
    # BELANJA MODAL
    if "belanja modal" in n or ("modal" in n and "belanja" in n):
        return "BELANJA_MODAL"
    # BELANJA LAINNYA
    if "hibah" in n or "bantu" in n or "subsidi" in n or "bagi hasil" in n:
        return "BELANJA_LAINNYA"
    # BELANJA TIDAK TERDUGA
    if "tidak terduga" in n:
        return "BELANJA_TIDAK_TERDUGA"
    # PEMBIAYAAN
    if "pembiayaan" in n or "penerimaan pembiayaan" in n or "sisa lebih" in n:
        return "PEMBIAYAAN"
    return "LAINNYA"

# -----------------------------
# All ratios definitions
# -----------------------------
def safe_pct(numer, denom):
    try:
        if denom == 0 or denom is None:
            return 0.0
        return (numer / denom) * 100
    except:
        return 0.0

def compute_all_ratios(totals_prev, totals):
    """totals and totals_prev are dicts with keys like PAD, TRANSFER, BELANJA_OPERASI, BELANJA_MODAL, TOTAL_BELANJA, PENDAPATAN"""
    r = {}
    # pendapatan totals
    PAD = totals.get("PAD", 0.0)
    TRANSFER = totals.get("TRANSFER", 0.0)
    PENDAPATAN = totals.get("PENDAPATAN", 0.0)
    TOTAL_BELANJA = totals.get("TOTAL_BELANJA", 0.0)
    BEL_OP = totals.get("BELANJA_OPERASI", 0.0)
    BEL_MOD = totals.get("BELANJA_MODAL", 0.0)
    ANG_BELANJA = totals.get("ANGGARAN_BELANJA", 0.0)
    # core ratios
    r["Rasio Kemandirian (%)"] = safe_pct(PAD, TRANSFER)
    r["Rasio Ketergantungan Transfer (%)"] = safe_pct(TRANSFER, PENDAPATAN)
    r["Rasio Efektivitas PAD (%)"] = safe_pct(totals.get("Realisasi_PAD", 0.0), totals.get("Anggaran_PAD", 0.0))
    r["Rasio Efisiensi Belanja (%)"] = safe_pct(totals.get("Realisasi_Belanja", 0.0), ANG_BELANJA)
    r["Rasio Belanja Operasi (%)"] = safe_pct(BEL_OP, TOTAL_BELANJA)
    r["Rasio Belanja Modal (%)"] = safe_pct(BEL_MOD, TOTAL_BELANJA)
    r["Rasio Belanja Pegawai terhadap Belanja (%)"] = safe_pct(totals.get("Belanja_Pegawai",0.0), TOTAL_BELANJA)
    r["Rasio Belanja Barang/Jasa terhadap Belanja (%)"] = safe_pct(totals.get("Belanja_BarangJasa",0.0), TOTAL_BELANJA)
    # growth rates if previous totals supplied
    if totals_prev:
        r["Pertumbuhan Pendapatan (%)"] = safe_pct(totals.get("PENDAPATAN",0.0) - totals_prev.get("PENDAPATAN",0.0), totals_prev.get("PENDAPATAN",1.0))
        r["Pertumbuhan Belanja (%)"] = safe_pct(TOTAL_BELANJA - totals_prev.get("TOTAL_BELANJA",0.0), totals_prev.get("TOTAL_BELANJA",1.0))
        # SILPA ratio if available
        r["Pertumbuhan PAD (%)"] = safe_pct(totals.get("PAD",0.0) - totals_prev.get("PAD",0.0), totals_prev.get("PAD",1.0))
    else:
        r["Pertumbuhan Pendapatan (%)"] = None
        r["Pertumbuhan Belanja (%)"] = None
        r["Pertumbuhan PAD (%)"] = None
    # Pembiayaan & SILPA
    r["SILPA (Receipts)"] = totals.get("SILPA", 0.0)
    return r

# -----------------------------
# Rule-based interpretation engine
# -----------------------------
def interpret_ratios(ratios):
    lines = []
    # kemandirian
    k = ratios.get("Rasio Kemandirian (%)", 0.0)
    if k is None: k = 0.0
    if k < 10:
        lines.append(f"Rasio kemandirian sebesar {k:.2f}% menunjukkan sangat rendahnya kemampuan PAD; daerah sangat bergantung pada transfer pusat.")
    elif k < 20:
        lines.append(f"Rasio kemandirian sebesar {k:.2f}% tergolong rendah; perlu strategi peningkatan PAD (pajak, retribusi, sumber baru).")
    elif k < 50:
        lines.append(f"Rasio kemandirian {k:.2f}% tergolong sedang — ada kapasitas PAD tetapi masih perlu penguatan.")
    else:
        lines.append(f"Rasio kemandirian {k:.2f}% tergolong tinggi; daerah relatif mandiri.")

    # efektivitas
    ef = ratios.get("Rasio Efektivitas PAD (%)", 0.0)
    if ef is not None:
        if ef < 80:
            lines.append(f"Efektivitas PAD ({ef:.2f}%) rendah — realisasi PAD jauh di bawah target.")
        elif ef <= 100:
            lines.append(f"Efektivitas PAD ({ef:.2f}%) baik — realisasi mendekati atau sesuai target.")
        else:
            lines.append(f"Efektivitas PAD ({ef:.2f}%) tinggi — realisasi melebihi target, perlu verifikasi apakah target realistis.")

    # efisiensi belanja
    efi = ratios.get("Rasio Efisiensi Belanja (%)", 0.0)
    if efi is not None:
        if efi > 100:
            lines.append(f"Rasio efisiensi belanja ({efi:.2f}%) menunjukkan belanja melebihi anggaran — potensi pemborosan atau realokasi anggaran.")
        elif efi >= 90:
            lines.append(f"Rasio efisiensi belanja ({efi:.2f}%) cukup baik, serapan wajar terhadap anggaran.")
        else:
            lines.append(f"Rasio efisiensi belanja ({efi:.2f}%) rendah — serapan belanja rendah terhadap anggaran.")

    # belanja komposisi
    bo = ratios.get("Rasio Belanja Operasi (%)", 0.0)
    bm = ratios.get("Rasio Belanja Modal (%)", 0.0)
    lines.append(f"Komposisi belanja: Operasi {bo:.2f}%, Modal {bm:.2f}% — ideal tergantung prioritas; belanja modal rendah dapat berdampak pada investasi infrastruktur.")

    # pertumbuhan
    pg = ratios.get("Pertumbuhan Pendapatan (%)")
    if pg is not None:
        lines.append(f"Pertumbuhan pendapatan tahunan: {pg:.2f}% (jika tersedia data tahun sebelumnya).")

    # pembiayaan / SILPA
    silpa = ratios.get("SILPA (Receipts)")
    if silpa and silpa != 0:
        lines.append(f"Terdapat SILPA sebesar {silpa:,.0f} — perlu analisis alokasi dan penyebab (serapan, penyusunan anggaran).")

    return "\n\n".join(lines)

# -----------------------------
# UI: Upload & Process
# -----------------------------
st.sidebar.header("Kontrol")
st.sidebar.write("Pilih menu untuk upload dan analisis.")
menu = st.sidebar.radio("Menu", ["Upload & Analyze", "Download Template", "About"])

if menu == "Download Template":
    st.header("Download Template")
    sample_df = pd.DataFrame([["Pendapatan Daerah","3557491170098","3758774961806","105.66","2024"],
                              ["PAD","322846709929","561854145372","174.03","2024"]],
                             columns=["Akun","Anggaran","Realisasi","Persentase","Tahun"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sample_df.to_excel(writer, index=False, sheet_name="APBD")
    buf.seek(0)
    st.download_button("Download template_apbd.xlsx", data=buf, file_name="template_apbd.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.info("Template sederhana berformat: Akun | Anggaran | Realisasi | Persentase | Tahun")

elif menu == "About":
    st.header("About")
    st.markdown("""
    APBD Analyzer — versi robust.
    - Auto-clean angka (menghapus titik ribuan)
    - Auto-classify akun (PAD/Transfer/Belanja)
    - Menghitung banyak rasio penting untuk akuntansi publik
    - Interpretasi rule-based offline (tidak memerlukan API)
    """)

else:
    st.header("Upload & Analyze (format A: Akun | Anggaran | Realisasi | Persentase | Tahun optional)")
    uploaded = st.file_uploader("Unggah file .xlsx (mentah dari portal APBD atau file lain)", type=["xlsx"])
    if uploaded is None:
        st.info("Silakan upload file Excel dahulu atau download template.")
        st.stop()

    try:
        raw = pd.read_excel(uploaded, sheet_name=0, dtype=str)
    except Exception as e:
        st.error("Gagal membaca file Excel: " + str(e))
        st.stop()

    st.subheader("Preview (mentah)")
    st.dataframe(raw.head(10), use_container_width=True)

    # detect columns
    akun_col = find_column_by_keywords(raw, ["akun","rekening","uraian","keterangan","nama akun"]) or raw.columns[0]
    anggaran_col = find_column_by_keywords(raw, ["anggaran","pagu","nilai anggaran","nilai","budget"]) 
    realisasi_col = find_column_by_keywords(raw, ["realisasi","realisasi (rp)","realisasi anggaran","realisasi"])
    persen_col = find_column_by_keywords(raw, ["persentase","persen","%"])
    tahun_col = find_column_by_keywords(raw, ["tahun","periode"])

    st.markdown(f"Detected columns → Akun: {akun_col}, Anggaran: {anggaran_col}, Realisasi: {realisasi_col}, Tahun: {tahun_col}")

    if anggaran_col is None and realisasi_col is None:
        st.error("Tidak menemukan kolom Anggaran / Realisasi secara otomatis. Pastikan file memiliki kolom angka atau gunakan template.")
        st.stop()

    # if only one numeric col found, heuristics: map to Anggaran or Realisasi accordingly
    numeric_candidates = []
    for c in raw.columns:
        sample = raw[c].dropna().astype(str).head(10).tolist()
        numeric_like = all(re.sub(r'[^\d\.\,\-\(\)]','',s).strip() != "" for s in sample) if sample else False
        if numeric_like:
            numeric_candidates.append(c)
    if anggaran_col is None and len(numeric_candidates) >= 1:
        anggaran_col = numeric_candidates[0]
    if realisasi_col is None and len(numeric_candidates) >= 2:
        realisasi_col = numeric_candidates[1] if numeric_candidates[1] != anggaran_col else numeric_candidates[0]

    # build clean df
    df = raw.copy()
    df.rename(columns={akun_col:"Akun"}, inplace=True)
    if anggaran_col:
        df["Anggaran_raw"] = df[anggaran_col].astype(str)
        df["Anggaran"] = df["Anggaran_raw"].apply(parse_number)
    else:
        df["Anggaran"] = 0.0
    if realisasi_col:
        df["Realisasi_raw"] = df[realisasi_col].astype(str)
        df["Realisasi"] = df["Realisasi_raw"].apply(parse_number)
    else:
        df["Realisasi"] = 0.0
    # optional year
    if tahun_col:
        df["Tahun"] = df[tahun_col].astype(str)
    else:
        df["Tahun"] = None

    # categorize accounts
    df["Kategori"] = df["Akun"].apply(classify_account)

    st.subheader("Cleaned sample (first 50 rows)")
    st.dataframe(df[["Akun","Anggaran","Realisasi","Kategori","Tahun"]].head(50), use_container_width=True)

    # aggregate by category
    agg = df.groupby("Kategori").agg({
        "Anggaran":"sum",
        "Realisasi":"sum"
    }).reset_index().rename(columns={"Anggaran":"Anggaran_sum","Realisasi":"Realisasi_sum"})
    st.subheader("Aggregated by Kategori")
    st.dataframe(agg, use_container_width=True)

    # totals needed
    totals = {}
    totals["PAD"] = agg.loc[agg["Kategori"]=="PAD","Realisasi_sum"].sum() if "PAD" in agg["Kategori"].values else 0.0
    totals["TRANSFER"] = agg.loc[agg["Kategori"]=="TRANSFER","Realisasi_sum"].sum() if "TRANSFER" in agg["Kategori"].values else 0.0
    totals["PENDAPATAN"] = agg.loc[agg["Kategori"]=="PENDAPATAN","Realisasi_sum"].sum() if "PENDAPATAN" in agg["Kategori"].values else 0.0
    totals["BELANJA_OPERASI"] = agg.loc[agg["Kategori"]=="BELANJA_OPERASI","Realisasi_sum"].sum() if "BELANJA_OPERASI" in agg["Kategori"].values else 0.0
    totals["BELANJA_MODAL"] = agg.loc[agg["Kategori"]=="BELANJA_MODAL","Realisasi_sum"].sum() if "BELANJA_MODAL" in agg["Kategori"].values else 0.0
    totals["TOTAL_BELANJA"] = agg[agg["Kategori"].str.contains("BELANJA")]["Realisasi_sum"].sum() if any(agg["Kategori"].str.contains("BELANJA")) else 0.0
    # fallback for anggaran sums (if present in file)
    totals["ANGGARAN_BELANJA"] = agg.loc[agg["Kategori"].str.contains("BELANJA"),"Anggaran_sum"].sum() if "Anggaran_sum" in agg.columns else 0.0
    totals["Realisasi_Belanja"] = totals["TOTAL_BELANJA"]
    # optionally compute PAD anggaran/realisasi if present in raw by searching rows with category PAD
    totals["Anggaran_PAD"] = df.loc[df["Kategori"]=="PAD","Anggaran"].sum() if "PAD" in df["Kategori"].values else 0.0
    totals["Realisasi_PAD"] = totals["PAD"]

    # previous-year totals detection (if file contains multiple years)
    totals_prev = {}
    if df["Tahun"].notnull().any():
        # attempt to get previous year aggregation if multiple years present
        years = df["Tahun"].dropna().unique().tolist()
        if len(years) >= 2:
            years_sorted = sorted(years)
            prev_year = years_sorted[-2]
            curr_year = years_sorted[-1]
            df_prev = df[df["Tahun"]==prev_year]
            df_curr = df[df["Tahun"]==curr_year]
            # compute prev totals
            totals_prev["PENDAPATAN"] = df_prev.loc[df_prev["Kategori"].isin(["PAD","TRANSFER","PENDAPATAN"]),"Realisasi"].sum()
            totals_prev["TOTAL_BELANJA"] = df_prev.loc[df_prev["Kategori"].str.contains("BELANJA"),"Realisasi"].sum()
            totals_prev["PAD"] = df_prev.loc[df_prev["Kategori"]=="PAD","Realisasi"].sum()
        else:
            totals_prev = None
    else:
        totals_prev = None

    # compute ratios
    ratios = compute_all_ratios(totals_prev, totals)

    st.subheader("Rasio Lengkap")
    # show nicely
    for k,v in ratios.items():
        if v is None:
            st.write(f"- *{k}*: -")
        elif isinstance(v, (int,float)):
            # format percent-like keys
            if "Rasio" in k or "Pertumbuhan" in k:
                st.write(f"- *{k}*: {v:.2f}%")
            elif k == "SILPA (Receipts)":
                st.write(f"- *{k}*: {v:,.0f}")
            else:
                st.write(f"- *{k}*: {v}")

    # rule-based interpretation (offline)
    st.subheader("Interpretasi Otomatis (Rule-Based, Offline)")
    interpretation = interpret_ratios(ratios)
    st.write(interpretation)

    # visual composition
    st.subheader("Visual: Komposisi Belanja")
    comp_df = pd.DataFrame({
        "Kategori":["Belanja Operasi","Belanja Modal","Belanja Lainnya"],
        "Nilai":[totals["BELANJA_OPERASI"], totals["BELANJA_MODAL"], max(0, totals["TOTAL_BELANJA"] - totals["BELANJA_OPERASI"] - totals["BELANJA_MODAL"])]
    })
    fig = px.pie(comp_df, names="Kategori", values="Nilai", title="Komposisi Belanja (Realisasi)")
    st.plotly_chart(fig, use_container_width=True)

    # trend chart if Tahun present
    if df["Tahun"].notnull().any():
        try:
            pivot = df.groupby("Tahun").agg({"Realisasi":"sum"}).reset_index()
            figt = px.line(pivot, x="Tahun", y="Realisasi", title="Tren Realisasi per Tahun")
            st.plotly_chart(figt, use_container_width=True)
        except Exception:
            pass

    # download cleaned aggregated CSV
    st.subheader("Download Hasil (CSV)")
    out = agg.copy()
    out["Realisasi_sum"] = out["Realisasi_sum"].astype(float)
    csv = out.to_csv(index=False).encode("utf-8")
    st.download_button("Download aggregated CSV", data=csv, file_name="apbd_aggregated.csv", mime="text/csv")

    st.success("Analisis selesai. Jika hasil tidak sesuai, gunakan menu Download Template dan sesuaikan header Excel.")
