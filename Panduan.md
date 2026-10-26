# Panduan.md — Rencana Perbaikan Data Profiling, Cleansing, dan ETL

## Tujuan dokumen

Dokumen ini adalah instruksi kerja untuk Claude sebagai **implementer kode**. Keputusan alur, aturan bisnis, urutan pengerjaan, dan kriteria penerimaan sudah ditetapkan di sini. Claude diminta membuat/memperbaiki kode sesuai panduan, bukan mengganti arsitektur atau aturan tanpa persetujuan.

Kerjakan hanya pada branch kerja yang sudah disiapkan. Jangan menghapus data, mengubah sumber OLTP, atau melakukan perubahan destruktif tanpa persetujuan.

## 1. Keputusan arsitektur dan alur final

Gunakan alur berikut:

1. **OLTP sumber**: CSV asli di `data/raw/` menjadi referensi kebenaran. Perlakukan sebagai read-only.
2. **Generate staging dirty**: bangun dataset kotor yang reproducible dari sumber OLTP.
3. **Profiling awal**: ukur kualitas data staging dirty dan simpan laporan baseline.
4. **Cleansing di Pentaho PDI**: baca staging dirty secara langsung, validasi kolom, pulihkan nilai yang bisa dibuktikan dari OLTP, dan pisahkan baris yang tidak bisa dipulihkan ke reject/error.
5. **Profiling ulang dan rekonsiliasi**: periksa hasil clean, reject, dan perubahan jumlah baris.
6. **Load dimension**.
7. **Load fact** setelah dimension berhasil.
8. **Dashboard**: gunakan tabel DWH yang benar dan sudah tervalidasi.

Job terjadwal boleh mengorkestrasi langkah cleansing → load dimension → load fact setelah setiap transformasi lolos pengujian. Profiling sebelum/sesudah cleansing harus tetap dapat dijalankan dan hasilnya disimpan. Jangan menjalankan load fact jika cleansing atau load dimension gagal.

## 2. Dataset dirty final dan generator

Tujuan tugas adalah menguji **data profiling dan data cleansing pada dataset besar**. Dataset boleh sintetis; jangan mengklaim seluruh satu juta baris merupakan transaksi nyata dari OLTP.

Keputusan final:
- Generator menghasilkan **tepat 1.000.000 baris total**, termasuk anomali dan duplikasi yang sengaja diinjeksi.
- Output utama: `data/staging_dirty/order_transactions_dirty.csv` (tanpa suffix `_1M`).
- Semua random memakai seed tetap; dua run dengan seed/konfigurasi sama harus menghasilkan file identik.
- Tidak menggunakan `sample_id`.
- Jangan memakai sampling dengan replacement sebagai cara utama memperbanyak transaksi, karena transaksi yang berulang bisa membuat omzet terhitung berulang dan menyulitkan definisi grain.
- Pertahankan transaksi OLTP asli yang unik, lalu buat item/order sintetis tambahan dengan ID yang tidak bentrok dan relasi header-detail yang konsisten. Dataset sintetis harus jelas didokumentasikan sebagai data simulasi.
- Simpan referensi sintetis yang diperlukan untuk memulihkan nilai di `data/staging_dirty/` dengan nama terpisah dan jelas, misalnya file referensi order/item sintetis. Jangan mengubah `data/raw/`.
- Buat sejumlah duplikat persis yang disengaja dan terdokumentasi untuk menguji deduplikasi. Target awal 1% (10.000 baris) boleh dipakai kecuali generator lama menunjukkan alasan kuat untuk angka lain; laporkan angka final.
- Buat sejumlah kecil pelanggaran integritas referensial yang disengaja untuk menguji pemeriksaan foreign key. Karena referensi buku membahas *Referential Integrity Checking*, dokumentasikan ini sebagai **pelanggaran integritas referensial**; tidak perlu memakai istilah bisnis “orphan order”. Baris uji harus memakai key yang tidak ada pada OLTP maupun referensi sintetis. Target awal 0,1% (1.000 baris) boleh dipakai dan harus masuk reject setelah cleansing.
- Jumlah baris dan kategori harus dirancang agar 1.000.000 adalah jumlah total akhir, bukan jumlah dasar ditambah anomali.

