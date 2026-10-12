from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ PATH
BASE = Path(__file__).resolve().parent.parent
CSV_PATH = BASE / "1_Data_Sources" / "staging_dirty" / "order_transactions_dirty_1M.csv"
RAW_DIR = BASE / "1_Data_Sources" / "raw"
OUT_DIR = BASE / "4_Docs" / "data_profiling"
OUT_XLSX = OUT_DIR / "hasil_data_profiling_orders.xlsx"

DATE_COLS = ["order_date", "required_date", "shipped_date"]
# pola tanggal yang dikenali (angka diganti 9) -> format parsing
DATE_FORMATS = {
    "9999-99-99": "%Y-%m-%d",   # standar (ISO)
    "9999/99/99": "%Y/%m/%d",
    "99/99/9999": "%d/%m/%Y",
    "99-99-9999": "%d-%m-%Y",
}
STANDARD_PATTERN = "9999-99-99"


# ------------------------------------------------------------- HELPERS
def pct(n, total):
    return round(n / total * 100, 3) if total else 0.0


def date_pattern(s):
    """Ubah tiap digit jadi '9' agar pola format terlihat."""
    return s.str.replace(r"\d", "9", regex=True)


def parse_dates(s):
    """Parse kolom tanggal campur-format. Gagal parse -> NaT."""
    mask = date_pattern(s.astype("string"))
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for pat, fmt in DATE_FORMATS.items():
        idx = (mask == pat).fillna(False).to_numpy()
        if idx.any():
            out[idx] = pd.to_datetime(s[idx], format=fmt, errors="coerce")
    return out


# ----------------------------------------------------- 1. PROFIL KOLOM
def profile_columns(df):
    rows = []
    total = len(df)
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        vc = s.value_counts(dropna=True)
        r = {
            "kolom": c,
            "tipe_data": str(s.dtype),
            "jumlah_baris": total,
            "terisi": non_null,
            "kosong": total - non_null,
            "kosong_%": pct(total - non_null, total),
            "nilai_unik": int(s.nunique()),
            "unik_%": pct(s.nunique(), total),
            "nilai_terbanyak": vc.index[0] if len(vc) else None,
            "frekuensi_terbanyak": int(vc.iloc[0]) if len(vc) else None,
        }
        if pd.api.types.is_numeric_dtype(s):
            r.update(
                min=s.min(), max=s.max(), rata2=round(s.mean(), 3),
                median=s.median(), std=round(s.std(), 3),
            )
        else:
            L = s.dropna().astype(str).str.len()
            r.update(panjang_min=L.min(), panjang_maks=L.max())
        rows.append(r)
    return pd.DataFrame(rows)


# --------------------------------------------- 2. POLA FORMAT TANGGAL
def profile_date_patterns(df):
    rows = []
    total = len(df)
    for c in DATE_COLS:
        pat = date_pattern(df[c].astype("string")).fillna("(kosong)")
        for p, n in pat.value_counts().items():
            rows.append({
                "kolom": c, "pola_format": p, "jumlah": int(n),
                "persen_%": pct(n, total),
                "status": "Standar" if p == STANDARD_PATTERN
                else ("Kosong" if p == "(kosong)" else "Tidak konsisten"),
            })
    return pd.DataFrame(rows)


