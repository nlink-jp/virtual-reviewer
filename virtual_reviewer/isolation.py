"""Prompt injection isolation using nonce-tagged XML wrapping.

Untrusted data (application materials, Q&A answers) is wrapped in XML tags
with a cryptographically random nonce suffix. The LLM is instructed via
system prompt to treat content within these tags as data, not instructions.

Approach adapted from gem-cli (nlink-jp/gem-cli).

Usage:
    wrapped, tag = wrap(untrusted_text)
    system_prompt = expand_tag(system_prompt_template, tag)
"""

from __future__ import annotations

import os


def _generate_tag() -> str:
    """Generate a unique nonce tag name."""
    nonce = os.urandom(4).hex()
    return f"user_data_{nonce}"


def wrap(data: str) -> tuple[str, str]:
    """Wrap untrusted data in nonce-tagged XML delimiters.

    Returns:
        (wrapped_data, tag_name)
    """
    tag = _generate_tag()
    wrapped = f"<{tag}>\n{data}\n</{tag}>"
    return wrapped, tag


def expand_tag(system_prompt: str, tag: str) -> str:
    """Replace {{DATA_TAG}} placeholder in system prompt with actual tag name.

    Only applied to system prompts (trusted), never to user input.
    """
    return system_prompt.replace("{{DATA_TAG}}", tag)