Sebelum mengganti file aktif:
1. Audit generator, skema CSV, tabel OLTP, dan seluruh referensi yang dipakai.
2. Bangun output sementara, verifikasi tepat 1.000.000 baris, validasi seed/reproducibility, dan pastikan tidak ada baris tambahan karena edit manual.
3. Arsipkan file dirty lama; jangan hapus.
4. Setelah tes sementara lulus, pindahkan hasil ke `data/staging_dirty/order_transactions_dirty.csv` dan gunakan file itu sebagai baseline tetap.
5. Jangan edit CSV dirty manual. Semua perubahan harus melalui generator dan seed/konfigurasi yang tercatat.

## 3. Aturan sumber, tanggal, dan pemulihan

Cleansing dilakukan pada staging dengan merujuk ke OLTP asli dan referensi sintetis yang dihasilkan secara eksplisit. **Jangan menulis perubahan ke file sumber OLTP di `data/raw/`.** Untuk transaksi sintetis, referensi sintetis yang konsisten adalah sumber kebenaran bagi baris sintetis tersebut.

### Audit sumber dan status order
- Sebelum menulis aturan, periksa kolom dan nilai aktual di file OLTP. Jangan mengarang kolom status, kode status, label status, atau arti kode.
- Jika OLTP memang memiliki kolom status, gunakan hanya nilai yang benar-benar ada. Cari definisi status di skema/dokumentasi/kode proyek. Jika makna kode tidak terdokumentasi, laporkan nilai yang ditemukan dan jangan menyimpulkan labelnya sendiri.
- Jangan menambahkan status bisnis baru ke OLTP atau ke kolom status order. Status kualitas data seperti `recovered` atau `rejected`, jika dibutuhkan, dicatat di laporan/metadata proses, bukan sebagai status order baru.

### Kunci pencocokan
- Gunakan `order_id` untuk mengambil atribut header seperti `order_date`, `required_date`, dan `shipped_date` dari sumber order yang sesuai.
- Gunakan kunci detail yang benar setelah memeriksa skema dan grain aktual. Jangan mengasumsikan nama kolom/kunci tanpa audit.
- Untuk data sintetis, lookup harus mengacu ke referensi sintetis yang dibuat generator. Jika key tidak ditemukan di OLTP maupun referensi sintetis, perlakukan sebagai pelanggaran integritas referensial dan reject.
- Jika satu kunci menghasilkan kandidat sumber yang bertentangan atau ambigu, jangan memilih secara acak; reject dengan alasan eksplisit.

### `order_date` dan `required_date`
- Normalisasikan tanggal valid ke format baku yang konsisten.
- Jika kosong/NULL, sentinel (termasuk `1900-01-01` atau `2000-01-01`), atau tidak valid, pulihkan hanya dari sumber yang cocok dan valid.
- Jangan mengisi tanggal dengan tanggal lain hanya untuk menghilangkan NULL.
- Jika nilai wajib tidak dapat dipulihkan secara meyakinkan, masukkan baris ke reject, bukan DWH.

### `shipped_date`
- Jangan menggunakan `required_date` sebagai pengganti `shipped_date`.
- Jika staging kosong/NULL atau berisi sentinel/tanggal tidak valid, cocokkan dengan OLTP atau referensi sintetis yang sesuai.
- Jika sumber yang sesuai memiliki `shipped_date` valid, pulihkan nilai tersebut.
- Jika sumber yang sesuai juga NULL, pertahankan NULL hanya bila data sumber/aturan yang terdokumentasi menyatakan bahwa NULL itu sah. Jangan menganggap semua NULL sebagai kesalahan dan jangan menganggap semua NULL sah tanpa pemeriksaan.
- Jika sumber tidak bisa menentukan apakah tanggal seharusnya ada, jangan mengarang tanggal atau status. Tandai sebagai tidak dapat dipastikan; berdasarkan aturan dataset ini, reject dari output clean/DWH dan catat alasannya.
- Gunakan status order hanya jika kolom dan makna status telah diverifikasi dari sumber/dokumentasi. Jangan menebak bahwa angka tertentu berarti “belum dikirim” atau “selesai”.

