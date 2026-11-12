import warnings


try:
    from matching_engine_core.order_book import PyOrderBook
    if not hasattr(PyOrderBook, "get_market_depth") or not hasattr(
        PyOrderBook, "get_book_summary"
    ):
        raise ImportError(
            "Cython order-book extension is outdated; rebuild it."
        )
except ImportError as error:
    warnings.warn(
        f"Cython engine unavailable ({error}); using the Python fallback.",
        RuntimeWarning,
        stacklevel=2,
    )
    from matching_engine_core.order_book_fallback import PyOrderBook


__all__ = ["PyOrderBook"]
