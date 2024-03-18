"""Class definition for QueryBot."""
import contextvars
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


from llamabot.config import default_language_model
from llamabot.bot.simplebot import SimpleBot
from llamabot.components.messages import AIMessage, HumanMessage
from llamabot.components.docstore import BM25DocStore, LanceDBDocStore
from llamabot.components.chatui import ChatUIMixin
from llamabot.components.messages import (
    RetrievedMessage,
    retrieve_messages_up_to_budget,
)
from llamabot.bot.model_tokens import model_context_window_sizes, DEFAULT_TOKEN_BUDGET
from slugify import slugify

load_dotenv()


CACHE_DIR = Path.home() / ".llamabot" / "cache"
prompt_recorder_var = contextvars.ContextVar("prompt_recorder")


class QueryBot(SimpleBot, ChatUIMixin):
    """QueryBot is a bot that uses the DocumentStore to answer questions about a document."""

    def __init__(
        self,
        system_prompt: str,
        collection_name: str,
        initial_message: Optional[str] = None,
        document_paths: Optional[Path | list[Path]] = None,
        temperature: float = 0.0,
        model_name: str = default_language_model(),
        stream_target: str = "stdout",
        **kwargs,
    ):
        SimpleBot.__init__(
            self,
            system_prompt=system_prompt,
            temperature=temperature,
            model_name=model_name,
            stream_target=stream_target,
            **kwargs,
        )
        self.lancedb_store = LanceDBDocStore(table_name=slugify(collection_name))
        self.bm25_store = BM25DocStore()
        if document_paths:
            self.lancedb_store.add_documents(document_paths=document_paths)
            self.bm25_store.add_documents(document_paths=document_paths)

        self.response_budget = 2_000

        ChatUIMixin.__init__(self, initial_message)

    def __call__(self, query: str, n_results: int = 10) -> AIMessage:
        """Query documents within QueryBot's document store.

        We use RAG to query out documents.

        :param query: The query to make of the documents.
        """
        messages = []

        context_budget = model_context_window_sizes.get(
            self.model_name, DEFAULT_TOKEN_BUDGET
        )

        retreived_messages = set()
        retrieved_messages = retreived_messages.union(
            self.lancedb_store.retrieve(query, n_results)
        )
        retrieved_messages = retreived_messages.union(
            self.bm25_store.retrieve(query, n_results)
        )

        retrieved = retrieve_messages_up_to_budget(
            messages=[RetrievedMessage(content=chunk) for chunk in retrieved_messages],
            character_budget=context_budget - self.response_budget,
        )
        messages.extend(retrieved)
        messages.append(HumanMessage(content=query))
        if self.stream_target == "stdout":
            response: AIMessage = self.stream_stdout(messages)
            return response
        elif self.stream_target == "panel":
            return self.stream_panel(messages)