### Prinsip masuk DWH
- Baris clean hanya berisi data yang lolos validasi dan aturan integritas yang disepakati.
- NULL `shipped_date` boleh dipertahankan jika terbukti merupakan NULL yang sah menurut sumber. Jika model fact/dashboard mendukungnya, status “belum dikirim” boleh ditampilkan sebagai interpretasi analitis, tetapi jangan menciptakan status order baru di OLTP.
- Baris yang tanggal wajibnya tidak bisa dipulihkan, relasinya tidak valid, atau anomali pentingnya tidak bisa diselesaikan masuk reject dengan alasan yang jelas.
- Simpan reject terpisah, misalnya `data/reject/order_transactions_rejected.csv`, dengan seluruh kolom input dan `reject_reason`/`reject_stage`. Nama final harus konsisten dengan repo.

## 4. Grain, duplikasi, dan integritas referensial

Grain final untuk dataset transaksi adalah **satu baris per item transaksi** dengan pasangan bisnis yang unik untuk setiap transaksi valid. Data sintetis harus diberi ID order/item baru agar tidak berbenturan dengan data asli; jangan menggunakan `sample_id`.

- Buat order sintetis dan detailnya secara konsisten; `order_id` detail harus ada pada sumber order asli atau referensi order sintetis, kecuali baris yang sengaja dibuat sebagai pelanggaran integritas referensial.
- Duplikat yang sengaja diinjeksi harus berupa salinan persis yang dapat dikenali dan dihitung. Dedup hanya menghapus duplikat yang didefinisikan generator sebagai duplikat uji; jangan menghapus semua baris dengan `order_id` sama karena satu order memang dapat memiliki beberapa item.
- Periksa keunikan grain setelah cleansing dan jelaskan aturan kunci bisnis yang digunakan.
- Buku *Data Warehouse: Teori dan Praktek*, Bab 10.3.5, membahas **Referential Integrity Checking** (halaman cetak 223 / halaman PDF 232): hubungan antar tabel melalui foreign key harus dijaga. Karena itu, uji pelanggaran referensial boleh digunakan sebagai anomali data-quality yang disengaja. Jangan menyebutnya sebagai status bisnis; gunakan istilah “pelanggaran integritas referensial”.
- Rekonsiliasi kategori tanpa tumpang tindih: `input = clean + reject + exact_duplicates_eliminated` (atau kategori lain yang memang terpisah dan didefinisikan). Pastikan satu baris tidak dihitung pada dua kategori sekaligus.
- Jangan menganggap semua baris staging akan menjadi clean. Jelaskan jumlah dan alasan perbedaan.

## 5. Profiling

Perbaiki/jalankan `src/data_profiling.py` pada:
- baseline dirty sebelum cleansing;
- output clean setelah cleansing;
- output reject.

Laporan minimum:
- jumlah baris dan kolom;
- NULL/kosong per kolom;
- format dan rentang tanggal, tanggal sentinel, serta urutan logis `order_date`, `required_date`, `shipped_date`;
- nilai tidak valid untuk quantity, discount, list_price, customer/store/staff/product identifiers;
- jumlah kunci bisnis unik dan duplikasi berdasarkan grain yang disepakati;
- jumlah baris yang berhasil dipulihkan, valid, ditolak, dan dieliminasi;
- alasan reject paling umum.

Laporan dirty lama jangan dianggap baseline final jika dataset dirty diubah/regenerate. Simpan laporan baru dengan nama yang menunjukkan versi/tahap dataset.

## 6. Pentaho PDI

