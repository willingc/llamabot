"""Tests for blogging prompts"""

from llamabot.prompt_library.blog import (
    compose_linkedin_post,
    compose_patreon_post,
    compose_twitter_post,
)
import pytest
from llamabot.components.messages import BaseMessage


@pytest.mark.parametrize(
    "prompt_func, args, expected_role",
    [
        (compose_linkedin_post, ("This is a blog post.",), "user"),
        (compose_patreon_post, ("This is a blog post.",), "user"),
        (compose_twitter_post, ("This is a blog post.",), "user"),
    ],
)
def test_prompt_library(prompt_func, args, expected_role):
    """Test that the prompt library returns the expected output.

    :param prompt_func: The prompt function to test.
    :param args: The arguments to pass into the prompt function.
    :param expected_role: The expected role of the returned BaseMessage.
    """
    result = prompt_func(*args)
    assert isinstance(result, BaseMessage)
    assert result.role == expected_role
    assert isinstance(result.content, str)
    assert len(result.content) > 0
    assert result.prompt_hash is not None

    # Test that the content is as expected
    expected_content = prompt_func.__wrapped__(*args).content
    assert result.content == expected_content
