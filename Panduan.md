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

## 2. Apakah staging dirty harus digenerate ulang?

**Rekomendasi: jangan menimpa file dirty yang sekarang terlebih dahulu.** Jadikan file yang sekarang sebagai arsip/baseline sementara, lalu audit generator dan sumbernya.

Dari pemeriksaan awal terhadap `src/generate_staging_data.py`, ada hal yang perlu dibenahi sebelum regenerasi:
- Sampling dilakukan dengan `replace=True`; karena itu baris transaksi yang berulang dapat terjadi secara sengaja.
- Script menambahkan 5.000 baris duplikat eksplisit setelah sampling 1.000.000 baris, sehingga total targetnya 1.005.000 baris, bukan tepat 1.000.000.
- `random.choice()` tidak dikunci seed-nya, sehingga hasil format tanggal tidak sepenuhnya reproducible.
- Output ditulis ke `order_transactions_dirty_1M.csv` di working directory, bukan secara eksplisit ke `data/staging_dirty/order_transactions_dirty_1M.csv`.
- Ada kemungkinan file saat ini pernah diedit manual sehingga tidak identik dengan keluaran generator.

Urutan yang benar:
1. Audit generator dan dataset saat ini; jangan menimpa file saat audit.
2. Putuskan target jumlah baris secara eksplisit. Untuk menjaga kompatibilitas nama dataset, rekomendasi default adalah **tepat 1.000.000 baris total termasuk anomali dan duplikasi**. Jika 5.000 duplikat eksplisit dipertahankan, jumlah baris sampling dasar harus disesuaikan menjadi 995.000. Catat keputusan ini di dokumentasi.
3. Perbaiki generator agar output path eksplisit, seed semua random generator, dan hasil dapat direproduksi.
4. Arsipkan salinan dataset dirty saat ini di luar jalur input aktif, tanpa menghapusnya.
5. Jalankan generator yang sudah diperbaiki satu kali untuk membuat baseline dirty baru. Jalankan profiling pada baseline tersebut.
6. Setelah baseline disetujui, jangan mengedit CSV dirty secara manual. Perubahan harus melalui generator dengan seed/versi yang tercatat.

Jangan regenerasi berulang kali selama mengembangkan cleansing; gunakan satu baseline dirty yang tetap agar hasil antar-run dapat dibandingkan. Regenerasi baru hanya dilakukan jika generator atau spesifikasi dataset berubah dan perubahan itu memang disengaja.

## 3. Aturan tanggal dan pemulihan staging dari OLTP

Pemulihan dilakukan di proses cleansing staging dengan mencocokkan baris ke data OLTP. **Jangan menulis perubahan ke file OLTP sumber.**

### Kunci pencocokan
- Gunakan `order_id` untuk mengambil atribut header order, termasuk `order_date`, `required_date`, dan `shipped_date`, dari `data/raw/orders.csv`.
- Gunakan kunci bisnis transaksi/item yang sesuai untuk mencocokkan detail order. Pastikan grain data dan struktur CSV dipahami sebelum join.
- Bila satu kunci menghasilkan lebih dari satu kandidat sumber yang bertentangan, jangan memilih secara acak. Masukkan baris ke reject dengan alasan ambigu.

### `order_date`
- Normalisasikan format tanggal yang valid ke format baku yang konsisten.
- Jika NULL/kosong, sentinel, atau tidak valid, coba pulihkan dari OLTP berdasarkan kunci yang valid.
- Jika sumber OLTP juga NULL/tidak tersedia atau pencocokan ambigu, baris **tidak boleh masuk DWH**; masukkan ke reject dengan alasan eksplisit.

### `required_date`
- Terapkan aturan yang sama seperti `order_date`.
- Jangan mengisi dari `order_date` atau tanggal lain hanya untuk menghilangkan NULL.

### `shipped_date`
- Normalisasikan format tanggal yang valid.
- Jika NULL/kosong atau sentinel seperti `1900-01-01`/`2000-01-01`, cek status order dan nilai pada OLTP.
- Jika OLTP memiliki `shipped_date` valid dan order cocok secara meyakinkan, pulihkan dari OLTP.
- Jika OLTP menunjukkan order belum dikirim dan `shipped_date` memang NULL, pertahankan NULL di staging clean. Ini adalah kondisi bisnis yang valid, bukan otomatis error.
- Jika OLTP menunjukkan order sudah dikirim tetapi tanggal sumber juga NULL/tidak valid, atau status/tanggal bertentangan dan tidak bisa diselesaikan dengan aturan yang disepakati, masukkan ke reject.
- **Jangan pernah mengisi `shipped_date` menggunakan `required_date`.** Kedua kolom memiliki makna berbeda.

