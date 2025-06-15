from hummingbot.client.config.config_validators import validate_decimal, validate_float, validate_int
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import AllConnectorSettings


def market_prompt() -> str:
    connector = market_state_config_map.get("connector").value
    example = AllConnectorSettings.get_example_pairs().get(connector)
    return f"Enter the token trading pair you would like to trade on {connector}{f' (e.g. {example})' if example else ''} >>> "


market_state_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="market_state_strategy",
    ),
    "connector": ConfigVar(
        key="connector",
        prompt="Enter the name of the exchange (e.g. binance, kucoin_spot) >>> ",
        prompt_on_new=True,
        default=None,
    ),
    "market": ConfigVar(
        key="market",
        prompt=market_prompt,
        prompt_on_new=True,
        default=None,
    ),
    "adx_short_window": ConfigVar(
        key="adx_short_window",
        prompt="Enter short-term ADX window (e.g. 7) >>> ",
        type_str="int",
        default=7,
        validator=validate_int,
    ),
    "adx_mid_window": ConfigVar(
        key="adx_mid_window",
        prompt="Enter mid-term ADX window (e.g. 14) >>> ",
        type_str="int",
        default=14,
        validator=validate_int,
    ),
    "adx_long_window": ConfigVar(
        key="adx_long_window",
        prompt="Enter long-term ADX window (e.g. 30) >>> ",
        type_str="int",
        default=30,
        validator=validate_int,
    ),
    "adx_trend_threshold": ConfigVar(
        key="adx_trend_threshold",
        prompt="Enter ADX trend threshold (e.g. 25) >>> ",
        type_str="float",
        default=25.0,
        validator=validate_float,
    ),
    "adx_range_threshold": ConfigVar(
        key="adx_range_threshold",
        prompt="Enter ADX range threshold (e.g. 20) >>> ",
        type_str="float",
        default=20.0,
        validator=validate_float,
    ),
    "update_interval": ConfigVar(
        key="update_interval",
        prompt="Enter update interval in seconds (e.g. 60) >>> ",
        type_str="float",
        default=60.0,
        validator=validate_float,
    ),
    "base_order_amount": ConfigVar(
        key="base_order_amount",
        prompt="Enter base order amount >>> ",
        type_str="decimal",
        default=10.0,
        validator=validate_decimal,
    ),
    "stop_loss_pct": ConfigVar(
        key="stop_loss_pct",
        prompt="Enter stop loss percentage (e.g. 15 for 15%) >>> ",
        type_str="float",
        default=15.0,
        validator=validate_float,
    ),
    "grid_levels": ConfigVar(
        key="grid_levels",
        prompt="Enter number of grid levels (e.g. 5) >>> ",
        type_str="int",
        default=5,
        validator=validate_int,
    ),
    "grid_spread": ConfigVar(
        key="grid_spread",
        prompt="Enter grid spread percentage (e.g. 1.0 for 1%) >>> ",
        type_str="float",
        default=1.0,
        validator=validate_float,
    ),
    "macd_fast": ConfigVar(
        key="macd_fast",
        prompt="Enter MACD fast period (e.g. 12) >>> ",
        type_str="int",
        default=12,
        validator=validate_int,
    ),
    "macd_slow": ConfigVar(
        key="macd_slow",
        prompt="Enter MACD slow period (e.g. 26) >>> ",
        type_str="int",
        default=26,
        validator=validate_int,
    ),
    "macd_signal": ConfigVar(
        key="macd_signal",
        prompt="Enter MACD signal period (e.g. 9) >>> ",
        type_str="int",
        default=9,
        validator=validate_int,
    ),
    "martingale_multiplier": ConfigVar(
        key="martingale_multiplier",
        prompt="Enter reverse martingale multiplier (e.g. 1.5) >>> ",
        type_str="float",
        default=1.5,
        validator=validate_float,
    ),
    "max_martingale_levels": ConfigVar(
        key="max_martingale_levels",
        prompt="Enter max martingale levels (e.g. 3) >>> ",
        type_str="int",
        default=3,
        validator=validate_int,
    ),
}
