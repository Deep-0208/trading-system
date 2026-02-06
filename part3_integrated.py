"""
Pivot ITM Trading System - Part 3: Position Management & Main Loop (WITH DASHBOARD)
Handles position entry/exit, order execution, and main trading loop
INTEGRATED WITH REAL-TIME DASHBOARD
"""

import sys
import time
import logging
from datetime import datetime

# Import from Part 1
from part1_config_and_utils import (
    TRADING_MODE, MAX_DAILY_TRADES, NIFTY_LOT_SIZE, TRADE_LOTS,
    STOP_LOSS_PERCENT, PROFIT_TARGET_PERCENT, EOD_EXIT, ENTRY_CUTOFF,
    BIAS_CANDLE_END, executed_trades_count, current_position,
    last_heartbeat_timestamp, HEARTBEAT_INTERVAL_SEC,
    log_trade_to_journal, log_system_heartbeat, generate_daily_report,
    is_trading_day, is_market_open, get_sleep_duration,
    initialize_logging, log_strategy_banner, initialize_groww_api,
    load_instrument_data
)

# Import from Part 2
from part2_strategy_logic import (
    reset_daily_state, fetch_spot_price, fetch_option_price,
    determine_daily_bias, is_in_pivot_zone, calculate_itm_strike,
    get_nearest_valid_expiry, find_option_instrument
)

# ============================================================================
# 🆕 DASHBOARD INTEGRATION - ADD THESE IMPORTS
# ============================================================================
from shared_state import state
from dashboard_server import start_dashboard


# =============================================================================
# POSITION MANAGEMENT
# =============================================================================

def calculate_position_size(option_price):
    """
    FIXED LOT POSITION SIZING
    Quantity = LOT_SIZE × TRADE_LOTS
    """
    if option_price <= 0:
        logging.error(f"❌ Invalid option price: {option_price}")
        return 0

    quantity = NIFTY_LOT_SIZE * TRADE_LOTS
    total_investment = option_price * quantity

    logging.info("=" * 60)
    logging.info("📊 FIXED LOT POSITION SIZE")
    logging.info(f"   📦 Lot Size        : {NIFTY_LOT_SIZE}")
    logging.info(f"   🔢 Trade Lots      : {TRADE_LOTS}")
    logging.info(f"   📊 Total Quantity  : {quantity}")
    logging.info(f"   💰 Option Price    : ₹{option_price:.2f}")
    logging.info(f"   💸 Investment      : ₹{total_investment:,.2f}")
    logging.info("=" * 60)

    return quantity


def can_enter_trade():
    """Check if new trade can be entered"""
    import part1_config_and_utils as config
    
    if config.executed_trades_count >= MAX_DAILY_TRADES:
        logging.warning(f"⛔ TRADE LIMIT REACHED | Executed: {config.executed_trades_count}/{MAX_DAILY_TRADES}")
        return False
    
    if config.current_position is not None:
        logging.debug("⏸️  Position already open - cannot enter new trade")
        return False
    
    return True


