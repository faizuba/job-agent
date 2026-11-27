"""
costs.py: turns token counts into dollars.

Every API response includes a `usage` block that says how many tokens you were
billed for. With prompt caching there are FOUR kinds of tokens, each priced differently:

    input        normal input tokens                      1x the input price
    cache write  input saved to the cache for next time   1.25x (5-minute cache)
    cache read   input served from the cache              ~0.1x (much cheaper!)
    output       what the model wrote                     the output price

Prices change over time. Check https://www.anthropic.com/pricing and update the
table below if they do. They're here so every run can print its own cost.
"""

from dataclasses import dataclass

# model: (input $, output $) per million tokens
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
CACHE_WRITE_MULTIPLIER = 1.25            # 5-minute cache writes cost 1.25x normal input
CACHE_READ_MULTIPLIER = {                 # cache reads cost a fraction of normal input
    "claude-opus-5-5": 0.05,
    "claude-sonnet-5-5": 0.05,
}
DEFAULT_CACHE_READ_MULTIPLIER = 0.10


@dataclass
class Usage:
    """Running token totals for one agent run."""
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    def add(self, usage) -> None:
        """Add one API response's usage. Missing fields count as 0."""
        self.input += usage.input_tokens or 0
        self.output += usage.output_tokens or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

    @property
    def total_input(self) -> int:
        """Everything the model read, whether or not it came from the cache."""
        return self.input + self.cache_write + self.cache_read

    def cost(self, model: str) -> float | None:
        """What this run actually cost, in dollars. None if the model isn't in PRICES."""
        if model not in PRICES:
            return None
        price_in, price_out = PRICES[model]
        read_mult = CACHE_READ_MULTIPLIER.get(model, DEFAULT_CACHE_READ_MULTIPLIER)
        return (self.input * price_in
                + self.cache_write * price_in * CACHE_WRITE_MULTIPLIER
                + self.cache_read * price_in * read_mult
                + self.output * price_out) / 1_000_000

    def cost_without_cache(self, model: str) -> float | None:
        """What the same tokens would have cost if every input token were billed at full price."""
        if model not in PRICES:
            return None
        price_in, price_out = PRICES[model]
        return (self.total_input * price_in + self.output * price_out) / 1_000_000

    def to_dict(self, model: str) -> dict:
        return {
            "input_tokens": self.input,
            "cache_write_tokens": self.cache_write,
            "cache_read_tokens": self.cache_read,
            "output_tokens": self.output,
            "cost_usd": self.cost(model),
            "cost_without_cache_usd": self.cost_without_cache(model),
        }
