import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pandas as pd
import ta

from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

hws_logger = None


def get_market_state(adx_short: float,
                     adx_mid: float,
                     adx_long: float,
                     plus_di: float,
                     minus_di: float,
                     trend_thresh: float,
                     range_thresh: float) -> str:
    """
    Determine market state based on multiple timeframe ADX indicators

    Args:
        adx_short: Short-term ADX value
        adx_mid: Mid-term ADX value
        adx_long: Long-term ADX value
        plus_di: Plus Directional Indicator
        minus_di: Minus Directional Indicator
        trend_thresh: Threshold for trend detection
        range_thresh: Threshold for range detection

    Returns:
        str: Market state - "TREND_UP", "TREND_DOWN", "RANGE", or "PAUSE"
    """
    # Check for NaN values
    if any(pd.isna([adx_short, adx_mid, adx_long, plus_di, minus_di])):
        return "PAUSE"

    # Strong trend: All timeframes show strong ADX
    strong_trend_all = adx_short > trend_thresh and adx_mid > trend_thresh and adx_long > trend_thresh

    # Medium trend: At least 2 timeframes show trend
    medium_trend = sum([adx_short > trend_thresh, adx_mid > trend_thresh, adx_long > trend_thresh]) >= 2

    # Determine trend direction
    if strong_trend_all:
        # Strong trend with clear direction
        if plus_di > minus_di * 1.1:  # 10% buffer to avoid noise
            return "TREND_UP"
        elif minus_di > plus_di * 1.1:
            return "TREND_DOWN"
        else:
            return "PAUSE"  # Conflicting signals

    elif medium_trend:
        # Medium strength trend
        if plus_di > minus_di * 1.05:  # 5% buffer
            return "TREND_UP"
        elif minus_di > plus_di * 1.05:
            return "TREND_DOWN"
        else:
            return "PAUSE"

    # Range market: Low ADX on medium and long timeframes
    elif adx_mid < range_thresh and adx_long < range_thresh:
        return "RANGE"

    # Default to pause for unclear conditions
    return "PAUSE"