def enter_position(groww, direction, symbol, segment, pivot):
    """Execute trade entry with comprehensive logging"""
    import part1_config_and_utils as config
    
    if not can_enter_trade():
        return None

    option_price = fetch_option_price(groww, symbol, segment)
    time.sleep(0.5)
    confirm_price = fetch_option_price(groww, symbol, segment)

    if (
        confirm_price is None or
        option_price is None or
        option_price <= 0 or
        confirm_price <= 0 or
        abs(confirm_price - option_price) / option_price > 0.05
    ):
        logging.error("❌ Option price unstable / invalid — entry aborted")
        # 🆕 DASHBOARD UPDATE
        state.add_event("Entry aborted - price unstable")
        return None

    option_price = confirm_price
    
    if option_price is None:
        logging.error("❌ Cannot proceed without option price")
        return None

    qty = calculate_position_size(option_price)
    if qty != NIFTY_LOT_SIZE * TRADE_LOTS:
        logging.error("❌ Quantity mismatch — aborting trade")
        return None

    if qty <= 0:
        logging.error("❌ Cannot enter position - invalid quantity")
        return None

    invested = option_price * qty
    paper_buy(symbol, qty, option_price)
    config.executed_trades_count += 1

    profit_target = round(option_price * (1 + PROFIT_TARGET_PERCENT), 2)
    stop_loss = round(option_price * (1 - STOP_LOSS_PERCENT), 2)

    logging.info("")
    logging.info("╔" + "═" * 78 + "╗")
    logging.info("║" + " " * 78 + "║")
    logging.info("║" + "              ✅ TRADE ENTRY EXECUTED ✅".center(78) + "║")
    logging.info("║" + " " * 78 + "║")
    logging.info("╚" + "═" * 78 + "╝")
    logging.info("")
    logging.info(f"📄 Symbol          : {symbol}")
    logging.info(f"➡️  Direction       : BUY {direction}")
    logging.info(f"💰 Entry Price     : ₹{option_price:.2f}")
    logging.info(f"📦 Quantity        : {qty}")
    logging.info(f"💵 Total Invested  : ₹{invested:,.2f}")
    logging.info(f"🎯 Profit Target   : ₹{profit_target:.2f} (+{PROFIT_TARGET_PERCENT*100:.0f}%)")
    logging.info(f"🛑 Stop Loss       : ₹{stop_loss:.2f} (-{STOP_LOSS_PERCENT*100:.0f}%)")
    logging.info(f"📍 Pivot Reference : {pivot:.2f}")
    logging.info(f"🔢 Trade Count     : {config.executed_trades_count}/{MAX_DAILY_TRADES}")
    logging.info(f"⏰ Entry Time      : {datetime.now().strftime('%H:%M:%S')}")
    logging.info("=" * 80)
    logging.info("")

    config.current_position = {
        "symbol": symbol,
        "segment": segment,
        "direction": direction,
        "entry_price": option_price,
        "quantity": qty,
        "entry_time": datetime.now(),
        "invested": invested,
        "profit_target": profit_target,
        "stop_loss": stop_loss,
        "pivot": pivot
    }

    # ============================================================================
    # 🆕 DASHBOARD UPDATE - Enter Trade
    # ============================================================================
    state.enter_trade(
        symbol=symbol,
        direction=direction,
        entry_price=option_price,
        quantity=qty,
        stop_loss=stop_loss,
        profit_target=profit_target
    )
    state.update_strategy_status("IN_TRADE")

    return config.current_position


def exit_position(exit_price, reason):
    """Exit current position with detailed logging"""
    import part1_config_and_utils as config
    
    if config.current_position is None:
        return

    paper_sell(
        symbol=config.current_position["symbol"],
        quantity=config.current_position["quantity"],
        price=exit_price,
        reason=reason
    )
    
    pnl = (exit_price - config.current_position['entry_price']) * config.current_position['quantity']
    pnl_pct = ((exit_price - config.current_position['entry_price']) / config.current_position['entry_price']) * 100
    
    result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
    
    logging.info("")
    logging.info("╔" + "═" * 78 + "╗")
    logging.info("║" + " " * 78 + "║")
    logging.info("║" + f"              {result_emoji} TRADE EXIT {result_emoji}".center(78) + "║")
    logging.info("║" + " " * 78 + "║")
    logging.info("╚" + "═" * 78 + "╝")
    logging.info("")
    logging.info(f"📄 Symbol         : {config.current_position['symbol']}")
    logging.info(f"➡️  Direction      : {config.current_position['direction']}")
    logging.info(f"💰 Entry Price    : ₹{config.current_position['entry_price']:.2f}")
    logging.info(f"💸 Exit Price     : ₹{exit_price:.2f}")
    logging.info(f"📊 P&L Amount     : ₹{pnl:,.2f}")
    logging.info(f"📈 P&L Percentage : {pnl_pct:+.2f}%")
    logging.info(f"🚪 Exit Reason    : {reason}")
    logging.info(f"⏱️  Duration       : {datetime.now() - config.current_position['entry_time']}")
    logging.info("=" * 80)
    logging.info("")

    log_trade_to_journal(config.current_position, exit_price, reason)
    
    # ============================================================================
    # 🆕 DASHBOARD UPDATE - Exit Trade
    # ============================================================================
    state.exit_trade(exit_price, reason)
    
    # Update status based on trade count
    if config.executed_trades_count >= MAX_DAILY_TRADES:
        state.update_strategy_status("TRADE_LIMIT_REACHED")
    else:
        state.update_strategy_status("WAITING_FOR_SETUP")
    
    config.current_position = None


def check_stop_loss(groww):
    """Check if stop loss is hit"""
    import part1_config_and_utils as config
    
    if config.current_position is None:
        return

    price = fetch_option_price(groww, config.current_position["symbol"], config.current_position["segment"])
    if price is None:
        return

    # ============================================================================
    # 🆕 DASHBOARD UPDATE - Update current price
    # ============================================================================
    state.update_trade_price(price)

    if price <= config.current_position["stop_loss"]:
        logging.warning("🛑 STOP LOSS TRIGGERED")
        exit_position(price, "STOP_LOSS")


