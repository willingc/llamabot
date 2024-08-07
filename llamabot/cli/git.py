"""Git subcommand for LlamaBot CLI."""

from pathlib import Path
import os

import git
from pyprojroot import here
from typer import Typer, echo

from llamabot import SimpleBot, prompt
from llamabot.bot.structuredbot import StructuredBot
from llamabot.code_manipulation import get_git_diff
from llamabot.prompt_library.git import (
    compose_release_notes,
)
from pydantic import BaseModel, Field, model_validator
from enum import Enum

gitapp = Typer()


class CommitType(str, Enum):
    """Type of commit."""

    fix = "fix"
    feat = "feat"
    build = "build"
    chore = "chore"
    ci = "ci"
    docs = "docs"
    style = "style"
    refactor = "refactor"
    perf = "perf"
    test = "test"
    other = "other"


class DescriptionEntry(BaseModel):
    """Description entry."""

    txt: str = Field(
        ...,
        description="A single bullet point describing one major change in the commit.",
    )

    @model_validator(mode="after")
    def validate_description(self):
        """Validate description length."""
        if len(self.txt) > 79:
            raise ValueError(
                "Description should be less than or equal to 160 characters."
            )
        return self


class CommitMessage(BaseModel):
    """Commit message."""

    commit_type: CommitType = Field(
        ...,
        description=(
            "Type of change. Should usually be fix or feat. "
            "But others, based on the Angular convention, are allowed, "
            "such as build, chore, ci, docs, style, refactor, perf, test, and others."
        ),
    )
    scope: str = Field(
        ...,
        description=(
            "Scope of change. "
            "Should be at most two words that accurately describes the scope of changes."
        ),
    )
    description: str = Field(
        ...,
        description="A one line description of the changes, in 79 characters.",
    )

    body: list[DescriptionEntry] = Field(
        ...,
        description=(
            "A list of description entries. "
            "Each description entry should have a single bullet point "
            "describing one change in the commit. "
            "At most 10 entries. "
            "Be very detailed."
        ),
    )

    breaking_change: bool = Field(
        ..., description="Whether or not there is a breaking change in the commit. "
    )

    footer: str = Field("", description="An optional footer.")
    emoji: str = Field("", description="An emoji that represents the commit content.")

    @model_validator(mode="after")
    def validate_scope(self):
        """Validate the scope length."""
        if len(self.scope) > 0 and len(self.scope.split()) > 2:
            raise ValueError("Scope should be at most two words.")
        return self

    @model_validator(mode="after")
    def validate_body(self):
        """Validate the body length."""
        if len(self.body) > 10:
            raise ValueError("Description entries should be no more than 10 in length.")
        return self

    def format(self) -> str:
        """Format the commit message according to the provided model.

        :return: Formatted commit message as a string.
        """
        return _fmt(self)


@prompt
def _fmt(cm) -> str:
    """{{ cm.commit_type.value }}({{ cm.scope }}){{ cm.emoji }}{%if cm.breaking_change %}!{% else %}{% endif %}: {{ cm.description }}

    {% for bullet in cm.body %}- {{ bullet.txt }}
    {% endfor %}

    {% if cm.footer %}{{ cm.footer }}{% endif %}
    """  # noqa: E501


def commitbot(model_name: str = "gpt-4-turbo") -> StructuredBot:
    """Return a structured bot for writing commit messages."""

    @prompt
    def commitbot_sysprompt() -> str:
        """You are an expert software developer
        who writes excellent and accurate commit messages.
        You are going to be given a diff as input,
        and you will generate a structured JSON output
        based on the pydantic model provided.
        """

    bot = StructuredBot(
        system_prompt=commitbot_sysprompt(),
        pydantic_model=CommitMessage,
        model_name=model_name,
        stream_target="none",
    )
    return bot


@gitapp.command()
def hooks(model_name: str = "gpt-4-turbo"):
    """Install a commit message hook that runs the commit message through the bot.

    :raises RuntimeError: If the current directory is not a git repository root.
    """
    # Check that we are in a repository's root. There should be a ".git" folder.
    # Use pathlib to verify.
    if not Path(".git").exists():
        raise RuntimeError(
            "You must be in a git repository root folder to use this command. "
            "Please `cd` into your git repo's root folder and try again, "
            "or use `git init` to create a new repository (if you haven't already)."
        )

    with open(".git/hooks/prepare-commit-msg", "w+") as f:
        contents = f"""#!/bin/sh

echo "Script started with arguments: $@"

# Check if the arguments contain '-m'
commit_message_provided=false

for arg in "$@"; do
    if [ "$arg" = "message" ]; then
        commit_message_provided=true
        break
    fi
done

if $commit_message_provided; then
    echo "Commit message provided, skipping llamabot git compose."
else
    echo "No commit message found, running llamabot git compose."
    llamabot git compose --model-name {model_name} > .git/COMMIT_EDITMSG
fi
"""
        f.write(contents)
    os.chmod(".git/hooks/prepare-commit-msg", 0o755)
    echo("Commit message hook successfully installed! 🎉")


@gitapp.command()
def compose(model_name: str = "groq/llama-3.1-70b-versatile"):
    """Autowrite commit message based on the diff."""
    try:
        diff = get_git_diff()
        bot = commitbot(model_name)
        response = bot(diff)
        print(response.format())
    except Exception as e:
        echo(f"Error encountered: {e}", err=True)
        echo("Please write your own commit message.", err=True)


@gitapp.command()
def write_release_notes(release_notes_dir: Path = Path("./docs/releases")):
    """Write release notes for the latest two tags to the release notes directory.

    :param release_notes_dir: The directory to write the release notes to.
        Defaults to "./docs/releases".
    """
    repo = git.Repo(here())
    tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)
    if len(tags) == 0:
        # No tags, get all commit messages from the very first commit
        log_info = repo.git.log()
    elif len(tags) == 1:
        # Only one tag, get all commit messages from that tag to the current commit
        tag = tags[0]
        log_info = repo.git.log(f"{tag.commit.hexsha}..HEAD")
    else:
        # More than one tag, get all commit messages between the last two tags
        tag1, tag2 = tags[-2], tags[-1]
        log_info = repo.git.log(f"{tag1.commit.hexsha}..{tag2.commit.hexsha}")

    bot = SimpleBot(
        "You are an expert software developer "
        "who knows how to write excellent release notes based on git commit logs.",
        model_name="mistral/mistral-medium",
        api_key=os.environ["MISTRAL_API_KEY"],
        stream_target="stdout",
    )
    notes = bot(compose_release_notes(log_info))

    # Create release_notes_dir if it doesn't exist:
    release_notes_dir.mkdir(parents=True, exist_ok=True)
    # Ensure only one newline at the end of the file
    trimmed_notes = notes.content.rstrip() + "\n"

    # Write release notes to the file
    with open(release_notes_dir / f"{tag2.name}.md", "w+") as f:
        f.write(trimmed_notes)
