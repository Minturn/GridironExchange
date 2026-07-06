"""Pure AMM math (SPEC §3.2). No I/O, no ORM — everything here is unit-testable exactly.

Linear bonding curve per player:  price(s) = p0 + slope·s
Buying n shares from s pays the integral along the curve, so big buys move the
price against you; selling returns value along the same curve. A flat fee_rate
on gross (burned) kills zero-risk oscillation around the curve.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def spot_price(p0: Decimal, slope: Decimal, shares_outstanding: int) -> Decimal:
    return money(p0 + slope * shares_outstanding)


def buy_gross(p0: Decimal, slope: Decimal, s: int, n: int) -> Decimal:
    # ∫ s..s+n of (p0 + slope·x) dx  =  n·p0 + slope·(s·n + n²/2)
    return money(n * p0 + slope * (Decimal(s * n) + Decimal(n * n) / 2))


def sell_gross(p0: Decimal, slope: Decimal, s: int, n: int) -> Decimal:
    # ∫ s-n..s — callers guarantee n ≤ s (you can't sell shares the league doesn't hold)
    return money(n * p0 + slope * (Decimal(s * n) - Decimal(n * n) / 2))


def default_slope(p0: Decimal, slope_pct: Decimal, share_cap: int) -> Decimal:
    # One member maxing the per-player cap moves the price ~ +slope_pct (SPEC §3.2).
    return (slope_pct * p0 / share_cap).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Quote:
    side: str            # buy | sell
    shares: int
    gross: Decimal
    fee: Decimal
    total: Decimal       # buy: cash out (gross+fee) · sell: cash in (gross−fee)
    price_avg: Decimal
    price_after: Decimal


def quote_buy(p0: Decimal, slope: Decimal, s: int, n: int, fee_rate: Decimal) -> Quote:
    gross = buy_gross(p0, slope, s, n)
    fee = money(gross * fee_rate)
    return Quote(
        side="buy", shares=n, gross=gross, fee=fee, total=money(gross + fee),
        price_avg=money(gross / n), price_after=spot_price(p0, slope, s + n),
    )


def quote_sell(p0: Decimal, slope: Decimal, s: int, n: int, fee_rate: Decimal) -> Quote:
    gross = sell_gross(p0, slope, s, n)
    fee = money(gross * fee_rate)
    return Quote(
        side="sell", shares=n, gross=gross, fee=fee, total=money(gross - fee),
        price_avg=money(gross / n), price_after=spot_price(p0, slope, s - n),
    )
