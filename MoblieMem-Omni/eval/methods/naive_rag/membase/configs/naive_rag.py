from .base import MemBaseConfig
from pydantic import (
    Field, 
    field_validator, 
    JsonValue,
)


class NaiveRAGConfig(MemBaseConfig):
    """Configuration for the naive RAG (online version)."""

    max_tokens: int | None = Field(
        default=None,
        description=(
            "Maximum total token count allowed in the buffer. When it is set, the message buffer "
            "trims oldest messages until the total token count is within this limit."
        ),
        gt=0,
    )
    num_overlap_msgs: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of previous messages to include when indexing a new message. "
            "This enables contextual continuity in online indexing scenarios. "
            "Set to 0 for independent message indexing."
        )
    )
    message_separator: str = Field(
        default="\n",
        description="Separator used to join messages into a document."
    )
    deferred: bool = Field(
        default=False,
        description=(
            "When it is enabled, messages are accumulated in the buffer and a document is "
            "only emitted when adding the next message would exceed the maximum token count. "
            "It requires `max_tokens` to be set. For example, if `max_tokens` is set to 1200, "
            "adding messages to the buffer will not trigger indexing until the next incoming "
            "message would cause the buffer's total token count to exceed 1200. At that point, "
            "the current buffer contents are concatenated into a single document for indexing, "
            "and the new message starts a fresh buffer. Combined with `num_overlap_msgs`, this "
            "achieves a chunking-with-overlap effect similar to offline chunking strategies."
        )
    )
    llm_model: str | None = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model name. It is used to get the corresponding tokenizer. "
            "An identifier from HuggingFace Hub or a local model path is also supported."
        ),
    )


    retriever_name_or_path: str = Field(
        default="huggingface:all-MiniLM-L6-v2",
        description=(
            "The name or path of the retriever model to use. "
            "The format should be `<provider>:<model_name>` where `<provider>` is one of `huggingface`, `openai`, `ollama`, etc. "
            "and `<model_name>` is the name of the model to use. "
            "For example, `huggingface:all-MiniLM-L6-v2` is the name of the all-MiniLM-L6-v2 model on Hugging Face."
        ),
    )
    retriever_dim: int = Field(
        default=384,
        ge=1, 
        description=(
            "The dimension of the retriever model. "
            "The default value is 384, which is the dimension of the all-MiniLM-L6-v2 model on Hugging Face. "
            "If you changes the value of `retriever_name_or_path`, "
            "you need to change the value of `retriever_dim` to the dimension of the new model."
        ),
    )
    embedding_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "Additional keyword arguments passed to ``langchain.embeddings.init_embeddings`` "
            "alongside ``retriever_name_or_path``. Common keys include ``api_key``, "
            "``base_url``, etc. See "
            "https://reference.langchain.com/python/langchain/embeddings/base/init_embeddings "
            "for supported parameters."
        ),
        examples=[
            # OpenAIEmbeddings integrations. 
            # See https://reference.langchain.com/python/langchain-openai/embeddings/base/OpenAIEmbeddings. 
            {
                "api_key": "sk-...", 
                "dimensions": 1024, 
                "max_retries": 3
            },
            {
                "api_key": "sk-...", 
                "base_url": "http://localhost:8000/v1", 
                "check_embedding_ctx_length": False,
            },
            # OllamaEmbeddings integration. 
            # See https://reference.langchain.com/python/langchain-ollama/embeddings/OllamaEmbeddings. 
            {
                "base_url": "http://localhost:11434", 
                "num_gpu": 1
            },
            # HuggingFaceEmbeddings integration. 
            # See https://reference.langchain.com/python/langchain-huggingface/embeddings/huggingface/HuggingFaceEmbeddings. 
            {
                "model_kwargs": {
                    "device": "cuda"
                }, 
                "encode_kwargs": {
                    "normalize_embeddings": True
                }, 
                "cache_folder": "/tmp/hf_cache"
            },
        ],
    )

    @field_validator("retriever_name_or_path")
    @classmethod
    def _validate_provider_model(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if ':' not in v:
            raise ValueError("Must be in format '<provider>:<model_name>' (missing ':').")
        provider, model_name = v.split(':', 1)
        if not provider or not model_name:
            raise ValueError("Provider and model name must be non-empty, separated by ':'.")
        return v 
