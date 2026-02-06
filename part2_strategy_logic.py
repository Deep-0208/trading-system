"""
Pivot ITM Trading System - Part 2: Strategy Logic & Data Fetching
Handles pivot calculation, bias determination, price fetching, and strategy logic
"""

import time
import logging
from datetime import datetime, date
import pandas as pd

# Import from Part 1
from part1_config_and_utils import (
    BIAS_CANDLE_START, BIAS_CANDLE_END, PIVOT_BUFFER_POINTS,
    MAX_RETRIES, RETRY_DELAY_SEC, MIN_SPOT_PRICE, MAX_SPOT_PRICE,
    MIN_OPTION_PRICE, MAX_OPTION_PRICE, NIFTY_LOT_SIZE,
    daily_bias, bias_lock_date, bias_candle_data, daily_pivot_point,
    instruments_data, instrument_lookup_cache, last_trading_date,
    executed_trades_count, current_position, last_status_timestamp,
    last_heartbeat_timestamp, spot_price_breaker, option_price_breaker,
    log_daily_bias_banner, generate_daily_report, load_instrument_data
)


# =============================================================================
# DAILY RESET & PIVOT CALCULATION
# =============================================================================

def reset_daily_state(groww):
    """Reset counters and fetch new pivot at start of trading day"""
    import part1_config_and_utils as config
    
    today = date.today()
    
    if config.last_trading_date == today:
        return  

    logging.info("")
    logging.info("=" * 80)
    logging.info(f"🔄 NEW TRADING DAY DETECTED: {today}")
    logging.info("=" * 80)

    # Generate previous day's report
    if config.last_trading_date is not None:
        logging.info(f"📊 Generating report for {config.last_trading_date}...")
        generate_daily_report(config.last_trading_date)

    # Reset all daily state
    logging.info("🧹 Resetting daily state variables...")
    config.executed_trades_count = 0
    config.current_position = None
    config.last_status_timestamp = None
    config.last_heartbeat_timestamp = None
    config.daily_bias = None
    config.bias_lock_date = None
    config.bias_candle_data = None
    config.spot_price_breaker.record_success()
    config.option_price_breaker.record_success()

    config.instrument_lookup_cache.clear()

    logging.info("✅ Daily state reset complete")
    logging.info(f"   • Trades executed: {config.executed_trades_count}")
    logging.info(f"   • Open position: {config.current_position}")
    logging.info(f"   • Daily bias: {config.daily_bias}")
    logging.info(f"   • Instrument cache cleared: {len(config.instrument_lookup_cache)} entries")

    # Reload instruments for new day
    logging.info("🔄 Reloading instrument data for new day...")
    load_instrument_data(groww)

    # Fetch new pivot
    logging.info("📍 Calculating pivot point for today...")
    config.daily_pivot_point = fetch_and_calculate_pivot(groww)
    
    if config.daily_pivot_point:
        logging.info("")
        logging.info("╔" + "═" * 78 + "╗")
        logging.info(f"║   📍 DAILY PIVOT POINT: {config.daily_pivot_point:.2f}".ljust(79) + "║")
        logging.info(f"║   📊 Pivot Zone: {config.daily_pivot_point - PIVOT_BUFFER_POINTS:.2f} - {config.daily_pivot_point + PIVOT_BUFFER_POINTS:.2f}".ljust(79) + "║")
        logging.info("╚" + "═" * 78 + "╝")
        logging.info("")
    else:
        logging.error("❌ CRITICAL: Failed to calculate pivot point")

    config.last_trading_date = today
    logging.info("=" * 80)
    logging.info("")


