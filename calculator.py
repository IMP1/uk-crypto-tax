
# Assumptions
#   * All dates are UTC

# Test Ideas
#   * Badly formatted CSV => errors
#   * Random date order CSV => chronological order
#   * correct date order CSV => chronological order
#   * gifts
#   * disposal with no corresponding buy --- should be costbasis of 0
#   * A BnB check with edge cases (29 days, 30 days, 31 days)

# TODO: work out for Gift/Tips
# TODO: calculate samples by hand to compare
# TODO: compare methods here with strategy in README and update/note differences
# TODO: check tax strategy

import sys
import csv
import logging
from datetime import datetime, timedelta
from enum import IntEnum, Enum
from typing import List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# TODO: Have config option of logging location
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


class GainType(Enum):
    FIFO = 1
    AVERAGE = 2


# TODO: Load this in from config file (but maybe still have as enum)
class TradeColumn(IntEnum):
    BUY_AMOUNT = 1
    BUY_CURRENCY = 2
    BUY_VALUE_BTC = 3
    BUY_VALUE_GBP = 4
    SELL_AMOUNT = 5
    SELL_CURRENCY = 6
    SELL_VALUE_BTC = 7
    SELL_VALUE_GBP = 8
    SPREAD = 9
    EXCHANGE = 10
    DATE = 12


# TODO: Load this in from config file (but maybe still have as enum)
class FeeColumn(IntEnum):
    FEE_AMOUNT = 2
    FEE_CURRENCY = 3
    FEE_VALUE_GBP_THEN = 4
    FEE_VALUE_GBP_NOW = 5
    TRADE_BUY_AMOUNT = 6
    TRADE_BUY_CURRENCY = 7
    TRADE_SELL_AMOUNT = 8
    TRADE_SELL_CURRENCY = 9
    EXCHANGE = 10
    DATE = 11


# TODO: Have all of these be loaded in from config file
BNB_TIME_DURATION = timedelta(days=30)
DATE_FORMAT = "%d.%m.%Y %H:%M"
NATIVE_CURRENCY = "GBP"
TAX_YEAR = 2020


class Trade:

    def __init__(self, buy_amount, buy_currency, buy_native_value, sell_amount, sell_currency, sell_native_value, date,
                 exchange):
        self.buy_amount = buy_amount
        self.buy_currency = buy_currency
        self.buy_native_value = buy_native_value
        self.sell_amount = sell_amount
        self.sell_currency = sell_currency
        self.sell_native_value = sell_native_value
        self.date = date
        self.exchange = exchange
        self.fee = None  # Set later from fee datafile

        self.native_value_per_coin = 0
        self.native_cost_per_coin = 0
        if self.buy_amount != 0:
            self.native_cost_per_coin = self.sell_native_value / self.buy_amount
            self.native_value_per_coin = self.buy_native_value / self.buy_amount

        self.unaccounted_buy_amount = self.buy_amount
        self.unaccounted_sell_amount = self.sell_amount

    @staticmethod
    def from_csv(row):
        return Trade(float(row[TradeColumn.BUY_AMOUNT]),
                     row[TradeColumn.BUY_CURRENCY],
                     float(row[TradeColumn.BUY_VALUE_GBP]),
                     float(row[TradeColumn.SELL_AMOUNT]),
                     row[TradeColumn.SELL_CURRENCY],
                     float(row[TradeColumn.SELL_VALUE_GBP]),
                     datetime.strptime(row[TradeColumn.DATE], DATE_FORMAT),
                     row[TradeColumn.EXCHANGE])

    def get_native_fee_cost(self):
        if self.fee is None:
            return 0
        else:
            return self.fee.fee_native_value_at_trade

    def get_unaccounted_cost(self):
        portion = self.unaccounted_buy_amount / self.buy_amount
        raw_cost = self.sell_native_value + self.get_native_fee_cost()
        return portion * raw_cost

    def get_current_disposal_value(self):
        portion = self.unaccounted_sell_amount / self.sell_amount
        raw_cost = self.buy_native_value
        return portion * raw_cost

    def is_viable_sell(self):
        return self.unaccounted_sell_amount > 0 and self.sell_currency != NATIVE_CURRENCY and self.sell_currency != ""

    def __repr__(self):
        return f"<Trade {self.date} ({self.exchange}) :: " \
               f"{self.buy_amount} {self.buy_currency} ({self.buy_native_value} GBP) <- " \
               f"{self.sell_amount} {self.sell_currency} ({self.sell_native_value} GBP) " \
               f"{self.fee}>"


