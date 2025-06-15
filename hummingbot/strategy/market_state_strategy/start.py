import logging
from decimal import Decimal

from hummingbot.client.config.config_helpers import parse_cvar_value, read_yml_file
from hummingbot.client.settings import STRATEGIES_CONF_DIR_PATH
from hummingbot.strategy.market_state_strategy.market_state_config_map import market_state_config_map as c_map
from hummingbot.strategy.market_state_strategy.market_state_strategy import MarketStateStrategy
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


def start(self):
    # Load config values from YAML file
    if hasattr(self, 'strategy_file_name') and self.strategy_file_name:
        try:
            strategy_file_path = STRATEGIES_CONF_DIR_PATH / self.strategy_file_name
            if strategy_file_path.exists():
                config_data = read_yml_file(strategy_file_path)
                for key, value in config_data.items():
                    if key in c_map:
                        cvar = c_map[key]
                        cvar.value = parse_cvar_value(cvar, value)
        except Exception as e:
            logging.getLogger().warning(f"Could not load config from {self.strategy_file_name}: {e}")

    # Validate required config values
    connector_value = c_map.get("connector").value
    if connector_value is None:
        raise ValueError("Connector not set. Please configure 'connector' in the config file.")

    connector = connector_value.lower()
    market = c_map.get("market").value

    if market is None:
        raise ValueError("Market not set. Please configure 'market' in the config file.")

    # Initialize strategy
    self._initialize_markets([(connector, [market])])
    base, quote = market.split("-")
    market_info = MarketTradingPairTuple(self.markets[connector], market, base, quote)

    self.strategy = MarketStateStrategy(
        market_info,
        # ADX parameters
        adx_short=c_map.get("adx_short_window").value,
        adx_mid=c_map.get("adx_mid_window").value,
        adx_long=c_map.get("adx_long_window").value,
        adx_trend_threshold=c_map.get("adx_trend_threshold").value,
        adx_range_threshold=c_map.get("adx_range_threshold").value,
        update_interval=c_map.get("update_interval").value,
        # Trading parameters
        base_order_amount=Decimal(str(c_map.get("base_order_amount").value)),
        stop_loss_pct=c_map.get("stop_loss_pct").value,
        # Grid trading parameters
        grid_levels=c_map.get("grid_levels").value,
        grid_spread=c_map.get("grid_spread").value,
        # MACD parameters
        macd_fast=c_map.get("macd_fast").value,
        macd_slow=c_map.get("macd_slow").value,
        macd_signal=c_map.get("macd_signal").value,
        # Reverse martingale parameters
        martingale_multiplier=c_map.get("martingale_multiplier").value,
        max_martingale_levels=c_map.get("max_martingale_levels").value,
    )
