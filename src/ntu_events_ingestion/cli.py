from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from .config import required_env
from .extractor import PROMPT_VERSION, SCHEMA_VERSION, OpenAIEventExtractor
from .storage import write_json
from .telegram_source import ChannelChoice, TelegramSource, parse_selection
from .workflow import process_messages

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION = ROOT / "storage" / "telegram" / "sessions" / "ingestion"
RUNS = ROOT / "storage" / "telegram" / "runs"
CACHE = ROOT / "storage" / "telegram" / "extraction_cache.json"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Guided Telegram text-to-event research pipeline")
    result.add_argument("command", nargs="?", choices=["run", "login", "channels"], default="run")
    result.add_argument("--messages", type=positive_int)
    result.add_argument("--max-calls", type=positive_int, default=200)
    result.add_argument("--concurrency", type=positive_int, default=10)
    result.add_argument("--model")
    result.add_argument("--force", action="store_true")
    return result


async def choose_channels(source: TelegramSource) -> list[ChannelChoice]:
    choices = await source.list_channels(20)
    if not choices:
        raise RuntimeError("No broadcast channels were found in this account")
    print("\nRecent broadcast channels:")
    for index, choice in enumerate(choices, 1):
        username = f"@{choice.username}" if choice.username else "no username"
        print(f"  {index:>2}. {choice.title} ({username})")
    raw = input(
        "\nSelect comma-separated numbers. Optionally add public usernames "
        "after ';' (example: 1,3;@club): "
    ).strip()
    numbered, separator, manual = raw.partition(";")
    selected = [choices[index] for index in parse_selection(numbered, len(choices))]
    if separator:
        for value in manual.split(","):
            if value.strip():
                resolved = await source.resolve_channel(value.strip())
                if all(item.channel_id != resolved.channel_id for item in selected):
                    selected.append(resolved)
    return selected


async def async_main(args: argparse.Namespace) -> int:
    load_dotenv(ROOT / ".env")
    api_id = int(required_env("TELEGRAM_API_ID"))
    api_hash = required_env("TELEGRAM_API_HASH")
    async with TelegramSource(api_id, api_hash, DEFAULT_SESSION) as source:
        if args.command == "login":
            print(f"Authorization saved at {DEFAULT_SESSION}.session")
            return 0
        if args.command == "channels":
            for index, channel in enumerate(await source.list_channels(20), 1):
                print(f"{index}. {channel.title} (@{channel.username or '-'})")
            return 0
        channels = await choose_channels(source)
        if args.messages:
            per_channel = args.messages
        else:
            raw_count = input("Messages per selected channel [30]: ").strip()
            per_channel = positive_int(raw_count) if raw_count else 30
        raw_messages = await source.fetch_text(channels, per_channel)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / timestamp
    write_json(run_dir / "raw_messages.json", raw_messages)
    print(f"\nSaved {len(raw_messages)} raw text messages to {run_dir}")
    base_manifest = {
        "run_id": timestamp,
        "channels": [
            {
                "channel_id": channel.channel_id,
                "title": channel.title,
                "username": channel.username,
            }
            for channel in channels
        ],
        "messages_per_channel_limit": per_channel,
        "raw_message_count": len(raw_messages),
        "completed_at": datetime.now(UTC).isoformat(),
    }
    if not raw_messages:
        for name in ("extraction_results", "event_candidates", "failures"):
            write_json(run_dir / f"{name}.json", [])
        write_json(
            run_dir / "run_manifest.json",
            {**base_manifest, "status": "no_text_messages"},
        )
        return 0

    model = args.model or os.getenv("OPENAI_MODEL", "gpt-5-nano")
    potential_calls = min(len(raw_messages), args.max_calls)
    approved = (
        input(f"Process up to {potential_calls} messages with {model}? [y/N]: ").strip().lower()
    )
    if approved not in {"y", "yes"}:
        write_json(
            run_dir / "run_manifest.json",
            {**base_manifest, "status": "raw_capture_only"},
        )
        print("Stopped after raw capture; no OpenAI calls were made.")
        return 0
    required_env("OPENAI_API_KEY")
    extractor = OpenAIEventExtractor(model=model, max_retries=1)
    try:
        records, failures, calls = await process_messages(
            raw_messages,
            extractor,
            run_dir,
            CACHE,
            max_calls=args.max_calls,
            max_concurrency=args.concurrency,
            force=args.force,
        )
    finally:
        await extractor.close()
    candidate_count = sum(len(record.result.events) for record in records)
    write_json(
        run_dir / "run_manifest.json",
        {
            **base_manifest,
            "status": "completed",
            "event_candidate_count": candidate_count,
            "failure_count": len(failures),
            "openai_calls": calls,
            "max_concurrency": args.concurrency,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "force": args.force,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    print(
        f"\nDone: {candidate_count} candidates, {len(failures)} failures, "
        f"{calls} OpenAI calls.\nOutput: {run_dir}"
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(async_main(build_parser().parse_args()))
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