def check_profit_target(groww):
    """Check if profit target is hit"""
    import part1_config_and_utils as config
    
    if config.current_position is None:
        return

    price = fetch_option_price(groww, config.current_position["symbol"], config.current_position["segment"])
    if price is None:
        return

    # ============================================================================
    # 🆕 DASHBOARD UPDATE - Update current price
    # ============================================================================
    state.update_trade_price(price)

    if price >= config.current_position["profit_target"]:
        logging.info("🎯 PROFIT TARGET HIT")
        exit_position(price, "PROFIT_TARGET")


def force_eod_exit(groww):
    """Force exit before market close"""
    import part1_config_and_utils as config
    
    if config.current_position is None:
        return

    logging.warning("⏰ END-OF-DAY EXIT TRIGGERED")
    
    # 🆕 DASHBOARD UPDATE
    state.add_event("EOD exit triggered")
    
    price = fetch_option_price(groww, config.current_position["symbol"], config.current_position["segment"])
    exit_price = price if price else config.current_position["entry_price"]
    
    exit_position(exit_price, "EOD_EXIT")


# =============================================================================
# PAPER ORDER EXECUTION (NO REAL ORDERS)
# =============================================================================

def paper_buy(symbol, quantity, price):
    """Simulate BUY order in PAPER mode"""
    logging.info("📝 PAPER BUY ORDER EXECUTED")
    logging.info(f"   📄 Symbol   : {symbol}")
    logging.info(f"   📦 Quantity : {quantity}")
    logging.info(f"   💰 Price    : ₹{price:.2f}")
    logging.info(f"   🧪 Mode     : PAPER")
    return True


def paper_sell(symbol, quantity, price, reason):
    """Simulate SELL order in PAPER mode"""
    logging.info("📝 PAPER SELL ORDER EXECUTED")
    logging.info(f"   📄 Symbol   : {symbol}")
    logging.info(f"   📦 Quantity : {quantity}")
    logging.info(f"   💰 Price    : ₹{price:.2f}")
    logging.info(f"   🚪 Reason   : {reason}")
    logging.info(f"   🧪 Mode     : PAPER")
    return True


# =============================================================================
# MAIN TRADING LOOP (WITH DASHBOARD UPDATES)
# =============================================================================

