import sys, os
import pandas as pd

STG = sys.argv[1] if len(sys.argv) > 1 else "order_transactions_dirty_1M.csv"
OLTP = sys.argv[2] if len(sys.argv) > 2 else "."

def rd(name):  # semua dibaca sebagai string supaya format asli tidak berubah
    return pd.read_csv(os.path.join(OLTP, f"{name}.csv"), dtype=str, keep_default_na=False)

stg = pd.read_csv(STG, dtype=str, keep_default_na=False)
orders, items, prod, cust, staff, store, stock, brand, cat = (
    rd(n) for n in ["orders", "order_items", "products", "customers", "staffs", "stores", "stocks", "brands", "categories"])
n = len(stg)
rows = []

def add(level, objek, teknik, temuan, jumlah, total=None):
    t = total or n
    rows.append((level, objek, teknik, temuan, int(jumlah), f"{jumlah / t:.2%}"))

def tgl(s):  # parse 4 format tanggal yang ditemukan di staging
    out = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    for f in ("%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        m = out.isna() & (s != "")
        out[m] = pd.to_datetime(s[m], format=f, errors="coerce")
    return out

# ============ LEVEL 1: DATA ELEMENT (staging) ============
for c in stg.columns:
    k = (stg[c].str.strip() == "").sum()
    if k:
        add("1-Element", c, "Kelengkapan", "nilai kosong", k)
add("1-Element", "customer_id", "Tipe data", "tersimpan desimal ('218.0'), seharusnya INT", stg.customer_id.str.endswith(".0").sum())
add("1-Element", "order_date", "Pola", "format bukan YYYY-MM-DD (dd/mm/yyyy, yyyy/mm/dd, dd-mm-yyyy)", (~stg.order_date.str.match(r"^\d{4}-\d{2}-\d{2}$")).sum())

# domain nilai valid diambil dari OLTP, bukan ditebak
dom_qty = set(items.quantity); dom_disc = set(items.discount); dom_status = set(orders.order_status)
add("1-Element", "quantity", "Domain (vs order_items)", f"nilai di luar domain OLTP {sorted(dom_qty)}", (~stg.quantity.isin(dom_qty)).sum())
add("1-Element", "discount", "Domain (vs order_items)", f"nilai di luar domain OLTP {sorted(dom_disc)}", (~stg.discount.isin(dom_disc)).sum())
add("1-Element", "order_status", "Domain (vs orders)", f"nilai di luar domain OLTP {sorted(dom_status)}", (~stg.order_status.isin(dom_status)).sum())
add("1-Element", "list_price", "Statistik", "bernilai 0 (harusnya > 0)", (pd.to_numeric(stg.list_price) <= 0).sum())

# ============ LEVEL 2: DATA RECORD (staging vs OLTP) ============
od, rq, sh = tgl(stg.order_date), tgl(stg.required_date), tgl(stg.shipped_date)
hdr = orders.set_index("order_id")
sentinel = sh == pd.Timestamp("2000-01-01")
add("2-Record", "shipped_date", "Dependency (tgl)", "tanggal kirim < tanggal pesan", (sh < od).sum())
add("2-Record", "shipped_date", "Sentinel value", "berisi 2000-01-01 (nilai default/dummy)", sentinel.sum())
add("2-Record", "required_date", "Dependency (tgl)", "tanggal dibutuhkan < tanggal pesan", (rq < od).sum())
add("2-Record", "order_status+shipped_date", "Dependency", "status 4 (selesai) tapi shipped_date kosong", ((stg.order_status == "4") & (stg.shipped_date == "")).sum())
add("2-Record", "order_status+shipped_date", "Dependency", "status 1-3 tapi shipped_date terisi", ((stg.order_status != "4") & (stg.shipped_date != "")).sum())

# harga harus sama dengan master produk
harga_master = stg.product_id.map(prod.set_index("product_id").list_price)
add("2-Record", "product_id -> list_price", "Dependency (vs products)", "list_price != harga master produk", (pd.to_numeric(stg.list_price) != pd.to_numeric(harga_master)).sum())
# staff harus bekerja di store tsb
store_master = stg.staff_id.map(staff.set_index("staff_id").store_id)
add("2-Record", "staff_id -> store_id", "Dependency (vs staffs)", "store_id != store tempat staff bertugas", (stg.store_id != store_master).sum())
# atribut header order harus sama dengan orders
for c in ["customer_id", "store_id", "staff_id", "order_status", "required_date"]:
    ref = stg.order_id.map(hdr[c])
    a = stg[c].str.replace(r"\.0$", "", regex=True)
    add("2-Record", f"order_id -> {c}", "Dependency (vs orders)", f"{c} != nilai di orders", ((a != ref) & (a != "")).sum())
ref_od = pd.to_datetime(stg.order_id.map(hdr.order_date))
add("2-Record", "order_id -> order_date", "Dependency (vs orders)", "tanggal pesan (setelah parse) != orders", (od != ref_od).sum())

# informasi: keterlambatan pengiriman (bukan error) - bandingkan dengan baseline OLTP
o_sh = pd.to_datetime(orders.shipped_date.replace("NULL", ""), errors="coerce")
late_src = (o_sh > pd.to_datetime(orders.required_date)).sum()
add("2-Record", "shipped_date vs required_date", "INFO (bukan error)", f"kirim melewati tanggal dibutuhkan; di OLTP juga ada ({late_src} dari {len(orders)} order)", ((sh > rq) & ~sentinel).sum())

# ============ LEVEL 3: DATA SET ============
add("3-Set", "(semua kolom)", "Duplikasi", "baris duplikat persis", stg.duplicated().sum())
uniq_key = len(stg.drop_duplicates(["order_id", "item_id"]))
add("3-Set", "(order_id,item_id)", "Duplikasi", f"baris berlebih; hanya {uniq_key} kunci unik = jumlah baris order_items OLTP ({len(items)})", len(stg) - uniq_key)

# integritas referensial staging -> master OLTP
cid = stg.customer_id.str.replace(r"\.0$", "", regex=True)
add("3-Set", "customer_id -> customers", "Integritas Referensial", "customer_id (terisi) tidak ada di master", ((cid != "") & ~cid.isin(cust.customer_id)).sum())
add("3-Set", "product_id -> products", "Integritas Referensial", "product_id tidak ada di master", (~stg.product_id.isin(prod.product_id)).sum())
add("3-Set", "staff_id -> staffs", "Integritas Referensial", "staff_id tidak ada di master", (~stg.staff_id.isin(staff.staff_id)).sum())
add("3-Set", "store_id -> stores", "Integritas Referensial", "store_id tidak ada di master", (~stg.store_id.isin(store.store_id)).sum())
k_stg = stg.set_index(["order_id", "item_id"]).index
add("3-Set", "(order_id,item_id) -> order_items", "Integritas Referensial", "kunci tidak ada di OLTP", (~k_stg.isin(items.set_index(["order_id", "item_id"]).index)).sum())
# cakupan: berapa baris OLTP yang muncul di staging
k_src = items.set_index(["order_id", "item_id"]).index
add("3-Set", "order_items -> staging", "Kelengkapan/cakupan", "baris OLTP yang tidak ada di staging", (~k_src.isin(k_stg)).sum(), len(items))

# ============ BASELINE: kualitas OLTP itu sendiri ============
nl = lambda df, c: (df[c] == "NULL").sum()
add("0-Baseline OLTP", "customers.phone", "Kelengkapan", "teks literal 'NULL' (bukan NULL sebenarnya)", nl(cust, "phone"), len(cust))
add("0-Baseline OLTP", "orders.shipped_date", "Kelengkapan", "teks literal 'NULL' (semua status 1-3)", nl(orders, "shipped_date"), len(orders))
add("0-Baseline OLTP", "staffs.manager_id", "Kelengkapan", "teks literal 'NULL' (staff paling atas)", nl(staff, "manager_id"), len(staff))
add("0-Baseline OLTP", "customers.street", "Pola", "spasi di ujung teks", (cust.street != cust.street.str.strip()).sum(), len(cust))
add("0-Baseline OLTP", "products", "Kelengkapan/cakupan", "produk tanpa baris stok di stocks", (~prod.product_id.isin(stock.product_id)).sum(), len(prod))
add("0-Baseline OLTP", "products", "Kelengkapan/cakupan", "produk yang tidak pernah dipesan", (~prod.product_id.isin(items.product_id)).sum(), len(prod))
add("0-Baseline OLTP", "order_items.product_id", "Integritas Referensial", "tidak ada di products", (~items.product_id.isin(prod.product_id)).sum(), len(items))
add("0-Baseline OLTP", "orders.shipped_date", "Dependency (tgl)", "kirim < pesan", (o_sh < pd.to_datetime(orders.order_date)).sum(), len(orders))

rep = pd.DataFrame(rows, columns=["level", "objek", "teknik", "temuan", "jumlah_baris", "persen"])
pd.set_option("display.width", 300, "display.max_colwidth", 90, "display.max_rows", 200)
print(f"Staging: {n:,} baris | Baris unik (semua kolom): {len(stg.drop_duplicates()):,}")
print(rep.sort_values("level", kind="stable").to_string(index=False))
rep.to_csv("data_profiling_report.csv", index=False)