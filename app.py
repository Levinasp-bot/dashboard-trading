import streamlit as st
import pandas as pd
import glob
import os
import plotly.graph_objects as go
import requests
import certifi

st.set_page_config(layout="wide")

st.sidebar.title("📌 Pilih Aset")
asset_type = st.sidebar.selectbox("Pilih Jenis Aset", ["Saham", "Cryptocurrency"])

def get_crypto_data(symbol, interval='1d', limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    response = requests.get(url, params=params, timeout=10, verify=certifi.where())
    data = response.json()

    df = pd.DataFrame(data, columns=[
        "Open Time", "Open", "High", "Low", "Close", "Volume",
        "Close Time", "Quote Asset Volume", "Number of Trades",
        "Taker Buy Base Asset Volume", "Taker Buy Quote Asset Volume", "Ignore"
    ])
    df["Open Time"] = pd.to_datetime(df["Open Time"], unit='ms')
    df["Close Time"] = pd.to_datetime(df["Close Time"], unit='ms')
    numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
    df[numeric_columns] = df[numeric_columns].astype(float)

    return df

# ======================== PROSES UNTUK DATA SAHAM ========================
if asset_type == "Saham":
    folder_path = "data saham/"
    file_list = glob.glob(os.path.join(folder_path, "Ringkasan Saham-*.xlsx"))

    if not file_list:
        st.error("❌ Tidak ditemukan file Ringkasan Saham di folder 'data saham'")
        st.stop()

    all_data = []
    for file in file_list:
        df = pd.read_excel(file)
        filename = os.path.basename(file)
        date_str = filename.split("-")[-1].split(".")[0]
        df["Tanggal"] = pd.to_datetime(date_str, format="%Y%m%d")
        all_data.append(df)

    df_all = pd.concat(all_data, ignore_index=True)

    required_columns = {"Kode Saham", "Open Price", "Tertinggi", "Terendah", "Penutupan", "Volume", "Frekuensi"}
    if not required_columns.issubset(df_all.columns):
        st.error(f"⚠️ Struktur kolom tidak sesuai. Pastikan file memiliki kolom: {required_columns}")
        st.stop()

    adjusted_open_file = os.path.join(folder_path, "data_saham_adjusted_open.csv")
    if not os.path.exists(adjusted_open_file):
        st.error("❌ File 'data_saham_adjusted_open.csv' tidak ditemukan di folder 'data saham'")
        st.stop()

    df_adjusted_open = pd.read_csv(adjusted_open_file)
    df_adjusted_open.rename(columns={"Code": "Kode Saham", "Date": "Tanggal"}, inplace=True)
    df_adjusted_open["Tanggal"] = pd.to_datetime(df_adjusted_open["Tanggal"])
    df_all["Tanggal"] = pd.to_datetime(df_all["Tanggal"])
    df_all = df_all.merge(df_adjusted_open, on=["Kode Saham", "Tanggal"], how="left")
    df_all["Open Price"] = df_all["Open Price"].combine_first(df_all["AdjustedOpenPrice"])

    missing_open = df_all[df_all["Open Price"].isna()]
    if not missing_open.empty:
        st.warning(f"⚠️ Masih ada {len(missing_open)} data Open Price yang kosong setelah pengambilan dari AdjustedOpenPrice.")

    saham_options = sorted(df_all["Kode Saham"].unique())
    selected_stock = st.sidebar.selectbox("Pilih Saham", options=saham_options)

    df_selected = df_all[df_all["Kode Saham"] == selected_stock].copy()
    if df_selected.empty:
        st.warning(f"⚠️ Tidak ada data untuk kode saham {selected_stock}")
        st.stop()

    df_selected = df_selected.sort_values(by="Tanggal")
    full_date_range = pd.date_range(start=df_selected["Tanggal"].min(), end=df_selected["Tanggal"].max())
    df_selected = df_selected.set_index("Tanggal").reindex(full_date_range).reset_index()
    df_selected.rename(columns={"index": "Tanggal"}, inplace=True)
    df_selected.fillna(method="ffill", inplace=True)

    df_selected["Frequency Analyzer"] = (df_selected["Volume"] / df_selected["Frekuensi"]) ** 3

    min_price = df_selected["Terendah"].min()
    max_price = df_selected["Tertinggi"].max()
    min_fa = df_selected["Frequency Analyzer"].min()
    max_fa = df_selected["Frequency Analyzer"].max()

    df_selected["Frequency Analyzer Scaled"] = min_price + (
        (df_selected["Frequency Analyzer"] - min_fa) / (max_fa - min_fa) * (max_price - min_price)
    )

    min_date = df_selected["Tanggal"].min()
    max_date = df_selected["Tanggal"].max()

    start_date, end_date = st.sidebar.slider(
        "Pilih Rentang Tanggal",
        min_value=min_date.to_pydatetime(),
        max_value=max_date.to_pydatetime(),
        value=(min_date.to_pydatetime(), max_date.to_pydatetime())
    )

    df_filtered = df_selected[(df_selected["Tanggal"] >= start_date) & (df_selected["Tanggal"] <= end_date)].copy()

    if df_filtered.empty:
        st.warning("⚠️ Tidak ada data dalam rentang tanggal yang dipilih.")
        st.stop()

    tv_embed_code = f"""
    <iframe src="https://s.tradingview.com/widgetembed/?symbol=IDX:{selected_stock}&interval=D&theme=dark&style=1&locale=id&toolbar_bg=161616"
    width="100%" height="500" frameborder="0" allowtransparency="true" scrolling="no"></iframe>
    """
    st.markdown(tv_embed_code, unsafe_allow_html=True)

    fig_analyzer = go.Figure()
    fig_analyzer.add_trace(go.Scatter(
        x=df_filtered["Tanggal"],
        y=df_filtered["Frequency Analyzer"],
        mode="lines",
        name="Frequency Analyzer",
        line=dict(color="green", width=1),
        yaxis="y1"
    ))
    fig_analyzer.add_trace(go.Scatter(
        x=df_filtered["Tanggal"],
        y=df_filtered["Penutupan"],
        mode="lines",
        name="Closes",
        line=dict(color="orange", width=1),
        yaxis="y2"
    ))

    fig_analyzer.update_layout(
        title="Frequency Analyzer with Price Overlay",
        xaxis=dict(title="Tanggal"),
        yaxis=dict(title="Analyzed Frequency", tickfont=dict(color="green")),
        yaxis2=dict(title="Closes", overlaying="y", side="right", tickfont=dict(color="orange")),
        template="plotly_dark",
        legend=dict(x=0.01, y=0.99)
    )

    st.plotly_chart(fig_analyzer, use_container_width=True)

elif asset_type == "Cryptocurrency":
    crypto_options = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "EURUSDT"]  # Tambah coin lainnya jika perlu
    selected_crypto = st.sidebar.selectbox("Pilih Cryptocurrency", options=crypto_options)

    # Dropdown pilih timeframe
    timeframe_options = {
        "1 Hari": "1d",
        "4 Jam": "4h",
        "1 Jam": "1h",
        "15 Menit": "15m"
    }
    selected_timeframe_label = st.sidebar.selectbox("Pilih Timeframe", options=list(timeframe_options.keys()))
    selected_interval = timeframe_options[selected_timeframe_label]

    # Ambil data crypto sesuai interval
    df_crypto = get_crypto_data(selected_crypto, interval=selected_interval)

    # Mapping interval untuk embed TradingView
    tv_interval_map = {
        "1d": "D",
        "4h": "240",
        "1h": "60",
        "15m": "15"
    }
    tv_interval = tv_interval_map.get(selected_interval, "D")

    # TradingView embed (https://www.tradingview.com/widget/advanced-chart/)
    tv_embed_code = f"""
    <iframe src="https://s.tradingview.com/widgetembed/?symbol=BINANCE%3A{selected_crypto}&interval={tv_interval}&theme=dark&style=1&locale=id&toolbar_bg=161616"
    width="100%" height="500" frameborder="0" allowtransparency="true" scrolling="no"></iframe>
    """
    st.markdown(tv_embed_code, unsafe_allow_html=True)

    # Hitung Frequency Analyzer
    df_crypto["Frequency Analyzer"] = (df_crypto["Volume"] / df_crypto["Number of Trades"]) ** 3

    # Normalisasi Frequency Analyzer ke skala harga untuk overlay (jika dibutuhkan)
    min_price = df_crypto["Low"].min()
    max_price = df_crypto["High"].max()
    min_fa = df_crypto["Frequency Analyzer"].min()
    max_fa = df_crypto["Frequency Analyzer"].max()

    df_crypto["Frequency Analyzer Scaled"] = min_price + (
        (df_crypto["Frequency Analyzer"] - min_fa) / (max_fa - min_fa) * (max_price - min_price)
    )

    # Filter tanggal dengan slider
    min_date = df_crypto["Open Time"].min()
    max_date = df_crypto["Open Time"].max()

    min_date = pd.to_datetime(min_date).to_pydatetime()
    max_date = pd.to_datetime(max_date).to_pydatetime()

    start_date, end_date = st.sidebar.slider(
        "Pilih Rentang Tanggal",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date)
    )

    df_filtered = df_crypto[(df_crypto["Open Time"] >= start_date) & (df_crypto["Open Time"] <= end_date)].copy()
    if df_filtered.empty:
        st.warning("⚠️ Tidak ada data dalam rentang tanggal yang dipilih.")
        st.stop()

    # Info timeframe yang sedang digunakan
    st.info(f"Timeframe dipilih: {selected_timeframe_label} ({selected_interval})")

    # Chart: Frequency Analyzer + Harga Penutupan
    fig_analyzer = go.Figure()
    fig_analyzer.add_trace(go.Scatter(
        x=df_filtered["Open Time"],
        y=df_filtered["Frequency Analyzer"],
        mode="lines",
        name="Frequency Analyzer",
        line=dict(color="green", width=1),
        yaxis="y1"
    ))
    fig_analyzer.add_trace(go.Scatter(
        x=df_filtered["Open Time"],
        y=df_filtered["Close"],
        mode="lines",
        name="Close Price",
        line=dict(color="orange", width=1),
        yaxis="y2"
    ))

    fig_analyzer.update_layout(
        title=f"Frequency Analyzer with Price Overlay for {selected_crypto}",
        xaxis=dict(title="Tanggal"),
        yaxis=dict(title="Analyzed Frequency", tickfont=dict(color="green")),
        yaxis2=dict(title="Close Price (USDT)", overlaying="y", side="right", tickfont=dict(color="orange")),
        template="plotly_dark",
        legend=dict(x=0.01, y=0.99)
    )

    st.plotly_chart(fig_analyzer, use_container_width=True)