# ------------------------------------------------ 3. TEMUAN KUALITAS
def run_quality_checks(df):
    total = len(df)
    issues, masks = [], {}

    def add(dimensi, cek, kolom, mask, ket=""):
        mask = pd.Series(mask, index=df.index).fillna(False)
        n = int(mask.sum())
        issues.append({
            "dimensi": dimensi, "pengecekan": cek, "kolom": kolom,
            "jumlah_baris": n, "persen_%": pct(n, total), "keterangan": ket,
        })
        masks[cek] = mask

    od = parse_dates(df["order_date"])
    rd = parse_dates(df["required_date"])
    sd = parse_dates(df["shipped_date"])

    # --- Completeness
    for c in df.columns:
        add("Completeness", f"{c} kosong (NULL)", c, df[c].isna())
    add("Completeness", "shipped_date kosong padahal order_status=4 (selesai)",
        "shipped_date", df["shipped_date"].isna() & (df["order_status"] == 4),
        "NULL pada shipped_date wajar untuk order yang belum dikirim; "
        "yang janggal adalah order berstatus selesai tanpa tanggal kirim")

    # --- Consistency
    for c in DATE_COLS:
        pat = date_pattern(df[c].astype("string"))
        add("Consistency", f"{c} bukan format YYYY-MM-DD", c,
            pat.notna() & (pat != STANDARD_PATTERN))

    # --- Validity
    add("Validity", "quantity <= 0", "quantity", df["quantity"] <= 0)
    add("Validity", "list_price <= 0", "list_price", df["list_price"] <= 0)
    add("Validity", "discount < 0 atau > 1", "discount",
        (df["discount"] < 0) | (df["discount"] > 1),
        "diskon dalam bentuk pecahan, 1.0 = 100%")
    add("Validity", "order_status di luar 1-4", "order_status",
        ~df["order_status"].isin([1, 2, 3, 4]) & df["order_status"].notna())
    for c, parsed in zip(DATE_COLS, [od, rd, sd]):
        add("Validity", f"{c} tidak bisa di-parse sebagai tanggal", c,
            df[c].notna() & parsed.isna())

    # --- Outlier (IQR) untuk numerik utama
    for c in ["quantity", "list_price"]:
        q1, q3 = df[c].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        add("Validity", f"{c} outlier (IQR)", c, (df[c] < lo) | (df[c] > hi),
            f"batas wajar {lo:.2f} s/d {hi:.2f}")

    # --- Accuracy / aturan bisnis lintas kolom
    add("Accuracy", "shipped_date < order_date", "shipped_date/order_date",
        sd < od, "barang tidak mungkin dikirim sebelum dipesan")
    add("Accuracy", "required_date < order_date", "required_date/order_date",
        rd < od)
    add("Accuracy", "shipped_date bertahun 2000", "shipped_date",
        sd.dt.year == 2000, "data order hanya tahun 2016-2018")

    # --- Uniqueness
    add("Uniqueness", "baris duplikat persis (semua kolom)", "(semua kolom)",
        df.duplicated(keep="first"),
        "dihitung sebagai kemunculan ke-2 dst.")
    add("Uniqueness", "duplikat kunci (order_id, item_id)",
        "order_id+item_id", df.duplicated(["order_id", "item_id"], keep="first"),
        "kombinasi ini seharusnya unik di tabel order_items")

    return pd.DataFrame(issues), masks


# ---------------------------------------------------- 4. DUPLIKASI
def profile_duplicates(df):
    total = len(df)
    full = int(df.duplicated(keep="first").sum())
    key = int(df.duplicated(["order_id", "item_id"], keep="first").sum())
    uniq_full = len(df.drop_duplicates())
    uniq_key = len(df.drop_duplicates(["order_id", "item_id"]))
    return pd.DataFrame([
        {"metrik": "Total baris", "nilai": total},
        {"metrik": "Baris unik (semua kolom)", "nilai": uniq_full},
        {"metrik": "Duplikat persis (kemunculan ke-2 dst)", "nilai": full},
        {"metrik": "Persentase duplikat persis (%)", "nilai": pct(full, total)},
        {"metrik": "Kombinasi unik (order_id, item_id)", "nilai": uniq_key},
        {"metrik": "Duplikat kunci (order_id, item_id)", "nilai": key},
        {"metrik": "Persentase duplikat kunci (%)", "nilai": pct(key, total)},
    ])