def run_trading_loop(groww):
    """Main trading loop with enhanced logging and dashboard updates"""
    import part1_config_and_utils as config
    
    logging.info("🚀 TRADING LOOP STARTED")
    config.last_status_timestamp = datetime.now()
    config.last_heartbeat_timestamp = datetime.now()

    while True:
        try:
            if (datetime.now() - config.last_heartbeat_timestamp).total_seconds() >= HEARTBEAT_INTERVAL_SEC:
                log_system_heartbeat()
                config.last_heartbeat_timestamp = datetime.now()

            if not is_trading_day():
                # 🆕 DASHBOARD UPDATE
                state.update_market(status="CLOSED")
                state.update_strategy_status("MARKET_CLOSED")
                time.sleep(get_sleep_duration())
                continue

            reset_daily_state(groww)

            if config.daily_pivot_point is None:
                logging.error("❌ Pivot not available, retrying in 60s")
                # 🆕 DASHBOARD UPDATE
                state.add_event("Waiting for pivot calculation")
                time.sleep(60)
                continue

            # ============================================================================
            # 🆕 DASHBOARD UPDATE - Update market data
            # ============================================================================
            state.update_market(
                pivot=config.daily_pivot_point,
                status="OPEN" if is_market_open() else "CLOSED"
            )

            # POSITION MANAGEMENT
            if config.current_position is not None:
                eod_time = datetime.strptime(EOD_EXIT, "%H:%M").time()
                if datetime.now().time() >= eod_time:
                    force_eod_exit(groww)
                    time.sleep(get_sleep_duration())
                    continue

                check_stop_loss(groww)
                if config.current_position is None:
                    time.sleep(get_sleep_duration())
                    continue

                check_profit_target(groww)
                time.sleep(get_sleep_duration())
                continue

            # ENTRY LOGIC
            entry_cutoff = datetime.strptime(ENTRY_CUTOFF, "%H:%M").time()
            
            if datetime.now().time() >= entry_cutoff:
                logging.info("⏰ Entry cutoff reached (12:00 PM) - No new trades")
                # 🆕 DASHBOARD UPDATE
                state.update_strategy_status("ENTRY_CUTOFF_REACHED")
                time.sleep(get_sleep_duration())
                continue
            
            # Ensure bias candle completed
            bias_end = datetime.strptime(BIAS_CANDLE_END, "%H:%M").time()

            if datetime.now().time() < bias_end:
                # 🆕 DASHBOARD UPDATE
                state.update_strategy_status("WAITING_FOR_BIAS")
                time.sleep(get_sleep_duration())
                continue

            # 1️⃣ Determine bias first
            determine_daily_bias(groww)

            if config.daily_bias is None or config.daily_bias == "NEUTRAL":
                # 🆕 DASHBOARD UPDATE
                if config.daily_bias == "NEUTRAL":
                    state.update_strategy_status("NO_TRADE_TODAY")
                    state.add_event("No clear bias - no trade today")
                time.sleep(get_sleep_duration())
                continue

            # ============================================================================
            # 🆕 DASHBOARD UPDATE - Bias determined
            # ============================================================================
            state.update_market(bias=config.daily_bias)
            state.update_strategy_status(f"WAITING_FOR_PULLBACK")

            # 2️⃣ Fetch spot ONLY after bias is confirmed
            spot = fetch_spot_price(groww)
            if spot is None:
                time.sleep(get_sleep_duration())
                continue
            
            # ============================================================================
            # 🆕 DASHBOARD UPDATE - Spot price
            # ============================================================================
            state.update_market(spot_price=spot)
            
            if not is_in_pivot_zone(spot, config.daily_pivot_point):
                time.sleep(get_sleep_duration())
                continue
            
            # ============================================================================
            # 🆕 DASHBOARD UPDATE - In pivot zone
            # ============================================================================
            state.add_event("Pullback to pivot zone detected")
            state.update_strategy_status("READY_TO_ENTER")
            
            # Direction from bias
            direction = "CALL" if config.daily_bias == "BULLISH" else "PUT"

            itm_strike = calculate_itm_strike(spot, direction)
            option_type = "CE" if direction == "CALL" else "PE"

            expiry = get_nearest_valid_expiry("NIFTY")
            if expiry is None:
                time.sleep(get_sleep_duration())
                continue

            instrument = find_option_instrument(
                underlying="NIFTY",
                expiry=expiry,
                strike=itm_strike,
                option_type=option_type
            )

            if instrument is None:
                time.sleep(get_sleep_duration())
                continue

            enter_position(groww, direction, instrument["symbol"], instrument["segment"], config.daily_pivot_point)
            time.sleep(get_sleep_duration())

        except KeyboardInterrupt:
            logging.warning("🛑 Keyboard interrupt - shutting down gracefully")
            # 🆕 DASHBOARD UPDATE
            state.add_event("System shutdown initiated")
            if config.current_position:
                spot = fetch_spot_price(groww)
                logging.warning(f"⚠️  Open position exists at spot: {spot}")
            generate_daily_report()
            break

        except Exception as e:
            logging.exception(f"❌ Unexpected error: {e}")
            # 🆕 DASHBOARD UPDATE
            state.add_event(f"Error: {str(e)[:100]}")
            time.sleep(30)


# =============================================================================
# MAIN ENTRY POINT (WITH DASHBOARD)
# =============================================================================

def main():
    """Main entry point with dashboard integration"""
    initialize_logging()
    log_strategy_banner()

    if TRADING_MODE not in ["PAPER", "LIVE"]:
        logging.error(f"❌ Invalid TRADING_MODE: {TRADING_MODE}")
        sys.exit(1)

    logging.info(f"⚙️  Trading Mode: {TRADING_MODE}")
    if TRADING_MODE == "LIVE":
        logging.warning("⚠️  LIVE MODE - Real orders will be placed!")

    if TRADING_MODE == "LIVE" and TRADE_LOTS > 1:
        logging.error("❌ LIVE MODE blocked: TRADE_LOTS > 1 is not allowed")
        sys.exit(1)
    
    # ============================================================================
    # 🆕 START DASHBOARD SERVER
    # ============================================================================
    logging.info("")
    logging.info("=" * 80)
    logging.info("🌐 STARTING DASHBOARD SERVER")
    logging.info("=" * 80)
    
    start_dashboard(host='127.0.0.1', port=5000)
    
    logging.info("✅ Dashboard server started successfully")
    logging.info("📊 Open your browser to: http://127.0.0.1:5000")
    logging.info("=" * 80)
    logging.info("")
    
    # ============================================================================
    # 🆕 INITIALIZE SHARED STATE
    # ============================================================================
    state.mode = TRADING_MODE
    state.current_date = datetime.now().strftime("%Y-%m-%d")
    state.add_event("Trading system initialized")
    state.add_event(f"Mode: {TRADING_MODE}")
    
    groww = initialize_groww_api()
    load_instrument_data(groww)
    reset_daily_state(groww)

    logging.info("")
    logging.info("🟢 SYSTEM READY - Starting Trading Loop")
    logging.info("")

    run_trading_loop(groww)


if __name__ == "__main__":
    main()
