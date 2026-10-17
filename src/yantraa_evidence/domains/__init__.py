"""Built-in domains. Importing this package registers them."""

from ..domain import register_domain
from .returns import ReturnsDomain

register_domain(ReturnsDomain())

__all__ = ["ReturnsDomain"]
