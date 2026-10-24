import os
import time
import json
import requests
import numpy as np
from datetime import datetime
from supabase import create_client, Client
from google import genai
from google.genai import types

# --- CONFIGURAZIONE CREDENZIALI ---
SUPABASE_URL = "https://wgliaidollibufxesvqi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndnbGlhaWRvbGxpYnVmeGVzdnFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI4NDU5OTMsImV4cCI6MjEwODQyMTk5M30.Rld18wsMSHlWu35mDXqfWxAYj505aRZhhWMbJf4EYMQ"

GEMINI_API_KEY = "AIzaSyDVCNNLPXYkMZBc1JD2PWEYwdypWa2TGnA"

# Configurazione Telegram Ufficiale (@FlowIATradingBot)
TELEGRAM_BOT_TOKEN = "8613746316:AAFEQ-wOuA6eHKVBOkC8Jnxp3xdkCnmXAZc"
TELEGRAM_CHAT_ID = "941089324"

# Inizializzazione Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

ACTIVE_ASSET = "XAUUSD" 

def send_telegram_notification(message: str):
    """Invia una notifica push immediata su Telegram."""
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                print("[NOTIFICA] Inviata con successo su Telegram!")
            else:
                print(f"[ERRORE NOTIFICA TG]: {response.text}")
        except Exception as e:
            print(f"[ERRORE NOTIFICA]: {e}")

def calculate_rsi(prices, period=14):
    """Calcola matematicamente l'indicatore RSI."""
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up/down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100./(1. + rs)
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up/down if down != 0 else 0
        rsi[i] = 100. - 100./(1. + rs)
    return float(rsi[-1])

def fetch_and_filter_market_data(asset: str):
    """Scarica i dati storici e il prezzo spot esatto dell'Oro (XAU/USD) con gestione sicura dei mercati chiusi."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XAU=X?interval=5m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        # Controllo di sicurezza se il mercato è chiuso o i dati non sono disponibili
        if not data.get('chart') or not data['chart'].get('result'):
            print("[MERCATO CHIUSO / DATI ASSENTI] Impossibile recuperare il feed spot in questo momento.")
            return {"is_interesting": False, "asset": asset, "current_price": 0.0}
            
        result = data['chart']['result'][0]
        quotes = result['indicators']['quote'][0]
        
        closes = np.array([c for c in quotes['close'] if c is not None])
        volumes = np.array([v for v in quotes['volume'] if v is not None])
        
        if len(closes) < 10:
            print("[ATTENZIONE] Dati storici insufficienti ricevuti.")
            return {"is_interesting": False, "asset": asset, "current_price": 0.0}
            
        current_price = float(closes[-1])
        
        rsi_14 = calculate_rsi(closes, period=14) if len(closes) >= 14 else 50.0
        ema_9 = float(np.mean(closes[-9:])) if len(closes) >= 9 else current_price
        ema_21 = float(np.mean(closes[-21:])) if len(closes) >= 21 else current_price
        
        volume_ratio = 120.0 if len(volumes) == 0 else float((volumes[-1] / np.mean(volumes[-20:])) * 100) if np.mean(volumes[-20:]) > 0 else 100.0
        
        trend_m5 = "BULLISH" if current_price > ema_9 and ema_9 > ema_21 else "BEARISH"
        
        print(f"[DATI ORO SPOT] Prezzo: ${current_price:.2f} | RSI: {rsi_14:.2f} | Trend: {trend_m5}")
        
        is_interesting = (30 <= rsi_14 <= 70)
        
        return {
            "is_interesting": is_interesting,
            "asset": asset,
            "current_price": current_price,
            "rsi_14": round(rsi_14, 2),
            "ema_9": round(ema_9, 2),
            "ema_21": round(ema_21, 2),
            "volume_ratio": round(volume_ratio, 2),
            "calculated_trend": trend_m5,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"[ERRORE FETCH ORO SPOT]: {e}")
        return {"is_interesting": False, "asset": asset, "current_price": 0.0}

def generate_algorithmic_signal(market_data):
    """Genera un segnale basato sulla matematica per l'Oro con SL/TP calibrati."""
    price = market_data["current_price"]
    trend = market_data["calculated_trend"]
    direction = "BUY" if trend == "BULLISH" else "SELL"
    
    sl_distance = 3.50
    tp1_distance = 5.50
    tp2_distance = 11.00
    
    if direction == "BUY":
        stop_loss = round(price - sl_distance, 2)
        tp1 = round(price + tp1_distance, 2)
        tp2 = round(price + tp2_distance, 2)
    else:
        stop_loss = round(price + sl_distance, 2)
        tp1 = round(price - tp1_distance, 2)
        tp2 = round(price - tp2_distance, 2)
        
    return {
        "valid_signal": True,
        "direction": direction,
        "entry_price": price,
        "stop_loss": stop_loss,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "sl_pips": sl_distance,
        "risk_reward_ratio": round(tp1_distance / sl_distance, 2),
        "confluence_score": 7,
        "confluence_factors": ["Algorithmic Price Action", f"EMA Trend {trend}", "RSI Filter"],
        "note": "⚠️ Generato senza IA (Solo Algoritmo Matematico)"
    }