class Fee:

    def __init__(self, fee_amount, fee_currency, fee_native_value_at_trade, fee_native_value_now, trade_buy_amount,
                 trade_buy_currency, trade_sell_amount, trade_sell_currency, date, exchange):
        self.fee_amount = fee_amount
        self.fee_currency = fee_currency
        self.fee_native_value_at_trade = fee_native_value_at_trade
        self.fee_native_value_now = fee_native_value_now
        self.trade_buy_amount = trade_buy_amount
        self.trade_buy_currency = trade_buy_currency
        self.trade_sell_amount = trade_sell_amount
        self.trade_sell_currency = trade_sell_currency
        self.date = date
        self.exchange = exchange


    @staticmethod
    def from_csv(row):
        return Fee(float(row[FeeColumn.FEE_AMOUNT]),
                   row[FeeColumn.FEE_CURRENCY],
                   float(row[FeeColumn.FEE_VALUE_GBP_THEN]),
                   float(row[FeeColumn.FEE_VALUE_GBP_NOW]),
                   float(row[FeeColumn.TRADE_BUY_AMOUNT]),
                   row[FeeColumn.TRADE_BUY_CURRENCY],
                   float(row[FeeColumn.TRADE_SELL_AMOUNT]),
                   row[FeeColumn.TRADE_SELL_CURRENCY],
                   row[FeeColumn.DATE],
                   row[FeeColumn.EXCHANGE])

    def __str__(self):
        return "buy_amount: " + str(self.buy_amount) + " Buy Currency: " + str(self.buy_currency) + " Date : " + str(
            self.date.strftime("%d.%m.%Y %H:%M"))


class Gain:

    def __init__(self, gain_type: GainType, disposal_amount, disposal: Trade,
                 corresponding_buy: Optional[Trade], cost=None):

        self.gain_type = gain_type
        self.currency = disposal.sell_currency
        self.date_sold = disposal.date

        self.sold_location = disposal.exchange
        self.disposal_trade = disposal
        self.disposal_amount_accounted = disposal_amount
        self.corresponding_buy = corresponding_buy

        if self.corresponding_buy:
            self.cost_basis = corresponding_buy.native_cost_per_coin * disposal_amount
        else:
            self.cost_basis = cost

        # NOTE: profit uses disposal.buy_native_value, not disposal.sell_native_value
        self.proceeds = disposal.buy_native_value * disposal_amount / disposal.unaccounted_sell_amount
        self.native_currency_gain_value = self.proceeds - self.cost_basis  # gain doesn't account for fees
        self.fee_native_value = disposal.get_native_fee_cost()

    def __str__(self):
        return f"Amount: {self.disposal_amount_accounted} Currency: {self.currency}" + " Date Acquired: " + str(
            self.date_acquired.strftime("%d.%m.%Y %H:%M")) + " Date Sold: " + str(
            self.date_sold.strftime("%d.%m.%Y %H:%M")) + " Location of buy: " + str(
            self.bought_location) + " Location of sell: " + str(self.sold_location) + " Proceeds in GBP: " + str(
            self.proceeds) + " Cost Basis in GBP: " + str(self.cost_basis) + " Fee in GBP: " + str(
            self.fee_native_value) + " Gain/Loss in GBP: " + str(self.native_currency_gain_value)

    def __repr__(self):
        return str(self)


def read_csv_into_trade_list(csv_filename):
    try:
        with open(csv_filename, encoding='utf-8') as csv_file:
            reader = csv.reader(csv_file)
            next(reader)  # Ignore Header Row
            trades = [Trade.from_csv(row) for row in list(reader)]
            trades.sort(key=lambda trade: trade.date)
            logger.debug(f"Loaded {len(trades)} trades from {csv_filename}.")
            return trades
    except FileNotFoundError as e:
        logger.error(f"Could not find fees csv: '{csv_filename}'.")
        raise
    except Exception as e:
        raise
        # TODO: Test with various wrong csvs and create nice error messages


def read_csv_into_fee_list(csv_filename):
    try:
        with open(csv_filename, encoding='utf-8') as csv_file:
            reader = csv.reader(csv_file)
            next(reader)  # Ignore header row
            fees = [Fee.from_csv(row) for row in list(reader)]
            logger.debug(f"Loaded {len(fees)} fees from {csv_filename}.")
            return fees
    except FileNotFoundError as e:
        logger.error(f"Could not find fees csv: '{csv_filename}'.")
        return []
    except Exception as e:
        raise
        # TODO: Test with various wrong csvs and create nice error messages


def fee_matches_trade(fee, trade):
    return trade.date == fee.date and \
           trade.sell_currency == fee.trade_sell_currency and \
           trade.sell_amount == fee.trade_sell_amount and \
           trade.buy_currency == fee.trade_buy_currency and \
           trade.buy_amount == fee.trade_buy_amount


def assign_fees_to_trades(trades, fees):
    for fee in fees:
        matching_trades = [t for t in trades if fee_matches_trade(fee, t)]
        if len(matching_trades) == 0:
            logger.warning(f"Could not find trade for fee {fee}.")
        elif len(matching_trades) > 1:
            logger.error(f"Found multiple trades for fee {fee}.")
        else:
            trade = matching_trades[0]
            trade.fee = fee


