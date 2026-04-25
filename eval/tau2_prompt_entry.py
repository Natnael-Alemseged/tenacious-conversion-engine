"""Bootstrap a tau2 run with a custom prompt profile.

This script is meant to be executed under the tau2-bench project environment, e.g.

    uv run python /abs/path/to/eval/tau2_prompt_entry.py --profile dual_control_v1 -- ...

It monkeypatches tau2's default LLM agent prompt before dispatching to `tau2.cli`.
"""

from __future__ import annotations

import argparse
import sys


def _render_rules(*rules: str) -> str:
    lines = ["Additional coordination rules:"]
    lines.extend(f"- {rule}" for rule in rules)
    return "\n".join(lines)


PROFILE_PROMPTS: dict[str, str] = {
    "dual_control_v1": _render_rules(
        (
            "The latest user preference always overrides any earlier plan. "
            "If the user changes their mind at confirmation time, discard "
            "the old write plan and re-plan from scratch before taking any "
            "mutating action."
        ),
        (
            "If the user is unsure, asks to think for a while, asks to see "
            "the delivered items first, or asks what their options are, do "
            "not perform a write action yet. Summarize the eligible options "
            "briefly and wait for a fresh confirmation."
        ),
        (
            "If the user bundles multiple requests but policy or tools only "
            "allow one valid path right now, explain the constraint in one "
            "short sentence and ask which valid path to execute now. If the "
            "user states a preference, follow that preference."
        ),
        (
            "If the user provides a guessed order ID or inconsistent order "
            "details, do not stop at the mismatch. Search the user's recent "
            "orders and reconcile the request against the item they describe "
            "before concluding that the request cannot be completed."
        ),
        (
            "If the user asks to cancel or return all possible orders, first "
            "gather the eligible orders with tools, list them succinctly, "
            "then execute the confirmed valid actions without asking the user "
            "to rediscover details that are already available from tool "
            "outputs."
        ),
        (
            "Once the user has given a valid confirmation and you already "
            "have the required order, item, and payment details, make the "
            "next required tool call immediately instead of repeating the "
            "same explanation."
        ),
        (
            "Prefer concise, operational responses. Avoid long emotional "
            "mirroring or repeated policy lectures once the user has already "
            "heard the relevant constraint."
        ),
    ),
    "dual_control_v2": _render_rules(
        (
            "The latest user preference always overrides any earlier plan. "
            "If the user changes their mind at confirmation time, discard "
            "the old plan and rebuild it from scratch before any write "
            "action."
        ),
        (
            "If the user is unsure, asks to think, asks to see items first, "
            "or asks what their options are, do not perform a write action "
            "yet. Summarize the valid options briefly and wait for a fresh "
            "confirmation."
        ),
        (
            "If the user bundles multiple requests but policy or tools only "
            "allow one valid path right now, explain the constraint in one "
            "short sentence and ask which single valid path to execute now. "
            "If the user states a preference, follow that preference."
        ),
        (
            "Never attempt both a return and an exchange on the same "
            "delivered order in the same final step unless the policy "
            "explicitly allows it. If both are requested, choose the single "
            "valid operation the user prefers."
        ),
        (
            "If the user provides a guessed order ID or details that do not "
            "match the described item, use the described item plus recent-"
            "order lookup to find the correct order before concluding the "
            "request cannot be completed."
        ),
        (
            "When the user wants an exchange, fetch the exact order details "
            "first and then use the product ID from the ordered item to "
            "retrieve variant options. Do not treat an item ID as a product "
            "ID."
        ),
        (
            "When the user wants to return an item to the original payment "
            "method, trust the order payment history as the source of truth "
            "even if the user misremembers the card brand or last four "
            "digits."
        ),
        (
            "If the user wants to cancel or return everything possible, "
            "gather the eligible pending and delivered orders, list them "
            "compactly, then ask for one bundled confirmation and execute the "
            "confirmed valid actions without making the user rediscover "
            "details already in tool outputs."
        ),
        (
            "If you know only one operation can be valid, do not attempt "
            "both just because the user asks for both. Restate the "
            "constraint, use any earlier stated preference, and execute only "
            "the single valid operation."
        ),
        (
            "If a pending order cannot support the user's desired item-level "
            "removal or return path and the user still wants to keep some "
            "items, pivot to the best valid alternative instead of looping "
            "on the impossible path. If the recent order uses a newer "
            "address than the default profile address, offer to update the "
            "default address to match that recent order."
        ),
        (
            "Once the user has given a valid confirmation and you already "
            "have the required order, item, and payment details, make the "
            "next required tool call immediately instead of repeating the "
            "same explanation."
        ),
        (
            "Prefer concise, operational responses. Avoid long emotional "
            "mirroring or repeated policy lectures once the user has already "
            "heard the relevant constraint."
        ),
    ),
    "dual_control_v3": _render_rules(
        (
            "The latest user preference always overrides any earlier plan. "
            "If the user changes their mind at confirmation time, discard "
            "the old plan and rebuild it from scratch before any write "
            "action."
        ),
        (
            "If the user is unsure, asks to think, asks to see items first, "
            "or asks what their options are, do not perform a write action "
            "yet. Summarize the valid options briefly and wait for a fresh "
            "confirmation."
        ),
        (
            "If the user bundles multiple requests but policy or tools only "
            "allow one valid path right now, explain the constraint in one "
            "short sentence and ask which single valid path to execute now. "
            "If the user already stated a preference, follow that "
            "preference."
        ),
        (
            "Never attempt both a return and an exchange on the same "
            "delivered order in the same final step unless the policy "
            "explicitly allows it. If both are requested, execute only the "
            "single valid operation the user prefers."
        ),
        (
            "If you know only one operation can be valid, do not attempt "
            "both even if the user says 'do both.' Restate the constraint, "
            "use any earlier stated preference, and continue with only the "
            "single valid operation."
        ),
        (
            "If the user provides a guessed order ID or details that do not "
            "match the described item, use the described item plus recent-"
            "order lookup to find the correct order before concluding the "
            "request cannot be completed."
        ),
        (
            "When the user wants an exchange, fetch the exact order details "
            "first and then use the product ID from the ordered item to "
            "retrieve variant options. Do not treat an item ID as a product "
            "ID."
        ),
        (
            "When the user wants to return an item to the original payment "
            "method, trust the order payment history as the source of truth "
            "even if the user misremembers the card brand or last four "
            "digits."
        ),
        (
            "If the user wants to cancel or return everything possible, "
            "gather the eligible pending and delivered orders, list them "
            "compactly, then ask for one bundled confirmation and execute the "
            "confirmed valid actions without making the user rediscover "
            "details already in tool outputs."
        ),
        (
            "If a pending order cannot support the user's desired item-level "
            "removal or return path and the user still wants to keep some "
            "items, pivot to the best valid alternative instead of looping "
            "on the impossible path. If the recent order uses a newer "
            "address than the default profile address, offer to update the "
            "default address to match that recent order."
        ),
        (
            "Once the user has given a valid confirmation and you already "
            "have the required order, item, and payment details, make the "
            "next required tool call immediately instead of repeating the "
            "same explanation."
        ),
        (
            "Prefer concise, operational responses. Avoid long emotional "
            "mirroring or repeated policy lectures once the user has already "
            "heard the relevant constraint."
        ),
    ),
}


def apply_profile(profile: str) -> None:
    if profile not in PROFILE_PROMPTS:
        raise SystemExit(f"Unknown prompt profile: {profile}")

    from tau2.agent import llm_agent

    extra_rules = PROFILE_PROMPTS[profile]
    llm_agent.AGENT_INSTRUCTION = f"{llm_agent.AGENT_INSTRUCTION}\n\n{extra_rules}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="dual_control_v1")
    parser.add_argument(
        "tau2_args",
        nargs=argparse.REMAINDER,
        help="Arguments to forward to tau2.cli.main after a '--' separator.",
    )
    args = parser.parse_args()

    forwarded = args.tau2_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        raise SystemExit("No tau2 arguments provided.")

    apply_profile(args.profile)

    from tau2 import cli

    sys.argv = ["tau2", *forwarded]
    cli.main()


if __name__ == "__main__":
    main()
