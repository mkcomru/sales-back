#!/usr/bin/env python3
"""Script to wipe all data related to a customer in a company.

This script deletes all customer-related data including:
- Threads and their messages
- Orders and their logs
- Tasks associated with orders
- Form submissions
- The customer itself

It also handles orphaned references (SET_NULL relationships) to ensure
complete cleanup.

Usage:
    cd apps/backend
    uv run python -m scripts.wipe_customer                               # interactive mode
    uv run python -m scripts.wipe_customer -i                            # explicit interactive
    uv run python -m scripts.wipe_customer <company_id> <customer_id>    # direct mode
    uv run python -m scripts.wipe_customer <company_id> --user-id <uid>  # by user_id

Requirements:
    - Run from apps/backend (or use: just script wipe_customer)
    - DATABASE__URL environment variable configured
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.backend.modules.chat.models import ChatMessage, Customer, Thread
from src.backend.modules.companies.models import Company
from src.backend.modules.core.database import close, init
from src.backend.modules.forms.models import FormSubmission
from src.backend.modules.orders.models import Order, OrderLog
from src.backend.modules.tasks.models import Task, TaskSubjectType


def print_info(msg: str) -> None:
    """Print info message."""
    print(f"[INFO] {msg}")


def print_success(msg: str) -> None:
    """Print success message."""
    print(f"[SUCCESS] {msg}")


def print_warn(msg: str) -> None:
    """Print warning message."""
    print(f"[WARN] {msg}")


def print_error(msg: str) -> None:
    """Print error message."""
    print(f"[ERROR] {msg}", file=sys.stderr)


async def wipe_customer_data(company_id: int, customer_id: int) -> None:
    """Wipe all data related to a customer.

    Args:
        company_id: Company ID
        customer_id: Customer ID to wipe
    """
    print(f"\n[WIPING] Customer {customer_id} in company {company_id}\n")

    customer = await Customer.filter(id=customer_id, company_id=company_id).first()
    if not customer:
        print_error(f"Customer {customer_id} not found in company {company_id}")
        return

    print_info(f"Found customer: {customer.name or 'N/A'} (user_id: {customer.user_id})")

    deleted_counts: dict[str, int] = {}

    threads = await Thread.filter(customer_id=customer_id, company_id=company_id).all()
    thread_ids = [t.id for t in threads]
    order_ids: list[int] = []

    orders = await Order.filter(customer_id=customer_id, company_id=company_id).all()
    order_ids.extend([o.id for o in orders])

    if threads:
        print_info(f"Found {len(threads)} thread(s)")
        for thread in threads:
            if thread.active_order_id:
                order_ids.append(thread.active_order_id)

    order_ids = list(set(order_ids))

    if order_ids:
        threads_with_orders = await Thread.filter(active_order_id__in=order_ids).all()
        if threads_with_orders:
            await Thread.filter(active_order_id__in=order_ids).update(active_order_id=None)
            print_info(f"Cleared active_order_id from {len(threads_with_orders)} thread(s)")

    if threads:
        for thread in threads:
            messages_count = await ChatMessage.filter(thread_id=thread.id).count()
            deleted_counts["chat_messages"] = deleted_counts.get("chat_messages", 0) + messages_count

            await ChatMessage.filter(thread_id=thread.id).delete()
            print_info(f"  Deleted {messages_count} message(s) from thread {thread.id}")

        await Thread.filter(id__in=thread_ids).delete()
        deleted_counts["threads"] = len(threads)
        print_success(f"Deleted {len(threads)} thread(s)")

    if order_ids:
        print_info(f"Found {len(order_ids)} order(s)")

        for order_id in order_ids:
            tasks = await Task.filter(
                company_id=company_id,
                subject_type=TaskSubjectType.ORDER,
                subject_id=order_id,
            ).all()
            if tasks:
                await Task.filter(
                    company_id=company_id,
                    subject_type=TaskSubjectType.ORDER,
                    subject_id=order_id,
                ).delete()
                deleted_counts["tasks"] = deleted_counts.get("tasks", 0) + len(tasks)
                print_info(f"  Deleted {len(tasks)} task(s) from order {order_id}")

            logs_count = await OrderLog.filter(order_id=order_id).count()
            await OrderLog.filter(order_id=order_id).delete()
            deleted_counts["order_logs"] = deleted_counts.get("order_logs", 0) + logs_count
            print_info(f"  Deleted {logs_count} log(s) from order {order_id}")

        await Order.filter(id__in=order_ids).delete()
        deleted_counts["orders"] = len(order_ids)
        print_success(f"Deleted {len(order_ids)} order(s)")

    form_submissions = await FormSubmission.filter(customer_id=customer_id).all()
    if form_submissions:
        await FormSubmission.filter(customer_id=customer_id).update(customer_id=None, order_id=None)
        deleted_counts["form_submissions"] = len(form_submissions)
        print_success(f"Cleared {len(form_submissions)} form submission(s)")

    if order_ids:
        form_submissions_with_orders = await FormSubmission.filter(order_id__in=order_ids).all()
        if form_submissions_with_orders:
            await FormSubmission.filter(order_id__in=order_ids).update(order_id=None)
            print_info(f"Cleared order_id from {len(form_submissions_with_orders)} form submission(s)")

    await Customer.filter(id=customer_id).delete()
    deleted_counts["customers"] = 1
    print_success(f"Deleted customer {customer_id}")

    print("\n[SUMMARY]")
    for entity, count in deleted_counts.items():
        print(f"  {entity}: {count}")

    print("\n[VERIFYING] No orphans remain...")

    remaining_threads = await Thread.filter(customer_id=customer_id).count()
    remaining_orders = await Order.filter(customer_id=customer_id).count()
    remaining_messages = await ChatMessage.filter(thread_id__in=thread_ids).count() if thread_ids else 0
    remaining_logs = await OrderLog.filter(order_id__in=order_ids).count() if order_ids else 0
    remaining_tasks = (
        await Task.filter(
            company_id=company_id,
            subject_type=TaskSubjectType.ORDER,
            subject_id__in=order_ids,
        ).count()
        if order_ids
        else 0
    )
    remaining_customer = await Customer.filter(id=customer_id).count()

    if any(
        [remaining_threads, remaining_orders, remaining_messages, remaining_logs, remaining_tasks, remaining_customer]
    ):
        print_warn("Some orphaned data remains:")
        if remaining_threads:
            print_warn(f"  Threads: {remaining_threads}")
        if remaining_orders:
            print_warn(f"  Orders: {remaining_orders}")
        if remaining_messages:
            print_warn(f"  Messages: {remaining_messages}")
        if remaining_logs:
            print_warn(f"  Order logs: {remaining_logs}")
        if remaining_tasks:
            print_warn(f"  Tasks: {remaining_tasks}")
        if remaining_customer:
            print_warn(f"  Customer: {remaining_customer}")
    else:
        print_success("No orphaned data found. Cleanup complete!")


def prompt_choice(prompt: str, options: list[tuple[str, str]], *, allow_empty: bool = False) -> str | None:
    """Display a numbered menu and return the selected value."""
    print(f"\n{prompt}\n")
    for idx, (_value, label) in enumerate(options, 1):
        print(f"  {idx}. {label}")

    while True:
        raw = input("\nEnter number" + (" (or Enter to skip)" if allow_empty else "") + ": ").strip()
        if allow_empty and raw == "":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print_error(f"Invalid choice: {raw}")


async def interactive_pick_company() -> int:
    companies = await Company.all().order_by("id")
    if not companies:
        print_error("No companies found in the database")
        sys.exit(1)

    options = [(str(c.id), f"[{c.id}] {c.name}") for c in companies]
    chosen = prompt_choice("Select a company:", options)
    assert chosen is not None
    return int(chosen)


async def interactive_pick_customer(company_id: int) -> int:
    customers = await Customer.filter(company_id=company_id).order_by("-created_at").limit(50)
    if not customers:
        print_error(f"No customers found in company {company_id}")
        sys.exit(1)

    options = [(str(c.id), f"[{c.id}] {c.name or 'N/A'} (user_id: {c.user_id})") for c in customers]
    chosen = prompt_choice(f"Select a customer (showing last 50 for company {company_id}):", options)
    assert chosen is not None
    return int(chosen)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Wipe all data for a customer in a company")
    parser.add_argument("company_id", type=int, nargs="?", help="Company ID")
    parser.add_argument("customer_id", type=int, nargs="?", help="Customer ID")
    parser.add_argument("--user-id", type=str, help="Customer user_id (alternative to customer_id)")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        default=False,
        help="Launch interactive picker (default when no positional args given)",
    )

    args = parser.parse_args()
    interactive = args.interactive or (args.company_id is None)

    await init()

    try:
        if interactive:
            company_id = await interactive_pick_company()
            customer_id = await interactive_pick_customer(company_id)
        else:
            company_id = args.company_id

            if not args.customer_id and not args.user_id:
                parser.error("Either customer_id or --user-id must be provided")
            if args.customer_id and args.user_id:
                parser.error("Cannot specify both customer_id and --user-id")

            customer_id: int | None = args.customer_id

            if args.user_id:
                customer = await Customer.filter(user_id=args.user_id, company_id=company_id).first()
                if not customer:
                    print_error(f"Customer with user_id '{args.user_id}' not found in company {company_id}")
                    sys.exit(1)
                customer_id = customer.id
                print_info(f"Found customer ID {customer_id} for user_id '{args.user_id}'")

            if customer_id is None:
                print_error("Could not determine customer_id")
                sys.exit(1)

        confirm = input(f"\nAbout to wipe customer {customer_id} in company {company_id}. Continue? [y/N]: ").strip()
        if confirm.lower() != "y":
            print_info("Aborted.")
            return

        await wipe_customer_data(company_id, customer_id)
    finally:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
