import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px

# Konfigurasi halaman Streamlit
st.set_page_config(
    page_title="Bike Store DWH Dashboard",
    page_icon="🚲",
    layout="wide"
)

# Fungsi untuk koneksi dan mengambil data dari MySQL DWH
@st.cache_resource
def init_connection():
    return mysql.connector.connect(
        host="localhost",       # Sesuaikan host database kamu
        user="root",            # Sesuaikan username database kamu
        password="",            # Sesuaikan password database kamu
        database="dwh_bike_store" # Nama database Data Warehouse kamu
    )

def run_query(query):
    conn = init_connection()
    try:
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        # Jika koneksi terputus, coba reconnect sekali
        conn.reconnect(attempts=3, delay=2)
        df = pd.read_sql(query, conn)
        return df

# Judul Dashboard
st.title("🚲 Executive Dashboard - Bike Store Data Warehouse")
st.markdown("Dashboard interaktif untuk memantau performa penjualan berdasarkan *Star Schema* DWH.")

# --- SIDEBAR: FILTER ---
st.sidebar.header("Filter Data")

# Mengambil daftar cabang untuk filter
df_cabang = run_query("SELECT DISTINCT id_cabang FROM dim_cabang")
selected_cabang = st.sidebar.selectbox("Pilih ID Cabang", options=["Semua Cabang"] + list(df_cabang['id_cabang']))

# --- QUERY UTAMA ---
# Mengambil data dari fact_sales yang di-join dengan dimensi terkait
query_fact = """
    SELECT 
        f.total_penjualan, 
        f.total_laba, 
        f.total_qty, 
        c.nama_cabang, 
        p.nama_produk, 
        p.kategori,
        w.bulan,
        w.tahun
    FROM fakta_penjualan_bulanan f
    JOIN dim_cabang c ON f.id_cabang = c.id_cabang
    JOIN dim_product p ON f.id_produk = p.id_produk
    JOIN dim_waktu w ON f.id_waktu = w.id_waktu
"""

if selected_cabang != "Semua Cabang":
    query_fact += f" WHERE f.id_cabang = {selected_cabang}"

df_sales = run_query(query_fact)

if df_sales.empty:
    st.warning("Belum ada data pada tabel fakta atau koneksi database kosong.")
else:
    # --- 1. KEY PERFORMANCE INDICATORS (KPI) ---
    total_revenue = df_sales['total_penjualan'].sum()
    total_profit = df_sales['total_laba'].sum()
    total_qty = df_sales['total_qty'].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pendapatan (Omzet)", f"Rp {total_revenue:,.0f}")
    col2.metric("Total Laba Bersih", f"Rp {total_profit:,.0f}")
    col3.metric("Total Unit Terjual", f"{total_qty:,} pcs")

    st.markdown("---")

    # --- 2. GRAFIK VISUALISASI ---
    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.subheader("📊 Performa Penjualan per Cabang")
        df_cabang_group = df_sales.groupby('nama_cabang')['total_penjualan'].sum().reset_index()
        fig_cabang = px.bar(
            df_cabang_group, 
            x='nama_cabang', 
            y='total_penjualan', 
            text_auto='.2s',
            color='nama_cabang',
            labels={'nama_cabang': 'Cabang', 'total_penjualan': 'Total Omzet (Rp)'}
        )
        st.plotly_chart(fig_cabang, use_container_width=True)

    with row1_col2:
        st.subheader("🏆 Top 5 Produk Terlaris")
        df_produk_group = df_sales.groupby('nama_produk')['total_qty'].sum().reset_index()
        df_produk_group = df_produk_group.sort_values(by='total_qty', ascending=False).head(5)
        fig_produk = px.bar(
            df_produk_group, 
            x='total_qty', 
            y='nama_produk', 
            orientation='h',
            text_auto=True,
            labels={'total_qty': 'Total Terjual (Unit)', 'nama_produk': 'Nama Produk'}
        )
        fig_produk.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_produk, use_container_width=True)

    # Grafik Tren Waktu (Bulanan)
    st.subheader("📈 Tren Total Penjualan Bulanan")
    if 'bulan' in df_sales.columns and 'tahun' in df_sales.columns:
        df_time_group = df_sales.groupby(['tahun', 'bulan'])['total_penjualan'].sum().reset_index()
        df_time_group['periode'] = df_time_group['tahun'].astype(str) + "-" + df_time_group['bulan'].astype(str).str.zfill(2)
        df_time_group = df_time_group.sort_values('periode')
        
        fig_time = px.line(
            df_time_group, 
            x='periode', 
            y='total_penjualan', 
            markers=True,
            labels={'periode': 'Periode (Tahun-Bulan)', 'total_penjualan': 'Total Pendapatan (Rp)'}
        )
        st.plotly_chart(fig_time, use_container_width=True)

    # --- 3. TABEL DETAIL DATA ---
    with st.expander("Lihat Detail Tabel Data Warehouse"):
        st.dataframe(df_sales, use_container_width=True)