"""Launch the web app to visualize and compare prompts and messages."""

from typing import Optional
import typer
import uvicorn
from pathlib import Path
from pyprojroot import here
from llamabot.web.app import create_app

app = typer.Typer()


@app.command()
def launch(
    db_path: Optional[Path] = None,
    host: str = typer.Option("0.0.0.0", help="Host to bind the server to"),
    port: int = typer.Option(8000, help="Port to run the server on"),
):
    """Launch the web app to visualize and compare prompts and messages.

    :param db_path: The path to the database to use.
    :param host: The host to bind the server to.
    :param port: The port to run the server on.
    """
    if db_path is None:
        db_path = here() / "message_log.db"

    fastapi_app = create_app(db_path)
    uvicorn.run(fastapi_app, host=host, port=port)


if __name__ == "__main__":
    app()
