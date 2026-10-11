# Data Profiling & Cleansing - Bike Store Sales

Repositori ini berisi alur kerja proyek Data Warehouse untuk mempraktikkan skenario _Data Profiling_ dan _Data Cleansing_ menggunakan Pentaho Data Integration, berdasarkan dataset "Bike Store Sales and Order Analysis".

## 👥 Tim Pengembang (Kelompok X)

- **Astri** - Rekayasa Dataset & Data Profiling
- **Angelina** - Git Master & Eksekusi ETL (Pentaho)
- **Radit** - Finalisasi & Laporan

## 📂 Dataset

Dataset bersumber dari [Kaggle: Bike Store Sales and Order Analysis](https://www.kaggle.com/code/derekeodice/bike-store-sales-and-order-analysis-sql-python).
Dataset mentah di dalam folder `data/raw/` telah direkayasa secara sengaja (ditambahkan _missing values_, format tidak konsisten, dan duplikasi) untuk keperluan simulasi masalah kualitas data.

## ⚙️ Prasyarat (Prerequisites)

- [Pentaho Data Integration (PDI / Kettle)](link-unduh-pentaho) versi X.X
- Java Runtime Environment (JRE)

## 🚀 Cara Menjalankan Proyek

1. Clone repositori ini: `git clone https://github.com/anggienadia/dwh-with-dataprofiling-cleansing.git`
2. Buka aplikasi **Spoon** (Pentaho).
3. Jalankan file transformasi `pentaho_etl/cleansing_process.ktr` untuk melihat proses standarisasi dan pembersihan data.
4. Output data bersih akan tersimpan secara otomatis di folder `data/cleansed/`.

## 📄 Hasil & Laporan

Laporan analisis profiling dan rangkuman kualitas data dapat dilihat pada folder `docs/`.
