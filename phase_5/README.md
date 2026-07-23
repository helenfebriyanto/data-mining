# Dashboard Deteksi Fraud Perbankan — Kelompok Fance (Phase 5)

Dashboard interaktif berbasis Python Dash untuk hasil Data Mining Project Phase 1-4
(preprocessing → segmentasi KMeans → pola asosiasi → deteksi anomali) di atas dataset
PaySim (~6,3 juta transaksi). Dibangun ulang dari draf sebelumnya untuk menjawab
catatan revisi dosen, dengan bahasa Indonesia penuh, filter/slicer di setiap halaman,
dan backend Elasticsearch + DuckDB.

## Daftar Isi
1. [Mulai Cepat (mode demo)](#1-mulai-cepat-mode-demo)
2. [Menjalankan dengan Data Asli Kelompok](#2-menjalankan-dengan-data-asli-kelompok)
3. [Mengaktifkan Elasticsearch](#3-mengaktifkan-elasticsearch)
4. [Arsitektur](#4-arsitektur)
5. [Performa (<100ms) — Apa yang Sudah Diuji](#5-performa-100ms--apa-yang-sudah-diuji)
6. [Tentang Dimensi "Wilayah" (Spasial)](#6-tentang-dimensi-wilayah-spasial)
7. [Checklist Catatan Dosen → Perubahan](#7-checklist-catatan-dosen--perubahan)
8. [Batasan & Hal yang Perlu Diketahui](#8-batasan--hal-yang-perlu-diketahui)
9. [Struktur Folder](#9-struktur-folder)

---

## 1. Mulai Cepat (mode demo)

Mode ini memakai data **sintetis** (~6,3 juta baris, meniru statistik agregat asli
kelompok kalian persis - lihat [bagian 8](#8-batasan--hal-yang-perlu-diketahui))
supaya dashboard bisa langsung dicoba tanpa perlu data mentah Phase 1-4.

```bash
python -m venv venv && source venv/bin/activate   # opsional tapi disarankan
pip install -r requirements.txt
pip install -r requirements-dev.txt                # dibutuhkan utk generator data sintetis

# 1) Buat data sintetis (~1-2 menit, hanya perlu dijalankan sekali)
python tools/generate_synthetic_data.py

# 2) Jalankan pipeline (isi DuckDB, coba index ke Elasticsearch kalau menyala)
python -m pipeline.flow --mode synthetic

# 3) Jalankan dashboard
python app.py
```

Buka `http://localhost:8050`. Kalau Elasticsearch belum menyala, dashboard otomatis
memakai DuckDB (lihat badge di kanan atas navbar) - **tidak akan error**.

## 2. Menjalankan dengan Data Asli Kelompok

```bash
python -m pipeline.flow --mode real --data-root /path/ke/folder/project/kalian
```

`--data-root` mengikuti struktur folder yang sama dengan dashboard versi sebelumnya
(`phase_2/`, `phase_3/`, `phase_4/`, `models/`, dst). Pipeline akan mencari, berurutan:

- **Dataset skor penuh** (6,3 juta baris + risk_score): `phase_4/paysim_full_scored.parquet`.
  Kalau ADA, seluruh dashboard (termasuk Jelajah Data & Anomali) bekerja atas SELURUH
  data. **Phase 4 kalian saat ini TIDAK menulis berkas ini** (lihat bagian 8) -
  tambahkan baris berikut di akhir flow `phase_4.py` kalian, lalu jalankan ulang:

  ```python
  # taruh tepat sebelum/sesudah export_results(top_df, ...) dipanggil di flow phase_4
  df.to_parquet("phase_4/paysim_full_scored.parquet", index=False)
  ```

- **Fallback**: `phase_5/cache/top_suspicious_light.parquet` (20.000 transaksi
  ter-mencurigakan yang sudah ada) - dashboard tetap jalan penuh, hanya saja
  pencarian/penjelajahan transaksi individual terbatas pada 20.000 baris ini,
  bukan 6,3 juta. Pipeline akan memberi peringatan jelas di log & di `manifest.json`
  kalau berjalan dalam mode ini.

- **Pola asosiasi**: pipeline mencari `phase_3/report_worthy_rules.csv` atau
  `phase_3/fraud_focused_rules.csv` (pool pola yg lebih besar dari 10) untuk
  mengisi fitur "10 pola utama + selebihnya tetap bisa diakses". Kalau tidak
  ada, hanya 10 pola utama (`top_10_final_rules.csv`) yang tersedia.

Setelah pipeline selesai: `python app.py`.

## 3. Mengaktifkan Elasticsearch

```bash
docker-compose up -d elasticsearch
# tunggu ~30-60 detik sampai sehat:
curl http://localhost:9200/_cluster/health

# ulangi pipeline supaya data ikut ter-index ke Elasticsearch:
python -m pipeline.flow --mode synthetic      # atau --mode real --data-root ...

python app.py   # sekarang badge navbar akan menampilkan "Elasticsearch"
```

Dashboard **tidak pernah bergantung mutlak** pada Elasticsearch - kalau container-nya
mati atau belum dinyalakan, `app.py` otomatis memakai DuckDB tanpa perlu konfigurasi
apa pun (lihat `pilih_backend()` di `app.py`).

## 4. Arsitektur

```
                     ┌──────────────────────┐
 Phase 1-4 (asli) →  │ pipeline/flow.py      │  (Prefect @flow/@task, sama gaya dgn Phase 1-4)
 atau data sintetis  │  - enrich.py          │  label ID, dimensi wilayah, gabung pool pola
                     │  - es_indexer.py      │  mapping index & bulk indexing
                     └──────────┬───────────┘
                                │  tulis
                 ┌──────────────┴───────────────┐
                 ▼                              ▼
      data/fance_dashboard.duckdb      Elasticsearch (opsional, best-effort)
        - tabel `transaksi` (6,3jt)      - index fance_transaksi
        - tabel `cube` (~1.700 baris     - index fance_pola_asosiasi
          pra-agregasi utk KPI instan)
        - tabel `pola` (135 pola)
                 │                              │
                 └──────────────┬───────────────┘
                                ▼
                  data_backend/{duckdb_backend,es_backend}.py
                  (satu antarmuka DataBackend - lihat base.py)
                                ▼
                     app.py memilih otomatis, lalu
                     components/ & pages/*.py memakainya
                     TANPA tahu/peduli backend mana yg aktif
```

**Kenapa ada tabel `cube`?** KPI & ringkasan (segmen, level risiko, jenis anomali, dst.)
tidak perlu memindai 6,3 juta baris tiap kali filter berubah - cukup memindai hasil
pra-agregasi (~1.700 baris) atas semua kombinasi dimensi filter. Hanya fitur
pencarian/penjelajahan baris individual (Jelajah Data, tabel di halaman Anomali)
yang benar-benar menyentuh tabel penuh.

## 5. Performa (<100ms) — Apa yang Sudah Diuji

Diukur di lingkungan pengembangan (sandbox **1 vCPU**, 3,9GB RAM - lebih terbatas
dari laptop biasa) memakai `data_backend/duckdb_backend.py:benchmark()` atas
6.362.604 baris:

| Skenario | Median | Keterangan |
|---|---|---|
| KPI tanpa filter | ~1-3 ms | via tabel `cube` |
| KPI dgn filter wilayah+segmen+risiko | ~1-3 ms | via tabel `cube` |
| Ringkasan segmen / wilayah / overlap metode | ~1-4 ms | via tabel `cube` |
| Cari transaksi (filter kategorikal, tanpa teks) | ~10-60 ms | tabel `transaksi`, pakai indeks |
| Cari berdasarkan ID transaksi persis | ~1-6 ms | tabel `transaksi`, indeks unik |
| Cari kata kunci metode (mis. "hdbscan") | ~15-30 ms | diterjemahkan ke filter boolean ber-indeks |
| Cari teks bebas tak dikenal (ILIKE substring) | **~500-800 ms** | lihat catatan di bawah |

**Catatan jujur soal baris terakhir**: pencarian substring bebas di atas 6,3 juta baris
teks pada satu core CPU memang lambat di DuckDB (ini murni batas mesin pemindaian
baris demi baris, bukan bug) - inilah PERSIS kasus yang Elasticsearch selesaikan
lewat inverted index-nya, dan alasan utama Elasticsearch dipilih sebagai backend
utama di proyek ini. Nyalakan Elasticsearch (bagian 3) untuk performa <100ms yang
konsisten pada pencarian bebas sekalipun. Angka DuckDB di atas juga akan lebih
cepat lagi di laptop dgn CPU multi-core (bukan cuma 1 core seperti sandbox
pengembangan ini) karena DuckDB memparalelkan pemindaian kolom.

Halaman Jelajah Data menampilkan **latensi query yang sesungguhnya** (bukan angka
di atas kertas) tiap kali kalian mengubah filter - lihat badge ⚡ di halaman tsb.

## 6. Tentang Dimensi "Wilayah" (Spasial)

Dataset PaySim asli **tidak memiliki atribut geografis apa pun** (11 kolom asli:
step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig, nameDest, oldbalanceDest,
newbalanceDest, isFraud, isFlaggedFraud — sudah dicek di seluruh kode Phase 1-4,
tidak ada kolom lokasi/negara/wilayah sama sekali). Sesuai arahan dosen ("spatio aja
gausah temporal karena di dataset kita gaada temporal atribute"), pipeline menempelkan
kolom **`wilayah`** yang:

- **Deterministik**: diturunkan dari hash kombinasi atribut transaksi yang sudah ada
  (nominal, saldo, dll - lihat `pipeline/enrich.py:assign_wilayah()`), BUKAN acak
  murni, dan akan selalu sama tiap pipeline dijalankan ulang pada data yang sama.
- **Ilustratif**, bukan data lokasi asli - ini ditampilkan secara transparan di
  dashboard (lihat footer & `config.WILAYAH_DISCLOSURE`) supaya bisa dijelaskan
  apa adanya ke dosen: dashboard MAMPU melakukan slicing spasial (sesuai arahan),
  namun dataset PaySim memang tidak membawa geografi asli untuk didemonstrasikan.
- **Mudah diganti**: kalau kelompok mendapat/membuat atribut wilayah yang lebih
  sahih di kemudian hari, cukup pastikan kolom `wilayah` tersedia sebelum data
  masuk ke `pipeline/flow.py` - fungsi `assign_wilayah` otomatis dilewati kalau
  kolom itu sudah ada (lihat `pipeline/enrich.py:standardize_schema`).

## 7. Checklist Catatan Dosen → Perubahan

| # | Catatan dosen | Yang dilakukan |
|---|---|---|
| 1 | Customer segments ada yang ga keliatan di grafiknya | `population_share_bar` pakai skala **log** + label angka selalu tampil di ujung bar (Segmen 0 = 0,03% tetap terbaca) |
| 2 | Karakteristik segmen | Radar chart multi-metrik (`segment_radar`) + rincian per segmen di kartu |
| 3 | Tambahkan grafik di segmen, jangan teks doang | 4 grafik (populasi, radar, risiko, peta populasi-risiko) + sebaran wilayah, semua ikut ter-highlight saat kartu segmen diklik |
| 4 | Pattern recommendation lebih detail, tambahkan rekomendasi di halaman pattern | Tiap pola punya field `recommendation` (aksi bisnis konkret) ditampilkan di kartu, terpisah dari `takeaway` |
| 5 | Justifikasi kenapa pakai anomali | Section "Mengapa Memakai 5 Metode Sekaligus?" di halaman Anomali, didukung angka nyata kajian tumpang-tindih metode |
| 6 | Setiap page minimal ada slicer | Semua 6 halaman punya filter bar fungsional (bukan pajangan) - lihat `components/filter_bar.py` |
| 7 | Fitur apa yang membentuk fitur flag | 5 kartu metode (`anomaly_method_card`) menyebut persis fitur input & bobot tiap flag |
| 8 | Sebagian grafik ada hover, sebagian tidak | Semua grafik lewat satu modul `components/charts.py` + `theme.apply_theme()` - hover template konsisten di semua chart |
| 9 | Main behavior kurang kelihatan (presentasi) | `.behavior-callout` - kotak menonjol, font lebih besar & tebal, warna aksen, bukan lagi baris teks biasa |
| 10 | Spasial saja, temporal tidak perlu | Filter wilayah tersedia luas; tidak ada filter berbasis waktu di mana pun |
| 11 | Tampilkan 10 saja, sisanya tetap bisa diakses, diberi label penting/tidak | Halaman Pola: 10 kartu besar (`is_top10`) + tabel semua 135 pola bisa dicari/diurutkan, ditandai "Insight utama" vs "Insight tambahan" |
| 12 | Data spasial(-temporal) bisa di-slice | Filter wilayah memengaruhi KPI, grafik, & tabel transaksi secara real-time di semua halaman yang relevan |

## 8. Batasan & Hal yang Perlu Diketahui

- **Data sintetis vs asli**: Berkas ZIP proyek yang diunggah berisi kode Phase 1-4
  dan cache ringkasan Phase 5 (`cluster_summary.parquet`, `top_rules_business.parquet`,
  dst - 8 tabel kecil + 1 tabel 20.000 baris), TAPI TIDAK berisi dataset mentah 6,3
  juta baris (ukurannya tidak realistis ikut ter-upload). Untuk menguji dashboard
  secara end-to-end di lingkungan pengembangan, dibuat dataset sintetis
  (`tools/generate_synthetic_data.py`) yang meniru **seluruh statistik agregat asli**
  kalian (jumlah per segmen, tingkat fraud, distribusi skor risiko, dll - lihat
  nilai persis di file tsb) pada skala 6.362.604 baris yang sama. Semua angka yang
  dijalankan di lingkungan pengembangan berasal dari data ini, BUKAN data asli
  kalian. Setelah menjalankan `pipeline.flow --mode real` dengan data kalian
  sendiri, seluruh angka di dashboard otomatis jadi angka asli kalian.
- **10 pola + pool tambahan**: 10 pola utama memakai angka ASLI dari
  `top_rules_business.parquet` kalian (tidak diubah). Pool pola tambahan (di luar
  10 besar) yang dipakai utk menguji fitur "lihat semua pola" ditambang ulang
  (apriori, parameter identik dgn Phase 3 asli) dari data sintetis di atas -
  begitu kalian menjalankan pipeline dgn `report_worthy_rules.csv`/
  `fraud_focused_rules.csv` asli, pool ini otomatis diganti pola asli kalian.
- **Phase 4 tidak menyimpan dataset skor penuh**: lihat bagian 2 - saat ini
  `phase_4.py` hanya mengekspor `top_df` (20 ribu baris) dan tabel ringkasan.
  Tambahkan satu baris export (dicontohkan di bagian 2) kalau ingin Jelajah
  Data & Anomali bekerja di atas SELURUH 6,3 juta baris data asli, bukan 20 ribu.
- **Elasticsearch tidak diuji langsung di lingkungan pengembangan**: sandbox
  tempat proyek ini dibangun tidak memiliki akses jaringan ke elastic.co atau
  Docker Hub, jadi `data_backend/es_backend.py` tidak bisa dites terhadap cluster
  sungguhan di sana. Kode memakai `elasticsearch-py` resmi dengan Query DSL
  standar (terms/filter aggregation, multi_match) - sudah diverifikasi lewat
  pemeriksaan struktur query, tapi tetap jalankan `docker-compose up -d` dan
  lakukan pengecekan singkat di komputer kalian sendiri sebelum presentasi.
- **Nominal transaksi**: kolom `amount` pada cache lama (`top_suspicious_light.parquet`)
  sudah melalui `log1p` + `RobustScaler` (bukan nilai Rupiah asli). Dataset sintetis
  di lingkungan pengembangan memakai nilai nominal asli (tidak diskalakan) supaya
  lebih mudah dibaca. Kalau menjalankan mode `real`, pastikan kolom `amount` yang
  dipakai adalah versi SEBELUM scaling (gabungkan balik dari output Phase 1 mentah)
  supaya nominal yang tampil ke pengguna awam masuk akal.

## 9. Struktur Folder

```
app.py                   Entry point Dash (routing, navbar, pilih backend otomatis)
config.py                Semua label bisnis Indonesia, ambang risiko, daftar wilayah
theme.py                 Warna, tipografi, template Plotly bersama
docker-compose.yml        Elasticsearch (+ Dejavu opsional utk debugging index)
requirements.txt          Dependensi dashboard & pipeline
requirements-dev.txt       Dependensi tambahan khusus tools/ (generator data uji)

data_backend/
  base.py                 Kontrak DataBackend + dataclass Filters
  duckdb_backend.py        Implementasi DuckDB (tabel cube utk performa)
  es_backend.py            Implementasi Elasticsearch

pipeline/
  flow.py                  Prefect @flow utama (--mode real|synthetic)
  enrich.py                 Lapisan presentasi: wilayah, label ID, gabung pool pola
  es_indexer.py             Mapping index & bulk indexing Elasticsearch

components/
  filter_bar.py             Filter/slicer dipakai semua halaman
  cards.py                  KPI card, segment card, rule card, dst.
  charts.py                  Semua fungsi pembuat grafik (hover & warna konsisten)

pages/                     6 halaman (Dash Pages, routing otomatis dari nama file)
  ringkasan.py               "/"   - Ringkasan Eksekutif
  segmentasi.py               "/segmentasi"
  pola.py                     "/pola"
  anomali.py                   "/anomali"
  rekomendasi.py                "/rekomendasi"
  jelajah.py                    "/jelajah"

assets/style.css            Sistem desain (navy + emas, Space Grotesk/Inter/IBM Plex Mono)

tools/                      Skrip pengembangan/uji (BUKAN bagian dashboard produksi)
  generate_synthetic_data.py  Data uji ~6,3 juta baris
  build_rules_and_db.py        Skrip referensi awal (tambang pola + build DuckDB)
```