Audit dan perbaiki file berikut:
- `PENTAHO_ETL/01_Pembersihan_Data_Transaksi.ktr`
- `PENTAHO_ETL/02_Load_Dim.ktr`
- `PENTAHO_ETL/02_Load_Fact.ktr`
- `PENTAHO_ETL/Jadwal_ETL_BikeStore.kjb`

Persyaratan:
- Cleansing membaca satu file dirty resmi, bukan `order_transactions_filled.csv`.
- Input lookup OLTP harus jelas, dan hasil lookup harus mempertahankan NULL jika NULL itu memang valid.
- Semua hop/condition filter harus benar-benar mengalirkan baris sesuai kondisi; verifikasi output setiap cabang.
- Output clean dan reject menggunakan nama/path resmi yang sama di semua transformasi.
- Hindari nama ganda seperti `order_transactions_clean.csv.csv`.
- Load dimension harus selesai sebelum fact.
- Semua foreign key fact harus merujuk ke dimension yang tersedia.
- Sediakan baris unknown/unspecified pada dimension jika model membutuhkannya; jangan membiarkan foreign key yatim.
- Tentukan strategi rerun/idempotency. Menjalankan job dua kali tidak boleh menggandakan data tanpa disengaja.
- Jangan menggunakan truncate secara sembarangan; jelaskan apakah strategi full refresh atau incremental dan pastikan konsisten.
- Hindari hard-coded path mesin pengembang. Gunakan parameter atau path relatif yang didukung PDI.
- Catat jumlah input, output clean, reject, dan error pada setiap tahap.
- Jika langkah gagal, langkah berikutnya tidak boleh berjalan seolah-olah sukses.

### Tanggal di DWH
Jika analisis membutuhkan order, required, dan shipped date, evaluasi penambahan `required_date_key` dan `shipped_date_key` pada fact dengan `dim_time` yang sama sebagai role-playing dimensions. Jangan mengubah skema database secara diam-diam: laporkan perubahan skema dan sesuaikan dashboard/SQL terkait.

## 7. Konsistensi dashboard

Audit `src/app.py` dan cocokkan dengan skema DWH yang benar-benar dibuat oleh skrip SQL dan Pentaho. Jangan mengarang nama tabel/kolom untuk membuat dashboard jalan. Bila app memakai tabel yang tidak tersedia:
1. identifikasi skema aktual;
2. putuskan apakah query dashboard atau skema DWH yang harus disesuaikan;
3. dokumentasikan dan uji seluruh query dashboard.

Dashboard dikerjakan setelah cleansing, load dimension, dan load fact tervalidasi.

## 8. File yang dipertahankan, dihentikan, dan dibuat ulang

### Pertahankan
- Semua sumber OLTP di `data/raw/`.
- `data/staging_dirty/order_transactions_dirty.csv` setelah generator baru lolos uji; arsipkan dataset lama terlebih dahulu.
- Dataset lama `data/staging_dirty/order_transactions_dirty_1M-lama12okt.csv` sebagai arsip bila masih berguna.
- Laporan profiling lama sebagai catatan historis, tetapi jangan menyebutnya hasil dari dataset baru.

### Hentikan dari alur aktif
- `src/fill_shipped_date.py` dan `data/staging_dirty/order_transactions_filled.csv`. Jangan gunakan file filled sebagai input cleansing. File boleh dihapus hanya setelah seluruh referensi sudah dihilangkan dan salinan arsip tidak diperlukan.
- Kedua file clean lama tidak boleh dianggap output valid terbaru. Setelah Pentaho diperbaiki, buat ulang ke satu nama output resmi; arsipkan atau hapus salinan lama setelah memastikan tidak ada kebutuhan pembandingan.

### Buat ulang setelah kode disetujui
- Baseline `order_transactions_dirty.csv`, hanya setelah generator diperbaiki dan dataset lama diarsipkan.
- Laporan profiling baseline untuk dataset dirty yang baru.
- Output clean dan reject dari cleansing terbaru.
- Dimensi dan fact DWH sesuai strategi refresh yang ditetapkan.
- Screenshot/log/bukti pengujian untuk dokumentasi.