### Aturan masuk DWH untuk tanggal
- Baris hanya boleh masuk DWH jika seluruh kolom wajib untuk grain/fact yang disepakati valid dan relasi kunci yang diperlukan valid.
- NULL pada `shipped_date` boleh dipertahankan untuk order yang belum dikirim, asalkan model DWH mendukungnya. Jangan mengganti NULL dengan tanggal buatan atau tanggal sentinel.
- Jika `order_date` atau `required_date` wajib untuk model DWH dan tidak dapat dipulihkan dari OLTP, tolak baris dari DWH dan catat alasannya.
- Reject harus disimpan sebagai output terpisah, misalnya `data/reject/order_transactions_rejected.csv`, dengan kolom sumber plus `reject_reason` dan/atau `reject_stage`. Nama final boleh disesuaikan dengan konvensi repo, tetapi harus konsisten.

## 4. Grain, duplikasi, dan jumlah baris

Generator menggunakan sampling dengan replacement. Artinya, kemunculan order/item yang sama belum tentu merupakan kesalahan: itu dapat menjadi bagian dari desain dataset simulasi.

Sebelum membuat aturan deduplikasi:
1. Tetapkan grain dataset yang sebenarnya.
2. Identifikasi duplikat yang sengaja diinjeksi generator secara terpisah dari duplikat akibat sampling dengan replacement.
3. Jangan menghapus semua baris dengan kombinasi `(order_id, item_id)` yang sama secara otomatis apabila sampling memang mengulang transaksi tersebut.
4. Jika tujuan tugas mengharuskan satu baris per item order unik, ubah strategi pembentukan dataset atau tambahkan identitas replika/sampel agar jumlah observasi tidak hilang diam-diam. Dokumentasikan keputusan.
5. Setiap baris yang dihapus atau ditolak harus dapat dihitung dan dijelaskan.

Jangan membuat asumsi bahwa 1.000.000 baris staging akan menjadi 1.000.000 baris clean. Jumlah clean ditentukan aturan validasi dan model data, lalu direkonsiliasi dengan jumlah reject dan baris yang dieliminasi sesuai aturan eksplisit.

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
- `data/staging_dirty/order_transactions_dirty_1M.csv` yang ada sampai audit dan arsip selesai.
- Dataset lama `data/staging_dirty/order_transactions_dirty_1M-lama12okt.csv` sebagai arsip bila masih berguna.
- Laporan profiling lama sebagai catatan historis, tetapi jangan menyebutnya hasil dari dataset baru.

### Hentikan dari alur aktif
- `src/fill_shipped_date.py` dan `data/staging_dirty/order_transactions_filled.csv`. Jangan gunakan file filled sebagai input cleansing. File boleh dihapus hanya setelah seluruh referensi sudah dihilangkan dan salinan arsip tidak diperlukan.
- Kedua file clean lama tidak boleh dianggap output valid terbaru. Setelah Pentaho diperbaiki, buat ulang ke satu nama output resmi; arsipkan atau hapus salinan lama setelah memastikan tidak ada kebutuhan pembandingan.

### Buat ulang setelah kode disetujui
- Baseline `order_transactions_dirty_1M.csv`, hanya setelah generator diperbaiki dan dataset lama diarsipkan.
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
- Generator menghasilkan jumlah baris yang ditentukan dan dapat direproduksi dengan seed yang sama.
- Sumber OLTP tidak berubah.
- Cleansing tidak lagi membaca `order_transactions_filled.csv`.
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

Mulai dari **Tahap 1: audit repository saja**. Jangan menulis atau menghapus file sampai laporan audit dan daftar perubahan diajukan. Jika ada konflik antara kode lama dan panduan ini, ikuti panduan ini dan jelaskan konflik tersebut. Jangan mengubah aturan bisnis atau skema DWH tanpa melaporkan dampaknya terlebih dahulu.