class MarketStateStrategy(StrategyPyBase):
    """
    Enhanced Market State Strategy using multi-timeframe ADX analysis with trading capabilities

    This strategy analyzes market conditions using ADX indicators across multiple timeframes
    to determine if the market is trending up, trending down, ranging, or in a pause state.

    Trading Logic:
    - RANGE: Grid trading with buy/sell orders at multiple levels
    - TREND_UP/TREND_DOWN: MACD-based entries with reverse martingale position sizing
    - Stop loss at 15% for all positions
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global hws_logger
        if hws_logger is None:
            hws_logger = logging.getLogger(__name__)
        return hws_logger

    def __init__(self,
                 market_info: MarketTradingPairTuple,
                 adx_short: int = 7,
                 adx_mid: int = 14,
                 adx_long: int = 30,
                 adx_trend_threshold: float = 25.0,
                 adx_range_threshold: float = 20.0,
                 update_interval: float = 60.0,
                 base_order_amount: Decimal = Decimal("10.0"),
                 stop_loss_pct: float = 15.0,
                 grid_levels: int = 5,
                 grid_spread: float = 1.0,
                 macd_fast: int = 12,
                 macd_slow: int = 26,
                 macd_signal: int = 9,
                 martingale_multiplier: float = 1.5,
                 max_martingale_levels: int = 3):
        super().__init__()
        self.market_info = market_info
        self.add_markets([market_info.market])

        # ADX parameters
        self.adx_short = adx_short
        self.adx_mid = adx_mid
        self.adx_long = adx_long
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold

        # Trading parameters
        self.base_order_amount = base_order_amount
        self.stop_loss_pct = stop_loss_pct

        # Grid trading parameters
        self.grid_levels = grid_levels
        self.grid_spread = grid_spread

        # MACD parameters
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

        # Reverse martingale parameters
        self.martingale_multiplier = martingale_multiplier
        self.max_martingale_levels = max_martingale_levels

        # State tracking
        self.current_state: Optional[str] = None
        self.previous_state: Optional[str] = None
        self.state_change_timestamp: Optional[float] = None

        # Update control
        self.update_interval = update_interval
        self.last_update_timestamp: float = 0

        # Market data cache
        self._market_data_cache: Optional[pd.DataFrame] = None
        self._indicators_cache: Optional[Dict] = None

        # Trading state
        self.grid_orders: List[str] = []  # Track grid order IDs
        self.position_side: Optional[str] = None  # "LONG" or "SHORT"
        self.entry_price: Optional[Decimal] = None
        self.martingale_level: int = 0
        self.last_macd_signal: Optional[str] = None  # "BUY" or "SELL"
        self.winning_streak: int = 0

    def get_current_market_state(self) -> Optional[str]:
        """
        Public method to get current market state
        Can be called by other strategies
        """
        return self.current_state

    def get_market_indicators(self) -> Optional[Dict]:
        """
        Get current market indicators for analysis
        """
        return self._indicators_cache

    def tick(self, timestamp: float):
        """
        Main strategy tick - analyzes market state and executes trading logic
        """
        if not self.market_info.market.ready:
            self.logger().info(f"{self.market_info.market.name} not ready, waiting...")
            return

        # Only update at specified intervals to avoid excessive computation
        if timestamp - self.last_update_timestamp < self.update_interval:
            return

        try:
            # Get market data and calculate indicators
            market_data = self._get_market_data()
            if market_data is None or len(market_data) < max(self.adx_short, self.adx_mid, self.adx_long, self.macd_slow):
                self.logger().warning("Insufficient market data for analysis")
                return

            # Calculate ADX indicators
            indicators = self._calculate_indicators(market_data)
            if indicators is None:
                self.logger().warning("Failed to calculate indicators")
                return

            # Determine market state
            new_state = get_market_state(
                indicators['adx_short'],
                indicators['adx_mid'],
                indicators['adx_long'],
                indicators['plus_di'],
                indicators['minus_di'],
                self.adx_trend_threshold,
                self.adx_range_threshold
            )

            # Update state if changed
            if new_state != self.current_state:
                self.previous_state = self.current_state
                self.current_state = new_state
                self.state_change_timestamp = timestamp
                self._on_state_change(new_state, timestamp)

            # Cache data
            self._market_data_cache = market_data
            self._indicators_cache = indicators
            self.last_update_timestamp = timestamp

            # Execute trading logic based on current state
            self._execute_trading_logic(indicators, timestamp)

            # Check stop loss
            self._check_stop_loss(indicators)

            # Log current state periodically
            if timestamp % 300 < self.update_interval:  # Every 5 minutes
                self._log_market_state(indicators)

        except Exception as e:
            self.logger().error(f"Error in market state analysis: {e}", exc_info=True)

    def _get_market_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data from the market
        """
        try:
            limit = max(self.adx_short, self.adx_mid, self.adx_long, self.macd_slow) + 20  # Extra buffer for calculations
            candles = self.market_info.market.get_ohlcv(
                self.market_info.trading_pair,
                interval="1m",
                limit=limit
            )

            if not candles or len(candles) == 0:
                return None

            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

            # Convert to numeric and handle any data issues
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Remove any rows with NaN values
            df = df.dropna()

            return df if len(df) > 0 else None

        except Exception as e:
            self.logger().error(f"Error fetching market data: {e}")
            return None

    def _calculate_indicators(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Calculate ADX, DI, and MACD indicators
        """
        try:
            # Calculate ADX for different timeframes
            adx_short = ta.trend.adx(df["high"], df["low"], df["close"], window=self.adx_short)
            adx_mid = ta.trend.adx(df["high"], df["low"], df["close"], window=self.adx_mid)
            adx_long = ta.trend.adx(df["high"], df["low"], df["close"], window=self.adx_long)

            # Calculate Directional Indicators
            plus_di = ta.trend.plus_di(df["high"], df["low"], df["close"], window=self.adx_mid)
            minus_di = ta.trend.minus_di(df["high"], df["low"], df["close"], window=self.adx_mid)

            # Calculate MACD
            macd_line = ta.trend.macd(df["close"], window_slow=self.macd_slow, window_fast=self.macd_fast)
            macd_signal_line = ta.trend.macd_signal(df["close"], window_slow=self.macd_slow,
                                                    window_fast=self.macd_fast, window_sign=self.macd_signal)
            macd_histogram = ta.trend.macd_diff(df["close"], window_slow=self.macd_slow,
                                                window_fast=self.macd_fast, window_sign=self.macd_signal)

            # Get latest values
            latest_idx = -1
            indicators = {
                'adx_short': adx_short.iloc[latest_idx] if not adx_short.empty else None,
                'adx_mid': adx_mid.iloc[latest_idx] if not adx_mid.empty else None,
                'adx_long': adx_long.iloc[latest_idx] if not adx_long.empty else None,
                'plus_di': plus_di.iloc[latest_idx] if not plus_di.empty else None,
                'minus_di': minus_di.iloc[latest_idx] if not minus_di.empty else None,
                'macd': macd_line.iloc[latest_idx] if not macd_line.empty else None,
                'macd_signal': macd_signal_line.iloc[latest_idx] if not macd_signal_line.empty else None,
                'macd_histogram': macd_histogram.iloc[latest_idx] if not macd_histogram.empty else None,
                'current_price': df["close"].iloc[latest_idx] if not df.empty else None,
                'timestamp': df["timestamp"].iloc[latest_idx] if not df.empty else None
            }

            # Validate indicators
            if any(v is None or pd.isna(v) for v in indicators.values() if v is not None):
                return None

            return indicators

        except Exception as e:
            self.logger().error(f"Error calculating indicators: {e}")
            return None

    def _execute_trading_logic(self, indicators: Dict, timestamp: float):
        """
        Execute trading logic based on current market state
        """
        try:
            if self.current_state == "RANGE":
                self._execute_grid_trading(indicators)
            elif self.current_state in ["TREND_UP", "TREND_DOWN"]:
                self._execute_macd_trading(indicators)
            elif self.current_state == "PAUSE":
                # Close all positions and orders in pause state
                self._close_all_positions()

        except Exception as e:
            self.logger().error(f"Error in trading logic execution: {e}")

    def _execute_grid_trading(self, indicators: Dict):
        """
        Execute grid trading strategy for range-bound markets
        """
        try:
            current_price = Decimal(str(indicators['current_price']))

            # Cancel existing grid orders if any
            self._cancel_grid_orders()

            # Calculate grid levels
            grid_step = current_price * Decimal(str(self.grid_spread / 100))

            # Place buy orders below current price
            for i in range(1, self.grid_levels + 1):
                buy_price = current_price - (grid_step * i)
                order_amount = self.base_order_amount

                order_id = self.buy_with_specific_market(
                    self.market_info,
                    order_amount,
                    order_type=OrderType.LIMIT,
                    price=buy_price
                )
                if order_id:
                    self.grid_orders.append(order_id)

            # Place sell orders above current price
            for i in range(1, self.grid_levels + 1):
                sell_price = current_price + (grid_step * i)
                order_amount = self.base_order_amount

                order_id = self.sell_with_specific_market(
                    self.market_info,
                    order_amount,
                    order_type=OrderType.LIMIT,
                    price=sell_price
                )
                if order_id:
                    self.grid_orders.append(order_id)

            self.logger().info(f"Grid trading: Placed {len(self.grid_orders)} orders around price {current_price}")

        except Exception as e:
            self.logger().error(f"Error in grid trading execution: {e}")

    def _execute_macd_trading(self, indicators: Dict):
        """
        Execute MACD-based trading with reverse martingale for trending markets
        """
        try:
            macd = indicators['macd']
            macd_signal = indicators['macd_signal']
            macd_histogram = indicators['macd_histogram']
            current_price = Decimal(str(indicators['current_price']))

            # Determine MACD signal
            current_signal = None
            if macd > macd_signal and macd_histogram > 0:
                if self.current_state == "TREND_UP":
                    current_signal = "BUY"
            elif macd < macd_signal and macd_histogram < 0:
                if self.current_state == "TREND_DOWN":
                    current_signal = "SELL"

            # Execute trade if signal changed
            if current_signal and current_signal != self.last_macd_signal:
                self._execute_macd_order(current_signal, current_price)
                self.last_macd_signal = current_signal

        except Exception as e:
            self.logger().error(f"Error in MACD trading execution: {e}")

    def _execute_macd_order(self, signal: str, current_price: Decimal):
        """
        Execute MACD-based order with reverse martingale sizing
        """
        try:
            # Calculate position size with reverse martingale
            if self.winning_streak > 0:
                multiplier = self.martingale_multiplier ** min(self.winning_streak, self.max_martingale_levels)
                order_amount = self.base_order_amount * Decimal(str(multiplier))
            else:
                order_amount = self.base_order_amount

            # Close opposite position if exists
            if self.position_side and self.position_side != signal.replace("BUY", "LONG").replace("SELL", "SHORT"):
                self._close_all_positions()

            if signal == "BUY":
                order_id = self.buy_with_specific_market(
                    self.market_info,
                    order_amount,
                    order_type=OrderType.MARKET
                )
                if order_id:
                    self.position_side = "LONG"
                    self.entry_price = current_price
                    self.logger().info(f"MACD BUY signal: Opened LONG position of {order_amount} at {current_price}")

            elif signal == "SELL":
                order_id = self.sell_with_specific_market(
                    self.market_info,
                    order_amount,
                    order_type=OrderType.MARKET
                )
                if order_id:
                    self.position_side = "SHORT"
                    self.entry_price = current_price
                    self.logger().info(f"MACD SELL signal: Opened SHORT position of {order_amount} at {current_price}")

        except Exception as e:
            self.logger().error(f"Error executing MACD order: {e}")

    def _check_stop_loss(self, indicators: Dict):
        """
        Check and execute stop loss if necessary
        """
        try:
            if not self.position_side or not self.entry_price:
                return

            current_price = Decimal(str(indicators['current_price']))
            stop_loss_threshold = Decimal(str(self.stop_loss_pct / 100))

            should_stop = False

            if self.position_side == "LONG":
                loss_pct = (self.entry_price - current_price) / self.entry_price
                if loss_pct >= stop_loss_threshold:
                    should_stop = True

            elif self.position_side == "SHORT":
                loss_pct = (current_price - self.entry_price) / self.entry_price
                if loss_pct >= stop_loss_threshold:
                    should_stop = True

            if should_stop:
                self.logger().warning(f"Stop loss triggered! Position: {self.position_side}, "
                                      f"Entry: {self.entry_price}, Current: {current_price}")
                self._close_all_positions()
                self.winning_streak = 0  # Reset winning streak on stop loss

        except Exception as e:
            self.logger().error(f"Error checking stop loss: {e}")

    def _cancel_grid_orders(self):
        """
        Cancel all grid orders
        """
        try:
            for order_id in self.grid_orders:
                self.cancel(self.market_info.market, order_id)
            self.grid_orders.clear()
        except Exception as e:
            self.logger().error(f"Error canceling grid orders: {e}")

    def _close_all_positions(self):
        """
        Close all open positions and cancel all orders
        """
        try:
            self.cancel_all()
            self._cancel_grid_orders()

            # Reset position tracking
            was_profitable = False
            if self.position_side and self.entry_price and self._indicators_cache:
                current_price = Decimal(str(self._indicators_cache['current_price']))
                if self.position_side == "LONG" and current_price > self.entry_price:
                    was_profitable = True
                elif self.position_side == "SHORT" and current_price < self.entry_price:
                    was_profitable = True

            # Update winning streak for reverse martingale
            if was_profitable:
                self.winning_streak += 1
            else:
                self.winning_streak = 0

            self.position_side = None
            self.entry_price = None
            self.martingale_level = 0

        except Exception as e:
            self.logger().error(f"Error closing positions: {e}")

    def _on_state_change(self, new_state: str, timestamp: float):
        """
        Handle market state changes
        """
        self.logger().info(
            f"Market state changed: {self.previous_state} -> {new_state} "
            f"at {timestamp}"
        )

        # Close all positions and orders when state changes
        self._close_all_positions()
        self.last_macd_signal = None  # Reset MACD signal tracking

    def _log_market_state(self, indicators: Dict):
        """
        Log current market state and indicators
        """
        position_info = ""
        if self.position_side:
            position_info = f" | Position: {self.position_side} @ {self.entry_price}"

        self.logger().info(
            f"Market State: {self.current_state} | "
            f"ADX(S/M/L): {indicators['adx_short']:.2f}/{indicators['adx_mid']:.2f}/{indicators['adx_long']:.2f} | "
            f"+DI: {indicators['plus_di']:.2f} | -DI: {indicators['minus_di']:.2f} | "
            f"MACD: {indicators['macd']:.4f} | MACD Signal: {indicators['macd_signal']:.4f}"
            f"{position_info} | Win Streak: {self.winning_streak}"
        )

    def format_status(self) -> str:
        """
        Format strategy status for display
        """
        lines = []
        lines.append("=== Market State Strategy ===")
        lines.append(f"Trading Pair: {self.market_info.trading_pair}")
        lines.append(f"Current State: {self.current_state or 'INITIALIZING'}")

        if self.previous_state:
            lines.append(f"Previous State: {self.previous_state}")

        if self._indicators_cache:
            indicators = self._indicators_cache
            lines.append("--- ADX Indicators ---")
            lines.append(f"Short ADX ({self.adx_short}): {indicators['adx_short']:.2f}")
            lines.append(f"Mid ADX ({self.adx_mid}): {indicators['adx_mid']:.2f}")
            lines.append(f"Long ADX ({self.adx_long}): {indicators['adx_long']:.2f}")
            lines.append(f"+DI: {indicators['plus_di']:.2f}")
            lines.append(f"-DI: {indicators['minus_di']:.2f}")
            lines.append("--- MACD Indicators ---")
            lines.append(f"MACD: {indicators['macd']:.4f}")
            lines.append(f"MACD Signal: {indicators['macd_signal']:.4f}")
            lines.append(f"MACD Histogram: {indicators['macd_histogram']:.4f}")
            lines.append("--- Thresholds ---")
            lines.append(f"Trend Threshold: {self.adx_trend_threshold}")
            lines.append(f"Range Threshold: {self.adx_range_threshold}")

        lines.append("--- Trading Status ---")
        lines.append(f"Position: {self.position_side or 'None'}")
        if self.entry_price:
            lines.append(f"Entry Price: {self.entry_price}")
        lines.append(f"Stop Loss: {self.stop_loss_pct}%")
        lines.append(f"Grid Orders: {len(self.grid_orders)}")
        lines.append(f"Winning Streak: {self.winning_streak}")

        return "\n".join(lines)
