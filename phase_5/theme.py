"""
theme.py
========
Sistem desain terpusat untuk seluruh dashboard (warna, tipografi, dan template
grafik Plotly). Semua modul chart/komponen WAJIB mengambil warna dan style dari
sini supaya tampilan konsisten di semua halaman (termasuk hover, yang jadi
salah satu catatan dosen: "yang di graph ada yang di hover ada yang ga").

Filosofi palet: "ruang kendali risiko perbankan" - tenang, tegas, dapat
dipercaya, dengan satu aksen hangat (emas/tembaga) untuk menandai hal yang
butuh perhatian. Skala risiko memakai gradasi sejuk -> hangat -> panas
(bukan hijau/merah generik) supaya tetap enak dibaca dan tidak norak.
"""

# ---------------------------------------------------------------------------
# PALET WARNA
# ---------------------------------------------------------------------------

COLORS = {
    # Netral / permukaan
    "bg": "#F2F4F9",            # latar halaman (abu-biru sangat muda)
    "bg_alt": "#E9ECF4",        # latar sekunder (strip, hover row)
    "surface": "#FFFFFF",       # kartu / panel
    "surface_sunken": "#F7F8FC",# kotak info di dalam kartu
    "border": "#DFE3EE",
    "border_strong": "#C7CEE0",
    "ink": "#121A2E",            # teks utama
    "ink_soft": "#4B5468",       # teks sekunder
    "ink_faint": "#8A93A8",      # teks tersier / placeholder

    # Merek
    "brand": "#122A52",          # navy ledger - header, nav, judul
    "brand_deep": "#0B1B38",     # navy lebih gelap (hero gradient)
    "brand_soft": "#E7ECF7",     # tint navy sangat muda (chip/badge default)
    "accent": "#D99A3D",         # emas/tembaga - aksen, CTA, sorotan "penting"
    "accent_deep": "#B87B25",
    "accent_soft": "#FBEDD4",

    # Skala risiko sekuensial (Normal -> Kritis), sejuk -> panas
    "risk_normal": "#9AA6BC",
    "risk_low": "#4E9C86",
    "risk_medium": "#E3B04B",
    "risk_high": "#DB7C3F",
    "risk_critical": "#C1483F",

    # Kualitatif untuk 4 segmen nasabah (dibuat beda hue, saturasi mirip)
    "seg_0": "#2C5490",
    "seg_1": "#3E8E7E",
    "seg_2": "#8C6AA8",
    "seg_3": "#C98A46",

    # Status
    "success": "#3E8E63",
    "warning": "#D99A3D",
    "danger": "#C1483F",
    "info": "#3E6FA8",
}

# Urutan warna kategorikal default untuk grafik multi-kategori umum
CATEGORICAL_SEQUENCE = [
    COLORS["brand"], COLORS["accent"], COLORS["seg_1"], COLORS["seg_2"],
    COLORS["seg_3"], COLORS["info"], COLORS["danger"], COLORS["ink_faint"],
]

RISK_ORDER = ["Normal", "Rendah", "Sedang", "Tinggi", "Kritis"]
RISK_COLOR_MAP = {
    "Normal": COLORS["risk_normal"],
    "Rendah": COLORS["risk_low"],
    "Sedang": COLORS["risk_medium"],
    "Tinggi": COLORS["risk_high"],
    "Kritis": COLORS["risk_critical"],
}

SEGMENT_COLOR_LIST = [COLORS["seg_0"], COLORS["seg_1"], COLORS["seg_2"], COLORS["seg_3"]]


def segment_color(cluster_id):
    try:
        return SEGMENT_COLOR_LIST[int(cluster_id) % len(SEGMENT_COLOR_LIST)]
    except (ValueError, TypeError):
        return COLORS["ink_faint"]


# ---------------------------------------------------------------------------
# TIPOGRAFI
# ---------------------------------------------------------------------------
# - Space Grotesk : judul/heading (karakter geometris, terasa "analitik")
# - Inter         : UI & body copy (sangat terbaca untuk teks padat)
# - IBM Plex Mono : angka KPI & skor (kesan presisi "buku besar")

FONT_HEADING = "'Space Grotesk', 'Inter', sans-serif"
FONT_BODY = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace"

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;600;700&"
    "family=Inter:wght@400;500;600;700&"
    "family=IBM+Plex+Mono:wght@500;600&display=swap"
)

# ---------------------------------------------------------------------------
# TEMPLATE PLOTLY BERSAMA
# ---------------------------------------------------------------------------
# Dipakai oleh SEMUA fungsi pembuat grafik di components/charts.py supaya
# hover, font, dan warna latar konsisten di seluruh dashboard.

PLOTLY_LAYOUT_DEFAULTS = dict(
    font=dict(family=FONT_BODY, size=13, color=COLORS["ink"]),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel=dict(
        bgcolor=COLORS["brand_deep"],
        bordercolor=COLORS["brand_deep"],
        font=dict(family=FONT_BODY, size=12.5, color="#FFFFFF"),
        align="left",
    ),
    hovermode="closest",
    margin=dict(l=48, r=24, t=40, b=40),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=12), bgcolor="rgba(0,0,0,0)",
    ),
    xaxis=dict(
        gridcolor=COLORS["border"], zerolinecolor=COLORS["border"],
        showline=True, linecolor=COLORS["border_strong"], ticks="outside",
        tickcolor=COLORS["border"],
    ),
    yaxis=dict(
        gridcolor=COLORS["border"], zerolinecolor=COLORS["border"],
        showline=False,
    ),
)


def apply_theme(fig, *, legend=True, height=None):
    """Terapkan template visual standar ke sebuah Plotly figure.
    Panggil ini di akhir SETIAP fungsi pembuat grafik agar konsisten."""
    fig.update_layout(**PLOTLY_LAYOUT_DEFAULTS)
    if not legend:
        fig.update_layout(showlegend=False)
    if height:
        fig.update_layout(height=height)
    fig.update_layout(modebar_remove=[
        "lasso2d", "select2d", "autoScale2d", "toggleSpikelines"
    ])
    return fig


GRAPH_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}
