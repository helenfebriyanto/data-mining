"""
app.py
=======
Entry point dashboard. Menjalankan:

    python app.py

Backend data dipilih OTOMATIS saat startup:
1) Coba Elasticsearch (ELASTICSEARCH_URL, default http://localhost:9200).
2) Kalau tidak terjangkau, otomatis pakai DuckDB (data/fance_dashboard.duckdb).
Status backend yang aktif ditampilkan di badge pojok kanan atas setiap halaman
supaya transparan ke pengguna (dan dosen) data sedang dilayani dari mana.

Jalankan `python -m pipeline.flow --mode synthetic` (atau --mode real) dulu
kalau data/fance_dashboard.duckdb belum ada.
"""
from __future__ import annotations

import logging
import os

import dash
from dash import Dash, html, dcc, Input, Output

import config as cfg
from theme import GOOGLE_FONTS_URL
from data_backend.base import DataBackend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fance-dashboard")


def pilih_backend() -> DataBackend:
    """Coba Elasticsearch dulu (sesuai permintaan awal proyek), fallback ke
    DuckDB kalau tidak menyala - dashboard TIDAK PERNAH gagal total hanya
    karena satu servis mati."""
    import logging as _logging
    _logging.getLogger("elastic_transport").setLevel(_logging.CRITICAL)

    force = cfg.FORCE_BACKEND
    if force != "duckdb":
        try:
            from data_backend.es_backend import ElasticsearchBackend
            es = ElasticsearchBackend(cfg.ELASTICSEARCH_URL, timeout=2)
            es.client = es.client.options(max_retries=0)
            if es.ping():
                logger.info(f"✅ Elasticsearch aktif di {cfg.ELASTICSEARCH_URL} - dashboard memakai Elasticsearch.")
                return es
            logger.warning(f"Elasticsearch di {cfg.ELASTICSEARCH_URL} tidak merespons ping - beralih ke DuckDB.")
        except Exception as e:
            logger.warning(f"Elasticsearch tidak tersedia ({e}) - beralih ke DuckDB.")

    from data_backend.duckdb_backend import DuckDBBackend
    if not os.path.exists(cfg.DUCKDB_PATH):
        raise FileNotFoundError(
            f"Tidak menemukan {cfg.DUCKDB_PATH}. Jalankan dulu:\n"
            f"  python -m pipeline.flow --mode synthetic   (data uji)\n"
            f"  python -m pipeline.flow --mode real --data-root <folder>   (data asli)"
        )
    logger.info(f"✅ DuckDB aktif ({cfg.DUCKDB_PATH}) - dashboard memakai mode lokal DuckDB.")
    return DuckDBBackend(cfg.DUCKDB_PATH, read_only=True)


BACKEND = pilih_backend()

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="Dashboard Deteksi Fraud Perbankan — Kelompok Fance",
    update_title=None,
    index_string=f"""<!DOCTYPE html>
<html lang="id">
<head>
    {{%metas%}}
    <title>{{%title%}}</title>
    {{%favicon%}}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="{GOOGLE_FONTS_URL}" rel="stylesheet">
    {{%css%}}
</head>
<body>
    {{%app_entry%}}
    <footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer>
</body>
</html>""",
)
server = app.server

NAV_ITEMS = [
    ("/", "Ringkasan Eksekutif", "📊"),
    ("/segmentasi", "Segmentasi Nasabah", "🧩"),
    ("/pola", "Pola & Asosiasi", "🔗"),
    ("/anomali", "Aktivitas Tidak Wajar", "🚨"),
    ("/rekomendasi", "Rekomendasi", "✅"),
    ("/jelajah", "Jelajah Data", "🔍"),
]


def navbar(pathname: str) -> html.Div:
    links = []
    for path, label, icon in NAV_ITEMS:
        active = (pathname == path) or (path != "/" and pathname and pathname.startswith(path))
        links.append(dcc.Link(
            [html.Span(icon, className="nav-icon"), html.Span(label)],
            href=path, className="nav-link" + (" nav-link-active" if active else ""),
        ))
    backend_badge = html.Div([
        html.Span("●", className="backend-dot"),
        html.Span(f"Sumber data: {'Elasticsearch' if BACKEND.name == 'elasticsearch' else 'DuckDB (lokal)'}"),
    ], className=f"backend-badge backend-badge-{BACKEND.name}")

    return html.Div([
        html.Div([
            html.Div([
                html.Span("🏦", className="brand-icon"),
                html.Div([
                    html.Div("Deteksi Fraud Perbankan", className="brand-title"),
                    html.Div("Kelompok Fance — Data Mining Project Phase 5", className="brand-subtitle"),
                ]),
            ], className="brand"),
            backend_badge,
        ], className="navbar-top"),
        html.Div(links, className="navbar-links"),
    ], className="navbar")


app.layout = html.Div([
    dcc.Location(id="url"),
    html.Div(id="navbar-container"),
    html.Div(dash.page_container, className="page-content"),
    html.Footer([
        html.P([
            "Dashboard dibangun di atas hasil analisis Phase 1-4 (preprocessing, segmentasi, pola asosiasi, "
            "deteksi anomali). ", html.Span(cfg.WILAYAH_DISCLOSURE, className="footer-disclosure"),
        ]),
    ], className="app-footer"),
], className="app-shell")


@app.callback(Output("navbar-container", "children"), Input("url", "pathname"))
def _update_navbar(pathname):
    return navbar(pathname)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=port)