def fetch_and_calculate_pivot(groww):
    """Fetch previous day's OHLC and calculate pivot point"""
    try:
        logging.info("📡 Fetching historical data for pivot calculation...")
        
        # Fetch last 7 days of daily candles
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (7 * 24 * 60 * 60 * 1000)

        response = groww.get_historical_candle_data(
            trading_symbol="NIFTY",
            exchange=groww.EXCHANGE_NSE,
            segment=groww.SEGMENT_CASH,
            start_time=start_ms,
            end_time=end_ms,
            interval_in_minutes=1440  # Daily
        )

        candles = response.get("candles", [])
        if not candles:
            logging.error("❌ No candle data received from API")
            return None

        logging.info(f"📊 Received {len(candles)} daily candles")

        # Convert to DataFrame
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
        df["date"] = df["datetime"].dt.date

        # Get only completed trading days (before today)
        today = date.today()
        completed_days = df[df["date"] < today].copy()

        if completed_days.empty:
            logging.error("❌ No completed trading day found in historical data")
            return None

        # Get most recent completed day
        completed_days.sort_values("date", inplace=True)
        prev_day = completed_days.iloc[-1]

        high = float(prev_day["high"])
        low = float(prev_day["low"])
        close = float(prev_day["close"])
        prev_date = prev_day["date"]

        # Calculate pivot point: (H + L + C) / 3
        pivot = round((high + low + close) / 3, 2)

        logging.info("")
        logging.info("📊 PIVOT CALCULATION:")
        logging.info(f"   • Previous Day : {prev_date}")
        logging.info(f"   • High         : {high:.2f}")
        logging.info(f"   • Low          : {low:.2f}")
        logging.info(f"   • Close        : {close:.2f}")
        logging.info(f"   • Pivot        : {pivot:.2f}")
        logging.info(f"   • Formula      : (H + L + C) / 3 = ({high:.2f} + {low:.2f} + {close:.2f}) / 3")
        logging.info("")

        return pivot

    except Exception as e:
        logging.exception(f"❌ Failed to calculate pivot: {e}")
        return None


# =============================================================================
# PRICE FETCHING
# =============================================================================

