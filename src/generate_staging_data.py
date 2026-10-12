import pandas as pd
import numpy as np
import random

def generate_dirty_dataset():
    print("Membaca dataset referensi asli...")
    orders = pd.read_csv('data/raw/orders.csv')
    order_items = pd.read_csv('data/raw/order_items.csv')
    
    # Menggabungkan order_items dan orders sebagai tabel fakta utama
    df_base = pd.merge(order_items, orders, on='order_id', how='left')
    
    # 1. DUPLIKASI DATA HINGGA 1 JUTA BARIS
    print("Menduplikasi data menjadi 1.000.000 baris dengan random sampling...")
    n_rows = 1_000_000
    df = df_base.sample(n=n_rows, replace=True, random_state=42).reset_index(drop=True)
    
    print("Menginjeksikan anomali untuk praktik data profiling...")
    
    # A. Completeness (Data Kosong)
    df.loc[df.sample(frac=0.05, random_state=1).index, 'customer_id'] = np.nan
    df.loc[df.sample(frac=0.02, random_state=2).index, 'shipped_date'] = np.nan

    # B. Consistency (Inkonsistensi Format Tanggal)
    def mess_up_date(date_str):
        if pd.isna(date_str): return date_str
        try:
            d = pd.to_datetime(date_str)
            choices = [d.strftime('%d/%m/%Y'), d.strftime('%Y/%m/%d'), d.strftime('%d-%m-%Y')]
            return random.choice(choices)
        except:
            return date_str

    inconsistent_idx = df.sample(frac=0.05, random_state=3).index
    df.loc[inconsistent_idx, 'order_date'] = df.loc[inconsistent_idx, 'order_date'].apply(mess_up_date)

    # C. Validity (Data Tidak Valid / Outliers)
    df.loc[df.sample(frac=0.01, random_state=4).index, 'quantity'] = -10
    df.loc[df.sample(frac=0.005, random_state=5).index, 'discount'] = 1.5  # Diskon 150% (tidak valid)
    df.loc[df.sample(frac=0.005, random_state=6).index, 'list_price'] = 0  # Harga 0 (gratis tanpa alasan)

    # D. Accuracy (Kesalahan Logika Data)
    # Membuat waktu pengiriman terjadi jauh sebelum waktu pesanan (tahun 2000)
    mismatch_idx = df.sample(frac=0.02, random_state=7).index
    df.loc[mismatch_idx, 'shipped_date'] = '2000-01-01'

    # E. Uniqueness (Data Ganda)
    # Menambahkan 5.000 duplikat baris identik ke dalam dataset
    print("Menambahkan baris duplikat untuk mengecek uniqueness...")
    duplicates = df.sample(n=5000, random_state=8)
    df = pd.concat([df, duplicates], ignore_index=True)

    # Mengacak urutan baris agar anomali dan duplikat tersebar alami
    df = df.sample(frac=1, random_state=9).reset_index(drop=True)
    
    return df

# Eksekusi fungsi
df_dirty = generate_dirty_dataset()
print(f"Proses selesai! Total dataset saat ini: {len(df_dirty)} baris.")

# Ekspor kembali ke file CSV
nama_file = 'order_transactions_dirty_1M.csv'
df_dirty.to_csv(nama_file, index=False)
print(f"Dataset kotor berhasil disimpan sebagai '{nama_file}'")