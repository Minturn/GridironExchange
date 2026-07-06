from decimal import Decimal

from app.engine.amm import (
    buy_gross,
    default_slope,
    quote_buy,
    quote_sell,
    sell_gross,
    spot_price,
)

P0 = Decimal("100.00")
SLOPE = Decimal("0.32")  # 0.08 × 100 / 25
FEE = Decimal("0.01")


def test_default_slope_from_rules():
    assert default_slope(P0, Decimal("0.08"), 25) == Decimal("0.320000")


def test_spot_price_rises_with_shares_outstanding():
    assert spot_price(P0, SLOPE, 0) == Decimal("100.00")
    assert spot_price(P0, SLOPE, 10) == Decimal("103.20")


def test_buy_gross_is_the_curve_integral():
    # ∫0..10 (100 + 0.32x) dx = 1000 + 0.32·50 = 1016
    assert buy_gross(P0, SLOPE, 0, 10) == Decimal("1016.00")


def test_sell_gross_is_symmetric_with_buy():
    assert sell_gross(P0, SLOPE, 10, 10) == buy_gross(P0, SLOPE, 0, 10)


def test_big_buy_pays_above_spot():
    q = quote_buy(P0, SLOPE, 0, 10, FEE)
    assert q.price_avg == Decimal("101.60") > spot_price(P0, SLOPE, 0)
    assert q.price_after == Decimal("103.20")


def test_round_trip_costs_exactly_two_fees():
    buy = quote_buy(P0, SLOPE, 0, 10, FEE)
    sell = quote_sell(P0, SLOPE, 10, 10, FEE)
    assert buy.gross == sell.gross == Decimal("1016.00")
    assert buy.fee == sell.fee == Decimal("10.16")
    assert buy.total - sell.total == buy.fee + sell.fee


def test_quotes_are_cent_quantized():
    q = quote_buy(P0, Decimal("0.333333"), 7, 3, FEE)
    for v in (q.gross, q.fee, q.total, q.price_avg, q.price_after):
        assert v == v.quantize(Decimal("0.01"))