**Jangan menghapus file apa pun secara otomatis dalam tahap audit.** Buat daftar file kandidat arsip/hapus dan minta persetujuan sebelum penghapusan.

## 9. Urutan implementasi yang harus diikuti Claude

Lakukan satu tahap per satu tahap dan laporkan hasil sebelum lanjut:

1. **Audit repository**: peta file, path input/output, kolom, tabel, serta dependensi. Jangan ubah file.
2. **Rencana dataset**: perbaiki spesifikasi generator agar jumlah baris, seed, dan output path jelas. Minta konfirmasi jika ada keputusan yang tidak tercakup.
3. **Generator reproducible**: implementasikan dan uji pada file uji/temporary terlebih dahulu; jangan langsung menimpa baseline.
4. **Profiling baseline**: jalankan pada dataset yang sudah disetujui dan simpan laporan.
5. **Cleansing**: implementasikan aturan pemulihan lookup OLTP, tanggal, validasi, dan reject.
6. **Profiling pasca-cleansing**: buat rekonsiliasi hasil.
7. **Dimension/fact**: audit dan implementasikan load dengan foreign key dan rerun yang aman.
8. **Job orchestration**: atur urutan dan kegagalan job.
9. **Dashboard**: cocokkan query dengan skema aktual.
10. **Dokumentasi dan review**: catat perubahan, perintah menjalankan, hasil pengujian, asumsi, dan hal yang belum bisa diverifikasi.

Jangan mengimplementasikan semua tahap sekaligus. Pada akhir setiap tahap, tampilkan file yang diubah, ringkasan perubahan, tes yang dijalankan, hasil tes, dan tahap berikutnya.

## 10. Kriteria penerimaan

Project belum dianggap selesai sampai:
- Generator menghasilkan tepat 1.000.000 baris total dan dapat direproduksi dengan seed yang sama.
- Tidak ada `sample_id`; data sintetis ditandai/didokumentasikan dan memakai key unik.
- Kode/label status order tidak dikarang; hanya memakai kolom dan definisi yang terverifikasi dari sumber.
- Sumber OLTP tidak berubah.
- Cleansing membaca `data/staging_dirty/order_transactions_dirty.csv` secara langsung, bukan `order_transactions_filled.csv`.
- Tidak ada pengisian `shipped_date` dari `required_date`.
- Tanggal bermasalah dipulihkan hanya bila ada sumber yang cocok dan valid; nilai yang tidak dapat dipulihkan masuk reject, bukan dipaksakan masuk DWH.
- NULL `shipped_date` yang sah untuk order belum dikirim tetap NULL.
- Jumlah input = jumlah clean + reject + baris yang secara eksplisit dieliminasi, dengan kategori yang tidak tumpang tindih dan rekonsiliasi terdokumentasi.
- Semua foreign key fact valid.
- Load dimension terjadi sebelum fact.
- Job rerun tidak menggandakan data tanpa disengaja.
- Dashboard memakai nama tabel dan kolom yang benar-benar tersedia.
- Semua klaim keberhasilan didukung tes/log nyata; jangan mengklaim Pentaho berhasil dijalankan jika belum diuji di lingkungan PDI.

## Instruksi terakhir untuk Claude

Mulai dari audit generator dan sumber, lalu implementasikan tahap 1–6 saja: generator 1.000.000 baris, profiling baseline, cleansing, profiling ulang, rekonsiliasi, dan verifikasi independen. Jangan lanjut mengubah Pentaho atau dashboard sampai hasil tahap 1–6 dilaporkan dan disetujui. Uji generator pada file sementara sebelum mengganti baseline. Jangan menghapus file lama; arsipkan dan laporkan kandidat penghapusan terlebih dahulu. Jika ada konflik antara kode lama dan panduan ini, ikuti panduan ini dan jelaskan konflik tersebut. Jangan mengubah aturan bisnis atau skema DWH tanpa melaporkan dampaknya terlebih dahulu.