def analyze_market_with_ai(market_data):
    """Tenta l'analisi con Gemini, con fallback automatico."""
    price = market_data["current_price"]
    rsi = market_data["rsi_14"]
    trend = market_data["calculated_trend"]
    
    prompt = f"""
    Sei un Quantitative Trading Engine specializzato nello scalping su Oro (XAUUSD). Prezzo spot attuale: ${price}.
    - RSI: {rsi} | Trend M5: {trend}
    Restituisci ESCLUSIVAMENTE un JSON valido:
    {{
      "valid_signal": true,
      "direction": "BUY" o "SELL",
      "entry_price": {price},
      "stop_loss": float,
      "take_profit_1": float,
      "take_profit_2": float,
      "sl_pips": float,
      "risk_reward_ratio": float,
      "confluence_score": int (1-10),
      "confluence_factors": ["stringa 1", "stringa 2"]
    }}
    """
    
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            ),
        )
        result = json.loads(response.text)
        result["note"] = "✅ Analizzato e Validato da Gemini AI"
        return result
    except Exception as e:
        print(f"[AVVISO] Impossibile contattare Gemini. Attivo fallback matematico.")
        return generate_algorithmic_signal(market_data)

def save_and_notify(data, asset):
    try:
        if not data.get("valid_signal", True):
            return
        
        payload = {
            "asset": asset,
            "direction": data["direction"],
            "entry_price": data["entry_price"],
            "stop_loss": data["stop_loss"],
            "take_profit_1": data["take_profit_1"],
            "take_profit_2": data["take_profit_2"],
            "sl_pips": data.get("sl_pips", 3.5),
            "risk_reward_ratio": data.get("risk_reward_ratio", 1.5),
            "confluence_score": data.get("confluence_score", 7),
            "confluence_factors": data.get("confluence_factors", []),
            "status": "ACTIVE",
            "note": data.get("note", "Segnale Attivo")
        }
        
        supabase.table("signals").insert(payload).execute()
        print(f"[SEGNALE DB] 🚨 Segnale XAUUSD salvato nel database!")
        
        msg = (
            f"🚨 *SEGNALE XAUUSD VALIDATO* 🚨\n"
            f"_{payload['note']}_\n\n"
            f"Direzione: *{payload['direction']}*\n"
            f"📍 Entry: `{payload['entry_price']}`\n"
            f"🛑 Stop Loss: `{payload['stop_loss']}`\n"
            f"🎯 TP1: `{payload['take_profit_1']}` | TP2: `{payload['take_profit_2']}`\n"
        )
        send_telegram_notification(msg)
            
    except Exception as e:
        print(f"[ERRORE DB/NOTIFICA]: {e}")

def run_engine():
    print(f"--- Avvio Command Center XAUUSD Engine ---")
    
    while True:
        market_data = fetch_and_filter_market_data(ACTIVE_ASSET)
        
        if market_data["is_interesting"] and market_data["current_price"] > 0:
            print("[TRIGGER] Condizioni soddisfacenti su XAUUSD. Analisi in corso...")
            analysis = analyze_market_with_ai(market_data)
            save_and_notify(analysis, ACTIVE_ASSET)
        else:
            print("[SKIPPED] Mercato in attesa o dati non validi.")
        
        print("In attesa del prossimo ciclo (5 minuti)...\n")
        time.sleep(300)

if __name__ == "__main__":
    run_engine()