def fetch_spot_price(groww):
    """Fetch NIFTY spot price with retry logic and circuit breaker"""
    if spot_price_breaker.is_open():
        logging.warning(f"⛔ Spot price circuit breaker is OPEN: {spot_price_breaker.status()}")
        return None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = groww.get_ltp(
                segment=groww.SEGMENT_CASH,
                exchange_trading_symbols="NSE_NIFTY"
            )

            spot = response.get("NSE_NIFTY")
            if spot is None:
                raise ValueError("Spot price not in API response")

            spot = float(spot)
            
            # Validate range
            if not (MIN_SPOT_PRICE <= spot <= MAX_SPOT_PRICE):
                logging.warning(f"⚠️  Spot price {spot:.2f} outside expected range [{MIN_SPOT_PRICE}-{MAX_SPOT_PRICE}]")
                if attempt < MAX_RETRIES:
                    logging.info(f"🔄 Retrying... ({attempt}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY_SEC)
                    continue
                spot_price_breaker.record_failure()
                return None

            spot_price_breaker.record_success()
            logging.debug(f"💹 Spot price fetched: {spot:.2f}")
            return spot

        except Exception as e:
            logging.error(f"❌ Spot fetch attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
            else:
                spot_price_breaker.record_failure()
                return None


def fetch_option_price(groww, symbol, segment):
    """Fetch option LTP with retry logic and circuit breaker"""
    if option_price_breaker.is_open():
        logging.warning(f"⛔ Option price circuit breaker is OPEN: {option_price_breaker.status()}")
        return None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            full_symbol = f"NSE_{symbol}"
            response = groww.get_ltp(
                exchange_trading_symbols=full_symbol,
                segment=segment
            )

            price = response.get(full_symbol)
            if price is None:
                raise ValueError("Option price not in API response")

            price = float(price)
            
            # Validate range
            if not (MIN_OPTION_PRICE <= price <= MAX_OPTION_PRICE):
                logging.warning(f"⚠️  Option price {price:.2f} outside expected range [{MIN_OPTION_PRICE}-{MAX_OPTION_PRICE}]")
                if attempt < MAX_RETRIES:
                    logging.info(f"🔄 Retrying... ({attempt}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY_SEC)
                    continue
                option_price_breaker.record_failure()
                return None

            option_price_breaker.record_success()
            logging.debug(f"💰 Option price fetched: {price:.2f} ({symbol})")
            return price

        except Exception as e:
            logging.error(f"❌ Option price attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
            else:
                option_price_breaker.record_failure()
                return None


# =============================================================================
# STRATEGY LOGIC
# =============================================================================

def get_first_5min_candle(groww):
    """Fetch first 5-minute candle of the day (09:15–09:20)"""
    today = date.today()

    # Step 1: create naive timestamps
    start_dt = pd.Timestamp.combine(
        today,
        pd.to_datetime(BIAS_CANDLE_START).time()
    )

    end_dt = pd.Timestamp.combine(
        today,
        pd.to_datetime(BIAS_CANDLE_END).time()
    )

    # Step 2: localize to IST
    start_dt = start_dt.tz_localize("Asia/Kolkata")
    end_dt = end_dt.tz_localize("Asia/Kolkata")

    # Convert to milliseconds
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    try:
        logging.info(f"📡 Fetching first candle data ({BIAS_CANDLE_START}-{BIAS_CANDLE_END})...")

        response = groww.get_historical_candle_data(
            trading_symbol="NIFTY",
            exchange=groww.EXCHANGE_NSE,
            segment=groww.SEGMENT_CASH,
            start_time=start_ms,
            end_time=end_ms,
            interval_in_minutes=5
        )

        candles = response.get("candles", [])
        if not candles:
            logging.warning("⚠️ No candle data available yet")
            return None

        c = candles[0]
        candle_data = {
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
        }

        logging.info(
            f"✅ First candle fetched: "
            f"O={candle_data['open']:.2f}, "
            f"H={candle_data['high']:.2f}, "
            f"L={candle_data['low']:.2f}, "
            f"C={candle_data['close']:.2f}"
        )

        return candle_data

    except Exception as e:
        logging.error(f"❌ Failed to fetch first candle: {e}")
        return None


def determine_daily_bias(groww):
    """Decide daily bias using FIRST 5-min candle vs pivot"""
    import part1_config_and_utils as config
    
    if config.daily_bias is not None:
        return  # Bias already locked

    if config.daily_pivot_point is None:
        logging.error("❌ Pivot not available — cannot determine bias")
        return

    # Check if we're past bias candle time
    now = datetime.now().time()
    bias_end_time = datetime.strptime(BIAS_CANDLE_END, "%H:%M").time()
    
    if now < bias_end_time:
        logging.debug(f"⏳ Waiting for bias candle completion ({BIAS_CANDLE_END})")
        return

    first_candle = get_first_5min_candle(groww)
    if first_candle is None:
        return  # Candle not ready yet

    close_price = first_candle["close"]

    # Determine bias
    if close_price > config.daily_pivot_point:
        config.daily_bias = "BULLISH"
    elif close_price < config.daily_pivot_point:
        config.daily_bias = "BEARISH"
    else:
        logging.info("")
        logging.info("⚖️  FIRST CANDLE CLOSED EXACTLY AT PIVOT - NO CLEAR BIAS")
        logging.info("⛔ NO TRADE TODAY - Waiting for next trading day")
        logging.info("")
        config.daily_bias = "NEUTRAL"  # Mark as determined but no trade
        return

    config.bias_lock_date = date.today()
    config.bias_candle_data = first_candle

    log_daily_bias_banner(
        first_candle=first_candle,
        pivot=config.daily_pivot_point,
        bias=config.daily_bias
    )


def is_in_pivot_zone(spot, pivot):
    """
    ⚠️ CRITICAL STRATEGY CHECK ⚠️
    Check if spot is within pivot pullback zone
    This is THE CORE of our entry logic
    """
    lower = pivot - PIVOT_BUFFER_POINTS
    upper = pivot + PIVOT_BUFFER_POINTS
    distance_from_pivot = spot - pivot

    in_zone = lower <= spot <= upper

    if in_zone:
        logging.info("=" * 80)
        logging.info("✅ SPOT IS IN PIVOT ZONE - PULLBACK DETECTED")
        logging.info(f"   📍 Pivot       : {pivot:.2f}")
        logging.info(f"   📊 Spot        : {spot:.2f}")
        logging.info(f"   📏 Distance    : {distance_from_pivot:+.2f} points from pivot")
        logging.info(f"   🎯 Valid Zone  : {lower:.2f} to {upper:.2f}")
        logging.info("   ✅ Entry condition MET - Ready to trade")
        logging.info("=" * 80)
        return True

    logging.info(
        f"⏳ Waiting for pivot pullback | "
        f"Spot={spot:.2f} | "
        f"Pivot={pivot:.2f} | "
        f"Distance={distance_from_pivot:+.2f} pts"
    )

    return False


def calculate_itm_strike(spot, direction):
    """Calculate near-ITM strike (100-point multiples)"""
    if direction == "CALL":
        strike = int(spot // 100) * 100
        logging.info(f"🎯 ITM CALL Strike: {strike:.0f} (spot: {spot:.2f})")
    elif direction == "PUT":
        strike = int((spot + 99) // 100) * 100
        logging.info(f"🎯 ITM PUT Strike: {strike:.0f} (spot: {spot:.2f})")
    else:
        return None
    
    return strike


def get_nearest_valid_expiry(underlying):
    """
    Select nearest valid expiry from Groww instruments CSV
    RULE: expiry_date >= today
    """
    import part1_config_and_utils as config
    today = date.today()

    df = config.instruments_data[
        (config.instruments_data["underlying_symbol"] == underlying) &
        (config.instruments_data["segment"] == "FNO")
    ].copy()

    df["expiry_date"] = pd.to_datetime(df["expiry_date"]).dt.date

    future_expiries = sorted(d for d in df["expiry_date"].unique() if d >= today)

    # WEEKLY = nearest expiry (<= 7 days away)
    weekly_expiries = [d for d in future_expiries if (d - today).days <= 7]

    if not weekly_expiries:
        logging.error("❌ No weekly expiry found")
        return None

    nearest = weekly_expiries[0]
    logging.info(f"📆 Nearest valid expiry selected: {nearest}")
    return nearest


# =============================================================================
# INSTRUMENT LOOKUP
# =============================================================================

def find_option_instrument(underlying, expiry, strike, option_type):
    """Find nearest available option with caching"""
    import part1_config_and_utils as config
    
    cache_key = f"{underlying}_{expiry}_{strike}_{option_type}"
    if cache_key in config.instrument_lookup_cache:
        logging.debug(f"📦 Using cached instrument: {cache_key}")
        return config.instrument_lookup_cache[cache_key]

    logging.info(f"🔍 Searching for {option_type} option: Strike {strike}, Expiry {expiry}")

    expiry = pd.to_datetime(expiry).date()

    filtered = config.instruments_data[
        (config.instruments_data["underlying_symbol"] == underlying) &
        (pd.to_datetime(config.instruments_data["expiry_date"]).dt.date == expiry) &
        (config.instruments_data["instrument_type"] == option_type)
    ].copy()
    
    # 🔒 Ensure option is BUY-allowed (Groww rule)
    filtered = filtered[filtered["buy_allowed"] == 1]

    if filtered.empty:
        logging.error(
            f"❌ No BUY-allowed {option_type} options found | Expiry={expiry}"
        )
        return None

    filtered["strike_price"] = pd.to_numeric(filtered["strike_price"], errors="coerce")
    filtered = filtered.dropna(subset=["strike_price"])

    if filtered.empty:
        logging.error("❌ No valid strike prices found")
        return None

    filtered["strike_diff"] = (filtered["strike_price"] - strike).abs()
    filtered.sort_values("strike_diff", inplace=True)
    nearest = filtered.iloc[0]

    if int(nearest["lot_size"]) != NIFTY_LOT_SIZE:
        logging.error(
            f"❌ LOT SIZE MISMATCH | Expected={NIFTY_LOT_SIZE}, "
            f"Got={nearest['lot_size']} | {nearest['trading_symbol']}"
        )
        return None
    
    logging.info(f"✅ Instrument found: {nearest['trading_symbol']}")
    logging.info(f"   Requested Strike: {strike}")
    logging.info(f"   Actual Strike   : {nearest['strike_price']}")
    logging.info(f"   Lot Size        : {nearest['lot_size']}")

    result = {
        "symbol": nearest["trading_symbol"],
        "segment": nearest["segment"],
        "lot_size": nearest["lot_size"],
        "strike": nearest["strike_price"]
    }

    config.instrument_lookup_cache[cache_key] = result
    return result