def within_tax_year(trade, tax_year):
    tax_year_start = datetime(tax_year - 1, 4, 6)  # 2018 taxyear is 2017/18 taxyear and starts 06/04/2017
    tax_year_end = datetime(tax_year, 4, 6)  # This needs to be 6 as 05.06.2018 < 05.06.2018 12:31
    return tax_year_start <= trade.date < tax_year_end


def currency_match(disposal, corresponding_buy):
    return disposal.sell_currency == corresponding_buy.buy_currency


def gain_from_pair(disposal, corresponding_buy):
    disposal_amount_accounted_for = min(1, corresponding_buy.unaccounted_buy_amount / disposal.unaccounted_sell_amount)
    gain = Gain(GainType.FIFO, disposal_amount_accounted_for, disposal, corresponding_buy)
    logger.debug(f"Matched {disposal_amount_accounted_for * 100}% of \n\t{disposal} with \n\t{corresponding_buy}.")

    disposal.unaccounted_sell_amount -= disposal_amount_accounted_for * disposal.unaccounted_sell_amount
    corresponding_buy.unaccounted_buy_amount -= disposal_amount_accounted_for * corresponding_buy.unaccounted_buy_amount
    return gain


def calculate_day_gains_fifo(trade_list):
    condition = lambda disposal, corresponding_buy: \
        disposal.date.date() == corresponding_buy.date.date()
    return calculate_fifo_gains(trade_list, condition)


def calculate_bnb_gains_fifo(trade_list):
    condition = lambda disposal, corresponding_buy: \
        disposal.date.date() < corresponding_buy.date.date() < (disposal.date + BNB_TIME_DURATION).date()
    return calculate_fifo_gains(trade_list, condition)


def calculate_fifo_gains(trade_list, trade_within_date_range):
    gains = []
    for disposal in trade_list:
        for corresponding_buy in trade_list:
            if currency_match(disposal, corresponding_buy) and disposal.is_viable_sell() and \
               trade_within_date_range(disposal, corresponding_buy):
                calculated_gain = gain_from_pair(disposal, corresponding_buy)
                gains.append(calculated_gain)
    return gains


def calculate_104_gains_for_asset(currency, trade_list: List[Trade]):
    number_of_shares_in_pool = 0
    total_pool_cost = 0
    gain_list = []

    for trade in trade_list:
        if trade.buy_currency == currency:
            number_of_shares_in_pool += trade.unaccounted_buy_amount
            total_pool_cost += trade.get_unaccounted_cost()
            trade.unaccounted_buy_amount = 0

        if trade.sell_currency == currency:
            number_of_shares_to_sell = min(trade.unaccounted_sell_amount, number_of_shares_in_pool)

            if number_of_shares_in_pool > 0:
                cost = total_pool_cost * number_of_shares_to_sell / number_of_shares_in_pool
                gain = Gain(GainType.AVERAGE, number_of_shares_to_sell, trade, None, cost)
                gain_list.append(gain)

                number_of_shares_in_pool -= number_of_shares_to_sell
                total_pool_cost -= cost
                trade.unaccounted_sell_amount -= number_of_shares_to_sell

            if trade.unaccounted_sell_amount > 0:
                # TODO: Where disposal is not fully accounted for, need to do FIFO on later trades(after all 104 holdings have been done)
                #   see https://bettingbitcoin.io/cryptocurrency-uk-tax-treatments
                logger.debug(f"Not all accounted for with trade {trade}. Checking subsequent buys.")
                calculate_future_fifo(trade)

            if trade.unaccounted_sell_amount > 0:
                logger.warning(f"Could not account for all of trade {trade}. Treating it as a gift.")
                # raise ValueError

    return gain_list


def calculate_future_fifo(trade):
    pass


def calculate_104_holding_gains(trade_list):
    currency_list = set([trade.sell_currency for trade in trade_list])
    gain_list = []
    for currency in currency_list:
        gain_list.extend(calculate_104_gains_for_asset(currency, trade_list))
    return gain_list


def calculate_capital_gain(trade_list: List[Trade]):
    gains = []
    gains.extend(calculate_day_gains_fifo(trade_list))
    gains.extend(calculate_bnb_gains_fifo(trade_list))
    gains.extend(calculate_104_holding_gains(trade_list))
    return gains


def output_to_html(results, html_filename):
    html_text = "<!DOCTYPE html>"
    # TODO: Have format of this file in config file, and pass values to that formatting string.
    # TODO: Create output html file


def main():
    trades = read_csv_into_trade_list("examples/sample-trade-list.csv")
    fees = read_csv_into_fee_list("examples/sample-fee-list.csv")
    assign_fees_to_trades(trades, fees)
    capital_gains = calculate_capital_gain(trades)
    relavant_capital_gains = [g for g in capital_gains if within_tax_year(g.disposal_trade, TAX_YEAR)]
    output_to_html(capital_gains, "tax-report.html")


if __name__ == "__main__":
    main()
