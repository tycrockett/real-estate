from __future__ import annotations

_registry: dict[str, type] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def get_formatter(name: str, **kwargs):
    if name not in _registry:
        available = list(_registry.keys())
        raise KeyError(f"Unknown formatter '{name}'. Available: {available}")
    return _registry[name](**kwargs)


def available() -> list[str]:
    return list(_registry.keys())


from realestate.output import table, json_out, csv_out  # noqa: E402, F401
