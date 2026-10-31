"""Integration capability definitions — single source of truth.

Defines which capabilities an external integration can provide and
which agent tools each capability activates.
"""

from __future__ import annotations

from enum import StrEnum

from common.tools import AvailableTool


class Capability(StrEnum):
    PRODUCTS = "products"
    SCHEDULING = "scheduling"
    STAFF = "staff"
    CUSTOMER_DATA = "customer_data"
    ORDERS = "orders"


CAPABILITY_TOOLS: dict[Capability, list[AvailableTool]] = {
    Capability.SCHEDULING: [
        AvailableTool.GET_BOOKING_SERVICES,
        AvailableTool.GET_AVAILABLE_DATES,
        AvailableTool.GET_AVAILABLE_SLOTS,
        AvailableTool.CREATE_BOOKING,
    ],
    Capability.STAFF: [
        AvailableTool.LIST_STAFF,
    ],
}
