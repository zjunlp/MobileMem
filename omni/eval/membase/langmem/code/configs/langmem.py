from .base import MemBaseConfig
from pydantic import (
    Field, 
    field_validator, 
    JsonValue,
)


class LangMemConfig(MemBaseConfig):
    """The default configuration for LangMem."""

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

    llm_model: str = Field(
        default="openai:gpt-4o-mini",
        description="The base backbone model to use. "
        "The format should be `<provider>:<model_name>` where `<provider>` is one of `openai`, `ollama`, etc. "
        "and `<model_name>` is the name of the model to use. "
        "For example, `openai:gpt-4o-mini` is the name of the gpt-4o-mini model on OpenAI.", 
    )
    llm_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "Additional keyword arguments passed to ``langchain.chat_models.init_chat_model`` "
            "alongside ``llm_model``. Common keys include ``api_key``, ``base_url``, "
            "``temperature``, ``max_tokens``, etc. This is also used for the query model. "
            "See https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model "
            "for supported parameters."
        ),
        examples=[
            # ChatOpenAI integration. 
            # See https://reference.langchain.com/python/langchain-openai/chat_models/base/ChatOpenAI
            {
                "api_key": "sk-...", 
                "reasoning_effort": "medium", 
                "max_retries": 3
            },
            {
                "api_key": "sk-...", 
                "base_url": "http://localhost:8000/v1", 
                "temperature": 0.0, 
                "max_tokens": 4096
            },
            # ChatHuggingFace integration. 
            # See https://reference.langchain.com/python/langchain-huggingface/chat_models/huggingface/ChatHuggingFace. 
            {
                "do_sample": True, 
                "max_new_tokens": 4096, 
                "repetition_penalty": 1.02
            },
        ],
    )

    # You can look up the following parameters in the `create_memory_store_manager` function.
    query_model: str | None = Field(
        default=None, 
        description=(
            "The model to use for generating queries. "
            "If not provided, the dialated window trick over the conversation "
            "is used to generate queries and the number of queries is controlled by `query_limit`. "
            "The format should be `<provider>:<model_name>` where `<provider>` is one of `openai`, `ollama`, etc. "
            "and `<model_name>` is the name of the model to use. "
            "For example, `openai:gpt-4o-mini` is the name of the gpt-4o-mini model on OpenAI."
        ), 
    )
    enable_inserts: bool = Field(
        default=True, 
        description=(
            "Whether to allow creating new memory entries. "
            "When False, the manager will only update existing memories. Defaults to True."
        ),
    )
    enable_deletes: bool = Field(
        default=True, 
        description=(
            "Whether to allow deleting existing memories "
            "that are outdated or contradicted by new information. Defaults to True."
        ),
    )

    # Before the agent needs to extract valuable information to be memorized
    # it firsts generate a list of queries to retrieve relevant memories.
    # The `query_limit` is the maximum number of related memories to retrieve for each query.
    # When `query_model` is not provided, the dialated window trick over the conversation 
    # is used to generate queries and the number of queries is controlled by `query_limit` (at most `query_limit // 4`).
    query_limit: int = Field(
        default=5,
        ge=1, 
        description=(
            "Maximum number of relevant memories to retrieve " 
            "for each conversation. Higher limits provide more context but may slow down processing. "
            "Defaults to 5."
        ),
    )

    @field_validator("retriever_name_or_path", "llm_model", "query_model")
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

    def get_llm_models(self) -> list[str]:
        res = [self.llm_model.split(':', 1)[1]]
        if self.query_model is not None:
            res.append(self.query_model.split(':', 1)[1])
        return sorted(set(res))