# ------------------------------------------------ 5. DISTRIBUSI NILAI
def value_distribution(df):
    rows = []
    total = len(df)
    for c in ["order_status", "store_id", "staff_id", "discount", "quantity"]:
        for v, n in df[c].value_counts(dropna=False).head(15).items():
            rows.append({"kolom": c, "nilai": v, "jumlah": int(n),
                         "persen_%": pct(n, total)})
    return pd.DataFrame(rows)


# ------------------------------------------ 6. REFERENTIAL INTEGRITY
def check_referential(df):
    rows = []
    for fname, col, key in [("customers.csv", "customer_id", "customer_id"),
                            ("products.csv", "product_id", "product_id")]:
        f = RAW_DIR / fname
        if not f.exists():
            rows.append({"relasi": f"{col} -> {fname}", "status": "dilewati (file raw tidak ditemukan)",
                         "baris_orphan": None, "persen_%": None})
            continue
        ref = pd.read_csv(f, usecols=[key])[key]
        orphan = df[col].notna() & ~df[col].isin(ref)
        rows.append({"relasi": f"{col} -> {fname}", "status": "dicek",
                     "baris_orphan": int(orphan.sum()),
                     "persen_%": pct(orphan.sum(), len(df))})
    return pd.DataFrame(rows)


# ------------------------------------------------ 7. CONTOH ANOMALI
def sample_anomalies(df, issues, masks, n=5):
    parts = []
    for _, r in issues.iterrows():
        if r["jumlah_baris"] == 0:
            continue
        m = masks[r["pengecekan"]]
        s = df[m].head(n).copy()
        s.insert(0, "pengecekan", r["pengecekan"])
        parts.append(s)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ----------------------------------------------------------------- MAIN
def main():
    if not CSV_PATH.exists():
        raise SystemExit(f"File tidak ditemukan: {CSV_PATH}")
    print(f"Membaca {CSV_PATH.name} ...")
    df = pd.read_csv(CSV_PATH, dtype={c: "string" for c in DATE_COLS})
    print(f"{len(df):,} baris, {df.shape[1]} kolom. Mulai profiling...")

    summary = pd.DataFrame([
        {"item": "Nama file", "nilai": CSV_PATH.name},
        {"item": "Ukuran file (MB)", "nilai": round(CSV_PATH.stat().st_size / 1e6, 2)},
        {"item": "Jumlah baris", "nilai": len(df)},
        {"item": "Jumlah kolom", "nilai": df.shape[1]},
        {"item": "Daftar kolom", "nilai": ", ".join(df.columns)},
    ])
    col_profile = profile_columns(df)
    date_patterns = profile_date_patterns(df)
    issues, masks = run_quality_checks(df)
    dups = profile_duplicates(df)
    dist = value_distribution(df)
    ref = check_referential(df)
    samples = sample_anomalies(df, issues, masks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="1_Ringkasan_Dataset", index=False)
        col_profile.to_excel(xw, sheet_name="2_Profil_Kolom", index=False)
        date_patterns.to_excel(xw, sheet_name="3_Pola_Format_Tanggal", index=False)
        issues.to_excel(xw, sheet_name="4_Temuan_Kualitas", index=False)
        dups.to_excel(xw, sheet_name="5_Duplikasi", index=False)
        dist.to_excel(xw, sheet_name="6_Distribusi_Nilai", index=False)
        ref.to_excel(xw, sheet_name="7_Referential_Integrity", index=False)
        samples.to_excel(xw, sheet_name="8_Contoh_Anomali", index=False)
        for ws in xw.book.worksheets:           # lebar kolom otomatis
            for col in ws.columns:
                w = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(w + 2, 60)

    print("\n=== TEMUAN KUALITAS DATA (yang ada isinya) ===")
    print(issues[issues["jumlah_baris"] > 0][
        ["dimensi", "pengecekan", "jumlah_baris", "persen_%"]].to_string(index=False))
    print(f"\nSelesai. Hasil disimpan di: {OUT_XLSX}")


if __name__ == "__main__":
    main()